"""
Test Script: Compare Main Endpoint (coa-rag-v2) vs Enhanced BQ + FlashRank RAG

Compares:
1. CURRENT: /api/chat/coa-rag-v2/{process_id} endpoint (rag_orchestrator.py with alpha=0.7)
2. ENHANCED: BQ + FlashRank approach (overfetch + rerank)

Tests with user prompts:
- What is the batch name
- What is the project name
- What is the mean value
- Who is the user
- What is the method
- What is the method description
- What is the file

Uses:
- Weaviate server: http://10.242.190.53:8080
- Collection: DocumentChunk
- Process ID: 53e654a3-d0ce-47ed-9d7f-d5d676958d80
"""

import os
import sys
import json
import time
import requests
import hashlib
from typing import List, Dict, Optional, Any
from collections import OrderedDict
from dataclasses import dataclass

# Configure stdout for Windows
sys.stdout.reconfigure(encoding='utf-8')

# Try to import FlashRank for reranking
try:
    from flashrank import Ranker, RerankRequest
    FLASHRANK_AVAILABLE = True
except ImportError:
    print("WARNING: FlashRank not installed. Install with: pip install flashrank")
    FLASHRANK_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://10.242.190.53:8080")
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Backend API URL
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")

# Test configuration
PROCESS_ID = "53e654a3-d0ce-47ed-9d7f-d5d676958d80"
COLLECTION_NAME = "DocumentChunk"
EMBEDDING_MODEL = "text-embedding-3-large"

@dataclass
class SearchConfig:
    # Standard search (current endpoint uses alpha=0.7)
    STANDARD_ALPHA: float = 0.7

    # BQ-optimized search
    BQ_ALPHA: float = 0.5

    # Overfetch for reranking
    OVERFETCH_MULTIPLIER: int = 10
    OVERFETCH_MIN: int = 50
    OVERFETCH_MAX: int = 200

    # Reranking
    RERANK_MAX: int = 100
    FLASHRANK_MODEL: str = "ms-marco-TinyBERT-L-2-v2"
    FLASHRANK_BODY_LIMIT: int = 512

    # Results
    FINAL_TOP_K: int = 5
    MAX_PER_SOURCE: int = 2


CONFIG = SearchConfig()

# =============================================================================
# EMBEDDING SERVICE (using Iliad API)
# =============================================================================

class LRUCache:
    """Bounded LRU cache to prevent memory issues."""
    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[List[float]]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: List[float]):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


