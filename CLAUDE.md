# CLAUDE.md

## Project Overview

OCR Chatbot - Document intelligence system for COA/HBR extraction using AWS Textract + Claude AI. FastAPI backend + Next.js frontend.

## Key Architecture

### Backend (`backend/`)
- `app.py` - Main FastAPI server, RAG endpoints
- `textractservices/` - OCR pipeline (textract_single.py, gpt_excel_extractor.py)
- `services/` - RAG components (weaviate_indexer.py, neo4j_service.py, rag_orchestrator.py)

### Frontend (`frontend/src/`)
- `app/chat/page.tsx` - Main chat UI
- `services/agent.ts` - AI chatbot with streaming
- `services/fileUtils.ts` - File upload handlers

## Processing Pipelines

### COA Upload
- `/upload-coa` - RAG-only (~40s): Textract → Chunk → Weaviate
- `/upload-coa-full` - With Excel (~65s): Textract → GPT → Validation → Excel → Weaviate

### RAG Chat
- Weaviate hybrid search (70% semantic, 30% BM25)
- Claude Sonnet for answer synthesis
- `cell_grounding` for table cell references

## Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/upload-coa` | RAG-only upload |
| `/upload-coa-full` | Full extraction |
| `/api/chat/coa-rag/{process_id}` | Chat with COA |
| `/api/chat/coa-rag-stream/{process_id}` | Streaming chat |

## Models

- **Claude 3.7 Sonnet** - Extraction, RAG answers (endpoint: `claude-3.7-sonnet`)
- **GPT-4o mini** - Summaries, keywords
- **text-embedding-3-large** - 3072-dim embeddings

## Dev Commands

```bash
# Backend
cd backend && python app.py

# Frontend
cd frontend && npm run dev
```

## Current Work: Multi-Agent GraphRAG

Testing file: `backend/test_multiagent_cypher.py`

**Test commands:**
```bash
cd backend
python run_test_queries.py 1      # Single query
python run_test_queries.py easy   # All easy queries
python run_test_queries.py hard   # All hard queries
```

**Key components:**
- Structural Probe - Finds WHERE data exists (Cell/Line/Section)
- Hard Constraints - Forces correct node type selection
- NEV Auditor - Validates topology before execution
- Success Bank - Dynamic few-shot learning

## Configuration

- Weaviate: `http://10.242.190.53:8080`
- Neo4j: `bolt://10.242.190.53:7687`
- Iliad API: `https://api-epic.ir-gateway.abbvienet.com/iliad`

## Extended Documentation

For detailed architecture, see: `docs/ARCHITECTURE_DETAILS.md`
For implementation phases, see: `frontend/feature_implementation/IMPLEMENTATION_PHASES.md`
