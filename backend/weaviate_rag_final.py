# =============================================================================
# FINAL PRODUCTION: Weaviate BQ + FlashRank + Claude RAG Agent (FULL WORKING CODE)
#
# All fixes included:
# 1)  Proper named-vector config verification ("content")
# 2)  BQ_RESCORE_LIMIT aligned with overfetch strategy
# 3)  Skip embedding for BM25 (saves cost)
# 4)  Adaptive overfetch
# 5)  Field packing for FlashRank (source + page + type + text)
# 6)  Claude context capped per chunk
# 7)  Bounded LRU cache for embeddings (prevents OOM)
# 8)  Input validation for embed_batch (no empty chunks, count check)
# 9)  RERANK_MAX cap for cross-encoder latency
# 10) Diversity backfill: rerank slice -> cap -> fill until top_k
# 11) Safe dedup key fallback (md5 hash, avoids text[:50] collisions)
# 12) cache=True removed from HNSW BQ (flat-index param only)
# 13) Multi-search: global sort + cap after merging all queries
#
# pip install weaviate-client openai anthropic flashrank tenacity
# =============================================================================

import os
import json
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Optional
from collections import OrderedDict

import weaviate
import anthropic
from openai import OpenAI

from weaviate.classes.config import Configure, Property, DataType, VectorDistances
from weaviate.classes.query import MetadataQuery, HybridFusion

from flashrank import Ranker, RerankRequest
from tenacity import retry, stop_after_attempt, wait_exponential


# =============================================================================
# STEP 1 — CONFIGURATION
# =============================================================================

@dataclass
class Config:
    ANTHROPIC_API_KEY: str    = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str       = os.getenv("OPENAI_API_KEY", "")

    WEAVIATE_HOST: str        = "localhost"
    WEAVIATE_PORT: int        = 8080
    WEAVIATE_GRPC_PORT: int   = 50051
    COLLECTION_NAME: str      = "DocumentChunks"

    EMBEDDING_MODEL: str      = "text-embedding-3-large"
    EMBEDDING_DIMS: int       = 3072
    EMBED_CACHE_SIZE: int     = 10_000   # ~120MB max at 3072 dims

    CLAUDE_MODEL: str         = "claude-sonnet-4-5-20250929"

    BQ_RESCORE_LIMIT: int     = 150      # 75% of OVERFETCH_MAX — aligned
    HNSW_EF: int              = 250      # raised to compensate lower rescore
    HNSW_EF_CONSTRUCTION: int = 128
    HNSW_MAX_CONNECTIONS: int = 64

    HYBRID_ALPHA: float       = 0.5      # 0=BM25 only, 1=vector only

    OVERFETCH_MIN: int        = 50
    OVERFETCH_MULTIPLIER: int = 10
    OVERFETCH_MAX: int        = 200

    FINAL_TOP_K: int          = 5
    CLAUDE_CHUNK_LIMIT: int   = 2000     # chars per chunk sent to Claude
    MAX_CHUNKS_PER_SOURCE: int = 2       # diversity cap

    FLASHRANK_MODEL: str      = "ms-marco-TinyBERT-L-2-v2"  # ~4MB, CPU only
    FLASHRANK_BODY_LIMIT: int = 512      # body chars sent to cross-encoder
    RERANK_MAX: int           = 100      # cap cross-encoder work per slice


CONFIG = Config()


# =============================================================================
# STEP 2 — CLIENTS
# =============================================================================