class IliadEmbeddingService:
    """Embedding service using Iliad API."""

    def __init__(self):
        self._cache = LRUCache(max_size=1000)

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            return None

        key = self._key(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            response = requests.post(
                f"{ILIAD_URL}/api/v1/embed/{EMBEDDING_MODEL}",
                headers={
                    "x-api-key": ILIAD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"input": [text[:8000]]},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    vec = embeddings[0]
                    self._cache.set(key, vec)
                    return vec
            return None
        except Exception as e:
            print(f"Embedding error: {e}")
            return None


embedder = IliadEmbeddingService()

# =============================================================================
# FLASHRANK RERANKER
# =============================================================================

class FlashRankReranker:
    """Cross-encoder reranker using FlashRank."""

    def __init__(self):
        self.ranker = None
        if FLASHRANK_AVAILABLE:
            try:
                print(f"Loading FlashRank model: {CONFIG.FLASHRANK_MODEL}")
                self.ranker = Ranker(
                    model_name=CONFIG.FLASHRANK_MODEL,
                    cache_dir="/tmp/flashrank_cache",
                )
                print("FlashRank ready!")
            except Exception as e:
                print(f"FlashRank init failed: {e}")

    def _pack_passage(self, r: Dict) -> str:
        """Pack metadata + content for cross-encoder."""
        header = (
            f"Page: {r.get('page', 0)} | "
            f"Type: {r.get('chunk_type', 'text')}"
        )
        body = (r.get("content", "") or "")[:CONFIG.FLASHRANK_BODY_LIMIT]
        return f"{header}\n{body}"

    def rerank(self, query: str, results: List[Dict], top_k: int) -> List[Dict]:
        """Rerank results using FlashRank cross-encoder."""
        if not self.ranker or not results or top_k <= 0:
            return results[:top_k]

        passages = [
            {
                "id": i,
                "text": self._pack_passage(r),
                "meta": {"chunk_id": r.get("chunk_id", "")},
            }
            for i, r in enumerate(results)
        ]

        reranked = self.ranker.rerank(RerankRequest(query=query, passages=passages))

        final = []
        for item in reranked[:top_k]:
            idx = int(item["id"])
            original = results[idx].copy()
            original["flashrank_score"] = float(item["score"])
            final.append(original)
        return final


reranker = FlashRankReranker() if FLASHRANK_AVAILABLE else None

# =============================================================================
# WEAVIATE SEARCH FUNCTIONS
# =============================================================================

def search_weaviate_hybrid(
    query: str,
    process_id: str,
    limit: int,
    alpha: float,
    query_vector: List[float]
) -> List[Dict]:
    """Execute hybrid search on Weaviate."""
    escaped_query = query.replace('"', '\\"')

    graphql_query = f'''
    {{
        Get {{
            {COLLECTION_NAME}(
                hybrid: {{
                    query: "{escaped_query}"
                    alpha: {alpha}
                    vector: {json.dumps(query_vector)}
                }}
                where: {{
                    path: ["process_id"],
                    operator: Equal,
                    valueText: "{process_id}"
                }}
                limit: {limit}
            ) {{
                chunk_id
                page
                chunk_index
                chunk_type
                content
                cell_grounding
                _additional {{
                    score
                }}
            }}
        }}
    }}
    '''

    try:
        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": graphql_query},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("data", {}).get("Get", {}).get(COLLECTION_NAME, [])
            for r in results:
                r["score"] = r.get("_additional", {}).get("score", 0)
            return results
        else:
            print(f"Search error: {response.status_code}")
            return []
    except Exception as e:
        print(f"Search exception: {e}")
        return []


def compute_overfetch(top_k: int) -> int:
    """Calculate overfetch amount for reranking."""
    return min(
        max(CONFIG.OVERFETCH_MIN, top_k * CONFIG.OVERFETCH_MULTIPLIER),
        CONFIG.OVERFETCH_MAX
    )


def apply_per_source_cap(results: List[Dict], max_per_source: int = None) -> List[Dict]:
    """Deduplicate and cap results per source."""
    max_per_source = max_per_source or CONFIG.MAX_PER_SOURCE
    seen = set()
    source_counts: Dict[str, int] = {}
    capped = []

    for r in results:
        page = r.get("page", 0)
        txt = r.get("content", "")[:50]
        uid = r.get("chunk_id") or f"{page}|{txt}"

        if uid in seen:
            continue

        src = f"page_{page}"
        if source_counts.get(src, 0) >= max_per_source:
            continue

        seen.add(uid)
        source_counts[src] = source_counts.get(src, 0) + 1
        capped.append(r)

    return capped


# =============================================================================
# APPROACH 1: Call Main Endpoint (coa-rag-v2)
# =============================================================================

def test_main_endpoint(query: str, process_id: str) -> Dict[str, Any]:
    """
    Test the main /api/chat/coa-rag-v2/{process_id} endpoint.
    """
    start = time.time()

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/chat/coa-rag-v2/{process_id}",
            json={"message": query},
            timeout=60
        )

        total_time = time.time() - start

        if response.status_code == 200:
            data = response.json()
            return {
                "approach": "MAIN ENDPOINT (coa-rag-v2)",
                "success": data.get("success", True),
                "answer": data.get("answer", "")[:200] + "..." if len(data.get("answer", "")) > 200 else data.get("answer", ""),
                "confidence": data.get("confidence", 0),
                "query_type": data.get("query_type", "unknown"),
                "references_count": len(data.get("references", [])),
                "timings": {
                    "total_ms": round(total_time * 1000, 1)
                }
            }
        else:
            return {
                "approach": "MAIN ENDPOINT (coa-rag-v2)",
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:200]}",
                "timings": {
                    "total_ms": round(total_time * 1000, 1)
                }
            }
    except requests.exceptions.ConnectionError:
        return {
            "approach": "MAIN ENDPOINT (coa-rag-v2)",
            "success": False,
            "error": "Cannot connect to backend. Is it running on http://localhost:5000?",
            "timings": {"total_ms": 0}
        }
    except Exception as e:
        return {
            "approach": "MAIN ENDPOINT (coa-rag-v2)",
            "success": False,
            "error": str(e),
            "timings": {"total_ms": 0}
        }


