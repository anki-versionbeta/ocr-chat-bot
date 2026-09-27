# Complete RAG Flow with Bounding Boxes

> **Document Purpose:** Complete flow from document upload to retrieval, explaining how bounding boxes are stored without affecting search
> **Created:** January 2026
> **Key Insight:** Bounding boxes are just metadata - they don't affect retrieval at all!

---

## Table of Contents

1. [Complete Flow Overview](#complete-flow-overview)
2. [Step-by-Step Process](#step-by-step-process)
3. [Does BBOX Affect Retrieval?](#does-bbox-affect-retrieval)
4. [Retrieval Flow - Q&A](#retrieval-flow-qa)
5. [Retrieval Flow - Extraction (Hybrid Search)](#retrieval-flow-extraction-hybrid-search)
6. [Summary](#summary)

---

## Complete Flow Overview

```
DOCUMENT UPLOAD
      ↓
TEXTRACT EXTRACTION (with bounding boxes)
      ↓
CHUNKING (bbox stored as metadata)
      ↓
EMBEDDING (only content text is embedded)
      ↓
STORE IN RAG (Elasticsearch/pgvector)
      ↓
RETRIEVAL (bbox comes along for free!)
```

---

## Step-by-Step Process

### Step 1: Document Upload

```
User uploads PDF
      ↓
```

### Step 2: Textract Extraction

```
Textract processes PDF
      ↓
Output: Raw blocks with bounding boxes
      ├── TABLE blocks (with bbox)
      │   └── CELL blocks (with bbox)
      └── LINE blocks (with bbox)
      ↓
```

### Step 3: Chunking (with bounding boxes)

Transform Textract blocks into chunks. Each chunk contains:

```json
{
  "id": "uuid-123",
  "content": "Product: ATX-101...",    // ← For embedding
  "type": "table",
  "page": 0,
  "section": "Product Info",
  "bbox": {                            // ← Stored as metadata
    "left": 0.08,
    "top": 0.18,
    "right": 0.90,
    "bottom": 0.25
  }
}
```

### Step 4: Embedding

Embed the **"content" field ONLY**:

```
NV-Embed-v2 embeds: "Product: ATX-101..."
      ↓
Output: [0.1, 0.2, 0.3, ...] (4096 dimensions)
```

**BBOX is NOT embedded!** Only the text content.

### Step 5: Store in Elasticsearch/Vector DB

Store EVERYTHING together in one record:

```json
{
  "id": "uuid-123",
  "content": "Product: ATX-101...",        // ← Searchable text
  "embedding": [0.1, 0.2, ...],            // ← For semantic search
  "type": "table",                          // ← Metadata
  "page": 0,                                // ← Metadata
  "section": "Product Info",                // ← Metadata (for keyword filter)
  "bbox_left": 0.08,                        // ← Metadata (NOT searched!)
  "bbox_top": 0.18,                         // ← Metadata (NOT searched!)
  "bbox_right": 0.90,                       // ← Metadata (NOT searched!)
  "bbox_bottom": 0.25                       // ← Metadata (NOT searched!)
}
```

---

## Does BBOX Affect Retrieval?

### NO! Bounding box is just metadata.

### What IS Used for Retrieval:

| Field | Used For |
|-------|----------|
| `content` | Keyword search (ILIKE '%Sample Summary%') |
| `embedding` | Semantic search (vector similarity) |
| `section` | Keyword filter |
| `page` | Filtering by page |

### What is NOT Used for Retrieval:

| Field | Purpose |
|-------|---------|
| `bbox_left` | Just stored, not searched |
| `bbox_top` | Just stored, not searched |
| `bbox_right` | Just stored, not searched |
| `bbox_bottom` | Just stored, not searched |

**Bounding box is just METADATA - it rides along with the chunk but doesn't participate in search!**

### Visual Representation

```
┌─────────────────────────────────────────────────────────────────┐
│  CHUNK RECORD IN DATABASE                                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SEARCHABLE FIELDS (used in retrieval)                   │   │
│  │                                                          │   │
│  │  content: "Product: ATX-101, Material: 96309DB"         │   │
│  │  embedding: [0.1, 0.2, 0.3, ...]                        │   │
│  │  section: "Product Information"                         │   │
│  │  page: 0                                                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  METADATA FIELDS (just stored, returned with results)    │   │
│  │                                                          │   │
│  │  bbox_left: 0.08                                        │   │
│  │  bbox_top: 0.18                                         │   │
│  │  bbox_right: 0.90                                       │   │
│  │  bbox_bottom: 0.25                                      │   │
│  │  type: "table"                                          │   │
│  │  id: "uuid-123"                                         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Retrieval Flow: Q&A

```
User: "What is the product name?"
      ↓
STEP 1: Create query embedding
      "What is the product name?" → [0.2, 0.3, ...]
      ↓
STEP 2: Hybrid Search
      ├── Keyword filter: WHERE content ILIKE '%product%'
      └── Semantic rank: ORDER BY embedding <=> query_embedding
      ↓
STEP 3: Get results WITH bbox (it's in the same row!)
```

### SQL Query

```sql
SELECT
    id,
    content,           -- For answer
    page,              -- For reference
    bbox_left,         -- Comes along for free!
    bbox_top,          -- Comes along for free!
    bbox_right,        -- Comes along for free!
    bbox_bottom        -- Comes along for free!
FROM chunks
WHERE content ILIKE '%product%'
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

### Response with References

```json
{
  "answer": "The product name is ATX-101",
  "references": [
    {
      "page": 0,
      "bbox": {
        "left": 0.08,
        "top": 0.18,
        "right": 0.90,
        "bottom": 0.25
      }
    }
  ]
}
```

---

## Retrieval Flow: Extraction (Hybrid Search)

```
User: "Extract all Sample Summary data to Excel"
      ↓
STEP 1: Classify intent → EXTRACTION
      ↓
STEP 2: Hybrid search (NO LIMIT)
```

### SQL Query (No Limit for Extraction)

```sql
SELECT DISTINCT page, bbox_left, bbox_top, bbox_right, bbox_bottom
FROM chunks
WHERE content ILIKE '%Sample Summary%'
   OR section ILIKE '%Sample Summary%'
ORDER BY page;
```

### Results: ALL Matching Pages with BBoxes

```
Page 5:   bbox {0.08, 0.14, 0.90, 0.45}
Page 45:  bbox {0.08, 0.14, 0.90, 0.45}
Page 89:  bbox {0.08, 0.14, 0.90, 0.45}
... (all 20 pages)
      ↓
STEP 3: Claude processes each page → Excel
```

---

## Summary

### BBOX Does NOT Affect Anything!

| Component | Does BBOX Affect? | Why |
|-----------|-------------------|-----|
| **Embedding** | ❌ NO | Only "content" text is embedded |
| **Semantic Search** | ❌ NO | Only embedding vector is compared |
| **Keyword Search** | ❌ NO | Only content/section is searched |
| **Hybrid Search** | ❌ NO | Still uses content + embedding |
| **Q&A Retrieval** | ❌ NO | Same search, bbox just comes along |
| **Extraction** | ❌ NO | Same search, finds pages correctly |

### The Analogy

**BBOX is like a passenger in a car:**
- The car (search) works the same whether the passenger (bbox) is there or not
- The passenger just rides along and gets delivered to the destination
- The passenger doesn't drive or affect how the car works

### Final Flow Diagram

```
RETRIEVAL PROCESS:
══════════════════

Query: "What is the product?"
           │
           ▼
    Search using:
    - content (keyword)
    - embedding (semantic)
           │
           ▼
    Match found!
           │
           ▼
    Return ENTIRE record:
    ├── content ✓
    ├── page ✓
    ├── bbox_left ✓    ← FREE! Just comes with the record
    ├── bbox_top ✓     ← FREE!
    ├── bbox_right ✓   ← FREE!
    └── bbox_bottom ✓  ← FREE!
           │
           ▼
    Frontend draws highlight on PDF at bbox coordinates!
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
