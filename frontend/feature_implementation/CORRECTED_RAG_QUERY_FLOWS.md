# CORRECTED RAG Query Flows - Triple Database Architecture

> **Purpose:** Correct documentation of THREE query flows based on user intent
> **Date:** January 23, 2026
> **Status:** ✅ VERIFIED - Weaviate is ALWAYS the foundation
> **Key Principle:** Vector search provides context for ALL queries

---

## Metadata Available for Query Routing

**From Weaviate chunks (after transformation):**

```json
{
  "chunk_index": 5,           // Sequential position (0, 1, 2...)
  "page": 1,                  // Page number
  "type": "table",            // "table" or "text"
  "cell_grounding": {
    "1-31": {
      "cell_id": "1-31",      // Generated: "{page}-{sequence}"
      "row": 7,               // From Textract RowIndex
      "col": 3,               // From Textract ColumnIndex
      "text": "6.1",          // Extracted from WORD children
      "box": {...}            // Normalized bbox
    }
  },
  "document_id": "uuid",      // Document identifier
  "process_id": "uuid"        // Session identifier
}
```

**All metadata exists in Weaviate - NO additional fields needed!**

---

## Flow 1: Simple Q&A (90% of queries)

**Examples:**
- "What is the pH value?"
- "What is the batch number?"
- "Show me the test results"