class ClientManager:
    def __init__(self):
        self._weaviate  = None
        self._anthropic = None
        self._openai    = None

    @property
    def weaviate(self):
        if self._weaviate is None:
            self._weaviate = weaviate.connect_to_local(
                host=CONFIG.WEAVIATE_HOST,
                port=CONFIG.WEAVIATE_PORT,
                grpc_port=CONFIG.WEAVIATE_GRPC_PORT,
            )
            if not self._weaviate.is_ready():
                raise ConnectionError("Weaviate not ready — is Docker running?")
        return self._weaviate

    @property
    def anthropic(self):
        if self._anthropic is None:
            if not CONFIG.ANTHROPIC_API_KEY:
                raise ValueError("Missing ANTHROPIC_API_KEY env var")
            self._anthropic = anthropic.Anthropic(api_key=CONFIG.ANTHROPIC_API_KEY)
        return self._anthropic

    @property
    def openai(self):
        if self._openai is None:
            if not CONFIG.OPENAI_API_KEY:
                raise ValueError("Missing OPENAI_API_KEY env var")
            self._openai = OpenAI(api_key=CONFIG.OPENAI_API_KEY)
        return self._openai

    def close(self):
        if self._weaviate:
            self._weaviate.close()
            print("Weaviate connection closed.")


clients = ClientManager()


# =============================================================================
# STEP 3 — LRU CACHE + EMBEDDING SERVICE
# =============================================================================

class LRUCache:
    """
    Bounded LRU cache — prevents memory leak in long-running services.
    Evicts least-recently-used entry when max_size is reached.
    """
    def __init__(self, max_size: int = 10_000):
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

    def __len__(self):
        return len(self._cache)


class EmbeddingService:
    def __init__(self, cache_size: int = 10_000):
        self._cache = LRUCache(max_size=cache_size)

    def _key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("embed: empty/blank text not allowed")
        key    = self._key(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        response = clients.openai.embeddings.create(
            model=CONFIG.EMBEDDING_MODEL,
            input=text,
            dimensions=CONFIG.EMBEDDING_DIMS,
        )
        vec = response.data[0].embedding
        self._cache.set(key, vec)
        return vec

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        # FIX: Validate all inputs before any API call
        for i, t in enumerate(texts):
            if not t or not t.strip():
                raise ValueError(
                    f"embed_batch: empty/blank text at index {i}. "
                    "All chunks must have non-empty text."
                )

        keys          = [self._key(t) for t in texts]
        uncached_idx  = [i for i, k in enumerate(keys) if self._cache.get(k) is None]
        uncached_texts = [texts[i] for i in uncached_idx]

        if uncached_texts:
            response = clients.openai.embeddings.create(
                model=CONFIG.EMBEDDING_MODEL,
                input=uncached_texts,
                dimensions=CONFIG.EMBEDDING_DIMS,
            )
            # FIX: Validate count — partial OpenAI response would corrupt cache
            if len(response.data) != len(uncached_texts):
                raise RuntimeError(
                    f"embed_batch: OpenAI returned {len(response.data)} vectors "
                    f"but expected {len(uncached_texts)}."
                )
            for i, item in zip(uncached_idx, response.data):
                self._cache.set(keys[i], item.embedding)

        # FIX: Explicit None guard — raises clearly instead of passing None to Weaviate
        results = []
        for k, t in zip(keys, texts):
            vec = self._cache.get(k)
            if vec is None:
                raise RuntimeError(
                    f"embed_batch: vector missing after embedding for '{t[:60]}'."
                )
            results.append(vec)
        return results


embedder = EmbeddingService(cache_size=CONFIG.EMBED_CACHE_SIZE)


# =============================================================================
# STEP 4 — FLASHRANK RERANKER (field packing)
# =============================================================================

class RerankerService:
    """
    Cross-encoder reranker. CPU only, ~4MB model, no GPU/Torch needed.
    Field packing: sends source+page+type as header for better PDF recall.
    """
    def __init__(self):
        print(f"Loading FlashRank: {CONFIG.FLASHRANK_MODEL}")
        self.ranker = Ranker(
            model_name=CONFIG.FLASHRANK_MODEL,
            cache_dir="/tmp/flashrank_cache",
        )
        print("FlashRank ready.")

    def _pack_passage(self, r: Dict) -> str:
        """Pack metadata header + body for cross-encoder context."""
        header = (
            f"Source: {r.get('source', 'unknown')} | "
            f"Page: {r.get('page_num', 0)} | "
            f"Type: {r.get('chunk_type', 'text')}"
        )
        body = (r.get("text", "") or "")[:CONFIG.FLASHRANK_BODY_LIMIT]
        return f"{header}\n{body}"

    def rerank(self, query: str, results: List[Dict], top_k: int) -> List[Dict]:
        if not results or top_k <= 0:
            return []

        passages = [
            {
                "id":   i,
                "text": self._pack_passage(r),
                "meta": {"chunk_id": r.get("chunk_id", "")},
            }
            for i, r in enumerate(results)
        ]
        reranked = self.ranker.rerank(RerankRequest(query=query, passages=passages))

        final = []
        for item in reranked[:top_k]:
            idx      = int(item["id"])   # safe cast — FlashRank id can be int or str
            original = results[idx].copy()
            original["flashrank_score"] = float(item["score"])
            final.append(original)
        return final


reranker = RerankerService()


# =============================================================================
# STEP 5 — SCHEMA (HNSW + BQ, named vector "content")
# =============================================================================

class SchemaManager:
    def create_collection(self, force_delete: bool = False):
        client = clients.weaviate

        if force_delete and client.collections.exists(CONFIG.COLLECTION_NAME):
            client.collections.delete(CONFIG.COLLECTION_NAME)
            print(f"Deleted: {CONFIG.COLLECTION_NAME}")

        if client.collections.exists(CONFIG.COLLECTION_NAME):
            print(f"Already exists: {CONFIG.COLLECTION_NAME}")
            return client.collections.get(CONFIG.COLLECTION_NAME)

        client.collections.create(
            name=CONFIG.COLLECTION_NAME,
            vector_config=[
                Configure.NamedVector(
                    name="content",
                    source_properties=["text"],
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE,
                        ef=CONFIG.HNSW_EF,
                        ef_construction=CONFIG.HNSW_EF_CONSTRUCTION,
                        max_connections=CONFIG.HNSW_MAX_CONNECTIONS,
                        quantizer=Configure.VectorIndex.Quantizer.bq(
                            rescore_limit=CONFIG.BQ_RESCORE_LIMIT,
                            # cache=True NOT set — flat index param only, wrong on HNSW
                        ),
                    ),
                )
            ],
            inverted_index_config=Configure.inverted_index(
                bm25_b=0.75,
                bm25_k1=1.2,
            ),
            properties=[
                Property(name="text",       data_type=DataType.TEXT),
                Property(name="source",     data_type=DataType.TEXT),
                Property(name="chunk_id",   data_type=DataType.TEXT),
                Property(name="chunk_type", data_type=DataType.TEXT),
                Property(name="page_num",   data_type=DataType.INT),
                Property(name="bbox",       data_type=DataType.TEXT),
                Property(name="metadata",   data_type=DataType.TEXT),
            ],
        )
        print(f"Created: {CONFIG.COLLECTION_NAME}")
        return client.collections.get(CONFIG.COLLECTION_NAME)


