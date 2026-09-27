# Implementation Phases - OCR RAG System

> **Purpose:** Master document tracking all implementation phases with references
> **For Agents:** Use this file first to understand system status and next steps
> **Created:** February 4, 2026
> **Last Updated:** February 10, 2026

---

## Quick Status Overview

| Phase | Name | Status | Schema/Plan Files |
|-------|------|--------|-------------------|
| **Phase 1** | Database Schema Creation | ✅ DONE | `dbschemas/` folder |
| **Phase 2** | Chat History & Persistence | ✅ DONE | `CHAT_HISTORY_*.md` |
| **Phase 3** | Textract Chunking Pipeline | ✅ DONE | `COMPLETE_CHUNKING_STRATEGY.md`, `TRANSFORMATION_*.md` |
| **Phase 4** | Multi-Agent RAG Orchestration | ✅ DONE | `RAG_QUERY_*.md`, `PHASE4_MULTIAGENT_ORCHESTRATION.md` |
| **Phase 5** | PDF Viewer & Highlighting | 🔲 NEXT | `PDF_VIEWER_*.md`, `BBOX_HIGHLIGHT_*.md` |
| **Phase 6** | Neo4j Structural Integration | 🔲 PENDING | `NEO4J_*.md` |

---

## Phase 1: Database Schema Creation ✅ COMPLETED

### What Was Done
All three database schemas created and deployed on production servers.

### Schema Documentation (Reference Files)

```
frontend/feature_implementation/dbschemas/
├── PHASE1_POSTGRESQL_SCHEMA.md   ← 5 tables, 2 triggers, indexes
├── PHASE2_WEAVIATE_SCHEMA.md     ← DocumentChunk collection (22 properties)
└── PHASE3_NEO4J_SCHEMA.md        ← 10 constraints, 12 indexes, node types
```

### Connection Details

| Database | Host | Details |
|----------|------|---------|
| **PostgreSQL** | `intelligentparsing-ngxp-dev.cimrdaj1f7u6.us-east-1.rds.amazonaws.com` | DB: `ocr_rag_system`, Schema: `rag` |
| **Weaviate** | `http://10.242.190.53:8080` | Collection: `DocumentChunk` |
| **Neo4j** | `bolt://10.242.190.53:7687` | User: `neo4j`, Pass: `ocr@4567` |

### Tables/Collections Created

**PostgreSQL (5 tables):**
- `rag.users` - User accounts
- `rag.chats` - Chat sessions with `summary`, `message_count`, `active_document_id`
- `rag.chat_documents` - Documents per chat with `upload_order`, `extraction_prompt`
- `rag.messages` - Messages with `sequence_num`, `references`, `is_summarized`
- `rag.pdf_page_cache` - Cached PDF page images

**Weaviate (22 properties):**
- Identification: `document_id`, `process_id`, `chunk_id`, `page`, `chunk_index`
- Types: `chunk_type` (text/table), `layout_type` (SECTION_HEADER, TEXT, etc.)
- Search: `content` (BM25), embedding vector (1536-dim)
- Bbox: `bbox_left`, `bbox_top`, `bbox_right`, `bbox_bottom`
- Grounding: `cell_grounding` (JSON), `line_grounding` (JSON), `markdown`
- Metadata: `filename`, `document_type`, `document_summary`, `keywords`

**Neo4j (10 node types):**
- Document, Page, Section, Table, Cell, Line, Word, KV, MergedCell, Selection
- Relationships: HAS_PAGE, HAS_CELL, SAME_ROW, SAME_COL, etc.

### Additional Config Files
- `WEAVIATE_NEO4J_CONFIG.md` - EC2 setup, Docker commands, Python/Node integration

---

## Phase 2: Chat History & Persistence ✅ COMPLETED

> **Completed:** February 5, 2026

### What Was Implemented

All chat history features are now fully functional:

### Backend (Python/FastAPI)

| Feature | File | Status |
|---------|------|--------|
| Chat CRUD endpoints | `backend/services/chat_routes.py` | ✅ Done |
| Message endpoints with FOR UPDATE locking | `backend/services/database.py` | ✅ Done |
| Summarization (triggers at 31, 61, 91 messages) | `backend/services/summarization.py` | ✅ Done |
| Document upload tracking | `backend/services/chat_routes.py` | ✅ Done |
| Auto-generate chat title (first meaningful message) | `backend/services/summarization.py` | ✅ Done |

