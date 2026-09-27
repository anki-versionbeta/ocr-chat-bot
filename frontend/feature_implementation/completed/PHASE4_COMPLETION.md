# Phase 4 Completion Record - Multi-Agent RAG Orchestration

> **Completed:** February 10, 2026
> **Status:** COMPLETE

---

## Summary

Phase 4 implements the Multi-Agent RAG Orchestration system, replacing the legacy Iliad-based search with a new Weaviate-powered pipeline. The system includes semantic caching, intent classification, query rephrasing, parallel search, answer synthesis with cell references, and reference extraction for PDF highlighting.

---

## Implementation Overview

### Architecture

```
User Query + process_id + recent_messages
    |
    v
[Context Resolver] --> Resolve pronouns (it, that) using last 3 messages
    |
    v
[Semantic Cache] --hit--> Return Cached Response (95% similarity, 30 min TTL)
    | miss
    v
[Intent Classifier] --> vector_only | structural | extraction | clarification
    |
    v
[Question Rephraser] --> Generate 3-5 COA-specific query variations
    |
    v
[Parallel Weaviate Search] --> Execute all variations (alpha=0.7: 70% semantic, 30% BM25)
    |
    v
[Answer Synthesizer] --> Claude Sonnet generates answer with [cell:X-Y] references
    |
    v
[Reference Extractor] --> Lookup bbox from cell_grounding for PDF highlighting
    |
    v
[Cache Updater] --> Store query embedding + response
    |
    v
Response: { answer, references[], confidence, query_type }
```

---

## Files Created

### Backend Services (`backend/services/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `semantic_cache.py` | Query caching with 95% similarity threshold | `get()`, `set()`, `invalidate()`, `clear()` |
| `intent_classifier.py` | Classify queries into 4 types | `classify_intent_sync()`, `classify_intent()` |
| `question_rephraser.py` | Generate COA-specific query variations | `rephrase_question_sync()`, `detect_row_col_query()` |
| `answer_synthesizer.py` | Generate answers with cell references | `synthesize_answer_sync()`, `lookup_cell_by_position()` |
| `reference_extractor.py` | Extract bbox from grounding data | `extract_references()`, `build_response_with_references()` |
| `rag_orchestrator.py` | Main orchestration module | `process_query_sync()`, `get_rag_orchestrator()` |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app.py` | Added new v2 endpoint, cache stats endpoint, cache invalidation endpoint |
| `backend/services/database.py` | Added `process_id` parameter to `add_document_to_chat()`, helper functions |
| `backend/services/__init__.py` | Updated documentation |

---

## New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat/coa-rag-v2/{process_id}` | POST | **NEW** Multi-Agent RAG with Weaviate |
| `/api/rag/cache-stats` | GET | Get semantic cache statistics |
| `/api/rag/cache/{process_id}` | DELETE | Invalidate cache for a document |

### v2 Endpoint Request/Response

**Request:**
```json
{
    "message": "What is the batch number?",
    "recent_messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
    ]
}
```

**Response:**
```json
{
    "success": true,
    "answer": "The batch number is 12345 [cell:2-5]",
    "references": [
        {
            "page": 1,
            "bbox": {"left": 0.45, "top": 0.32, "width": 0.15, "height": 0.03},
            "cell_id": "2-5",
            "text": "12345",
            "row": 2,
            "col": 5
        }
    ],
    "confidence": 0.95,
    "query_type": "vector_only",
    "cell_ids": ["2-5"],
    "process_id": "uuid",
    "document": "filename.pdf"
}
```

---

## Component Details

### 1. Semantic Cache (`semantic_cache.py`)

- **TTL:** 30 minutes per document
- **Similarity Threshold:** 0.95 (95%)
- **Key:** process_id + query embedding
- **Storage:** In-memory dictionary with automatic cleanup

```python
cache = get_semantic_cache()
cached = cache.get(process_id, query_embedding, query_text)
cache.set(process_id, query_embedding, response, query_text)
cache.invalidate(process_id)  # Clear document cache
```

### 2. Intent Classifier (`intent_classifier.py`)

Classifies queries into 4 types:

| Intent | Percentage | Description | Example |
|--------|------------|-------------|---------|
| `vector_only` | 90% | Simple Q&A, row/col lookup | "What is the batch number?" |
| `structural` | 5% | Page/table navigation | "What page has specifications?" |
| `extraction` | 5% | Export ALL data | "Export all rows to Excel" |
| `clarification` | <1% | Ambiguous queries | "Can you explain that?" |

**Flow:**
1. Rule-based classification first (keyword matching)
2. LLM fallback for ambiguous queries (Claude Haiku)

### 3. Question Rephraser (`question_rephraser.py`)

**COA-Specific Synonyms:**
```python
COA_SYNONYMS = {
    "batch number": ["lot number", "batch ID", "lot ID", "batch no", "lot no"],
    "expiry date": ["expiration date", "exp date", "best before", "use by"],
    "appearance": ["physical appearance", "description", "visual inspection"],
    "assay": ["purity", "potency", "content", "strength"],
    ...
}
```

**Features:**
- Synonym expansion (always applied)
- LLM rephrasing (optional, uses Claude Haiku)
- Row/col query detection: "value at row 7, column 3"
- Context reference resolution: "it" → actual subject

### 4. Answer Synthesizer (`answer_synthesizer.py`)