# =============================================================================
# APPROACH 2: Enhanced BQ + FlashRank Search (Direct Weaviate)
# =============================================================================

def search_bq_flashrank_approach(query: str, process_id: str, top_k: int = 5) -> Dict[str, Any]:
    """
    ENHANCED BQ + FlashRank APPROACH:
    1. Overfetch with BQ-optimized alpha (0.5)
    2. Rerank with FlashRank cross-encoder
    3. Apply diversity cap
    """
    start = time.time()

    # Generate embedding
    embed_start = time.time()
    query_vector = embedder.embed(query)
    embed_time = time.time() - embed_start

    if not query_vector:
        return {"error": "Failed to generate embedding", "results": []}

    # Calculate overfetch amount
    overfetch = compute_overfetch(top_k)

    # Search with BQ-optimized alpha (more balanced)
    search_start = time.time()
    raw_results = search_weaviate_hybrid(
        query=query,
        process_id=process_id,
        limit=overfetch,
        alpha=CONFIG.BQ_ALPHA,
        query_vector=query_vector
    )
    search_time = time.time() - search_start

    # Rerank with FlashRank
    rerank_start = time.time()
    if reranker and raw_results:
        # Sort by Weaviate score first
        raw_results.sort(key=lambda r: float(r.get("score", 0) or 0), reverse=True)

        # Rerank top portion
        to_rerank = raw_results[:CONFIG.RERANK_MAX]
        reranked = reranker.rerank(query, to_rerank, top_k=len(to_rerank))

        # Apply diversity cap
        final = apply_per_source_cap(reranked)[:top_k]
    else:
        # Fallback: just take top_k without reranking
        final = raw_results[:top_k]
    rerank_time = time.time() - rerank_start

    total_time = time.time() - start

    return {
        "approach": "BQ + FlashRank (alpha=0.5, overfetch+rerank)",
        "results": final,
        "result_count": len(final),
        "overfetch_count": len(raw_results),
        "timings": {
            "embedding_ms": round(embed_time * 1000, 1),
            "search_ms": round(search_time * 1000, 1),
            "rerank_ms": round(rerank_time * 1000, 1),
            "total_ms": round(total_time * 1000, 1)
        }
    }


# =============================================================================
# TEST QUERIES (User requested prompts)
# =============================================================================

TEST_QUERIES = [
    "What is the batch name?",
    "What is the project name?",
    "What is the mean value?",
    "Who is the user?",
    "What is the method?",
    "What is the method description?",
    "What is the file?",
]


def format_result_snippet(r: Dict, idx: int) -> str:
    """Format a single result for display."""
    content = (r.get("content") or "")[:80]
    # Handle Unicode for Windows console
    content = content.encode('ascii', 'replace').decode('ascii')

    try:
        score = float(r.get("score", 0) or 0)
    except (ValueError, TypeError):
        score = 0.0

    fr_score = r.get("flashrank_score", None)
    page = r.get("page", 0)
    chunk_type = r.get("chunk_type", "?")

    score_str = f"Weaviate: {score:.4f}"
    if fr_score:
        score_str += f" | FlashRank: {fr_score:.4f}"

    return f"    [{idx}] Page {page} ({chunk_type}) | {score_str}\n        {content}..."


