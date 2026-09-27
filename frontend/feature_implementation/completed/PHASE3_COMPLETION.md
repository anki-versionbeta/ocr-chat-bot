# Phase 3 Completion Record

> **Phase:** Textract Chunking Pipeline
> **Status:** COMPLETED
> **Completed:** February 5, 2026

---

## Summary

Phase 3 implemented layout-aware document chunking with grounding data for PDF highlighting (Phase 5). The system now uses Weaviate as the vector database instead of Iliad/Elasticsearch.

---

## What Was Implemented

### 1. Backend Services Created

| File | Purpose |
|------|---------|
| `backend/services/textract_parser.py` | Parses TABLE and LAYOUT blocks from Textract output |
| `backend/services/chunk_transformer.py` | Creates chunks with `cell_grounding` and `line_grounding` |
| `backend/services/weaviate_indexer.py` | Indexes chunks to Weaviate with embeddings (3072-dim) |

### 2. Endpoint Restructuring

| Endpoint | Flow | Time |
|----------|------|------|
| `/upload-coa` | RAG-only: Textract → Parse → Chunk → Weaviate | ~40s |
| `/upload-coa-full` | Full: Textract → GPT → Validation → Excel → Weaviate | ~65s |

### 3. Key Data Structures

**Table Chunk (with cell_grounding):**
```python
{
    "chunk_type": "table",
    "chunk_index": 5,
    "page": 2,
    "content": "TESTS | SPECIFICATIONS | METHOD | RESULTS\n...",
    "markdown": "<table><td id='2-5'>Appearance</td>...<td id='2-8'>Complies</td></table>",
    "cell_grounding": {
        "2-5": {"bbox": {"left": 0.04, "top": 0.24, "width": 0.29, "height": 0.02}, "text": "Appearance", "row": 2, "col": 1},
        "2-8": {"bbox": {"left": 0.78, "top": 0.24, "width": 0.18, "height": 0.02}, "text": "Complies", "row": 2, "col": 4}
    }
}
```

**Text Chunk (with line_grounding):**
```python
{
    "chunk_type": "text",
    "layout_type": "LAYOUT_KEY_VALUE",
    "chunk_index": 3,
    "page": 1,
    "content": "Batch Number: 0001903354",
    "line_grounding": {
        "uuid-abc": {"bbox": {"left": 0.05, "top": 0.30, "width": 0.40, "height": 0.02}, "text": "Batch Number: 0001903354"}
    }
}
```

---

## Testing Results

### Test 1: Full Pipeline (layout-full-test-c2d0b134)
- Textract with LAYOUT: 41 LAYOUT blocks + 4 TABLE blocks
- Parser: Successfully processed all block types
- Chunking: 43 chunks (4 table + 39 text) with grounding
- Indexing: All 43 chunks indexed to Weaviate
- Search: Hybrid search returns relevant results with grounding

### Test 2: Production Upload (41a175b6-7192-4d02-8abb-08a48a6a8770)
- File: CoA_1000792497.pdf
- Time: ~40 seconds (RAG-only mode)
- Results: 17 chunks (3 tables + 14 layouts) indexed
- Status: WORKING

---

## Log Prefixes

| Prefix | Meaning |
|--------|---------|
| `[COA-Simple]` | RAG-only upload started |
| `[COA-RAG-Only]` | RAG-only background processing |
| `[COA-RAG-WEAVIATE]` | Weaviate indexing in full flow |

---

## Fixes Applied

1. **f-string backslash issue** - Fixed in GraphQL query builder
2. **Embedding API endpoint** - Changed from `/embeddings` to `/embed/{model}`
3. **Embedding dimensions** - Updated from 1536 to 3072 (text-embedding-3-large actual)
4. **Bbox format** - Kept simple `{left, top, width, height}` (no right/bottom needed)

---

## Files Modified

- `backend/textractservices/textract_single.py:728` - Added LAYOUT to FeatureTypes
- `backend/app.py` - Added `/upload-coa` (RAG-only), renamed old to `/upload-coa-full`

---

## Ready for Phase 4

The grounding data is now stored in Weaviate, ready for:
- **Phase 4:** RAG Search & Query (use `cell_grounding`/`line_grounding` in responses)
- **Phase 5:** PDF Viewer & Highlighting (lookup bbox by cell_id, draw on canvas)

---

## How Cell ID Matching Works

```
Agent reads markdown:     <td id='2-8'>Complies</td>
                               ↓
Agent responds:           "The result is Complies [cell: 2-8]"
                               ↓
Frontend extracts:        cell_id = "2-8"
                               ↓
Frontend looks up:        cell_grounding["2-8"].bbox
                               ↓
Frontend highlights:      ctx.fillRect(left * W, top * H, width * W, height * H)
```

---

*Completed by: Claude Code*
*Date: February 5, 2026*