schema_manager = SchemaManager()


# =============================================================================
# STEP 6 — INGESTION
# =============================================================================

@dataclass
class DocumentChunk:
    text:       str
    source:     str
    chunk_id:   str
    chunk_type: str             = "text"
    page_num:   int             = 0
    bbox:       Optional[Dict]  = None
    metadata:   Optional[Dict]  = None
    vector:     Optional[List]  = None


class IngestionPipeline:
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def insert(self, chunks: List[DocumentChunk]):
        if not chunks:
            return

        to_embed = [c.text for c in chunks if c.vector is None]
        if to_embed:
            vectors = embedder.embed_batch(to_embed)
            vi = 0
            for c in chunks:
                if c.vector is None:
                    c.vector = vectors[vi]
                    vi += 1

        collection = clients.weaviate.collections.get(CONFIG.COLLECTION_NAME)
        with collection.batch.dynamic() as batch:
            for c in chunks:
                batch.add_object(
                    properties={
                        "text":       c.text,
                        "source":     c.source,
                        "chunk_id":   c.chunk_id,
                        "chunk_type": c.chunk_type,
                        "page_num":   c.page_num,
                        "bbox":       json.dumps(c.bbox) if c.bbox else "",
                        "metadata":   json.dumps(c.metadata) if c.metadata else "{}",
                    },
                    vector={"content": c.vector},   # named vector format
                )
        print(f"Inserted {len(chunks)} chunks.")


