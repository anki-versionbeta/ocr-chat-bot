# Phase 3: Neo4j Schema

> **Database:** Neo4j 5.x
> **Host:** `bolt://10.242.190.53:7687`
> **User:** `neo4j`
> **Created:** February 2026

---

## Schema Overview

| Component | Count |
|-----------|-------|
| **Node Types** | 10 |
| **Relationship Types** | 12 |
| **Constraints** | 10 |
| **Indexes** | 12 |

---

## Node Types (10 Total)

### Document Node

```cypher
(:Document {
    doc_id: STRING,           // Unique document identifier (UUID)
    filename: STRING,         // Original filename
    document_type: STRING,    // "COA", "HBR", etc.
    page_count: INTEGER,      // Total pages
    process_id: STRING,       // Session isolation
    username: STRING,         // Uploader
    created_at: DATETIME      // Index timestamp
})
```

### Page Node

```cypher
(:Page {
    page_key: STRING,         // "{doc_id}_page_{num}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // 1-indexed page number
    width: FLOAT,             // Page width (normalized or pixels)
    height: FLOAT             // Page height
})
```

### Section Node

```cypher
(:Section {
    section_key: STRING,      // "{doc_id}_section_{index}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    layout_type: STRING,      // SECTION_HEADER, TITLE, FOOTER, TEXT
    content: STRING,          // Section text
    chunk_index: INTEGER,     // Links to Weaviate chunk
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### Table Node

```cypher
(:Table {
    table_key: STRING,        // "{doc_id}_table_{index}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    row_count: INTEGER,       // Number of rows
    col_count: INTEGER,       // Number of columns
    chunk_index: INTEGER,     // Links to Weaviate chunk
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### Cell Node

```cypher
(:Cell {
    cell_key: STRING,         // "{doc_id}_cell_{block_id}" or "{doc_id}_{row}_{col}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    row_index: INTEGER,       // Row position (0-indexed)
    col_index: INTEGER,       // Column position (0-indexed)
    row_span: INTEGER,        // Rows spanned (default 1)
    col_span: INTEGER,        // Columns spanned (default 1)
    text: STRING,             // Cell content
    is_header: BOOLEAN,       // Header cell flag
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### Line Node

```cypher
(:Line {
    line_key: STRING,         // "{doc_id}_line_{block_id}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    text: STRING,             // Line text content
    chunk_index: INTEGER,     // Links to Weaviate chunk
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### Word Node

```cypher
(:Word {
    word_key: STRING,         // "{doc_id}_word_{block_id}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    text: STRING,             // Word text
    confidence: FLOAT,        // OCR confidence (0-100)
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### KeyValue Node

```cypher
(:KV {
    kv_key: STRING,           // "{doc_id}_kv_{index}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    key_text: STRING,         // Key/label text
    value_text: STRING,       // Value text
    confidence: FLOAT,        // Extraction confidence
    key_bbox_left: FLOAT,
    key_bbox_top: FLOAT,
    key_bbox_right: FLOAT,
    key_bbox_bottom: FLOAT,
    value_bbox_left: FLOAT,
    value_bbox_top: FLOAT,
    value_bbox_right: FLOAT,
    value_bbox_bottom: FLOAT
})
```

### MergedCell Node

```cypher
(:MergedCell {
    merged_key: STRING,       // "{doc_id}_merged_{index}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    text: STRING,             // Merged cell content
    row_span: INTEGER,        // Rows spanned
    col_span: INTEGER,        // Columns spanned
    start_row: INTEGER,       // Starting row
    start_col: INTEGER,       // Starting column
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

### Selection Node

```cypher
(:Selection {
    selection_key: STRING,    // "{doc_id}_sel_{index}"
    doc_id: STRING,           // Parent document
    page_num: INTEGER,        // Page number
    status: STRING,           // "SELECTED" or "NOT_SELECTED"
    text: STRING,             // Associated text
    bbox_left: FLOAT,
    bbox_top: FLOAT,
    bbox_right: FLOAT,
    bbox_bottom: FLOAT
})
```

---

## Relationship Types (12 Total)

### Document Hierarchy

| Relationship | From | To | Description |
|--------------|------|-------|-------------|
| `HAS_PAGE` | Document | Page | Document contains pages |
| `CONTAINS_SECTION` | Page | Section | Page contains sections |
| `CONTAINS_TABLE` | Page | Table | Page contains tables |
| `CONTAINS_LINE` | Page | Line | Page contains text lines |
| `HAS_KV` | Page | KV | Page contains key-value pairs |
| `HAS_SELECTION` | Page | Selection | Page contains selection elements |

### Table Structure

| Relationship | From | To | Description |
|--------------|------|-------|-------------|
| `HAS_CELL` | Table | Cell | Table contains cells |
| `SAME_ROW` | Cell | Cell | Cells in same row (left→right) |
| `SAME_COL` | Cell | Cell | Cells in same column (top→bottom) |
| `HAS_MERGED` | Table | MergedCell | Table contains merged cells |

### Text Hierarchy

| Relationship | From | To | Description |
|--------------|------|-------|-------------|
| `HAS_WORD` | Line | Word | Line contains words |
| `NEXT_LINE` | Line | Line | Sequential line ordering |

---

## Constraints (10 Total)

```cypher
-- Document uniqueness
CREATE CONSTRAINT doc_id IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;

-- Page uniqueness
CREATE CONSTRAINT page_key IF NOT EXISTS
FOR (p:Page) REQUIRE p.page_key IS UNIQUE;

-- Section uniqueness
CREATE CONSTRAINT section_key IF NOT EXISTS
FOR (s:Section) REQUIRE s.section_key IS UNIQUE;

-- Table uniqueness
CREATE CONSTRAINT table_key IF NOT EXISTS
FOR (t:Table) REQUIRE t.table_key IS UNIQUE;

-- Cell uniqueness
CREATE CONSTRAINT cell_key IF NOT EXISTS
FOR (c:Cell) REQUIRE c.cell_key IS UNIQUE;

-- Line uniqueness
CREATE CONSTRAINT line_key IF NOT EXISTS
FOR (l:Line) REQUIRE l.line_key IS UNIQUE;

-- Word uniqueness
CREATE CONSTRAINT word_key IF NOT EXISTS
FOR (w:Word) REQUIRE w.word_key IS UNIQUE;

-- KeyValue uniqueness
CREATE CONSTRAINT kv_key IF NOT EXISTS
FOR (k:KV) REQUIRE k.kv_key IS UNIQUE;

-- MergedCell uniqueness
CREATE CONSTRAINT merged_key IF NOT EXISTS
FOR (m:MergedCell) REQUIRE m.merged_key IS UNIQUE;

-- Selection uniqueness
CREATE CONSTRAINT selection_key IF NOT EXISTS
FOR (s:Selection) REQUIRE s.selection_key IS UNIQUE;
```

---

## Indexes (12 Total)

### Page Indexes

```cypher
-- Find pages by number
CREATE INDEX page_num_idx IF NOT EXISTS
FOR (p:Page) ON (p.page_num);
```

### Section Indexes

```cypher
-- Filter sections by layout type
CREATE INDEX section_layout_idx IF NOT EXISTS
FOR (s:Section) ON (s.layout_type);

-- Link sections to Weaviate chunks
CREATE INDEX section_chunk_idx IF NOT EXISTS
FOR (s:Section) ON (s.chunk_index);
```

### Table Indexes

```cypher
-- Link tables to Weaviate chunks
CREATE INDEX table_chunk_idx IF NOT EXISTS
FOR (t:Table) ON (t.chunk_index);

-- Find tables by page
CREATE INDEX table_page_idx IF NOT EXISTS
FOR (t:Table) ON (t.page_num);
```

### Cell Indexes

```cypher
-- Query cells by row position
CREATE INDEX cell_row_idx IF NOT EXISTS
FOR (c:Cell) ON (c.row_index);

-- Query cells by column position
CREATE INDEX cell_col_idx IF NOT EXISTS
FOR (c:Cell) ON (c.col_index);

-- Find cells by page
CREATE INDEX cell_page_idx IF NOT EXISTS
FOR (c:Cell) ON (c.page_num);

-- Full-text search on cell content
CREATE INDEX cell_text_idx IF NOT EXISTS
FOR (c:Cell) ON (c.text);
```

### Line Indexes

```cypher
-- Find lines by page
CREATE INDEX line_page_idx IF NOT EXISTS
FOR (l:Line) ON (l.page_num);

-- Link lines to Weaviate chunks
CREATE INDEX line_chunk_idx IF NOT EXISTS
FOR (l:Line) ON (l.chunk_index);

-- Full-text search on line content
CREATE INDEX line_text_idx IF NOT EXISTS
FOR (l:Line) ON (l.text);
```

---

## Common Query Patterns

### 1. Get Document Structure

```cypher
MATCH (d:Document {doc_id: $docId})-[:HAS_PAGE]->(p:Page)
OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
RETURN d, p, t, s
ORDER BY p.page_num
```

### 2. Get Table with All Cells

```cypher
MATCH (t:Table {table_key: $tableKey})-[:HAS_CELL]->(c:Cell)
RETURN t, c
ORDER BY c.row_index, c.col_index
```

### 3. Get Row Data (SAME_ROW Traversal)

```cypher
MATCH (c:Cell {cell_key: $startCellKey})
MATCH path = (c)-[:SAME_ROW*0..]->(neighbor:Cell)
RETURN neighbor
ORDER BY neighbor.col_index
```

### 4. Get Column Data (SAME_COL Traversal)

```cypher
MATCH (c:Cell {cell_key: $startCellKey})
MATCH path = (c)-[:SAME_COL*0..]->(neighbor:Cell)
RETURN neighbor
ORDER BY neighbor.row_index
```

### 5. Find Cells by Content

```cypher
MATCH (c:Cell)
WHERE c.text CONTAINS $searchTerm
RETURN c.cell_key, c.text, c.row_index, c.col_index, c.page_num
```

### 6. Link Neo4j Cell to Weaviate Chunk

```cypher
// Get chunk_index from Table node
MATCH (t:Table)-[:HAS_CELL]->(c:Cell {cell_key: $cellKey})
RETURN t.chunk_index AS weaviate_chunk_index

// Then query Weaviate:
// client.query.get("DocumentChunk").with_where({
//     "path": ["chunk_index"],
//     "operator": "Equal",
//     "valueInt": weaviate_chunk_index
// })
```

### 7. Get All Sections by Type

```cypher
MATCH (d:Document {doc_id: $docId})-[:HAS_PAGE]->(p:Page)
      -[:CONTAINS_SECTION]->(s:Section)
WHERE s.layout_type = 'SECTION_HEADER'
RETURN s.content, s.page_num, s.chunk_index
ORDER BY p.page_num, s.chunk_index
```

### 8. Delete Document and All Related Nodes

```cypher
MATCH (d:Document {doc_id: $docId})
OPTIONAL MATCH (d)-[*]->(n)
DETACH DELETE d, n
```

---

## Graph Visualization

```
                    ┌─────────────┐
                    │  Document   │
                    │  (doc_id)   │
                    └──────┬──────┘
                           │ HAS_PAGE
                           ▼
                    ┌─────────────┐
                    │    Page     │
                    │ (page_key)  │
                    └──────┬──────┘
           ┌───────────────┼───────────────┬────────────────┐
           │               │               │                │
           ▼               ▼               ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐     ┌──────────┐
    │ Section  │    │  Table   │    │   Line   │     │    KV    │
    │(section) │    │(table_k) │    │(line_key)│     │ (kv_key) │
    └──────────┘    └────┬─────┘    └────┬─────┘     └──────────┘
                         │               │
                    HAS_CELL         HAS_WORD
                         │               │
                         ▼               ▼
                    ┌──────────┐    ┌──────────┐
                    │   Cell   │    │   Word   │
                    │(cell_key)│    │(word_key)│
                    └──────────┘    └──────────┘
                         │
              ┌──────────┼──────────┐
              │                     │
         SAME_ROW              SAME_COL
              │                     │
              ▼                     ▼
         ┌─────────┐           ┌─────────┐
         │  Cell   │           │  Cell   │
         │ (right) │           │ (below) │
         └─────────┘           └─────────┘
```

---

## Verification Commands

### Check Constraints

```cypher
SHOW CONSTRAINTS
```

Expected output: 10 constraints

### Check Indexes

```cypher
SHOW INDEXES
```

Expected output: 12+ indexes (including constraint-backed indexes)

### Count Nodes by Type

```cypher
CALL apoc.meta.stats() YIELD labels
RETURN labels
```

### Test Constraint (Should Fail on Duplicate)

```cypher
CREATE (d1:Document {doc_id: 'test_001'})
CREATE (d2:Document {doc_id: 'test_001'})  // Should fail
```

---

## Docker Commands

### Access Neo4j Shell

```bash
docker exec -it neo4j cypher-shell -u neo4j -p 'ocr@4567'
```

### Run Single Query

```bash
docker exec neo4j cypher-shell -u neo4j -p 'ocr@4567' 'SHOW CONSTRAINTS'
```

### Check Neo4j Status

```bash
docker exec neo4j neo4j status
```

---

## Integration with Weaviate

### Linking Strategy

| Neo4j Node | Link Field | Weaviate Field |
|------------|------------|----------------|
| Table | `chunk_index` | `chunk_index` |
| Section | `chunk_index` | `chunk_index` |
| Line | `chunk_index` | `chunk_index` |
| Cell | via parent Table | `cell_grounding` JSON |

### Workflow Example

```
1. User asks: "What is the pH value?"

2. Weaviate hybrid search returns:
   - chunk_id: "chunk_042"
   - chunk_index: 5
   - chunk_type: "table"
   - cell_grounding: {"1-29": {"text": "6.1", "row": 7, "col": 3, ...}}

3. Neo4j structural query:
   MATCH (t:Table {chunk_index: 5})-[:HAS_CELL]->(c:Cell)
   WHERE c.row_index = 7
   RETURN c.text, c.col_index
   ORDER BY c.col_index

4. Result: Full row context for highlighting
   | Parameter | Method | Spec | Result |
   | pH        | QCG-055| 5.7-6.4 | 6.1  |
```

---

## Storage Estimates

| Document Size | Nodes | Relationships |
|---------------|-------|---------------|
| 5-page PDF | ~500 nodes | ~600 rels |
| 50-page PDF | ~5,000 nodes | ~6,000 rels |
| 235-page PDF | ~25,000 nodes | ~30,000 rels |

**Per Page Breakdown:**
- 1 Page node
- 5-10 Section nodes
- 2-5 Table nodes
- 50-200 Cell nodes
- 20-50 Line nodes
- 100-300 Word nodes

---

*Document Version: 1.0*
*Created: February 2026*
*Phase: 3 of 3*
