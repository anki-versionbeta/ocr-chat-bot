# Multi-Agent GraphRAG System - Complete Architecture Documentation

**Document Version:** 1.0
**Created:** February 12, 2026
**Author:** Claude Code
**Status:** Production Ready

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Document Ingestion Pipeline](#3-document-ingestion-pipeline)
4. [Database Schemas](#4-database-schemas)
5. [Query Processing Pipeline (5 Agents)](#5-query-processing-pipeline-5-agents)
6. [Algorithms & Techniques](#6-algorithms--techniques)
7. [Complete System Flow Diagram](#7-complete-system-flow-diagram)
8. [Performance Metrics](#8-performance-metrics)
9. [Configuration Reference](#9-configuration-reference)

---

## 1. Executive Summary

### What is this system?

A **Multi-Agent GraphRAG (Retrieval-Augmented Generation) System** that converts natural language questions into Neo4j Cypher queries to extract structured data from documents. It combines:

- **Weaviate** (Vector DB) for semantic search
- **Neo4j** (Graph DB) for structured data traversal
- **5 Specialized AI Agents** for query planning, generation, and validation
- **Dynamic Learning** via Success Bank for continuous improvement

### Key Achievements

| Metric | Value |
|--------|-------|
| Easy Query Success Rate | 100% (6/6) |
| Hard Query Success Rate | 100% (4/4) |
| First-Try Success Rate | 100% |
| Average Query Time | ~30 seconds |
| External AI Ratings | Kimi AI: 9.9/10, Google AI: "Research-grade" |

### Core Innovation

The system solves the **"Table-Centric Bias"** problem where traditional systems assume all data is in tables. Our **Structural Probe** first discovers WHERE data actually exists (Cell/Line/Section nodes), then enforces this as **Hard Constraints** that the LLM cannot ignore.

---

## 2. System Overview

### High-Level Architecture

```
                                    USER QUERY
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                         MULTI-AGENT PIPELINE                                │
│                                                                             │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│   │   AGENT 1   │   │   AGENT 2   │   │   AGENT 3   │   │  AGENT 3.5  │   │
│   │   Context   │──►│   Logic     │──►│   Cypher    │──►│    NEV      │   │
│   │   Gatherer  │   │   Planner   │   │   Generator │   │   Auditor   │   │
│   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘   │
│          │                                                      │          │
│          │                                                      ▼          │
│          │                                              ┌─────────────┐   │
│          │                                              │   AGENT 4   │   │
│          │                                              │  Validator  │   │
│          │                                              └─────────────┘   │
│          │                                                      │          │
│          ▼                                                      ▼          │
│   ┌─────────────┐                                       ┌─────────────┐   │
│   │  WEAVIATE   │                                       │   NEO4J     │   │
│   │  (Vectors)  │                                       │   (Graph)   │   │
│   └─────────────┘                                       └─────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                                   RESULTS
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Vector Database | Weaviate | Semantic search, hybrid retrieval |
| Graph Database | Neo4j | Structured data storage, Cypher queries |
| LLM (Planning) | Claude Haiku | Fast planning, intent classification |
| LLM (Generation) | Claude Sonnet | High-quality code generation |
| LLM (Validation) | Claude Haiku | Quick validation checks |
| Embedding Model | text-embedding-3-large | 3072-dimensional vectors |
| OCR Engine | AWS Textract | PDF text extraction |
| Framework | LangGraph | Multi-agent orchestration |

---

## 3. Document Ingestion Pipeline

### Step 1: PDF Upload & OCR Extraction

```
User uploads PDF
       │
       ▼
┌─────────────────────────────────────┐
│     AWS Textract (OCR Engine)       │
│  ─────────────────────────────────  │
│  - Extracts text from PDF           │
│  - Identifies TABLE blocks          │
│  - Identifies LAYOUT blocks         │
│  - Extracts bounding box (bbox)     │
│  - Returns blocks.json              │
└─────────────────────────────────────┘
       │
       ▼
   blocks.json
   {
     "BlockType": "TABLE" | "LINE" | "CELL",
     "Text": "...",
     "Geometry": {"BoundingBox": {...}},
     "Relationships": [...]
   }
```

### Step 2: Neo4j Graph Indexing

```
blocks.json
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│              Neo4j Graph Database Indexing                       │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Creates hierarchical graph structure:                          │
│                                                                  │
│                        (Document)                                │
│                            │                                     │
│                      [:HAS_PAGE]                                 │
│                            │                                     │
│                            ▼                                     │
│                         (Page)                                   │
│                        /      \                                  │
│           [:CONTAINS_TABLE]  [:CONTAINS_LINE]                   │
│                  /                  \                            │
│                 ▼                    ▼                           │
│             (Table)               (Line)                         │
│                │                                                 │
│          [:HAS_CELL]                                            │
│                │                                                 │
│                ▼                                                 │
│             (Cell)                                               │
│                                                                  │
│  Node Properties:                                                │
│  ─────────────────                                               │
│  Document: process_id, filename                                  │
│  Page: page_num                                                  │
│  Table: table_id, chunk_index, row_count, col_count             │
│  Cell: text, row_index, col_index, is_header, bbox_*            │
│  Line: text, line_id, bbox_*, confidence                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Step 3: Weaviate Vector Indexing

```
blocks.json + Parsed Content
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│              Weaviate Vector Database Indexing                   │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  1. Chunk Transformer creates chunks:                           │
│     ┌─────────────────────────────────────────────────────┐    │
│     │  TABLE chunks:                                       │    │
│     │  - content: "TESTS | SPECS | METHOD | RESULTS\n..." │    │
│     │  - markdown: "<table><td id='2-5'>...</td></table>" │    │
│     │  - cell_grounding: {"2-5": {"bbox": {...}}}         │    │
│     │                                                      │    │
│     │  TEXT chunks:                                        │    │
│     │  - content: "Batch Number: 0001903354"              │    │
│     │  - layout_type: "LAYOUT_KEY_VALUE"                  │    │
│     │  - line_grounding: {"uuid": {"bbox": {...}}}        │    │
│     └─────────────────────────────────────────────────────┘    │
│                                                                  │
│  2. Embedding Generation:                                        │
│     - Model: text-embedding-3-large                             │
│     - Dimensions: 3072                                           │
│     - Each chunk gets vector representation                     │
│                                                                  │
│  3. Store in "DocumentChunk" collection                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Database Schemas

### 4.1 Neo4j Graph Schema

```
┌─────────────────────────────────────────────────────────────────┐
│                     NEO4J GRAPH SCHEMA                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  NODE LABELS (10 total):                                        │
│  ─────────────────────────                                       │
│  Document    - Root node with process_id, filename              │
│  Page        - Has page_num, page_key                           │
│  Section     - Has section_id, text, content                    │
│  Table       - Has table_id, chunk_index, row_count, col_count  │
│  Cell        - Has text, row_index, col_index, is_header, bbox  │
│  Line        - Has text, line_id, bbox, confidence              │
│  Word        - Has word_id, text                                │
│  KV          - Has kv_id (Key-Value pairs)                      │
│  MergedCell  - Has merged_id (spanning cells)                   │
│  Selection   - Has selection_id                                 │
│                                                                  │
│  RELATIONSHIPS (7 total):                                        │
│  ───────────────────────                                         │
│  HAS_PAGE         : Document -> Page                            │
│  CONTAINS_TABLE   : Page -> Table                               │
│  HAS_CELL         : Table -> Cell                               │
│  CONTAINS_SECTION : Page -> Section                             │
│  CONTAINS_LINE    : Page -> Line                                │
│  SAME_ROW         : Cell -> Cell (horizontal adjacency)         │
│  SAME_COL         : Cell -> Cell (vertical adjacency)           │
│                                                                  │
│  VALID PATHS:                                                    │
│  ────────────                                                    │
│  PATH 1 (Tables):  Document->Page->Table->Cell                  │
│  PATH 2 (Text):    Document->Page->Line                         │
│  PATH 3 (Sections): Document->Page->Section                     │
│  PATH 4 (Adjacency): Cell-[:SAME_ROW]->Cell                     │
│                                                                  │
│  INVALID PATHS (Hallucinations to catch):                       │
│  ─────────────────────────────────────────                       │
│  Table->Line      (different branches)                          │
│  Document->Cell   (missing Page intermediate)                   │
│  Cell->Table      (reversed direction)                          │
│  Line->Cell       (different branches)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Weaviate Collections Schema

#### Collection 1: DocumentChunk (RAG Search)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DocumentChunk Collection                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Property          │ Type      │ Purpose                        │
│  ──────────────────┼───────────┼────────────────────────────────│
│  chunk_id          │ text      │ Unique identifier              │
│  process_id        │ text      │ Document UUID (filtering)      │
│  page              │ int       │ Page number                    │
│  chunk_index       │ int       │ Order within document          │
│  chunk_type        │ text      │ "table" or "text"              │
│  content           │ text      │ Raw text content               │
│  markdown          │ text      │ HTML/Markdown representation   │
│  cell_grounding    │ text      │ JSON: cell_id -> bbox mapping  │
│  vector            │ float[]   │ 3072-dim embedding             │
│                                                                  │
│  SEARCH ALGORITHM: HYBRID                                        │
│  ─────────────────────────                                       │
│  Score = 0.7 × semantic_score + 0.3 × bm25_score                │
│                                                                  │
│  Semantic: cosine_similarity(query_vec, chunk_vec)              │
│  BM25: term_frequency × inverse_document_frequency              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Collection 2: CypherSuccessBank (Dynamic Learning)

```
┌─────────────────────────────────────────────────────────────────┐
│                  CypherSuccessBank Collection                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Property            │ Type      │ Purpose                      │
│  ────────────────────┼───────────┼──────────────────────────────│
│  user_query          │ text      │ Original natural language Q  │
│  cypher_query        │ text      │ Generated Cypher that worked │
│  logical_plan        │ text      │ Step-by-step reasoning plan  │
│  node_types_used     │ text[]    │ [Cell, Line, Table, etc.]    │
│  relationship_path   │ text      │ HAS_PAGE->CONTAINS_TABLE->...│
│  structural_signature│ text      │ JSON of probe results        │
│  chunk_types_seen    │ text[]    │ Weaviate chunk types found   │
│  accuracy_score      │ float     │ 0.0 to 1.0 (success rating)  │
│  process_id          │ text      │ Document UUID                │
│  result_count        │ int       │ Rows returned                │
│  iterations_used     │ int       │ 1 = first-try success        │
│  created_at          │ date      │ Timestamp                    │
│  vector              │ float[]   │ Query embedding (3072-dim)   │
│                                                                  │
│  HOW IT WORKS:                                                   │
│  ─────────────                                                   │
│  1. On FIRST-TRY SUCCESS, query+cypher is auto-saved            │
│  2. Future similar queries retrieve these as few-shot examples  │
│  3. Uses vector similarity to find semantically similar queries │
│  4. Filters by node_types_used for structural compatibility     │
│                                                                  │
│  RETRIEVAL ALGORITHM:                                            │
│  ────────────────────                                            │
│  1. Embed user query (3072 dimensions)                          │
│  2. nearVector search in CypherSuccessBank                      │
│  3. Filter: accuracy_score > 0.7                                │
│  4. If probe says "Line only", prefer Line-compatible examples  │
│  5. Return top 2-3 examples                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Query Processing Pipeline (5 Agents)

### Overview Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   USER QUERY: "Get second Count row with Project Name for each page"        │
│                                                                              │
│   ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐     │
│   │  AGENT 1   │───►│  AGENT 2   │───►│  AGENT 3   │───►│ AGENT 3.5  │     │
│   │  Context   │    │   Logic    │    │   Cypher   │    │    NEV     │     │
│   │  Gatherer  │    │  Planner   │    │ Generator  │    │  Auditor   │     │
│   └────────────┘    └────────────┘    └────────────┘    └────────────┘     │
│         │                                                      │            │
│         │                                                      ▼            │
│         │                                              ┌────────────┐       │
│         │                                              │  AGENT 4   │       │
│         │                                              │ Validator  │       │
│         │                                              └────────────┘       │
│         │                                                    │              │
│         │              ┌─────────────────────────────────────┤              │
│         │              │                                     │              │
│         │         INVALID                                 VALID             │
│         │              │                                     │              │
│         │              ▼                                     ▼              │
│         │       ┌────────────┐                       ┌────────────┐        │
│         │       │   RETRY    │                       │  SUCCESS   │        │
│         │       │ (Agent 2)  │                       │   BANK     │        │
│         │       └────────────┘                       └────────────┘        │
│         │                                                    │              │
│         ▼                                                    ▼              │
│   ┌────────────┐                                      ┌────────────┐       │
│   │  WEAVIATE  │                                      │  RESULTS   │       │
│   └────────────┘                                      └────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Agent 1: Context Gatherer

**Purpose:** Collect all context needed for Cypher generation

**Model:** N/A (Pure data retrieval)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AGENT 1: CONTEXT GATHERER                                                  │
│   ═══════════════════════════                                                │
│                                                                              │
│   STEP 1: Extract Search Terms                                               │
│   ────────────────────────────                                               │
│   Input: "Get second Count row with Project Name for each page"             │
│   Output: ["second", "count", "row", "project", "name", "page"]             │
│                                                                              │
│   STEP 2: Weaviate Hybrid Search                                             │
│   ──────────────────────────────                                             │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    HYBRID SEARCH ALGORITHM                       │       │
│   │                                                                  │       │
│   │   final_score = 0.7 × semantic_score + 0.3 × bm25_score        │       │
│   │                                                                  │       │
│   │   Semantic Score:                                                │       │
│   │     cosine_similarity(query_embedding, chunk_embedding)         │       │
│   │                                                                  │       │
│   │   BM25 Score:                                                    │       │
│   │     Σ (tf × idf) for each term                                  │       │
│   │     tf = term_frequency in document                             │       │
│   │     idf = log(N / df) where df = docs containing term           │       │
│   │                                                                  │       │
│   │   Filter: process_id = "{document_uuid}"                        │       │
│   │   Limit: 10 chunks per search term                              │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   Returns: Relevant chunks + extracted column headers                       │
│                                                                              │
│   STEP 3: Structural Probe (KEY INNOVATION!)                                 │
│   ──────────────────────────────────────────                                 │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    STRUCTURAL PROBE                              │       │
│   │                                                                  │       │
│   │   Purpose: Find WHERE data ACTUALLY exists before generation    │       │
│   │                                                                  │       │
│   │   For each search term, query Neo4j:                            │       │
│   │                                                                  │       │
│   │   -- Check Cell nodes                                            │       │
│   │   MATCH (d:Document {process_id: $pid})                         │       │
│   │     -[:HAS_PAGE]->(p:Page)                                      │       │
│   │     -[:CONTAINS_TABLE]->(t:Table)                               │       │
│   │     -[:HAS_CELL]->(c:Cell)                                      │       │
│   │   WHERE toLower(c.text) CONTAINS $term                          │       │
│   │   RETURN 'Cell' as node_type, count(c), sample_pages            │       │
│   │                                                                  │       │
│   │   -- Check Line nodes                                            │       │
│   │   MATCH (d:Document {process_id: $pid})                         │       │
│   │     -[:HAS_PAGE]->(p:Page)                                      │       │
│   │     -[:CONTAINS_LINE]->(l:Line)                                 │       │
│   │   WHERE toLower(l.text) CONTAINS $term                          │       │
│   │   RETURN 'Line' as node_type, count(l), sample_pages            │       │
│   │                                                                  │       │
│   │   Example Result:                                                │       │
│   │   {                                                              │       │
│   │     "found_in": {                                                │       │
│   │       "count": [                                                 │       │
│   │         {"node_type": "Cell", "count": 144, "pages": [1,2,3]},  │       │
│   │         {"node_type": "Line", "count": 189, "pages": [1,2,3]}   │       │
│   │       ],                                                         │       │
│   │       "project": [                                               │       │
│   │         {"node_type": "Cell", "count": 102, "pages": [46,98]}   │       │
│   │       ]                                                          │       │
│   │     },                                                           │       │
│   │     "recommended_paths": [                                       │       │
│   │       "Document->Page->Table->Cell",                            │       │
│   │       "Document->Page->Line"                                    │       │
│   │     ]                                                            │       │
│   │   }                                                              │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 4: Few-Shot Retrieval from Success Bank                              │
│   ────────────────────────────────────────────                              │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                  SUCCESS BANK RETRIEVAL                          │       │
│   │                                                                  │       │
│   │   1. Embed user query using text-embedding-3-large              │       │
│   │   2. Query CypherSuccessBank with nearVector                    │       │
│   │   3. Filter: accuracy_score > 0.7                               │       │
│   │   4. STRUCTURAL COMPATIBILITY CHECK:                             │       │
│   │      - If probe says "Line only", prefer Line examples          │       │
│   │      - If probe says "Cell only", prefer Cell examples          │       │
│   │   5. Return top 2-3 matching examples                           │       │
│   │                                                                  │       │
│   │   Fallback: If Success Bank empty, use hardcoded FEW_SHOT_EXAMPLES     │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 5: Get Filtered Schema                                                │
│   ───────────────────────────                                                │
│   Query Neo4j for node counts specific to this document                     │
│                                                                              │
│   STEP 6: Get Data Snippets                                                  │
│   ─────────────────────────                                                  │
│   Retrieve actual sample rows from Neo4j for context                        │
│                                                                              │
│   OUTPUT:                                                                    │
│   ───────                                                                    │
│   {                                                                          │
│     "weaviate_chunks": [...],                                               │
│     "weaviate_headers": ["Batch Name:", "Project Name:", ...],             │
│     "structural_probe": {...},                                              │
│     "similar_examples": [...],                                              │
│     "filtered_schema": "...",                                               │
│     "data_snippet": "..."                                                   │
│   }                                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Agent 2: Logic-First Planner

**Purpose:** Generate step-by-step logical plan BEFORE any code

**Model:** Claude Haiku (fast)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AGENT 2: LOGIC-FIRST PLANNER                                               │
│   ════════════════════════════                                               │
│                                                                              │
│   KEY INNOVATION: Force LLM to reason BEFORE writing code                   │
│                                                                              │
│   STEP 1: Extract Hard Constraints                                           │
│   ───────────────────────────────                                            │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │               HARD CONSTRAINTS EXTRACTION                        │       │
│   │                                                                  │       │
│   │   Based on Structural Probe results:                            │       │
│   │                                                                  │       │
│   │   CASE 1: Data ONLY in Line nodes                               │       │
│   │     primary_node = "Line"                                        │       │
│   │     forbidden_nodes = ["Cell", "Table", "MergedCell"]           │       │
│   │     required_path = "Document->Page->Line"                      │       │
│   │                                                                  │       │
│   │   CASE 2: Data ONLY in Cell nodes                               │       │
│   │     primary_node = "Cell"                                        │       │
│   │     forbidden_nodes = ["Line"]                                  │       │
│   │     required_path = "Document->Page->Table->Cell"               │       │
│   │                                                                  │       │
│   │   CASE 3: Data in BOTH Cell and Line                            │       │
│   │     primary_node = "BOTH"                                        │       │
│   │     forbidden_nodes = []                                        │       │
│   │     required_path = "Use Page as join point"                    │       │
│   │                                                                  │       │
│   │   CASE 4: Simple lookup with Cell data available                │       │
│   │     primary_node = "Cell" (avoid complex UNION)                 │       │
│   │     forbidden_nodes = []                                        │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 2: Format Constraint Block                                            │
│   ───────────────────────────────                                            │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                                                                  │       │
│   │   +============================================================+│       │
│   │   |         MANDATORY CONSTRAINTS (VIOLATION = 0 ROWS)         ||       │
│   │   +============================================================+│       │
│   │   | PRIMARY NODE TYPE:  BOTH                                   ||       │
│   │   | FORBIDDEN NODES:    None                                   ||       │
│   │   | REQUIRED PATH:      Use Page as join point                 ||       │
│   │   +------------------------------------------------------------+│       │
│   │   | REASONING:                                                 ||       │
│   │   |  - Cell: 384 matches, Line: 505 matches                    ||       │
│   │   +============================================================+│       │
│   │                                                                  │       │
│   │   >>> WARNING: FAILURE TO FOLLOW = ZERO ROWS <<<                │       │
│   │   >>> DO NOT USE None NODES FOR THIS QUERY <<<                  │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 3: Generate Logical Plan (NO CYPHER!)                                │
│   ──────────────────────────────────────────                                 │
│   Prompt includes:                                                           │
│   - User query                                                               │
│   - Hard constraints block                                                   │
│   - Data source routing rules                                               │
│   - Weaviate context                                                        │
│   - Structural probe results                                                │
│   - Similar examples from Success Bank                                      │
│   - Filtered schema                                                         │
│   - Actual data samples                                                     │
│   - Previous feedback (if retry)                                            │
│                                                                              │
│   OUTPUT (plain English, NO code):                                           │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │   # LOGICAL PLAN                                                 │       │
│   │                                                                  │       │
│   │   1. Use CELL nodes as primary (per constraints)                │       │
│   │   2. Path: Document→Page→Table→Cell                             │       │
│   │   3. Find all "Count" labels at col_index=1                     │       │
│   │   4. Group by page, collect row_indexes                         │       │
│   │   5. Select index [1] (second Count row, 0-based)              │       │
│   │   6. Get all values from same row, all columns                  │       │
│   │   7. Also get Project Name from same page (row_index=2)        │       │
│   │   8. Return page_num, project_name, count_values                │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Agent 3: Cypher Generator

**Purpose:** Convert logical plan into executable Cypher code

**Model:** Claude Sonnet (best for code generation)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AGENT 3: CYPHER GENERATOR                                                  │
│   ═════════════════════════                                                  │
│                                                                              │
│   KEY INNOVATION: Dynamic rules based on Structural Probe                   │
│                                                                              │
│   STEP 1: Generate Dynamic Rules                                             │
│   ──────────────────────────────                                             │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │               DYNAMIC RULE INJECTION                             │       │
│   │                                                                  │       │
│   │   Based on primary_node from constraints:                       │       │
│   │                                                                  │       │
│   │   IF primary_node == "Line":                                    │       │
│   │     path_rule = "MUST USE: Page-[:CONTAINS_LINE]->Line"        │       │
│   │     props_rule = "text, line_id, bbox (NO row_index!)"         │       │
│   │     forbidden = "DO NOT use Table or Cell nodes!"               │       │
│   │                                                                  │       │
│   │   IF primary_node == "Cell":                                    │       │
│   │     path_rule = "MUST USE: Page-[:CONTAINS_TABLE]->Table->Cell"│       │
│   │     props_rule = "text, row_index, col_index, is_header"       │       │
│   │     forbidden = "DO NOT use Line nodes for table data!"         │       │
│   │                                                                  │       │
│   │   IF primary_node == "BOTH":                                    │       │
│   │     path_rule = "Use Page as join point for both paths"        │       │
│   │     props_rule = "Cell: row/col | Line: text/line_id"          │       │
│   │     forbidden = "Use correct node for each field!"              │       │
│   │                                                                  │       │
│   │   IF primary_node == "Section":                                 │       │
│   │     path_rule = "MUST USE: Page-[:CONTAINS_SECTION]->Section"  │       │
│   │     props_rule = "section_id, text, content"                   │       │
│   │     forbidden = "DO NOT use Table, Cell, or Line!"              │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 2: Build Generation Prompt                                            │
│   ───────────────────────────────                                            │
│   Includes:                                                                  │
│   - User query                                                               │
│   - Logical plan from Agent 2                                               │
│   - Filtered schema                                                         │
│   - Few-shot examples with actual Cypher                                    │
│   - Previous error feedback (if retry)                                      │
│   - Dynamic rules (path_rule, props_rule, forbidden)                        │
│                                                                              │
│   GENERATION RULES:                                                          │
│   ─────────────────                                                          │
│   1. ALWAYS start with: MATCH (d:Document {process_id: $process_id})       │
│   2. {path_rule} - Dynamic based on probe                                   │
│   3. {props_rule} - Dynamic based on probe                                  │
│   4. {forbidden_rule} - Dynamic based on probe                              │
│   5. Use toLower(coalesce(node.text, '')) for safe text matching           │
│   6. For multi-page: NO global LIMIT at end!                                │
│   7. For regex dots: escape as '5\\.00' or '5[.]00'                        │
│                                                                              │
│   OUTPUT: Executable Cypher query                                            │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │  MATCH (d:Document {process_id: $process_id})                   │       │
│   │    -[:HAS_PAGE]->(p:Page)                                       │       │
│   │    -[:CONTAINS_TABLE]->(t:Table)                                │       │
│   │    -[:HAS_CELL]->(label_cell:Cell)                              │       │
│   │  WHERE toLower(coalesce(label_cell.text, '')) = 'count'        │       │
│   │    AND label_cell.col_index = 1                                 │       │
│   │  WITH p.page_num AS page_num, t.table_id AS table_id,          │       │
│   │       label_cell.row_index AS row_index                         │       │
│   │  ORDER BY page_num, table_id, row_index                         │       │
│   │  WITH page_num, collect({...})[1] AS second_count              │       │
│   │  WHERE second_count IS NOT NULL                                 │       │
│   │  ...                                                            │       │
│   │  RETURN page_num, project_name, count_values                    │       │
│   │  ORDER BY page_num                                              │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Agent 3.5: NEV Auditor (Named Entity Verification)

**Purpose:** Validate and auto-correct generated Cypher before execution

**Model:** N/A (Rule-based validation)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AGENT 3.5: NEV AUDITOR                                                     │
│   ══════════════════════                                                     │
│                                                                              │
│   Named Entity Verification - Catches hallucinations BEFORE execution       │
│                                                                              │
│   STEP 0: TOPOLOGY VERIFICATION (First check - fail fast)                   │
│   ───────────────────────────────────────────────────────                   │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    TOPOLOGY CHECK                                │       │
│   │                                                                  │       │
│   │   CHECK 1: Invalid Direct Connections                           │       │
│   │   ─────────────────────────────────────                         │       │
│   │   Pattern                      │ Result                         │       │
│   │   ─────────────────────────────┼────────                        │       │
│   │   (:Table)-[*]->(:Line)       │ INVALID - different branches   │       │
│   │   (:Table)-[*]->(:Section)    │ INVALID                        │       │
│   │   (:Line)-[*]->(:Cell)        │ INVALID - different branches   │       │
│   │   (:Document)-[*]->(:Cell)    │ INVALID - missing Page         │       │
│   │   (:Cell)-[*]->(:Table)       │ INVALID - reversed direction   │       │
│   │   (:Page)-[*]->(:Document)    │ INVALID - reversed direction   │       │
│   │   (:Cell)-[:SAME_ROW]->(:Cell)│ VALID - allowed adjacency      │       │
│   │   (:Page)->(:Table)->(:Cell)  │ VALID                          │       │
│   │                                                                  │       │
│   │   CHECK 2: Probe Mismatch (Most Critical!)                      │       │
│   │   ─────────────────────────────────────────                     │       │
│   │   IF probe.found_in shows "Line only"                           │       │
│   │      BUT Cypher uses :Cell or :Table                            │       │
│   │      → REJECT with message:                                      │       │
│   │        "PROBE MISMATCH: Data in Line, not Cell!"                │       │
│   │                                                                  │       │
│   │   IF probe.found_in shows "Cell only"                           │       │
│   │      BUT Cypher uses :Line                                      │       │
│   │      → REJECT with message:                                      │       │
│   │        "PROBE MISMATCH: Data in Cell, not Line!"                │       │
│   │                                                                  │       │
│   │   CHECK 3: Relationship Type Validation                         │       │
│   │   ─────────────────────────────────────────                     │       │
│   │   Valid relationships:                                          │       │
│   │     HAS_PAGE, CONTAINS_TABLE, HAS_CELL,                        │       │
│   │     CONTAINS_SECTION, CONTAINS_LINE, SAME_ROW, SAME_COL        │       │
│   │                                                                  │       │
│   │   Any other relationship type → INVALID                         │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 1: Entity Extraction                                                  │
│   ─────────────────────────                                                  │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    ENTITY EXTRACTION                             │       │
│   │                                                                  │       │
│   │   From Cypher query, extract:                                   │       │
│   │                                                                  │       │
│   │   Labels:        :Document, :Page, :Table, :Cell               │       │
│   │   Relationships: [:HAS_PAGE], [:CONTAINS_TABLE], [:HAS_CELL]   │       │
│   │   Properties:    .text, .row_index, .col_index, .page_num      │       │
│   │   String Values: 'count', 'project name', etc.                 │       │
│   │   Map Keys:      {header: x, value: y} → [header, value]       │       │
│   │                                                                  │       │
│   │   IMPORTANT: Map literal keys are NOT Neo4j properties!        │       │
│   │   They should NOT be "corrected" to property names.            │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 2: Entity Verification                                                │
│   ───────────────────────────                                                │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    ENTITY VERIFICATION                           │       │
│   │                                                                  │       │
│   │   Query Neo4j for actual schema:                                │       │
│   │     CALL db.labels()           → actual_labels                 │       │
│   │     CALL db.relationshipTypes() → actual_rels                  │       │
│   │     CALL db.propertyKeys()     → actual_props                  │       │
│   │                                                                  │       │
│   │   For each extracted entity:                                    │       │
│   │     IF entity NOT IN actual_schema:                             │       │
│   │       → Find closest match using Levenshtein                    │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 3: Auto-Correction (Levenshtein Similarity)                          │
│   ────────────────────────────────────────────────                          │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    LEVENSHTEIN AUTO-CORRECTION                   │       │
│   │                                                                  │       │
│   │   Algorithm: SequenceMatcher from difflib                       │       │
│   │                                                                  │       │
│   │   def levenshtein_similarity(s1, s2):                           │       │
│   │       return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()     │
│   │                                                                  │       │
│   │   def find_closest_match(target, candidates, threshold=0.6):    │       │
│   │       best_match = None                                         │       │
│   │       best_score = threshold                                    │       │
│   │       for candidate in candidates:                              │       │
│   │           score = levenshtein_similarity(target, candidate)     │       │
│   │           if score > best_score:                                │       │
│   │               best_score = score                                │       │
│   │               best_match = candidate                            │       │
│   │       return best_match                                         │       │
│   │                                                                  │       │
│   │   Examples:                                                      │       │
│   │     "Cel" → "Cell" (similarity = 0.86)                         │       │
│   │     "HAS_CEL" → "HAS_CELL" (similarity = 0.88)                 │       │
│   │     "row_idx" → "row_index" (similarity = 0.73)                │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 4: String Value Verification                                          │
│   ─────────────────────────────────                                          │
│   Check that string values in CONTAINS clauses actually exist in data:      │
│   - Search both Cell AND Line nodes                                         │
│   - If not found, try partial match and suggest correction                  │
│                                                                              │
│   OUTPUT:                                                                    │
│   ───────                                                                    │
│   - Verified (or corrected) Cypher query                                    │
│   - List of corrections made                                                │
│   - nev_verified: true/false                                                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### Agent 4: Validator

**Purpose:** Execute query, validate results, trigger self-correction if needed

**Model:** Claude Haiku (for feedback generation)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AGENT 4: VALIDATOR                                                         │
│   ══════════════════                                                         │
│                                                                              │
│   STEP 1: Execute Cypher Query                                               │
│   ────────────────────────────                                               │
│   Run verified Cypher against Neo4j, capture results                        │
│                                                                              │
│   STEP 2: PROFILE Analysis (Performance Check)                               │
│   ────────────────────────────────────────────                               │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    PROFILE ANALYSIS                              │       │
│   │                                                                  │       │
│   │   Run: PROFILE {cypher_query}                                   │       │
│   │                                                                  │       │
│   │   Extract from profile:                                         │       │
│   │   - db_hits: Total database operations                          │       │
│   │   - has_label_scan: NodeByLabelScan detected?                  │       │
│   │   - has_all_nodes_scan: AllNodesScan detected?                 │       │
│   │   - operators: List of execution plan operators                │       │
│   │                                                                  │       │
│   │   Generate feedback:                                            │       │
│   │   - IF AllNodesScan: "Add process_id anchor!"                  │       │
│   │   - IF db_hits > 10,000 with LabelScan: "Add index hints"      │       │
│   │   - IF db_hits > 50,000: "Add early filters"                   │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 3: NULL Pattern Analysis                                              │
│   ─────────────────────────────                                              │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    NULL PATTERN DETECTION                        │       │
│   │                                                                  │       │
│   │   For each column in results:                                   │       │
│   │     Count NULL values vs non-NULL values                        │       │
│   │                                                                  │       │
│   │   Patterns detected:                                            │       │
│   │                                                                  │       │
│   │   all_null = True:                                              │       │
│   │     "Query structure OK but data extraction failed"             │       │
│   │     → Check OPTIONAL MATCH conditions                           │       │
│   │     → Check col_index alignment                                 │       │
│   │                                                                  │       │
│   │   mostly_null = True:                                           │       │
│   │     "Partial success - some columns working"                    │       │
│   │     → Fix specific column mappings                              │       │
│   │                                                                  │       │
│   │   some_null = True:                                             │       │
│   │     "Specific columns need attention"                           │       │
│   │     → May need cross-table lookup                               │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 3.5: Row Count Validation (Filter-Aware)                             │
│   ─────────────────────────────────────────────                              │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    ROW COUNT VALIDATION                          │       │
│   │                                                                  │       │
│   │   Detect multi-page keywords in query:                          │       │
│   │     "each page", "every page", "all pages", "per page",        │       │
│   │     "for each page", "across pages", "from all pages"          │       │
│   │                                                                  │       │
│   │   Detect filtering patterns:                                    │       │
│   │     nth_row: "first", "second", "third", "2nd", "3rd"          │       │
│   │     conditional: "only", "where", "if", "when", "having"       │       │
│   │     exclusion: "not", "except", "exclude", "without"           │       │
│   │                                                                  │       │
│   │   Validation Logic:                                              │       │
│   │   ─────────────────                                              │       │
│   │   IF result_count == 1 AND expects_multiple:                    │       │
│   │     → SUSPICIOUS! Likely LIMIT 1 bug                            │       │
│   │     → "Query should return one row PER PAGE, not one total"    │       │
│   │                                                                  │       │
│   │   IF result_count > 1 AND result_count < page_count:           │       │
│   │     AND has_filtering:                                          │       │
│   │     → VALID! Filtering reduced results                          │       │
│   │     → Log: "9/104 pages - VALID (nth-row selection)"           │       │
│   │                                                                  │       │
│   │   Example:                                                       │       │
│   │   Query: "Get second Count row for each page"                  │       │
│   │   Pages: 104, Results: 9                                        │       │
│   │   → VALID: Only 9 pages have 2+ Count rows                     │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 4: Validation Decision                                                │
│   ───────────────────────────                                                │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                                                                  │       │
│   │   IF all checks pass:                                           │       │
│   │     → is_valid = True                                           │       │
│   │     → IF iteration == 1: Write to Success Bank                 │       │
│   │     → Return results to user                                    │       │
│   │                                                                  │       │
│   │   IF checks fail AND iteration < max_iterations:               │       │
│   │     → is_valid = False                                          │       │
│   │     → Generate specific feedback                                │       │
│   │     → RETRY from Agent 2 (Planner)                             │       │
│   │                                                                  │       │
│   │   IF checks fail AND iteration >= max_iterations:              │       │
│   │     → Return failure with diagnostics                           │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
│   STEP 5: Success Bank Auto-Write                                            │
│   ───────────────────────────────                                            │
│   ┌─────────────────────────────────────────────────────────────────┐       │
│   │                    SUCCESS BANK WRITE                            │       │
│   │                                                                  │       │
│   │   Triggered: Only on first-try success (iteration == 1)        │       │
│   │                                                                  │       │
│   │   Extracts from state:                                          │       │
│   │   - user_query: Original natural language                      │       │
│   │   - cypher_query: Generated Cypher that worked                 │       │
│   │   - logical_plan: Step-by-step reasoning                       │       │
│   │   - node_types_used: [Document, Page, Table, Cell, ...]       │       │
│   │   - relationship_path: HAS_PAGE->CONTAINS_TABLE->HAS_CELL     │       │
│   │   - structural_signature: JSON of probe results                │       │
│   │   - accuracy_score: 1.0 (successful)                           │       │
│   │   - result_count: Number of rows                               │       │
│   │                                                                  │       │
│   │   Generates embedding for user_query                           │       │
│   │   POSTs to Weaviate CypherSuccessBank collection               │       │
│   │                                                                  │       │
│   │   Future similar queries will retrieve this as example!        │       │
│   │                                                                  │       │
│   └─────────────────────────────────────────────────────────────────┘       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Algorithms & Techniques

### 6.1 Hybrid Search Algorithm

```
┌─────────────────────────────────────────────────────────────────┐
│                    HYBRID SEARCH                                 │
│                                                                  │
│   final_score = α × semantic_score + (1-α) × bm25_score        │
│   where α = 0.7 (70% semantic, 30% keyword)                    │
│                                                                  │
│   SEMANTIC SCORE (Vector Similarity):                           │
│   ───────────────────────────────────                           │
│   semantic_score = cosine_similarity(query_vec, chunk_vec)      │
│                                                                  │
│   cosine_similarity(A, B) = (A · B) / (||A|| × ||B||)          │
│                                                                  │
│   where:                                                         │
│   - query_vec = embed(user_query)  [3072 dimensions]           │
│   - chunk_vec = stored embedding   [3072 dimensions]           │
│                                                                  │
│   BM25 SCORE (Keyword Matching):                                │
│   ──────────────────────────────                                │
│   bm25_score = Σ IDF(qi) × (f(qi,D) × (k1+1)) /                │
│                (f(qi,D) + k1 × (1 - b + b × |D|/avgdl))        │
│                                                                  │
│   where:                                                         │
│   - qi = query term i                                           │
│   - f(qi,D) = frequency of qi in document D                    │
│   - |D| = document length                                       │
│   - avgdl = average document length                             │
│   - k1 = 1.2 (term frequency saturation)                       │
│   - b = 0.75 (length normalization)                            │
│   - IDF = log((N - n(qi) + 0.5) / (n(qi) + 0.5))              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Structural Probe Algorithm

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRUCTURAL PROBE                              │
│                                                                  │
│   Purpose: Discover WHERE data exists BEFORE query generation   │
│                                                                  │
│   Algorithm:                                                     │
│   ──────────                                                     │
│   FOR each search_term in user_query:                           │
│       IF len(term) < 2: SKIP                                    │
│                                                                  │
│       # Check Cell nodes                                         │
│       cell_count = neo4j.run("""                                │
│           MATCH (d:Document {process_id: $pid})                 │
│             -[:HAS_PAGE]->(p)                                   │
│             -[:CONTAINS_TABLE]->(t)                             │
│             -[:HAS_CELL]->(c)                                   │
│           WHERE toLower(c.text) CONTAINS $term                  │
│           RETURN count(c), collect(DISTINCT p.page_num)[0..3]   │
│       """)                                                       │
│                                                                  │
│       # Check Line nodes                                         │
│       line_count = neo4j.run("""                                │
│           MATCH (d:Document {process_id: $pid})                 │
│             -[:HAS_PAGE]->(p)                                   │
│             -[:CONTAINS_LINE]->(l)                              │
│           WHERE toLower(l.text) CONTAINS $term                  │
│           RETURN count(l), collect(DISTINCT p.page_num)[0..3]   │
│       """)                                                       │
│                                                                  │
│       found_in[term] = {                                        │
│           "Cell": {"count": cell_count, "pages": [...]},       │
│           "Line": {"count": line_count, "pages": [...]}        │
│       }                                                          │
│                                                                  │
│   # Determine recommended paths                                  │
│   IF only Cell matches: recommend "Page->Table->Cell"          │
│   IF only Line matches: recommend "Page->Line"                  │
│   IF both match: recommend "Page as join point"                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Hard Constraints Extraction

```
┌─────────────────────────────────────────────────────────────────┐
│                    HARD CONSTRAINTS                              │
│                                                                  │
│   Purpose: Convert probe results into MANDATORY rules           │
│                                                                  │
│   Algorithm:                                                     │
│   ──────────                                                     │
│   line_count = sum(probe matches in Line nodes)                 │
│   cell_count = sum(probe matches in Cell nodes)                 │
│   section_count = sum(probe matches in Section nodes)           │
│                                                                  │
│   # Detect query type for smart decisions                       │
│   is_simple_lookup = regex_match(query, simple_patterns)        │
│   is_extraction = regex_match(query, extraction_patterns)       │
│                                                                  │
│   # Decision logic                                               │
│   IF line_count > 0 AND cell_count == 0:                       │
│       primary_node = "Line"                                     │
│       forbidden = ["Cell", "Table", "MergedCell"]              │
│       required_path = "Document->Page->Line"                    │
│                                                                  │
│   ELIF cell_count > 0 AND line_count == 0:                     │
│       primary_node = "Cell"                                     │
│       forbidden = ["Line"]                                      │
│       required_path = "Document->Page->Table->Cell"             │
│                                                                  │
│   ELIF cell_count > 0 AND line_count > 0:                      │
│       IF is_simple_lookup AND cell_count >= 1:                 │
│           # Avoid complex UNION for simple queries              │
│           primary_node = "Cell"                                 │
│           forbidden = []                                        │
│       ELSE:                                                      │
│           primary_node = "BOTH"                                 │
│           required_path = "Use Page as join point"             │
│                                                                  │
│   ELIF section_count > 0:                                       │
│       primary_node = "Section"                                  │
│       forbidden = ["Cell", "Table", "Line"]                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.4 Levenshtein Similarity (Auto-Correction)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LEVENSHTEIN SIMILARITY                        │
│                                                                  │
│   Used by: NEV Auditor for entity auto-correction               │
│                                                                  │
│   Implementation:                                                │
│   ───────────────                                                │
│   from difflib import SequenceMatcher                           │
│                                                                  │
│   def levenshtein_similarity(s1: str, s2: str) -> float:       │
│       """Calculate normalized similarity (0 to 1)"""           │
│       return SequenceMatcher(                                   │
│           None,                                                  │
│           s1.lower(),                                           │
│           s2.lower()                                            │
│       ).ratio()                                                  │
│                                                                  │
│   def find_closest_match(target, candidates, threshold=0.6):    │
│       """Find best match above threshold"""                     │
│       best_match = None                                         │
│       best_score = threshold                                    │
│                                                                  │
│       for candidate in candidates:                              │
│           score = levenshtein_similarity(target, candidate)     │
│           if score > best_score:                                │
│               best_score = score                                │
│               best_match = candidate                            │
│                                                                  │
│       return best_match                                         │
│                                                                  │
│   Examples:                                                      │
│   ─────────                                                      │
│   "Cel" vs "Cell"           → 0.857 → CORRECT to "Cell"        │
│   "row_idx" vs "row_index"  → 0.727 → CORRECT to "row_index"   │
│   "HAS_CEL" vs "HAS_CELL"   → 0.875 → CORRECT to "HAS_CELL"    │
│   "xyz" vs "Cell"           → 0.286 → NO MATCH (below 0.6)     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.5 Filter-Aware Row Count Validation

```
┌─────────────────────────────────────────────────────────────────┐
│                    FILTER-AWARE VALIDATION                       │
│                                                                  │
│   Purpose: Understand when fewer rows than pages is OK          │
│                                                                  │
│   Algorithm:                                                     │
│   ──────────                                                     │
│   # Detect multi-page expectation                               │
│   multi_page_keywords = [                                       │
│       "each page", "every page", "all pages",                  │
│       "per page", "for each page", "across pages"              │
│   ]                                                              │
│   expects_multiple = any(kw in query.lower()                   │
│                          for kw in multi_page_keywords)         │
│                                                                  │
│   IF NOT expects_multiple:                                      │
│       RETURN {is_suspicious: False}                             │
│                                                                  │
│   # Get page count                                               │
│   page_count = neo4j.run("MATCH (d)-[:HAS_PAGE]->(p)           │
│                          RETURN count(p)")                       │
│                                                                  │
│   # Detect filtering patterns                                    │
│   filtering_patterns = {                                        │
│       "nth_row": regex(r'first|second|third|\d+(st|nd|rd|th)'),│
│       "conditional": regex(r'only|where|if|when|having'),      │
│       "exclusion": regex(r'not|except|exclude|without')        │
│   }                                                              │
│   has_filtering = any(pattern.match(query)                     │
│                       for pattern in filtering_patterns)        │
│                                                                  │
│   # Validation logic                                             │
│   IF result_count == 1:                                         │
│       is_suspicious = True                                      │
│       feedback = "LIMIT 1 bug detected!"                        │
│                                                                  │
│   ELIF result_count < page_count AND has_filtering:            │
│       is_suspicious = False                                     │
│       feedback = f"VALID: {result_count}/{page_count} pages.   │
│                   Filtering detected: {filter_explanation}"     │
│                                                                  │
│   ELSE:                                                          │
│       is_suspicious = False                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.6 Success Bank Vector Retrieval

```
┌─────────────────────────────────────────────────────────────────┐
│                    SUCCESS BANK RETRIEVAL                        │
│                                                                  │
│   Purpose: Find similar successful queries for few-shot learning │
│                                                                  │
│   Algorithm:                                                     │
│   ──────────                                                     │
│   # 1. Generate query embedding                                  │
│   query_embedding = embed(user_query)  # 3072 dimensions        │
│                                                                  │
│   # 2. Determine node type filter from probe                    │
│   IF probe shows Line-only: node_filter = "Line"               │
│   ELIF probe shows Cell-only: node_filter = "Cell"             │
│   ELSE: node_filter = None                                      │
│                                                                  │
│   # 3. Query Weaviate with vector similarity                    │
│   results = weaviate.query("""                                  │
│       Get {                                                      │
│           CypherSuccessBank(                                    │
│               nearVector: {vector: $query_embedding}            │
│               where: {accuracy_score > 0.7}                     │
│               limit: 6                                          │
│           ) {                                                    │
│               user_query                                        │
│               cypher_query                                      │
│               logical_plan                                      │
│               node_types_used                                   │
│               _additional { distance }                          │
│           }                                                      │
│       }                                                          │
│   """)                                                           │
│                                                                  │
│   # 4. Structural compatibility filter                          │
│   IF node_filter:                                               │
│       results = [r for r in results                            │
│                  if node_filter in r.node_types_used]          │
│                                                                  │
│   # 5. Return top 2-3 examples                                  │
│   RETURN results[:3]                                            │
│                                                                  │
│   # 6. Fallback to hardcoded examples if bank empty            │
│   IF len(results) == 0:                                        │
│       RETURN keyword_match(FEW_SHOT_EXAMPLES, query)           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Complete System Flow Diagram

```
╔══════════════════════════════════════════════════════════════════════════════════════════════════╗
║                                                                                                  ║
║                           MULTI-AGENT GRAPHRAG SYSTEM - COMPLETE FLOW                            ║
║                                                                                                  ║
╠══════════════════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                                  ║
║   ┌─────────────────────────────────────── INGESTION PHASE ───────────────────────────────────┐ ║
║   │                                                                                           │ ║
║   │   [PDF Upload] ──► [AWS Textract] ──► [blocks.json]                                      │ ║
║   │                                              │                                            │ ║
║   │                          ┌───────────────────┴───────────────────┐                       │ ║
║   │                          ▼                                       ▼                       │ ║
║   │                  ┌───────────────┐                       ┌───────────────┐              │ ║
║   │                  │   NEO4J       │                       │   WEAVIATE    │              │ ║
║   │                  │   ═══════     │                       │   ════════    │              │ ║
║   │                  │               │                       │               │              │ ║
║   │                  │  Document     │                       │ DocumentChunk │              │ ║
║   │                  │     │         │                       │  - content    │              │ ║
║   │                  │     ▼         │                       │  - embedding  │              │ ║
║   │                  │   Page        │                       │  - grounding  │              │ ║
║   │                  │   / \         │                       │               │              │ ║
║   │                  │  ▼   ▼        │                       │ CypherSuccess │              │ ║
║   │                  │ Table Line    │                       │    Bank       │              │ ║
║   │                  │  │            │                       │  - query      │              │ ║
║   │                  │  ▼            │                       │  - cypher     │              │ ║
║   │                  │ Cell          │                       │  - embedding  │              │ ║
║   │                  └───────────────┘                       └───────────────┘              │ ║
║   │                                                                                          │ ║
║   └──────────────────────────────────────────────────────────────────────────────────────────┘ ║
║                                                                                                  ║
║   ┌─────────────────────────────────────── QUERY PHASE ───────────────────────────────────────┐ ║
║   │                                                                                           │ ║
║   │   USER: "Get second Count row with Project Name for each page"                           │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ╔═══════════════════════════════════════════════════════════════════════════════════╗  │ ║
║   │   ║  AGENT 1: CONTEXT GATHERER                                                        ║  │ ║
║   │   ║  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                   ║  │ ║
║   │   ║  │ Weaviate Search │  │ Structural      │  │ Success Bank    │                   ║  │ ║
║   │   ║  │ (Hybrid 70/30)  │  │ Probe (Neo4j)   │  │ Few-Shot        │                   ║  │ ║
║   │   ║  │                 │  │                 │  │                 │                   ║  │ ║
║   │   ║  │ → chunks        │  │ → Cell: 384    │  │ → similar       │                   ║  │ ║
║   │   ║  │ → headers       │  │ → Line: 505    │  │   examples      │                   ║  │ ║
║   │   ║  └─────────────────┘  └─────────────────┘  └─────────────────┘                   ║  │ ║
║   │   ╚═══════════════════════════════════════════════════════════════════════════════════╝  │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ╔═══════════════════════════════════════════════════════════════════════════════════╗  │ ║
║   │   ║  AGENT 2: LOGIC PLANNER (Claude Haiku)                                            ║  │ ║
║   │   ║  ┌─────────────────────────────────────────────────────────────────────────────┐ ║  │ ║
║   │   ║  │  +===========================================================+              │ ║  │ ║
║   │   ║  │  |  MANDATORY CONSTRAINTS (VIOLATION = 0 ROWS)               |              │ ║  │ ║
║   │   ║  │  |  PRIMARY: BOTH | FORBIDDEN: None | PATH: Page as join    |              │ ║  │ ║
║   │   ║  │  +===========================================================+              │ ║  │ ║
║   │   ║  │                                                                             │ ║  │ ║
║   │   ║  │  OUTPUT: Step-by-step logical plan (NO Cypher code)                        │ ║  │ ║
║   │   ║  └─────────────────────────────────────────────────────────────────────────────┘ ║  │ ║
║   │   ╚═══════════════════════════════════════════════════════════════════════════════════╝  │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ╔═══════════════════════════════════════════════════════════════════════════════════╗  │ ║
║   │   ║  AGENT 3: CYPHER GENERATOR (Claude Sonnet)                                        ║  │ ║
║   │   ║  ┌─────────────────────────────────────────────────────────────────────────────┐ ║  │ ║
║   │   ║  │  Dynamic Rules based on Structural Probe:                                   │ ║  │ ║
║   │   ║  │  IF Line-only → use CONTAINS_LINE path                                      │ ║  │ ║
║   │   ║  │  IF Cell-only → use CONTAINS_TABLE→HAS_CELL path                           │ ║  │ ║
║   │   ║  │  IF BOTH → use Page as join point                                           │ ║  │ ║
║   │   ║  │                                                                             │ ║  │ ║
║   │   ║  │  OUTPUT: Executable Cypher query                                            │ ║  │ ║
║   │   ║  └─────────────────────────────────────────────────────────────────────────────┘ ║  │ ║
║   │   ╚═══════════════════════════════════════════════════════════════════════════════════╝  │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ╔═══════════════════════════════════════════════════════════════════════════════════╗  │ ║
║   │   ║  AGENT 3.5: NEV AUDITOR                                                           ║  │ ║
║   │   ║  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                   ║  │ ║
║   │   ║  │ Topology Check  │  │ Entity Verify   │  │ Auto-Correct    │                   ║  │ ║
║   │   ║  │                 │  │                 │  │                 │                   ║  │ ║
║   │   ║  │ ✓ Valid paths   │  │ ✓ Labels exist  │  │ Levenshtein     │                   ║  │ ║
║   │   ║  │ ✗ Invalid paths │  │ ✓ Rels exist    │  │ similarity      │                   ║  │ ║
║   │   ║  │ ✗ Probe mismatch│  │ ✓ Props exist   │  │ > 0.6 → fix     │                   ║  │ ║
║   │   ║  └─────────────────┘  └─────────────────┘  └─────────────────┘                   ║  │ ║
║   │   ╚═══════════════════════════════════════════════════════════════════════════════════╝  │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ╔═══════════════════════════════════════════════════════════════════════════════════╗  │ ║
║   │   ║  AGENT 4: VALIDATOR                                                               ║  │ ║
║   │   ║  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                   ║  │ ║
║   │   ║  │ Execute Query   │  │ PROFILE Analysis│  │ Row Count Check │                   ║  │ ║
║   │   ║  │                 │  │                 │  │                 │                   ║  │ ║
║   │   ║  │ → Run on Neo4j  │  │ → DB Hits       │  │ → Filter-aware  │                   ║  │ ║
║   │   ║  │ → Get results   │  │ → Label Scans   │  │ → nth-row OK    │                   ║  │ ║
║   │   ║  │ → Check NULLs   │  │ → Performance   │  │ → LIMIT 1 bug   │                   ║  │ ║
║   │   ║  └─────────────────┘  └─────────────────┘  └─────────────────┘                   ║  │ ║
║   │   ║                                                                                   ║  │ ║
║   │   ║                    ┌────────────────────────────────┐                            ║  │ ║
║   │   ║                    │         VALID?                 │                            ║  │ ║
║   │   ║                    └────────────────────────────────┘                            ║  │ ║
║   │   ║                           │              │                                        ║  │ ║
║   │   ║                    YES ◄──┘              └──► NO                                  ║  │ ║
║   │   ║                     │                         │                                   ║  │ ║
║   │   ║                     ▼                         ▼                                   ║  │ ║
║   │   ║            ┌───────────────┐         ┌───────────────┐                           ║  │ ║
║   │   ║            │ Save to       │         │ Generate      │                           ║  │ ║
║   │   ║            │ Success Bank  │         │ Feedback      │──────► RETRY              ║  │ ║
║   │   ║            │ (if iter==1)  │         │ (if iter<max) │       (Agent 2)           ║  │ ║
║   │   ║            └───────────────┘         └───────────────┘                           ║  │ ║
║   │   ╚═══════════════════════════════════════════════════════════════════════════════════╝  │ ║
║   │                                           │                                               │ ║
║   │                                           ▼                                               │ ║
║   │   ┌───────────────────────────────────────────────────────────────────────────────────┐  │ ║
║   │   │                              FINAL RESULTS                                        │  │ ║
║   │   │  ┌─────────────────────────────────────────────────────────────────────────────┐ │  │ ║
║   │   │  │  page_num │ project_name                  │ count_values                    │ │  │ ║
║   │   │  │  ─────────┼───────────────────────────────┼─────────────────────────────────│ │  │ ║
║   │   │  │  1        │ ABBV1451_S01996_3M_p5-Run001  │ [Count, 3417, 782, 142, ...]   │ │  │ ║
║   │   │  │  12       │ ABBV1451_S01996_3M_p5-Run002  │ [Count, 3669, 831, 154, ...]   │ │  │ ║
║   │   │  │  ...      │ ...                           │ ...                             │ │  │ ║
║   │   │  └─────────────────────────────────────────────────────────────────────────────┘ │  │ ║
║   │   │                                                                                   │  │ ║
║   │   │  Success: TRUE | Iterations: 1 | Rows: 9                                         │  │ ║
║   │   └───────────────────────────────────────────────────────────────────────────────────┘  │ ║
║   │                                                                                           │ ║
║   └──────────────────────────────────────────────────────────────────────────────────────────┘ ║
║                                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════════════════════╝
```

---

## 8. Performance Metrics

### Test Results Summary

| Category | Tests | Passed | Success Rate |
|----------|-------|--------|--------------|
| **Easy** | 6 | 6 | **100%** |
| **Hard** | 4 | 4 | **100%** |
| **Total** | **10** | **10** | **100%** |

### Easy Query Results

| # | Query | Result | Iterations | Duration |
|---|-------|--------|------------|----------|
| 1 | What is the Batch Name? | PASS | 1 | 28.2s |
| 2 | What is the Project Name? | PASS | 1 | 26.8s |
| 3 | What is the Mean ECD value? | PASS | 1 | 31.6s |
| 4 | What is the Particle Count? | PASS | 1 | 29.8s |
| 15 | What is the document title? | PASS | 1 | 24.9s |
| 16 | Who is the User that created this analysis? | PASS | 1 | 25.9s |

### Hard Query Results

| # | Query | Result | Rows | Iterations | Duration |
|---|-------|--------|------|------------|----------|
| 8 | Get the second Count row values only | PASS | 1 | 1 | 33.9s |
| 12 | Get Project Name and Count values from all pages | PASS | 18 | 1 | 33.3s |
| 14 | Get second Count row with Project Name for each page | PASS | 9 | 1 | 32.0s |
| 18 | Get Batch Name and all Count values from the table | PASS | 1 | 1 | 31.7s |

### Key Metrics

| Metric | Value |
|--------|-------|
| First-Try Success Rate | 100% |
| Average Query Time | ~30 seconds |
| Average Iterations | 1.0 |
| NEV Corrections Needed | 0 |

### External AI Ratings

| AI System | Rating | Assessment |
|-----------|--------|------------|
| Kimi AI | 9.9/10 | "Outstanding architecture" |
| Google AI (Gemini) | "Research-grade" | "Suitable for academic publication" |

---

## 9. Configuration Reference

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WEAVIATE_URL` | `http://10.242.190.53:8080` | Weaviate server |
| `ILIAD_URL` | `https://api-epic.ir-gateway.abbvienet.com/iliad` | LLM API gateway |
| `ILIAD_API_KEY` | (required) | API authentication |

### Neo4j Configuration

```python
NEO4J_URI = "bolt://10.242.190.53:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = REDACTED
```

### Model Configuration

```python
MODELS = {
    "planner": "claude-haiku-4-5-20251001",     # Fast for planning
    "generator": "claude-sonnet-4-5-20250929",  # Best for code generation
    "validator": "claude-haiku-4-5-20251001",   # Fast for validation
}
```

### Pipeline Configuration

```python
MAX_ITERATIONS = 3              # Maximum retry attempts
SIMILARITY_THRESHOLD = 0.6      # Levenshtein auto-correct threshold
HYBRID_ALPHA = 0.7              # 70% semantic, 30% BM25
EMBEDDING_DIMENSIONS = 3072     # text-embedding-3-large
SUCCESS_BANK_MIN_SCORE = 0.7    # Minimum accuracy for retrieval
```

---

## Appendix A: Comparison with Traditional RAG

| Feature | Traditional RAG | Multi-Agent GraphRAG |
|---------|-----------------|----------------------|
| **Search** | Vector only | Hybrid (70% semantic + 30% BM25) |
| **Data Source** | Single DB | Dual DB (Weaviate + Neo4j) |
| **Query Generation** | Direct prompt | Multi-agent with planning |
| **Examples** | Static few-shot | Dynamic Success Bank |
| **Validation** | None | Topology + Entity + NULL + Row Count |
| **Self-Correction** | None | Retry with feedback loop |
| **Learning** | None | Auto-save successful queries |
| **Constraints** | Soft hints | Hard mandatory rules |
| **Entity Checking** | None | Levenshtein auto-correction |
| **Performance Analysis** | None | PROFILE-based feedback |

---

## Appendix B: Files Reference

| File | Purpose |
|------|---------|
| `backend/test_multiagent_cypher.py` | Main pipeline implementation (2900+ lines) |
| `backend/run_test_queries.py` | Test harness for validation |
| `backend/scripts/create_success_bank.py` | Weaviate collection setup |
| `backend/docs/NEV_TOPOLOGY_IMPLEMENTATION.md` | Implementation planning doc |
| `backend/docs/MULTIAGENT_GRAPHRAG_ARCHITECTURE.md` | This document |

---

**Document maintained by:** Claude Code
**Last updated:** February 12, 2026
**Status:** Production Ready
