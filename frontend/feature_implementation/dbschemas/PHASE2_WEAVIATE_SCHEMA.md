# Phase 2: Weaviate Schema

> **Collection:** `DocumentChunk`
> **Host:** `http://10.242.190.53:8080`
> **Version:** Weaviate 1.24.1
> **Created:** February 2026

---

## Collection Overview

| Property | Value |
|----------|-------|
| **Collection Name** | `DocumentChunk` |
| **Vectorizer** | `none` (embeddings provided externally) |
| **Vector Index** | HNSW |
| **Distance Metric** | Cosine |
| **Properties** | 22 |

---

## Schema Definition

```python
{
    "class": "DocumentChunk",
    "description": "Stores document chunks with embeddings and grounding data for RAG",
    "vectorizer": "none",
    "vectorIndexType": "hnsw",
    "vectorIndexConfig": {
        "distance": "cosine",
        "efConstruction": 128,
        "maxConnections": 64
    },
    "properties": [...]
}
```

---

## Properties (22 Total)

### Identification Fields

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `document_id` | text | ✅ | ✅ | Links to PostgreSQL chat_documents |
| `process_id` | text | ✅ | ✅ | Unique UUID for session isolation |
| `chunk_id` | text | ✅ | ✅ | Unique chunk identifier |
| `page` | int | ✅ | ❌ | Page number (1-indexed) |
| `chunk_index` | int | ✅ | ❌ | Reading order (0, 1, 2...) |

### Chunk Type Fields

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `chunk_type` | text | ✅ | ✅ | Type: 'text' or 'table' |
| `layout_type` | text | ✅ | ✅ | AWS LAYOUT type: SECTION_HEADER, TEXT, FOOTER, TITLE |

### Search Fields

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `content` | text | ✅ | ✅ | Plain text for BM25 keyword search |

### Bounding Box Fields (Region-Level)

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `bbox_left` | number | ✅ | ❌ | Normalized left coordinate (0-1) |
| `bbox_top` | number | ✅ | ❌ | Normalized top coordinate (0-1) |
| `bbox_right` | number | ✅ | ❌ | Normalized right coordinate (0-1) |
| `bbox_bottom` | number | ✅ | ❌ | Normalized bottom coordinate (0-1) |

### Grounding Maps (For Precise Highlighting)

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `line_grounding` | text | ✅ | ✅ | JSON: Line-level bboxes for TEXT chunks |
| `cell_grounding` | text | ✅ | ✅ | JSON: Cell-level bboxes for TABLE chunks |

### Markdown Field

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `markdown` | text | ✅ | ✅ | HTML with cell IDs for Claude parsing |

### Metadata Fields

| Property | Type | Filterable | Searchable | Description |
|----------|------|------------|------------|-------------|
| `filename` | text | ✅ | ✅ | Original filename |
| `document_type` | text | ✅ | ✅ | Document type: COA, HBR, etc. |
| `document_summary` | text | ✅ | ✅ | AI-generated summary |
| `keywords` | text | ✅ | ✅ | Comma-separated keywords |
| `source` | text | ✅ | ✅ | Source identifier |
| `username` | text | ✅ | ✅ | Username who uploaded |
| `created_at` | date | ✅ | ❌ | Index timestamp |

---

## Grounding JSON Structures

### line_grounding (For TEXT Chunks)

```json
{
  "uuid-abc123": {
    "box": {
      "left": 0.13,
      "top": 0.18,
      "right": 0.45,
      "bottom": 0.20
    },
    "text": "Batch #: 1000459079"
  },
  "uuid-def456": {
    "box": {
      "left": 0.13,
      "top": 0.21,
      "right": 0.40,
      "bottom": 0.23
    },
    "text": "Product: ATX-101"
  }
}
```

### cell_grounding (For TABLE Chunks)