### Frontend (Next.js/TypeScript)

| Feature | File | Status |
|---------|------|--------|
| Chat sidebar with time grouping (Today/Yesterday/etc) | `frontend/src/components/ChatSidebar.tsx` | ✅ Done |
| New Chat button (fresh page, creates on first message) | `ChatSidebar.tsx` + `page.tsx` | ✅ Done |
| Click to switch chats | `page.tsx` | ✅ Done |
| Chat history on page load | `page.tsx` | ✅ Done |
| Message persistence (user + assistant) | `page.tsx` | ✅ Done |
| Rename chat | `ChatSidebar.tsx` | ✅ Done |
| Delete chat with confirmation | `ChatSidebar.tsx` | ✅ Done |
| Archive/Unarchive chat | `ChatSidebar.tsx` | ✅ Done |
| Search chats | `ChatSidebar.tsx` | ✅ Done |
| Reload same chat (localStorage) | `page.tsx` | ✅ Done |
| Real-time title update after generation | `page.tsx` + `ChatSidebar.tsx` | ✅ Done |

### Key Implementation Details

- **Race condition prevention**: Uses `FOR UPDATE` lock on chat row
- **Summarization strategy**: Every 30 messages (at 31, 61, 91...)
- **Title generation**: First meaningful message (skips greetings)
- **Fresh page on load**: Like ChatGPT/Claude behavior
- **Archive section**: Collapsible at bottom of sidebar

---

## Phase 3: Textract Chunking Pipeline ✅ COMPLETED

> **Started:** February 5, 2026
> **Completed:** February 5, 2026

### Why This Phase
- Current code uses RecursiveCharacterTextSplitter (loses structure)
- Need cell_grounding and line_grounding for highlighting
- Must preserve TABLE structure and LAYOUT semantic regions

### Plan Files to Reference

| File | Purpose | Key Sections |
|------|---------|--------------|
| **`COMPLETE_CHUNKING_STRATEGY.md`** | Main chunking guide | TABLE vs TEXT chunks, replaces RecursiveCharacterTextSplitter |
| **`TRANSFORMATION_OF_CELL_GROUNDING.md`** | TABLE block transformation | Cell ID generation, cell_grounding map |
| **`TRANSFORMATION_OF_LINE_BLOCKS.md`** | LAYOUT block transformation | line_grounding map, semantic regions |
| **`COMPLETE_RAG_FLOW_WITH_BBOX.md`** | Bbox storage overview | How bbox is metadata, not searched |

### Implementation Progress

| Step | Task | Status |
|------|------|--------|
| 1 | Enable LAYOUT feature in Textract call | ✅ Done |
| 2 | Create `backend/services/textract_parser.py` | ✅ Done |
| 3 | Create `backend/services/chunk_transformer.py` | ✅ Done |
| 4 | Create `backend/services/weaviate_indexer.py` | ✅ Done |
| 5 | Create RAG-only endpoint `POST /upload-rag-doc` | ✅ Done |
| 6 | Add frontend `uploadRAGDocument()` function | ✅ Done |
| 7 | Test with sample COA document | ✅ Done |
| 8 | Test full pipeline with LAYOUT blocks | ✅ Done |
| 9 | Verify hybrid search works | ✅ Done |

### Files Created

**Backend:**
- `backend/services/textract_parser.py` - Parses TABLE and LAYOUT blocks with relationships
- `backend/services/chunk_transformer.py` - Builds chunks with cell_grounding/line_grounding
- `backend/services/weaviate_indexer.py` - Indexes chunks to Weaviate with embeddings

**Modified:**
- `backend/textractservices/textract_single.py:728` - Added LAYOUT to FeatureTypes
- `backend/app.py` - Restructured endpoints (see below)

**Frontend:**
- `frontend/src/services/fileUtils.ts` - Added `uploadRAGDocument()` and `checkRAGDocumentStatus()`

### Endpoint Routing (Final)