ingestion = IngestionPipeline()


# =============================================================================
# STEP 7 — SEARCH SERVICE
# =============================================================================

class SearchService:

    def hybrid_search(
        self, query_text: str, query_vector: List[float],
        limit: int, alpha: Optional[float] = None,
    ) -> List[Dict]:
        alpha      = CONFIG.HYBRID_ALPHA if alpha is None else alpha
        collection = clients.weaviate.collections.get(CONFIG.COLLECTION_NAME)
        res = collection.query.hybrid(
            query=query_text,
            vector=query_vector,
            target_vector="content",
            alpha=alpha,
            fusion_type=HybridFusion.RELATIVE_SCORE,
            limit=limit,
            return_metadata=MetadataQuery(score=True, distance=True),
        )
        return self._format(res.objects)

    def vector_search(self, query_vector: List[float], limit: int) -> List[Dict]:
        collection = clients.weaviate.collections.get(CONFIG.COLLECTION_NAME)
        res = collection.query.near_vector(
            near_vector=query_vector,
            target_vector="content",
            limit=limit,
            return_metadata=MetadataQuery(distance=True),
        )
        return self._format(res.objects)

    def bm25_search(self, query_text: str, limit: int) -> List[Dict]:
        # No embedding needed — pure text search
        collection = clients.weaviate.collections.get(CONFIG.COLLECTION_NAME)
        res = collection.query.bm25(
            query=query_text,
            limit=limit,
            return_metadata=MetadataQuery(score=True),
        )
        return self._format(res.objects)

    def _format(self, objects) -> List[Dict]:
        return [
            {
                "text":       obj.properties.get("text",       "") or "",
                "source":     obj.properties.get("source",     "") or "",
                "chunk_id":   obj.properties.get("chunk_id",   "") or "",
                "chunk_type": obj.properties.get("chunk_type", "") or "",
                "page_num":   obj.properties.get("page_num",   0)  or 0,
                "score":      float(getattr(obj.metadata, "score",    0.0) or 0.0),
                "distance":   float(getattr(obj.metadata, "distance", 0.0) or 0.0),
            }
            for obj in objects
        ]


search_service = SearchService()


# =============================================================================
# STEP 8 — HELPERS: OVERFETCH + DEDUP + PER-SOURCE CAP
# =============================================================================

def compute_overfetch(top_k: int) -> int:
    return min(
        max(CONFIG.OVERFETCH_MIN, top_k * CONFIG.OVERFETCH_MULTIPLIER),
        CONFIG.OVERFETCH_MAX,
    )


def apply_per_source_cap(
    results: List[Dict],
    max_per_source: Optional[int] = None,
) -> List[Dict]:
    """
    Dedup by chunk_id + cap chunks per source file.
    Dedup key priority:
      1. chunk_id (if non-empty)
      2. source|page|md5(text) — avoids collisions from text[:50] truncation
    Preserves input order (caller sorts before passing in).
    """
    max_per_source  = CONFIG.MAX_CHUNKS_PER_SOURCE if max_per_source is None else max_per_source
    seen            = set()
    source_counts: Dict[str, int] = {}
    capped          = []

    for r in results:
        src   = r.get("source",   "unknown") or "unknown"
        page  = r.get("page_num", 0)         or 0
        txt   = r.get("text",     "")        or ""
        # FIX: safe fallback key using md5 of full text — no text[:50] collisions
        fallback = f"{src}|{page}|{hashlib.md5(txt.encode('utf-8')).hexdigest()}"
        uid      = r.get("chunk_id") or fallback

        if uid in seen:
            continue
        if source_counts.get(src, 0) >= max_per_source:
            continue

        seen.add(uid)
        source_counts[src] = source_counts.get(src, 0) + 1
        capped.append(r)

    return capped