```json
{
  "1-28": {
    "box": {
      "left": 0.13,
      "top": 0.45,
      "right": 0.31,
      "bottom": 0.48
    },
    "text": "pH",
    "type": "tableCell",
    "row": 7,
    "col": 0
  },
  "1-29": {
    "box": {
      "left": 0.31,
      "top": 0.45,
      "right": 0.50,
      "bottom": 0.48
    },
    "text": "6.1",
    "type": "tableCell",
    "row": 7,
    "col": 1
  }
}
```

---

## Vector Index Configuration

```json
{
  "vectorIndexConfig": {
    "skip": false,
    "cleanupIntervalSeconds": 300,
    "maxConnections": 64,
    "efConstruction": 128,
    "ef": -1,
    "dynamicEfMin": 100,
    "dynamicEfMax": 500,
    "dynamicEfFactor": 8,
    "vectorCacheMaxObjects": 1000000000000,
    "flatSearchCutoff": 40000,
    "distance": "cosine"
  }
}
```

---

## BM25 Configuration

```json
{
  "invertedIndexConfig": {
    "bm25": {
      "b": 0.75,
      "k1": 1.2
    },
    "cleanupIntervalSeconds": 60,
    "stopwords": {
      "preset": "en"
    }
  }
}
```

---

## Hybrid Search Strategy

| Component | Weight | Method |
|-----------|--------|--------|
| **BM25 (Lexical)** | 30% | Keyword matching on `content`, `keywords`, `document_summary` |
| **Semantic (Vector)** | 70% | Cosine similarity on embedding vector (1536-dim) |

### Example Hybrid Query

```python
client.query.get("DocumentChunk", ["content", "page", "cell_grounding"])
    .with_hybrid(query="pH value", alpha=0.7)
    .with_where({
        "path": ["process_id"],
        "operator": "Equal",
        "valueText": "uuid-123"
    })
    .with_limit(10)
    .do()
```

---

## Sample Document Structure

```json
{
  "document_id": "doc_123",
  "process_id": "uuid-789",
  "chunk_id": "chunk_001",
  "page": 2,
  "chunk_index": 5,
  "chunk_type": "table",
  "layout_type": "TABLE",
  "content": "pH | QCG-055 | 5.7 to 6.4 | 6.1",
  "bbox_left": 0.13,
  "bbox_top": 0.30,
  "bbox_right": 0.84,
  "bbox_bottom": 0.70,
  "cell_grounding": "{\"1-29\": {\"box\": {...}, \"text\": \"6.1\", \"row\": 7, \"col\": 3}}",
  "markdown": "<table id='1-t0'><tr><td id='1-29'>6.1</td></tr></table>",
  "filename": "COA_001.pdf",
  "document_type": "COA",
  "document_summary": "Certificate of Analysis for Humira batch 96309DB",
  "keywords": "pH, osmolality, batch",
  "source": "coa_bapatar",
  "username": "bapatar",
  "created_at": "2026-02-03T00:00:00Z"
}
```

---

## Verification Commands

### Check Schema

```bash
curl -s http://10.242.190.53:8080/v1/schema | python -m json.tool
```

### Check Collection Exists

```python
import weaviate
client = weaviate.Client(url="http://10.242.190.53:8080")
print(client.schema.get("DocumentChunk"))
```

### Count Objects

```python
result = client.query.aggregate("DocumentChunk").with_meta_count().do()
print(result["data"]["Aggregate"]["DocumentChunk"][0]["meta"]["count"])
```

---

## Storage Estimates

| Document Size | Chunks | Storage |
|---------------|--------|---------|
| 5-page PDF | ~40 chunks | ~500 KB |
| 50-page PDF | ~400 chunks | ~5 MB |
| 235-page PDF | ~1,175 chunks | ~15 MB |

**Per Chunk Breakdown:**
- Content: ~1.5 KB
- Embedding (1536 × 4 bytes): ~6 KB
- Grounding maps: ~2-5 KB
- Metadata: ~0.5 KB
- **Total: ~10-16 KB per chunk**

---

*Document Version: 1.0*
*Created: February 2026*
*Phase: 2 of 3*
