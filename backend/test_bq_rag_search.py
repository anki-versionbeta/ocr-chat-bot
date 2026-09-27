"""
Test Script: BQ + FlashRank RAG Search vs Current Implementation

Compares:
1. CURRENT: Existing weaviate_indexer.py hybrid search (alpha=0.7)
2. NEW: weaviate_rag_final.py style BQ + FlashRank reranking

Uses the same:
- Weaviate server: http://10.242.190.53:8080
- Collection: DocumentChunk (existing)
- Process ID: 53e654a3-d0ce-47ed-9d7f-d5d676958d80
- Embedding: Iliad API text-embedding-3-large

Tests speed and precision of retrieval for vector search route.
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

# Try to import FlashRank for reranking
try:
    from flashrank import Ranker, RerankRequest
    FLASHRANK_AVAILABLE = True
except ImportError:
    print("WARNING: FlashRank not installed. Install with: pip install flashrank")
    FLASHRANK_AVAILABLE = False

# =============================================================================
# CONFIGURATION (matches your existing setup)
# =============================================================================

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://10.242.190.53:8080")
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Test configuration
PROCESS_ID = "53e654a3-d0ce-47ed-9d7f-d5d676958d80"
COLLECTION_NAME = "DocumentChunk"

# Search parameters
EMBEDDING_MODEL = "text-embedding-3-large"

@dataclass
class SearchConfig:
    # Standard search
    STANDARD_ALPHA: float = 0.7  # Current: 70% semantic, 30% BM25

    # BQ-optimized search
    BQ_ALPHA: float = 0.5  # BQ: 50% semantic, 50% BM25 (better with BQ compression)

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
# EMBEDDING SERVICE (using Iliad API like existing setup)
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
    """Embedding service using Iliad API (matches existing setup)."""

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
# SEARCH FUNCTIONS
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
            # Normalize results
            for r in results:
                r["score"] = r.get("_additional", {}).get("score", 0)
            return results
        else:
            print(f"Search error: {response.status_code}")
            return []
    except Exception as e:
        print(f"Search exception: {e}")
        return []


def search_current_approach(query: str, process_id: str, top_k: int = 5) -> Dict[str, Any]:
    """
    CURRENT APPROACH: Standard hybrid search with alpha=0.7
    (This is what weaviate_indexer.py does)
    """
    start = time.time()

    # Generate embedding
    embed_start = time.time()
    query_vector = embedder.embed(query)
    embed_time = time.time() - embed_start

    if not query_vector:
        return {"error": "Failed to generate embedding", "results": []}

    # Search with current alpha
    search_start = time.time()
    results = search_weaviate_hybrid(
        query=query,
        process_id=process_id,
        limit=top_k,
        alpha=CONFIG.STANDARD_ALPHA,
        query_vector=query_vector
    )
    search_time = time.time() - search_start

    total_time = time.time() - start

    return {
        "approach": "CURRENT (alpha=0.7, no rerank)",
        "results": results,
        "result_count": len(results),
        "timings": {
            "embedding_ms": round(embed_time * 1000, 1),
            "search_ms": round(search_time * 1000, 1),
            "total_ms": round(total_time * 1000, 1)
        }
    }


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

        # Use page as "source" for diversity
        src = f"page_{page}"
        if source_counts.get(src, 0) >= max_per_source:
            continue

        seen.add(uid)
        source_counts[src] = source_counts.get(src, 0) + 1
        capped.append(r)

    return capped


def search_bq_flashrank_approach(query: str, process_id: str, top_k: int = 5) -> Dict[str, Any]:
    """
    NEW BQ + FlashRank APPROACH:
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
        raw_results.sort(key=lambda r: r.get("score", 0), reverse=True)

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
# TEST QUERIES
# =============================================================================

TEST_QUERIES = [
    "What is the Batch Name?",
    "What is the Project Name?",
    "Get the Count values from ECD table",
    "What is the concentration range?",
    "Mean ECD value",
]


def format_result(r: Dict, idx: int) -> str:
    """Format a single result for display."""
    content = (r.get("content") or "")[:100]
    # Handle Unicode for Windows console
    content = content.encode('ascii', 'replace').decode('ascii')
    score = r.get("score", 0)
    fr_score = r.get("flashrank_score", None)
    page = r.get("page", 0)
    chunk_type = r.get("chunk_type", "?")

    # Ensure score is float
    try:
        score_float = float(score) if score else 0.0
    except (ValueError, TypeError):
        score_float = 0.0

    lines = [
        f"  [{idx}] Page {page} ({chunk_type})",
        f"      Weaviate: {score_float:.4f}" + (f" | FlashRank: {fr_score:.4f}" if fr_score else ""),
        f"      Content: {content}..."
    ]
    return "\n".join(lines)


def run_comparison_test():
    """Run comparison test between current and BQ+FlashRank approaches."""
    print("\n" + "=" * 80)
    print("BQ + FLASHRANK RAG SEARCH COMPARISON TEST")
    print("=" * 80)
    print(f"Weaviate: {WEAVIATE_URL}")
    print(f"Process ID: {PROCESS_ID}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"FlashRank available: {FLASHRANK_AVAILABLE}")
    print("=" * 80)

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

    # Run tests
    for query in TEST_QUERIES:
        print("\n" + "-" * 80)
        print(f"QUERY: {query}")
        print("-" * 80)

        # Test current approach
        current = search_current_approach(query, PROCESS_ID, top_k=5)

        print(f"\n[1] {current['approach']}")
        print(f"    Results: {current['result_count']}")
        print(f"    Timing: embed={current['timings']['embedding_ms']}ms, search={current['timings']['search_ms']}ms, total={current['timings']['total_ms']}ms")

        if current['results']:
            for i, r in enumerate(current['results'][:3], 1):
                print(format_result(r, i))

        # Test BQ + FlashRank approach
        bq_result = search_bq_flashrank_approach(query, PROCESS_ID, top_k=5)

        print(f"\n[2] {bq_result['approach']}")
        print(f"    Results: {bq_result['result_count']} (overfetch: {bq_result.get('overfetch_count', 'N/A')})")
        print(f"    Timing: embed={bq_result['timings']['embedding_ms']}ms, search={bq_result['timings']['search_ms']}ms, rerank={bq_result['timings'].get('rerank_ms', 0)}ms, total={bq_result['timings']['total_ms']}ms")

        if bq_result['results']:
            for i, r in enumerate(bq_result['results'][:3], 1):
                print(format_result(r, i))

        # Compare speeds
        current_time = current['timings']['total_ms']
        bq_time = bq_result['timings']['total_ms']
        diff = bq_time - current_time

        print(f"\n    COMPARISON: {'BQ is ' + str(abs(diff)) + 'ms ' + ('slower' if diff > 0 else 'faster')}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_comparison_test()