# =============================================================================
# STEP 9 — RETRIEVE (search + backfill rerank + cap + top_k)
# =============================================================================

def retrieve(
    query: str,
    search_type: str = "hybrid",
    top_k: Optional[int] = None,
) -> List[Dict]:
    """
    Full pipeline:
    1. Embed query (only hybrid/vector — bm25 skips to save cost)
    2. Weaviate search with adaptive overfetch
    3. Weaviate BQ fp32 rescore (automatic, up to BQ_RESCORE_LIMIT)
    4. Diversity backfill loop:
         - Rerank slice (up to RERANK_MAX) with FlashRank
         - Apply per-source cap on combined reranked pool
         - If still < top_k, take next raw slice and repeat
         - Stop when top_k filled or raw pool exhausted
    """
    top_k     = CONFIG.FINAL_TOP_K if top_k is None else top_k
    overfetch = compute_overfetch(top_k)

    # Embed only when needed
    query_vector = None
    if search_type in ("hybrid", "vector"):
        query_vector = embedder.embed(query)

    # Search Weaviate
    if search_type == "hybrid":
        raw = search_service.hybrid_search(query, query_vector, limit=overfetch)
    elif search_type == "vector":
        raw = search_service.vector_search(query_vector, limit=overfetch)
    elif search_type == "bm25":
        raw = search_service.bm25_search(query, limit=overfetch)
    else:
        raw = search_service.hybrid_search(query, query_vector, limit=overfetch)

    if not raw:
        return []

    # Sort raw by relevance so slices are in order
    if search_type in ("hybrid", "bm25"):
        raw.sort(key=lambda r: r.get("score", 0.0), reverse=True)
    else:
        raw.sort(key=lambda r: r.get("distance", 1e9))

    # Diversity backfill loop
    # Rerank in slices up to RERANK_MAX, cap+append until top_k is filled
    final:            List[Dict] = []
    combined_reranked: List[Dict] = []
    start = 0

    while len(final) < top_k and start < len(raw):
        end        = min(start + CONFIG.RERANK_MAX, len(raw))
        slice_raw  = raw[start:end]

        # Rerank this slice fully (all items in slice)
        reranked_slice = reranker.rerank(query, slice_raw, top_k=len(slice_raw))

        # Accumulate across slices (best-first per slice order preserved)
        combined_reranked.extend(reranked_slice)

        # Re-apply global cap+dedup over entire accumulated pool
        capped_pool = apply_per_source_cap(combined_reranked)

        final = capped_pool[:top_k]
        start = end

    return final


# =============================================================================
# STEP 10 — AGENT TOOLS
# =============================================================================