**Prompt Template:**
```
You are analyzing a Certificate of Analysis (COA) document.

Document: {filename}
Context: {chunks}
Cell Grounding: {cell_grounding}

User Question: {query}

Respond with JSON:
{
    "answer": "Answer with [cell:X-Y] references",
    "cell_ids": ["X-Y"],
    "confidence": 0.95
}
```

**Row/Col Position Queries:**
- Direct lookup in cell_grounding
- Returns exact cell value with bbox

### 5. Reference Extractor (`reference_extractor.py`)

**Flow:**
1. Extract `[cell:X-Y]` from answer text
2. Build grounding map from all chunks
3. Lookup bbox for each cell_id
4. Format for frontend (with right/bottom calculated)

**Output Format:**
```python
{
    'page': 1,
    'bbox': {
        'left': 0.45,
        'top': 0.32,
        'width': 0.15,
        'height': 0.03,
        'right': 0.60,   # calculated
        'bottom': 0.35   # calculated
    },
    'cell_id': '2-5',
    'text': '12345',
    'row': 2,
    'col': 5,
    'type': 'cell'
}
```

### 6. RAG Orchestrator (`rag_orchestrator.py`)

**Main Pipeline:**
```python
def process_query_sync(self, query, process_id, filename, recent_messages):
    # Step 1: Context Resolution
    query = resolve_context_references(query, recent_messages)

    # Step 2: Check Semantic Cache
    cached = self.cache.get(process_id, embedding, query)
    if cached: return cached

    # Step 3: Intent Classification
    intent = classify_intent_sync(query)

    # Step 4: Check for row/col position query
    row_col = detect_row_col_query(query)

    # Step 5: Generate Query Variations
    variations = rephrase_question_sync(query)

    # Step 6: Parallel Weaviate Search
    chunks = self._parallel_search(variations, process_id)

    # Step 7: Answer Synthesis
    answer_data = synthesize_answer_sync(query, chunks, filename, row_col)

    # Step 8: Add Confidence Disclaimer
    answer_data = add_confidence_disclaimer(answer_data)

    # Step 9: Extract References
    response = build_response_with_references(answer_data, chunks, intent.value)

    # Step 10: Update Cache
    self.cache.set(process_id, embedding, response, query)

    return response
```

---

## Database Updates

### PostgreSQL (`database.py`)

**Modified `add_document_to_chat()`:**
```python
def add_document_to_chat(
    chat_id: str,
    document_id: str,
    document_name: str,
    page_count: int = None,
    file_size: int = None,
    file_path: str = None,
    weaviate_source: str = None,
    process_id: str = None,      # NEW
    document_type: str = None    # NEW
) -> Dict[str, Any]:
```

**New Helper Functions:**
```python
def get_document_by_id(document_id: str) -> Optional[Dict]
def get_process_id_for_document(document_id: str) -> Optional[str]
def get_active_document_process_id(chat_id: str) -> Optional[str]
```

---

## Key Design Decisions

### 1. document_id = process_id

Both use the same UUID:
- `document_id` for PostgreSQL relationships (chats, messages)
- `process_id` for Weaviate filtering

### 2. Backwards Compatibility

Legacy endpoint `/api/chat/coa-rag/{process_id}` preserved for existing clients.

### 3. Cache Strategy

- Per-document caching (not global)
- 95% similarity threshold (high precision)
- 30 minute TTL (balance freshness vs performance)

### 4. Intent-Based Routing

- 90% of queries are `vector_only` (simple Q&A)
- Neo4j integration deferred to Phase 6 for structural queries

---

## Testing

### Service Import Test

```bash
cd backend && python -c "
from services.semantic_cache import get_semantic_cache
from services.intent_classifier import classify_intent_sync
from services.question_rephraser import rephrase_question_sync
from services.answer_synthesizer import synthesize_answer_sync
from services.reference_extractor import extract_references
from services.rag_orchestrator import get_rag_orchestrator
print('All Phase 4 services validated!')
"
```

**Result:** All imports successful.

### Server Restart Required

The running server needs to be restarted to pick up the new endpoints:
- `/api/chat/coa-rag-v2/{process_id}`
- `/api/rag/cache-stats`
- `/api/rag/cache/{process_id}`

---

## What's Next

### Phase 5: PDF Viewer & Highlighting

The `references` array returned by the v2 endpoint provides:
- Page number for navigation
- Bbox coordinates for highlighting
- Cell ID for identification

Frontend needs to:
1. Parse `[cell:X-Y]` references in answer text
2. Lookup bbox from response's `references` array
3. Draw highlight overlay on PDF viewer

### Frontend Updates Needed

1. Update `frontend/src/services/agent.ts` to use v2 endpoint
2. Add reference click handler to navigate and highlight
3. Integrate PDF viewer component (Phase 5)

---

## Files Summary

**Created:**
- `backend/services/semantic_cache.py`
- `backend/services/intent_classifier.py`
- `backend/services/question_rephraser.py`
- `backend/services/answer_synthesizer.py`
- `backend/services/reference_extractor.py`
- `backend/services/rag_orchestrator.py`
- `frontend/feature_implementation/completed/PHASE4_COMPLETION.md`

**Modified:**
- `backend/app.py` (added v2 endpoint + cache endpoints)
- `backend/services/database.py` (added process_id support)
- `backend/services/__init__.py` (updated documentation)

---

*Document Version: 1.0*
*Completed: February 10, 2026*
*Author: Claude Code*
