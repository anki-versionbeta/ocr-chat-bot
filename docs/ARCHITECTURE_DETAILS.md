# OCR Chatbot - Architecture Details

**Moved from CLAUDE.md to reduce context size. Reference this file when needed.**

---

## RAG System Architecture (Detailed)

### 1. Indexing Pipeline (app.py lines 1270-1520)

**Trigger:** After COA Excel generation completes successfully

**Steps:**
1. Read `{filename}_blocks.json` (Textract LINE block output)
2. Extract text from all LINE blocks: `block.get('BlockType') == 'LINE'`
3. Optionally add product info from extraction results
4. Split text into chunks:
   ```python
   text_splitter = RecursiveCharacterTextSplitter(
       chunk_size=1000,
       chunk_overlap=200,
       separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
   )
   ```
5. Generate embeddings via Iliad API
6. Create/verify Iliad source with custom fields
7. Upload each chunk individually with metadata
8. Store source name in `progress_store` and `results_store`

**Custom Fields Schema:**
```python
{
    "filename": {"type": "text"},
    "process_id": {"type": "text"},
    "document_summary": {"type": "text"},
    "keywords": {"type": "text"},
    "document_type": {"type": "text"},
    "chunk_text": {"type": "text"},
    "chunk_index": {"type": "integer"},
    "total_chunks": {"type": "integer"}
}
```

### 2. Search Pipeline (app.py lines 2609-2820)

**Endpoint:** `POST /api/chat/coa-rag/{process_id}`

### 3. Hybrid Search Weights

```python
# Lexical Search (30% weight) - BM25 keyword matching
{
    "multi_match": {
        "query": question,
        "fields": [
            "chunk_text^1.0",
            "chunk_text^1.5",
            "keywords^2.5",
            "document_summary^2.0",
            "filename^2.0"
        ]
    }
}

# Semantic Search (70% weight) - Vector similarity
{
    "script_score": {
        "query": {...},
        "script": {
            "source": "cosineSimilarity(params.query_vector, 'chunk_vector') * 0.7 + 1.0"
        }
    }
}
```

---

## Phase 4 - Multi-Agent RAG Orchestration (COMPLETED)

**Architecture Document:** `frontend/feature_implementation/PHASE4_MULTIAGENT_ORCHESTRATION.md`

### Query Flow Overview

```
User Message → Context Resolver → Semantic Cache → Intent Classifier
    │
    ├── vector_only (90%) → Weaviate Only
    ├── structural (5%) → Weaviate + Neo4j
    └── extraction (5%) → Weaviate + Neo4j
```

### Enhanced Flow Components

1. **Context Resolver** - Resolves pronouns using conversation history
2. **Semantic Cache** - Similarity > 0.95, TTL: 30 minutes
3. **Intent Classifier** - Claude Haiku classifies query type
4. **Question Rephraser** - 3-5 COA-specific variations
5. **Parallel Weaviate Search** - All variations simultaneously
6. **Result Aggregator** - Merge, deduplicate, keep highest scores
7. **Cross-Encoder Reranker** - Optional, top 15 → top 5-7
8. **Answer Synthesizer** - Claude Sonnet with cell_ids
9. **Confidence Checker** - >= 0.7 return, < 0.7 add disclaimer
10. **Reference Extractor** - Lookup bbox from cell_grounding
11. **Cache Updater** - Store for future hits

### Response Format
```json
{
    "answer": "The batch number is 12345 [cell:2-5]",
    "references": [{"page": 1, "bbox": {...}, "cell_id": "2-5", "text": "12345"}],
    "confidence": 0.95,
    "query_type": "vector_only"
}
```

---

## Phase 6 - Neo4j Structural Integration (IN PROGRESS)

**New Services:**
- `neo4j_service.py` - Connection management (bolt://10.242.190.53:7687)
- `neo4j_ingestion.py` - Index blocks.json to Neo4j graph
- `cypher_templates.py` - Reusable Cypher templates

**Intent Routing:**
| Intent | Handler | Database |
|--------|---------|----------|
| vector_only (90%) | _process_vector_only_query | Weaviate |
| structural (5%) | _process_structural_query | Neo4j |
| hybrid_semantic_structural | _process_hybrid_query | Weaviate → Neo4j |
| extraction (5%) | _process_extraction_query | Neo4j |

---

## Streaming Responses

### Main Chat (Agent Service)
- File: `frontend/src/services/agent.ts`
- Model: Claude 4.5 Haiku via Iliad API
- Format: JSON-encoded strings per line

### COA RAG Chat (Backend)
- Endpoint: `POST /api/chat/coa-rag-stream/{process_id}`
- Format: SSE with `text/event-stream`

---

## Authentication Flow

```python
def get_auth_token():
    try:
        response = requests.get("http://gprd-auth:8010/auth.service/auth/token")
        if response.status_code == 200:
            return response.json().get("token")
    except:
        pass
    return "eyJqa3UiOiJodHRwOi8v..."  # Fallback JWT
```

---

## Plan Files Location

```
frontend/feature_implementation/
├── IMPLEMENTATION_PHASES.md      ← Master tracking
├── dbschemas/                    ← Phase 1
├── CHAT_HISTORY_*.md             ← Phase 2
├── COMPLETE_CHUNKING_*.md        ← Phase 3
├── RAG_QUERY_*.md                ← Phase 4
├── PDF_VIEWER_*.md               ← Phase 5
├── NEO4J_*.md                    ← Phase 6
├── completed/                    ← Completion records
└── handoffs/                     ← Session handoffs
```

---

## Development Workflow Commands

| Command | Purpose |
|---------|---------|
| `/start_phase <N>` | Analyze & prepare |
| `/implement_phase <N>` | Execute with validation |
| `/complete_phase <N>` | Finalize & document |
| `/create_handoff` | Save context |
| `/resume_handoff <path>` | Continue from previous |

---

## Change History

### 2026-02-11: Phase 6 Started
- Neo4j services created
- Intent routing updated

### 2026-02-09: Streaming Implemented
- Main Chat: `callClaudeAPIStreaming()`
- COA RAG: SSE endpoint

### Previous Phases
- Phase 1-4: COMPLETED
- Phase 5-6: PENDING