| Endpoint | Flow | Use Case |
|----------|------|----------|
| **`/upload-coa`** | Textract → Parse → Chunk → Weaviate | **DEFAULT** - RAG chat only (fast ~40s) |
| **`/upload-coa-full`** | Textract → GPT → Validation → Excel → Weaviate | Full extraction with Excel report (~65s) |
| **`/upload-rag-doc`** | Same as `/upload-coa` | Alternative RAG-only endpoint |

**Log Prefixes:**
- `[COA-Simple]` / `[COA-RAG-Only]` → RAG-only flow
- `[COA-RAG-WEAVIATE]` → Weaviate indexing in full flow

### Key Features Implemented

1. **Layout-Aware Chunking**
   - TABLE blocks → table chunks with `cell_grounding`
   - LAYOUT blocks → text chunks with `line_grounding`
   - Preserves reading order by page + vertical position

2. **RAG-Only Upload Flow**
   - New endpoint: `POST /upload-rag-doc`
   - Textract → Parse → Chunk → Embed → Index
   - No GPT extraction (faster, for chat-only use)

3. **Weaviate Integration**
   - Schema creation/verification
   - Batch indexing with embeddings (3072 dimensions)
   - Hybrid search support (BM25 + semantic)

### Key Data Structures

```python
# Table chunk with cell_grounding
{
    "chunk_type": "table",
    "chunk_index": 5,
    "page": 2,
    "content": "TESTS | SPECIFICATIONS | METHOD | RESULTS\nAppearance | White to tan | Visual | Complies",
    "markdown": "<table id='2-t26'><td id='2-5'>Appearance</td>...<td id='2-8'>Complies</td></table>",
    "cell_grounding": {
        "2-5": {"bbox": {"left": 0.04, "top": 0.24, "width": 0.29, "height": 0.02}, "text": "Appearance", "row": 2, "col": 1},
        "2-8": {"bbox": {"left": 0.78, "top": 0.24, "width": 0.18, "height": 0.02}, "text": "Complies", "row": 2, "col": 4}
    }
}

# Text chunk with line_grounding
{
    "chunk_type": "text",
    "layout_type": "TEXT",
    "chunk_index": 3,
    "page": 1,
    "content": "Batch Number: 0001903354",
    "line_grounding": {
        "uuid-abc": {"bbox": {"left": 0.05, "top": 0.30, "width": 0.40, "height": 0.02}, "text": "Batch Number: 0001903354"}
    }
}
```

### How Cell ID Matching Works (For Phase 5 Highlighting)

```
MARKDOWN (Agent sees):                    CELL_GROUNDING (Bbox lookup):
─────────────────────────                 ─────────────────────────────
<td id='2-8'>Complies</td>       ───►     "2-8": {
                                            "bbox": {left, top, width, height},
                                            "text": "Complies",
                                            "row": 2, "col": 4
                                          }
```

Agent reads markdown → finds answer in `<td id='2-8'>` → responds with `[cell: 2-8]` → Frontend looks up bbox → Highlights on PDF

### Final Testing Summary (February 5, 2026)

**Full Pipeline Test:**
- Textract with LAYOUT: 41 LAYOUT blocks + 4 TABLE blocks extracted
- Parser: Successfully processed all block types
- Chunking: 43 chunks created (4 table + 39 text) with grounding
- Indexing: All 43 chunks indexed to Weaviate successfully
- Search: Hybrid search returns relevant results with grounding data

**Test Process ID:** `layout-full-test-c2d0b134`

**Fixes Applied:**
- Fixed f-string backslash issue in GraphQL query builder
- Fixed embedding API endpoint (changed from `/embeddings` to `/embed/{model}`)
- Updated embedding dimensions from 1536 to 3072 (actual for text-embedding-3-large)

---

## Phase 4: Multi-Agent RAG Orchestration ✅ COMPLETED

> **Started:** February 10, 2026
> **Completed:** February 11, 2026

### What Was Implemented

Complete Multi-Agent RAG Orchestration system with the following components:

### Backend Services Created (`backend/services/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `semantic_cache.py` | Query caching (95% similarity, 30 min TTL) | `get()`, `set()`, `invalidate()` |
| `intent_classifier.py` | Query classification (4 types) | `classify_intent_sync()` |
| `question_rephraser.py` | COA-specific query variations | `rephrase_question_sync()`, `detect_row_col_query()` |
| `answer_synthesizer.py` | Answer generation with [cell:X-Y] refs | `synthesize_answer_sync()` |
| `reference_extractor.py` | Bbox extraction from grounding | `extract_references()`, `build_response_with_references()` |
| `rag_orchestrator.py` | Main orchestration module | `process_query_sync()`, `get_rag_orchestrator()` |

### PostgreSQL Persistence (process_id)

Documents are now persisted to PostgreSQL `chat_documents` table with `process_id` for RAG queries to work after page refresh.

| File | Changes |
|------|---------|
| `backend/services/database.py` | Added `process_id`, `processing_status`, `extraction_done` to `add_document_to_chat()` |
| `backend/services/chat_routes.py` | Added fields to `AddDocumentRequest` model with defaults |
| `frontend/src/services/chatHistory.ts` | Added fields to `addDocumentToChat()` interface |
| `frontend/src/app/chat/page.tsx` | Save document on upload, restore on page load/chat switch |
| `frontend/src/services/fileUtils.ts` | Fixed duplicate `onProcessIdReceived` callback |

**Key Flow:**
1. COA uploaded → `process_id` saved to `chat_documents` table
2. Page reload → Fetch chat details → Restore active document from DB
3. Chat switch → Restore most recent document (highest `upload_order`)
4. RAG queries work because `process_id` is preserved

### New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chat/coa-rag-v2/{process_id}` | POST | **NEW** Multi-Agent RAG with Weaviate |
| `/api/rag/cache-stats` | GET | Get semantic cache statistics |
| `/api/rag/cache/{process_id}` | DELETE | Invalidate cache for a document |

### Query Flow (10 Steps)

```
User Query + process_id + recent_messages
    |
    v
1. [Context Resolver] --> Resolve pronouns (it, that)
    |
    v
2. [Semantic Cache] --hit--> Return Cached Response
    | miss
    v
3. [Intent Classifier] --> vector_only (90%) | structural (5%) | extraction (5%)
    |
    v
4. [Row/Col Detection] --> Check for "value at row X, col Y"
    |
    v
5. [Question Rephraser] --> Generate 3-5 COA-specific variations
    |
    v
6. [Parallel Weaviate Search] --> Execute all variations (alpha=0.7)
    |
    v
7. [Answer Synthesizer] --> Claude Sonnet generates answer with [cell:X-Y]
    |
    v
8. [Confidence Disclaimer] --> Add disclaimer if confidence < 0.7
    |
    v
9. [Reference Extractor] --> Lookup bbox from cell_grounding
    |
    v
10. [Cache Updater] --> Store query embedding + response
    |
    v
Response: { answer, references[], confidence, query_type }
```

### Key Design Decisions

1. **document_id = process_id**: Same UUID for PostgreSQL and Weaviate
2. **Backwards Compatible**: Legacy `/api/chat/coa-rag/{process_id}` preserved
3. **Intent-Based Routing**: 90% of queries are `vector_only` (simple Q&A)
4. **Neo4j Deferred**: Structural queries (5%) deferred to Phase 6

### Response Format

```json
{
    "success": true,
    "answer": "The batch number is 12345 [cell:2-5]",
    "references": [
        {
            "page": 1,
            "bbox": {"left": 0.45, "top": 0.32, "width": 0.15, "height": 0.03},
            "cell_id": "2-5",
            "text": "12345"
        }
    ],
    "confidence": 0.95,
    "query_type": "vector_only"
}
```

### Completion Record

See `frontend/feature_implementation/completed/PHASE4_COMPLETION.md` for full details

---

## Phase 5: PDF Viewer & Highlighting 🔲 NEXT

### Why This Phase
- Visual feedback for RAG answers
- User clicks reference → sees source highlighted
- Lazy loading for performance

### Plan Files to Reference

| File | Purpose |
|------|---------|
| **`PDF_VIEWER_CHAT_INTEGRATION.md`** | Complete UX flow, lazy loading, states |
| **`BBOX_HIGHLIGHT_IMPLEMENTATION.md`** | Canvas highlighting, coordinate conversion |
| **`LANDING_AI_VS_OUR_APPROACH_DETAILED.md`** | UI inspiration from Landing AI |