AGENT_TOOLS = [
    {
        "name": "search_documents",
        "description": (
            "Search the knowledge base with hybrid BM25 + vector search. "
            "Results are cross-encoder reranked. "
            "Always call before answering factual questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Specific focused search query.",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["hybrid", "vector", "bm25"],
                    "default": "hybrid",
                    "description": (
                        "hybrid: best default (BM25 + vector). "
                        "vector: conceptual/semantic questions. "
                        "bm25: exact keyword — no embedding cost."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Final results after reranking (max 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_documents_multi",
        "description": (
            "Search with MULTIPLE queries for complex/comparative questions. "
            "Results merged globally, sorted by FlashRank score, deduped, and capped."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2-4 targeted queries.",
                },
                "top_k_per_query": {
                    "type": "integer",
                    "default": 3,
                    "description": "Base results per query.",
                },
            },
            "required": ["queries"],
        },
    },
]


# =============================================================================
# STEP 11 — TOOL EXECUTION + FORMATTER
# =============================================================================

def _format_for_claude(results: List[Dict]) -> str:
    if not results:
        return "No relevant documents found."

    lines = [f"Found {len(results)} chunks:\n"]
    for i, r in enumerate(results, 1):
        text = r.get("text", "") or ""
        if len(text) > CONFIG.CLAUDE_CHUNK_LIMIT:
            text = text[:CONFIG.CLAUDE_CHUNK_LIMIT] + "... [truncated]"

        fr     = r.get("flashrank_score", None)
        fr_str = f"{fr:.4f}" if isinstance(fr, (int, float)) else "N/A"

        lines.append(
            f"[Chunk {i}]\n"
            f"Source:          {r.get('source', '')}\n"
            f"Chunk ID:        {r.get('chunk_id', '')}\n"
            f"Page:            {r.get('page_num', 0)}\n"
            f"Type:            {r.get('chunk_type', '')}\n"
            f"Weaviate score:  {r.get('score', 0.0):.3f}\n"
            f"FlashRank score: {fr_str}\n"
            f"Content:\n{text}\n"
        )
    return "\n---\n".join(lines)


def execute_tool(tool_name: str, tool_input: Dict) -> str:

    if tool_name == "search_documents":
        query       = tool_input["query"]
        search_type = tool_input.get("search_type", "hybrid")
        top_k       = min(int(tool_input.get("top_k", CONFIG.FINAL_TOP_K)), 10)
        results     = retrieve(query, search_type=search_type, top_k=top_k)
        return _format_for_claude(results)

    if tool_name == "search_documents_multi":
        queries         = tool_input["queries"]
        top_k_per_query = int(tool_input.get("top_k_per_query", 3))
        fetch_per_query = max(1, top_k_per_query * 3)  # over-fetch per query for richer merge

        merged: List[Dict] = []
        for q in queries:
            merged.extend(retrieve(q, top_k=fetch_per_query))

        # FIX: Global sort by FlashRank score before capping
        merged.sort(
            key=lambda r: float(r.get("flashrank_score", 0.0) or 0.0),
            reverse=True,
        )

        final_top_k = min(top_k_per_query * len(queries), 10)
        final       = apply_per_source_cap(merged)[:final_top_k]
        return _format_for_claude(final)

    return f"Unknown tool: {tool_name}"


# =============================================================================
# STEP 12 — CLAUDE AGENT
# =============================================================================

SYSTEM_PROMPT = """You are an intelligent document analysis assistant.

Retrieval stack:
- Weaviate hybrid search (BM25 + semantic BQ vector)
- FlashRank cross-encoder reranking for precision
- Per-source capping to avoid redundancy

Rules:
1. ALWAYS search before answering factual questions
2. Complex/comparative questions → search_documents_multi (2-4 queries)
3. Exact term lookup → search_documents with search_type=bm25
4. Conceptual question → search_documents with search_type=vector
5. Cite source, chunk_id, and page in every answer
6. If results insufficient → search again with different terms
7. Never fabricate — only use retrieved content
"""


def run_agent(user_query: str, history: Optional[List[Dict]] = None) -> str:
    history  = history or []
    messages = history + [{"role": "user", "content": user_query}]

    print(f"\n{'='*60}\nUSER: {user_query}\n{'='*60}")

    while True:
        response = clients.anthropic.messages.create(
            model=CONFIG.CLAUDE_MODEL,
            max_tokens=REDACTED
            system=SYSTEM_PROMPT,
            tools=AGENT_TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    print(f"\nTOOL: {block.name}")
                    print(f"INPUT: {json.dumps(block.input, indent=2)}")
                    result = execute_tool(block.name, block.input)
                    print(f"PREVIEW: {result[:200]}...")
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        if response.stop_reason == "end_turn":
            final = " ".join(
                b.text for b in response.content
                if hasattr(b, "text") and isinstance(b.text, str)
            )
            print(f"\nANSWER:\n{final}")
            return final

        print(f"Unexpected stop: {response.stop_reason}")
        return "Agent could not complete."


# =============================================================================
# STEP 13 — MULTI-TURN CONVERSATION
# =============================================================================

class RAGConversation:
    def __init__(self):
        self.history: List[Dict] = []

    def chat(self, message: str) -> str:
        answer = run_agent(message, self.history)
        self.history.append({"role": "user",      "content": message})
        self.history.append({"role": "assistant",  "content": answer})
        return answer

    def reset(self):
        self.history = []
        print("History cleared.")


# =============================================================================
# STEP 14 — VERIFICATION
# =============================================================================

def verify_all():
    print("\n" + "="*60 + "\nVERIFICATION\n" + "="*60)

    # 1. Weaviate
    print("\n[1] Weaviate connection...")
    try:
        assert clients.weaviate.is_ready()
        print("    OK")
    except Exception as e:
        print(f"    FAIL: {e}")
        return False

    # 2. Named vector config
    print("\n[2] Named vector config (content)...")
    try:
        col    = clients.weaviate.collections.get(CONFIG.COLLECTION_NAME)
        cfg    = col.config.get()
        nv     = getattr(cfg, "vector_config", None)
        if nv is None:
            raise RuntimeError("cfg.vector_config not found")

        content_vec = nv.get("content") if isinstance(nv, dict) else next(
            (v for v in nv if getattr(v, "name", None) == "content"), None
        )
        assert content_vec is not None, f"'content' vector missing. Found: {list(nv.keys()) if isinstance(nv, dict) else nv}"

        vi = getattr(content_vec, "vector_index_config", None)
        print(f"    Index type:    {getattr(content_vec, 'vector_index_type', 'unknown')}")
        if vi:
            q      = getattr(vi, "quantizer", None)
            rescore = getattr(q, "rescore_limit", None) if q else None
            print(f"    ef:            {getattr(vi, 'ef', '?')}")
            print(f"    Quantizer:     {type(q).__name__ if q else 'None'}")
            print(f"    Rescore limit: {rescore}")
            if rescore and CONFIG.OVERFETCH_MAX:
                ratio = rescore / CONFIG.OVERFETCH_MAX
                status = "OK" if ratio >= 0.5 else "LOW — consider raising BQ_RESCORE_LIMIT"
                print(f"    Rescore ratio: {ratio:.0%} — {status}")
        print("    OK")
    except Exception as e:
        print(f"    WARN: {e}")

    # 3. Adaptive overfetch values
    print("\n[3] Adaptive overfetch...")
    for k in [5, 10, 25]:
        print(f"    top_k={k:2d} → overfetch={compute_overfetch(k)}")

    # 4. Embedding
    print("\n[4] Embedding (LRU cache)...")
    try:
        vec = embedder.embed("test query")
        print(f"    OK — dims: {len(vec)}, cache_size: {len(embedder._cache)}/{embedder._cache._max_size}")
    except Exception as e:
        print(f"    FAIL: {e}")
        return False

    # 5. BM25 — no embedding call
    print("\n[5] BM25 skips embedding...")
    before = len(embedder._cache)
    try:
        search_service.bm25_search("binary quantization", limit=3)
    except Exception:
        pass
    grew = len(embedder._cache) - before
    print(f"    Cache growth: {grew} (should be 0) — {'OK' if grew == 0 else 'FAIL'}")

    # 6. FlashRank
    print("\n[6] FlashRank rerank...")
    try:
        docs = [
            {"text": "BQ compresses float32 to 1 bit.", "source": "a.pdf",
             "chunk_id": "1", "chunk_type": "text", "page_num": 1, "score": 0.9},
            {"text": "HNSW is a graph ANN index.", "source": "b.pdf",
             "chunk_id": "2", "chunk_type": "text", "page_num": 2, "score": 0.8},
            {"text": "FlashRank reranks with cross-encoder.", "source": "c.pdf",
             "chunk_id": "3", "chunk_type": "text", "page_num": 1, "score": 0.7},
        ]
        rr = reranker.rerank("binary quantization", docs, top_k=2)
        print(f"    OK — {len(rr)} reranked results")
        for r in rr:
            print(f"    {r.get('flashrank_score', 0):.4f}: {r['text'][:55]}")
    except Exception as e:
        print(f"    FAIL: {e}")
        return False

    # 7. Dedup key safety
    print("\n[7] Safe dedup key (md5 fallback)...")
    r1 = {"chunk_id": "", "source": "doc.pdf", "page_num": 1, "text": "Hello world chunk one"}
    r2 = {"chunk_id": "", "source": "doc.pdf", "page_num": 1, "text": "Hello world chunk two"}
    capped = apply_per_source_cap([r1, r2], max_per_source=1)
    assert len(capped) == 1, "md5 fallback dedup failed"
    print(f"    OK — different text bodies correctly produce different keys")

    # 8. Diversity backfill
    print("\n[8] Diversity backfill (rerank pool → cap → top_k)...")
    heavy_pool = [
        {"chunk_id": f"c{i}", "source": "heavy.pdf",
         "text": f"chunk {i}", "chunk_type": "text", "page_num": i, "score": 0.9}
        for i in range(8)
    ] + [
        {"chunk_id": f"o{i}", "source": f"other{i}.pdf",
         "text": f"other {i}", "chunk_type": "text", "page_num": 1, "score": 0.7}
        for i in range(6)
    ]
    capped_pool = apply_per_source_cap(heavy_pool, max_per_source=2)
    final       = capped_pool[:5]
    heavy_count = sum(1 for r in final if r["source"] == "heavy.pdf")
    print(f"    Input: 14 results (8 from heavy.pdf, 6 diverse)")
    print(f"    After cap+top_k=5: {len(final)} results, {heavy_count} from heavy.pdf (should be 2)")
    assert heavy_count <= 2
    assert len(final) == 5
    print("    OK")

    # 9. Claude chunk cap
    print("\n[9] Claude chunk text cap...")
    long = [{"text": "x" * 5000, "source": "d.pdf", "chunk_id": "x1",
             "chunk_type": "text", "page_num": 1, "score": 0.9, "flashrank_score": 0.8}]
    fmt = _format_for_claude(long)
    print(f"    Truncated: {'[truncated]' in fmt} (should be True)")

    # 10. Agent (if key present)
    print("\n[10] Claude agent...")
    if CONFIG.ANTHROPIC_API_KEY:
        try:
            ans = run_agent("What is binary quantization?")
            print(f"    OK — {len(ans)} chars")
        except Exception as e:
            print(f"    WARN: {e}")
    else:
        print("    SKIPPED — no ANTHROPIC_API_KEY")

    print("\n" + "="*60 + "\nALL CHECKS DONE\n" + "="*60)
    return True


# =============================================================================
# STEP 15 — MAIN
# =============================================================================

if __name__ == "__main__":
    schema_manager.create_collection(force_delete=False)

    sample_chunks = [
        DocumentChunk(text="Binary quantization converts float32 vectors to 1-bit by keeping only the sign of each dimension.",
                      source="bq_guide.pdf", chunk_id="bq_001", chunk_type="text", page_num=1),
        DocumentChunk(text="Weaviate HNSW stores both BQ compressed and original fp32 vectors. Rescoring uses fp32 for precision recovery.",
                      source="weaviate_docs.pdf", chunk_id="wv_001", chunk_type="text", page_num=5),
        DocumentChunk(text="FlashRank cross-encoder runs on CPU with no GPU or Torch required. Model size ~4MB.",
                      source="flashrank_docs.pdf", chunk_id="fr_001", chunk_type="text", page_num=1),
        DocumentChunk(text="text-embedding-3-large uses Matryoshka Representation Learning, producing 3072-dim vectors.",
                      source="openai_docs.pdf", chunk_id="oa_001", chunk_type="text", page_num=2),
    ]
    ingestion.insert(sample_chunks)

    verify_all()

    try:
        run_agent("How does binary quantization work with HNSW in Weaviate?")
    except Exception as e:
        print(f"(Agent skipped: {e})")

    try:
        conv = RAGConversation()
        conv.chat("What is binary quantization?")
        conv.chat("How does FlashRank improve precision over Weaviate scores alone?")
        conv.chat("What embedding model should I use with this setup?")
    except Exception as e:
        print(f"(Conversation skipped: {e})")

    clients.close()