**Characteristics:**
- Direct value lookup
- Answer exists in chunks
- No structural analysis needed

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  SIMPLE Q&A FLOW (Weaviate Only)                                           │
│  ════════════════════════════════                                           │
│                                                                             │
│  USER ASKS QUESTION                                                         │
│  ┌──────────────────────────────┐                                           │
│  │ "What is the pH value?"      │                                           │
│  └───────────┬──────────────────┘                                           │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Question Rephrasing (Claude 3.7 Sonnet)                     │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Generates 3-5 variations for better recall:                         │   │
│  │ • "pH value"                                                         │   │
│  │ • "pH level"                                                         │   │
│  │ • "acidity"                                                          │   │
│  │ • "potential hydrogen"                                               │   │
│  │                                                                      │   │
│  │ Time: 800-1500ms                                                     │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Weaviate Hybrid Search (FOUNDATION)                         │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ For EACH rephrased question:                                        │   │
│  │                                                                      │   │
│  │ query = {                                                            │   │
│  │   "vector": embedding("pH value"),                                  │   │
│  │   "where": {                                                         │   │
│  │     "process_id": "uuid-123"                                        │   │
│  │   },                                                                 │   │
│  │   "hybrid": {                                                        │   │
│  │     "alpha": 0.7,  // 70% semantic, 30% BM25                       │   │
│  │     "query": "pH value"                                             │   │
│  │   },                                                                 │   │
│  │   "limit": 10  // top_k for Q&A                                    │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Result: Top 10 semantically relevant chunks                         │   │
│  │                                                                      │   │
│  │ Time: 40-50ms per variation (total: 150-200ms for 3-5 variations)  │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: Deduplicate & Sort Results                                  │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ • Combine results from all query variations                         │   │
│  │ • Remove duplicates by content                                      │   │
│  │ • Sort by chunk_index (preserves reading order)                     │   │
│  │                                                                      │   │
│  │ Result:                                                              │   │
│  │ [                                                                    │   │
│  │   {                                                                  │   │
│  │     "type": "table",                                                │   │
│  │     "content": "pH | QCG-055 | 5.7 to 6.4 | 6.1",                 │   │
│  │     "page": 1,                                                      │   │
│  │     "chunk_index": 2,                                               │   │
│  │     "cell_grounding": {                                             │   │
│  │       "1-31": {                                                     │   │
│  │         "box": {left: 0.70, top: 0.45, right: 0.84, bottom: 0.48},│   │
│  │         "text": "6.1",                                              │   │
│  │         "row": 7, "col": 3                                          │   │
│  │       }                                                              │   │
│  │     },                                                               │   │
│  │     "markdown": "<table><td id='1-31'>6.1</td></table>"           │   │
│  │   }                                                                  │   │
│  │ ]                                                                    │   │
│  │                                                                      │   │
│  │ Time: 10ms                                                           │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 4: Claude Cell Matching (For Table Chunks)                     │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Prompt to Claude 3.7 Sonnet:                                        │   │
│  │                                                                      │   │
│  │ """                                                                  │   │
│  │ TABLE HTML: <table><td id="1-31">6.1</td></table>                  │   │
│  │ USER QUESTION: "What is the pH value?"                             │   │
│  │ Return cell IDs from <td id="..."> that contain the answer.        │   │
│  │ """                                                                  │   │
│  │                                                                      │   │
│  │ Claude Response:                                                     │   │
│  │ {"answer": "The pH value is 6.1", "cell_ids": ["1-31"]}           │   │
│  │                                                                      │   │
│  │ Time: 1000-1500ms                                                    │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 5: Build Response with Bbox                                    │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Backend looks up bbox from cell_grounding:                          │   │
│  │                                                                      │   │
│  │ bbox = chunk["cell_grounding"]["1-31"]["box"]                      │   │
│  │                                                                      │   │
│  │ Final Response:                                                      │   │
│  │ {                                                                    │   │
│  │   "answer": "The pH value is 6.1",                                 │   │
│  │   "references": [                                                    │   │
│  │     {                                                                │   │
│  │       "page": 1,                                                    │   │
│  │       "bbox": {left: 0.70, top: 0.45, right: 0.84, bottom: 0.48}, │   │
│  │       "cell_id": "1-31"                                             │   │
│  │     }                                                                │   │
│  │   ],                                                                 │   │
│  │   "databases_used": "Weaviate + PostgreSQL"                        │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Time: 50ms                                                           │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ DONE - Answer from Weaviate chunks only                          │   │
│  │ No Neo4j needed!                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: ~3 seconds
├─ Question rephrasing: 1200ms (40%)
├─ Weaviate search: 180ms (6%)
├─ Claude cell matching: 1500ms (50%)
└─ PostgreSQL save: 50ms (1.7%)

WHY NO NEO4J:
• Answer exists in chunks (cell_grounding has value)
• Bbox exists in chunks (cell_grounding has bbox)
• 90% of queries are this simple
```

---

## Flow 2: Extraction Queries (Find ALL Pages)

**Examples:**
- "Extract all test results from Sample Summary"
- "Process all pH values"
- "Export data to Excel"

**Characteristics:**
- Needs ALL pages (not top_k limited)
- Requires comprehensive search
- Image extraction on found pages

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  EXTRACTION FLOW (Weaviate Hybrid + SQL Search)                            │
│  ═══════════════════════════════════════════                                │
│                                                                             │
│  USER ASKS EXTRACTION QUERY                                                 │
│  ┌──────────────────────────────┐                                           │
│  │ "Extract all test results    │                                           │
│  │  from Sample Summary"         │                                           │
│  └───────────┬──────────────────┘                                           │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Intent Detection                                            │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Keywords detected: "extract", "all"                                 │   │
│  │ Decision: EXTRACTION intent                                         │   │
│  │                                                                      │   │
│  │ Time: 10ms                                                           │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Weaviate Hybrid Search (FOUNDATION - Understanding)         │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Purpose: Understand what "Sample Summary" means semantically        │   │
│  │                                                                      │   │
│  │ query = {                                                            │   │
│  │   "vector": embedding("Sample Summary test results"),              │   │
│  │   "where": {"process_id": "uuid-123"},                             │   │
│  │   "hybrid": {"alpha": 0.7, "query": "Sample Summary test results"},│   │
│  │   "limit": 5  // Just to understand, not final results             │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Returns: Sample chunks showing what "Sample Summary" looks like     │   │
│  │                                                                      │   │
│  │ Time: 50ms                                                           │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: Claude Analyzes Chunks & Extracts Keywords                  │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Prompt to Claude:                                                    │   │
│  │                                                                      │   │
│  │ """                                                                  │   │
│  │ Here are sample chunks from the document:                           │   │
│  │ - "Sample Summary | General Tests"                                  │   │
│  │ - "Test Results | pH | 6.1"                                        │   │
│  │                                                                      │   │
│  │ User wants: "Extract all test results from Sample Summary"         │   │
│  │                                                                      │   │
│  │ Extract keywords/variations for SQL search:                         │   │
│  │ """                                                                  │   │
│  │                                                                      │   │
│  │ Claude Response:                                                     │   │
│  │ {                                                                    │   │
│  │   "keywords": [                                                      │   │
│  │     "Sample Summary",                                                │   │
│  │     "General Tests",                                                 │   │
│  │     "Test Results",                                                  │   │
│  │     "test"                                                            │   │
│  │   ]                                                                  │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Time: 1000ms                                                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 4: Weaviate SQL Search (Find ALL Pages - No Limit)             │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Using keywords from Claude:                                          │   │
│  │                                                                      │   │
│  │ SELECT DISTINCT page                                                 │   │
│  │ FROM document_chunks                                                 │   │
│  │ WHERE process_id = 'uuid-123'                                       │   │
│  │   AND (content ILIKE '%Sample Summary%'                            │   │
│  │        OR content ILIKE '%General Tests%'                           │   │
│  │        OR content ILIKE '%Test Results%')                           │   │
│  │ ORDER BY page                                                        │   │
│  │ -- NO LIMIT - returns ALL matching pages                            │   │
│  │                                                                      │   │
│  │ Result: [1, 3, 5, 7, 9] - ALL pages with Sample Summary            │   │
│  │                                                                      │   │
│  │ Time: 80-120ms                                                       │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 5: Claude VISION Extraction (Process Page Images)              │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ For EACH page [1, 3, 5, 7, 9]:                                     │   │
│  │                                                                      │   │
│  │ - Load page image (PNG/JPEG)                                        │   │
│  │ - Send to Claude with extraction prompt                             │   │
│  │ - Extract structured data (parameters, values, criteria)            │   │
│  │                                                                      │   │
│  │ NOT processing chunks - processing actual page images!              │   │
│  │                                                                      │   │
│  │ Time: 2000ms per page × 5 pages = 10,000ms                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 6: Generate Excel with Results                                 │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Combine extracted data from all pages                               │   │
│  │                                                                      │   │
│  │ Excel Structure:                                                     │   │
│  │ | Page | Parameter  | Value | Criteria     | Status |              │   │
│  │ |------|------------|-------|--------------|--------|              │   │
│  │ | 1    | pH         | 6.1   | 5.7 to 6.4   | PASS   |              │   │
│  │ | 3    | Osmolality | 289   | 260-320      | PASS   |              │   │
│  │ | 5    | Endotoxins | 0.48  | NMT 0.50     | PASS   |              │   │
│  │                                                                      │   │
│  │ Time: 5000ms                                                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ DONE - Excel file ready for download                             │   │
│  │ No Neo4j needed! Weaviate SQL found ALL pages.                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: ~16 seconds
├─ Weaviate hybrid search: 50ms (<1%)
├─ Claude keyword extraction: 1000ms (6%)
├─ Weaviate SQL search: 100ms (<1%)
├─ Claude VISION extraction: 10,000ms (62%)
└─ Excel generation: 5,000ms (31%)

WHY NO NEO4J:
• Weaviate hybrid search understands semantic meaning
• Claude extracts better keywords from chunks
• Weaviate SQL finds ALL pages (no top_k limit)
• Image extraction is more accurate than chunk processing
```

---

## Flow 3: Complex/Specific Queries (10% - Need Neo4j)

**Examples:**
- "What's in the cell next to pH value?"
- "Show me all values in row 7"
- "What's in column 3 of the second table?"

**Characteristics:**
- Requires TABLE STRUCTURE (rows, columns, relationships)
- Needs graph traversal (SAME_ROW, SAME_COL)
- Weaviate chunks don't have relationship data

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  COMPLEX QUERY FLOW (Weaviate + Neo4j)                                     │
│  ══════════════════════════════════════                                     │
│                                                                             │
│  USER ASKS STRUCTURAL QUESTION                                              │
│  ┌──────────────────────────────┐                                           │
│  │ "What's in the cell next to  │                                           │
│  │  pH value?"                   │                                           │
│  └───────────┬──────────────────┘                                           │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Question Rephrasing                                          │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Generates variations                                                 │   │
│  │ Time: 1000ms                                                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Weaviate Hybrid Search (FOUNDATION)                         │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Find pH value chunk first                                           │   │
│  │                                                                      │   │
│  │ Returns:                                                             │   │
│  │ {                                                                    │   │
│  │   "content": "pH | QCG-055 | 5.7 to 6.4 | 6.1",                   │   │
│  │   "page": 1,                                                        │   │
│  │   "chunk_index": 2,                                                 │   │
│  │   "cell_grounding": {                                               │   │
│  │     "1-31": {                                                       │   │
│  │       "cell_id": "1-31",   ← Has this metadata                     │   │
│  │       "row": 7,             ← Has this metadata                     │   │
│  │       "col": 3,             ← Has this metadata                     │   │
│  │       "text": "6.1"                                                 │   │
│  │     }                                                                │   │
│  │   }                                                                  │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Time: 180ms                                                          │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: Claude Analyzes Chunk & Detects Structural Need             │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Prompt to Claude:                                                    │   │
│  │                                                                      │   │
│  │ """                                                                  │   │
│  │ Chunk: pH | QCG-055 | 5.7 to 6.4 | 6.1                            │   │
│  │ cell_grounding: {"1-31": {"row": 7, "col": 3, "text": "6.1"}}     │   │
│  │                                                                      │   │
│  │ User Question: "What's in the cell next to pH value?"              │   │
│  │                                                                      │   │
│  │ Analysis:                                                            │   │
│  │ - pH value is at row=7, col=3 (cell_id='1-31')                    │   │
│  │ - User wants "next to" = SAME_ROW, different column               │   │
│  │ - Need Neo4j to find adjacent cell                                 │   │
│  │                                                                      │   │
│  │ Generate Cypher query using chunk metadata.                         │   │
│  │ """                                                                  │   │
│  │                                                                      │   │
│  │ Claude Response:                                                     │   │
│  │ {                                                                    │   │
│  │   "needs_neo4j": true,                                              │   │
│  │   "cypher": "                                                        │   │
│  │     MATCH (cell:Cell {cell_id: '1-31', page_num: 1})              │   │
│  │     MATCH (cell)-[:SAME_ROW]->(neighbor:Cell)                      │   │
│  │     WHERE neighbor.col_index = 4                                    │   │
│  │     RETURN neighbor.text, neighbor.cell_id                          │   │
│  │   "                                                                  │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Time: 1500ms                                                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 4: Neo4j Executes Cypher Query                                 │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ MATCH (cell:Cell {cell_id: '1-31', page_num: 1})                  │   │
│  │ MATCH (cell)-[:SAME_ROW]->(neighbor:Cell)                          │   │
│  │ WHERE neighbor.col_index = 4                                        │   │
│  │ RETURN neighbor.text, neighbor.cell_id                              │   │
│  │                                                                      │   │
│  │ Result:                                                              │   │
│  │ {                                                                    │   │
│  │   "text": "5.7 to 6.4",  ← The acceptance criteria column          │   │
│  │   "cell_id": "1-30"                                                 │   │
│  │ }                                                                    │   │
│  │                                                                      │   │
│  │ Time: 15ms                                                           │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 5: Claude Generates Final Answer                               │   │
│  │ ──────────────────────────────────────────────────────────────────  │   │
│  │ Combines:                                                            │   │
│  │ - Weaviate chunk content: "pH | 6.1"                               │   │
│  │ - Neo4j structure result: "5.7 to 6.4" (adjacent cell)             │   │
│  │                                                                      │   │
│  │ Answer: "The cell next to pH value (6.1) is '5.7 to 6.4',          │   │
│  │         which is the acceptance criteria."                          │   │
│  │                                                                      │   │
│  │ Time: 2000ms                                                         │   │
│  └──────────────────────────────┬───────────────────────────────────────   │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ✅ DONE - Answer from Weaviate + Neo4j                              │   │
│  │ Neo4j provided structural relationships                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TOTAL TIME: ~5 seconds
├─ Question rephrasing: 1000ms (20%)
├─ Weaviate search: 180ms (3.6%)
├─ Claude analysis: 1500ms (30%)
├─ Neo4j query: 15ms (0.3%)
└─ Claude answer: 2000ms (40%)

WHEN NEO4J IS NEEDED:
• Keywords: "next to", "adjacent", "same row", "same column"
• Keywords: "second table", "first column", "row 7"
• Keywords: "before", "after", "surrounding"
• Any query requiring TABLE STRUCTURE relationships
```

---

## Summary: Query Routing Decision Tree

```
User Query
    ↓
┌───────────────────────────────────────┐
│ Detect Intent                         │
│ - Extract keywords                    │
│ - Classify query type                 │
└───────────┬───────────────────────────┘
            │
            ├─── Contains "extract", "process", "all", "export"?
            │    ↓ YES
            │    EXTRACTION FLOW
            │    - Weaviate hybrid search (understand)
            │    - Claude extracts keywords
            │    - Weaviate SQL search (find ALL pages)
            │    - Claude VISION extraction
            │    - Excel generation
            │
            ├─── Contains "next to", "row", "column", "adjacent"?
            │    ↓ YES
            │    COMPLEX FLOW (10%)
            │    - Weaviate hybrid search (find context)
            │    - Claude generates Cypher from chunk metadata
            │    - Neo4j validates structure
            │    - Claude combines results
            │
            └─── Simple value lookup?
                 ↓ YES (90%)
                 SIMPLE Q&A FLOW
                 - Weaviate hybrid search
                 - Claude extracts answer
                 - Bbox from cell_grounding
                 - Done (no Neo4j)
```

---

## Key Principles

**1. Weaviate is ALWAYS the foundation**
- Every query starts with Weaviate
- Provides semantic understanding
- Contains all content and bboxes

**2. Neo4j is OPTIONAL (10% of queries)**
- Only for structural queries
- Requires chunk metadata first (cell_id, row, col)
- Claude generates Cypher based on Weaviate chunks

**3. Metadata flow:**
```
Textract blocks.json
  ↓ (transformation)
Weaviate chunks with metadata
  ↓ (Claude analyzes)
Neo4j Cypher queries
  ↓ (validation)
Final answer
```

**4. All metadata exists in Weaviate:**
- cell_id (generated: "1-31")
- row, col (from Textract RowIndex, ColumnIndex)
- chunk_index (sequential position)
- page, document_id, process_id
- NO additional fields needed!

---

*Document Version: 1.0*
*Created: January 23, 2026*
*Status: ✅ CORRECTED - Weaviate-first approach verified*