### Implementation Steps

```
□ 1. PDF page cache (backend)
   - Convert PDF pages to WebP images
   - Store in pdf_page_cache table
   - Serve via /api/pdf/{document_id}/page/{page_num}

□ 2. PDF viewer component (frontend)
   - Lazy load pages on demand
   - Page navigation (prev/next)
   - LRU cache (max 20 pages)

   Reference: PDF_VIEWER_CHAT_INTEGRATION.md → Performance Strategy

□ 3. Canvas highlighting
   - Overlay canvas on PDF image
   - Convert normalized coords (0-1) to pixels
   - Draw highlight rectangle

   Reference: BBOX_HIGHLIGHT_IMPLEMENTATION.md → Coordinate Conversion

□ 4. Reference click handler
   - Click [Page 2] → navigate to page 2
   - Highlight bbox from message.references
   - Scroll highlight into view
```

---

## Phase 6: Neo4j Structural Integration 🔲 PENDING

### Why This Phase
- **Complete the Intent Classifier routing** (structural/extraction queries from Phase 4)
- Row/column traversal via SAME_ROW/SAME_COL relationships
- Better page finding than SQL text search
- Extract entire tables/columns across multiple pages

### Connection to Phase 4 (Intent Classifier)

The Intent Classifier in Phase 4 routes queries to 3 paths:

| Intent | Status | Database | Example |
|--------|--------|----------|---------|
| `vector_only` (90%) | ✅ Done | Weaviate only | "What is batch number?" |
| `structural` (5%) | 🔲 **Phase 6** | Weaviate + Neo4j | "What page has specifications?" |
| `extraction` (5%) | 🔲 **Phase 6** | Weaviate + Neo4j | "Get all rows from test results table" |

### Plan Files to Reference

| File | Purpose |
|------|---------|
| **`NEO4J_DEEP_INTEGRATION_ANALYSIS.md`** | Why Neo4j adds value, graph model |
| **`NEO4J_USE_CASES_ANALYSIS.md`** | Page finding, structural queries, Cypher templates |
| **`BEST_LIBRARY_FOR_NEO4J.md`** | Python library (neo4j-driver) |
| **`dbschemas/PHASE3_NEO4J_SCHEMA.md`** | Node types, relationships, indexes |
| **`PHASE4_MULTIAGENT_ORCHESTRATION.md`** | Intent routing architecture |

### Implementation Steps

```
□ 1. Neo4j ingestion script
   - Parse Textract blocks.json
   - Create Document, Page, Table, Cell, Line, Section nodes
   - Create SAME_ROW, SAME_COL relationships for cells
   - Add chunk_index to link to Weaviate
   - Store process_id for document isolation

   Reference: PHASE3_NEO4J_SCHEMA.md → Node Types

□ 2. Weaviate-Neo4j bridge service
   - When Weaviate returns chunk_index=5
   - Query Neo4j: MATCH (t:Table {chunk_index: 5})
   - Get full structural context (row, column data)

□ 3. Update rag_orchestrator.py for structural/extraction intents
   - Route `structural` intent to Neo4j queries
   - Route `extraction` intent to Neo4j bulk extraction

□ 4. Cypher query templates
   - Structural: Find pages with tables, find sections
   - Extraction: Get all rows, get specific columns
   - Row traversal: MATCH (c1)-[:SAME_ROW]->(c2)
   - Column traversal: MATCH (c1)-[:SAME_COL]->(c2)

   Example Cypher queries:
   - "Get all rows under Specifications table":
     MATCH (t:Table {name: "Specifications"})-[:HAS_CELL]->(c:Cell)
     RETURN c.row, c.col, c.text ORDER BY c.row, c.col

   - "Find page with test results":
     MATCH (p:Page)-[:HAS_TABLE]->(t:Table)
     WHERE t.content CONTAINS "Test Results"
     RETURN p.page_num

□ 5. Structural query endpoints
   - GET /api/neo4j/table/{chunk_index}/row/{row_num}
   - GET /api/neo4j/table/{chunk_index}/column/{col_num}
   - POST /api/neo4j/extract-table (bulk extraction)

   Reference: NEO4J_USE_CASES_ANALYSIS.md → Cypher Templates
```