def run_comparison_test():
    """Run comparison test between main endpoint and BQ+FlashRank."""
    print("\n" + "=" * 100)
    print("COMPARISON: MAIN ENDPOINT (coa-rag-v2) vs BQ + FLASHRANK RAG SEARCH")
    print("=" * 100)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Weaviate: {WEAVIATE_URL}")
    print(f"Process ID: {PROCESS_ID}")
    print(f"FlashRank available: {FLASHRANK_AVAILABLE}")
    print("=" * 100)

    # Check Weaviate connection
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        if response.status_code != 200:
            print(f"ERROR: Weaviate not ready (status {response.status_code})")
            return
        print("Weaviate connection: OK")
    except Exception as e:
        print(f"ERROR: Cannot connect to Weaviate: {e}")
        return

    # Check backend connection
    backend_available = True
    try:
        response = requests.get(f"{BACKEND_URL}/ping", timeout=5)
        if response.status_code == 200:
            print("Backend connection: OK")
        else:
            print(f"WARNING: Backend returned status {response.status_code}")
            backend_available = False
    except Exception as e:
        print(f"WARNING: Cannot connect to backend at {BACKEND_URL}: {e}")
        print("         Main endpoint tests will be skipped.")
        backend_available = False

    print("=" * 100)

    # Summary table
    summary_data = []

    # Run tests
    for query in TEST_QUERIES:
        print("\n" + "-" * 100)
        print(f"QUERY: {query}")
        print("-" * 100)

        # Test 1: Main Endpoint (if available)
        if backend_available:
            endpoint_result = test_main_endpoint(query, PROCESS_ID)

            print(f"\n[1] {endpoint_result['approach']}")
            if endpoint_result.get("success"):
                print(f"    Confidence: {endpoint_result.get('confidence', 0):.2f}")
                print(f"    Query Type: {endpoint_result.get('query_type', 'unknown')}")
                print(f"    References: {endpoint_result.get('references_count', 0)}")
                print(f"    Timing: {endpoint_result['timings']['total_ms']}ms")
                answer = endpoint_result.get("answer", "")
                # Clean for Windows console
                answer = answer.encode('ascii', 'replace').decode('ascii')
                print(f"    Answer: {answer[:150]}...")
            else:
                print(f"    ERROR: {endpoint_result.get('error', 'Unknown error')}")

            endpoint_time = endpoint_result['timings']['total_ms']
        else:
            print("\n[1] MAIN ENDPOINT - SKIPPED (backend not available)")
            endpoint_time = 0

        # Test 2: BQ + FlashRank approach
        bq_result = search_bq_flashrank_approach(query, PROCESS_ID, top_k=5)

        print(f"\n[2] {bq_result['approach']}")
        print(f"    Results: {bq_result['result_count']} (overfetch: {bq_result.get('overfetch_count', 'N/A')})")
        print(f"    Timing: embed={bq_result['timings']['embedding_ms']}ms, search={bq_result['timings']['search_ms']}ms, rerank={bq_result['timings'].get('rerank_ms', 0)}ms, total={bq_result['timings']['total_ms']}ms")

        if bq_result.get('results'):
            print("    Top Results:")
            for i, r in enumerate(bq_result['results'][:3], 1):
                print(format_result_snippet(r, i))

        bq_time = bq_result['timings']['total_ms']

        # Comparison
        if backend_available and endpoint_time > 0:
            diff = endpoint_time - bq_time
            if diff > 0:
                print(f"\n    COMPARISON: BQ+FlashRank is {abs(diff):.0f}ms FASTER")
            else:
                print(f"\n    COMPARISON: Main Endpoint is {abs(diff):.0f}ms FASTER")

        summary_data.append({
            "query": query,
            "endpoint_ms": endpoint_time if backend_available else "N/A",
            "bq_ms": bq_time,
            "bq_results": bq_result['result_count']
        })

    # Print Summary Table
    print("\n" + "=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    print(f"{'Query':<40} | {'Endpoint (ms)':<15} | {'BQ+FR (ms)':<15} | {'Diff':<12} | {'BQ Results'}")
    print("-" * 100)

    for row in summary_data:
        query_short = row['query'][:38]
        endpoint_ms = row['endpoint_ms'] if row['endpoint_ms'] != "N/A" else "N/A"
        bq_ms = row['bq_ms']

        if endpoint_ms != "N/A" and endpoint_ms > 0:
            diff = endpoint_ms - bq_ms
            diff_str = f"{'+' if diff > 0 else ''}{diff:.0f}ms"
        else:
            diff_str = "N/A"

        print(f"{query_short:<40} | {str(endpoint_ms):<15} | {bq_ms:<15.0f} | {diff_str:<12} | {row['bq_results']}")

    print("=" * 100)
    print("\nKEY:")
    print("  - Endpoint (ms): Response time from /api/chat/coa-rag-v2 endpoint")
    print("  - BQ+FR (ms): Response time from BQ + FlashRank direct search")
    print("  - Diff: Positive = BQ+FlashRank is faster by that amount")
    print("  - BQ Results: Number of chunks returned by BQ+FlashRank search")
    print("\nNOTE: Main endpoint includes full RAG pipeline (intent, rephrase, synthesis)")
    print("      BQ+FlashRank only includes search + rerank (no answer synthesis)")
    print("=" * 100)


if __name__ == "__main__":
    run_comparison_test()