---

## Additional Reference Documents

### Architecture & Design
- `COMPLETE_SYSTEM_DESIGN_DIAGRAM.md` - Overall system architecture
- `COMPLETE_USER_FLOW_ANALYSIS.md` - User journey analysis
- `DATABASE_SCHEMA_ERD.md` - ERD overview
- `ACTUAL_ERD.md` - Technical ERD with all fields

### Decision Documents
- `VECTOR_DB_FINAL_RECOMMENDATION.md` - Why Weaviate over Iliad/Qdrant
- `LANDING_AI_VS_OUR_APPROACH_DETAILED.md` - Landing AI comparison

### EC2 Setup
- `WEAVIATE_NEO4J_CONFIG.md` - Connection details, Docker commands
- `ec2-setup/` folder - EC2 configuration files

---

## File Structure

```
frontend/feature_implementation/
│
├── IMPLEMENTATION_PHASES.md          ← YOU ARE HERE (Master doc)
│
├── dbschemas/                        ← Phase 1 (COMPLETED)
│   ├── PHASE1_POSTGRESQL_SCHEMA.md
│   ├── PHASE2_WEAVIATE_SCHEMA.md
│   └── PHASE3_NEO4J_SCHEMA.md
│
├── Chat History (Phase 2)
│   ├── CHAT_HISTORY_IMPLEMENTATION_PLAN.md
│   ├── CHAT_HISTORY_PRESERVATION.md
│   ├── MULTI_DOCUMENT_WORKFLOW.md
│   └── MESSAGE_RENDERING_SYSTEM.md
│
├── Chunking (Phase 3)
│   ├── COMPLETE_CHUNKING_STRATEGY.md
│   ├── TRANSFORMATION_OF_CELL_GROUNDING.md
│   └── TRANSFORMATION_OF_LINE_BLOCKS.md
│
├── RAG Search (Phase 4)
│   ├── RAG_QUERY_EXTRACTION_STRATEGY.md
│   ├── CORRECTED_RAG_QUERY_FLOWS.md
│   ├── COMPLETE_RAG_FLOW_WITH_BBOX.md
│   ├── COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md
│   └── BBOX_MATCHING_STRATEGY.md
│
├── PDF Viewer (Phase 5)
│   ├── PDF_VIEWER_CHAT_INTEGRATION.md
│   ├── BBOX_HIGHLIGHT_IMPLEMENTATION.md
│   └── LANDING_AI_VS_OUR_APPROACH_DETAILED.md
│
├── Neo4j (Phase 6)
│   ├── NEO4J_DEEP_INTEGRATION_ANALYSIS.md
│   ├── NEO4J_USE_CASES_ANALYSIS.md
│   └── BEST_LIBRARY_FOR_NEO4J.md
│
├── Architecture
│   ├── COMPLETE_SYSTEM_DESIGN_DIAGRAM.md
│   ├── COMPLETE_USER_FLOW_ANALYSIS.md
│   ├── DATABASE_SCHEMA_ERD.md
│   ├── ACTUAL_ERD.md
│   └── VECTOR_DB_FINAL_RECOMMENDATION.md
│
└── Config
    ├── WEAVIATE_NEO4J_CONFIG.md
    └── ec2-setup/
```

---

## For AI Agents: How to Use This Document

### Starting Work
1. Read this file first
2. Check "Quick Status Overview" for current phase
3. Find the 🔲 NEXT phase
4. Read ALL plan files listed for that phase
5. Follow "Implementation Steps" checklist

### Continuing Work
1. Check which phase is in progress
2. Review the implementation steps
3. Mark completed items with ✅
4. Update this document when phase completes

### Marking Phase Complete
```
Change: 🔲 NEXT → ✅ DONE
Update: Date in "Last Updated"
Add: Completion notes if needed
```

---

*Document Version: 1.4*
*Created: February 4, 2026*
*Last Updated: February 10, 2026*
*Next Action: Start Phase 5 (PDF Viewer & Highlighting)*
