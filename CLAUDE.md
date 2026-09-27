# CLAUDE.md — OCR Chatbot

## Project Overview

Document intelligence system for processing **any kind of PDF document** — COA (Certificate of Analysis), HBR (Handwritten Batch Records), log sheets, manufacturing records, and other pharmaceutical/scientific documents. FastAPI backend + Next.js frontend. Uses AWS Textract for OCR, Weaviate for vector search, Neo4j for structural queries, and Claude/Gemini for AI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.10+), `backend/app.py` is the main server |
| Frontend | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS |
| Vector DB | Weaviate (hybrid BM25 + semantic search, 3072-dim embeddings) |
| Graph DB | Neo4j (document structure: Document→Page→Table→Cell) |
| SQL DB | PostgreSQL (chat history, user sessions, document metadata) |
| OCR | AWS Textract (tables, layouts, forms, signatures) |
| Embeddings | text-embedding-3-large (3072 dims) via Iliad API |
| LLMs | Claude 3.7 Sonnet (answers), Gemini 2.5 Flash (intent), Gemini 3.1 Pro (vision) |
| Reranker | FlashRank ms-marco-MiniLM-L-12-v2 (CPU cross-encoder) |
| S3 Bucket | `ost-intelligent-parsing-test` (local dev), `ost-intelligent-parsing-prod` (prod) |

## Dev Commands

```bash
# Backend (runs on port 5000)
cd backend && python app.py

# Frontend (runs on port 3000)
cd frontend && npm run dev
```

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `ngxp-prod` | Production code deployed on prod server |
| `AI_export_fixes` | Current development branch for UI/API fixes |
| `dev` | Legacy development branch |

## URL Configuration

All frontend files have 3 URL options (comment/uncomment as needed):
```typescript
const API_BASE_URL = "http://localhost:5000";                                         // Local development
//const API_BASE_URL = "https://dev.aiparser.ir-bioprocess-poc.awscloud.abbvienet.com"; // Dev environment
//const API_BASE_URL = "https://aiparser.abbvienet.com";                                // Prod environment
```

**Files that need URL changes for deployment:**
- `frontend/src/services/agent.ts`
- `frontend/src/services/chatHistory.ts`
- `frontend/src/services/fileUtils.ts`
- `frontend/src/services/schemaService.ts`
- `frontend/src/app/chat/page.tsx` (also has `PDF_BASE_URL` for PDF file serving)
- `frontend/src/app/login/page.tsx`
- `frontend/src/components/PDFPanel.tsx`
- `frontend/src/components/PDFPanelTest.tsx`

**Note:** PDFPanel and PDFPanelTest use `https://aiparser.abbvienet.com` even in local dev because PDF files are stored on the prod server.

## Deployment

```bash
# Prod server (10.220.173.77)
ssh BAPATAR@10.220.173.77
cd /homes/bapatar/ocr-chat-bot
# Backend: systemd or direct python
# Frontend: npm run build && npm start
# Prod URL: https://aiparser.abbvienet.com
```

## Architecture at a Glance

### Upload Flow
```
PDF → Textract (S3) → Parse blocks → Layout-aware chunking → [Weaviate indexing + Neo4j graph] → Ready for RAG
```

### Query Flow (Claude-routed)
```
User message → Claude Haiku (routing decision) →
  ├─ [ROUTE:RAG] → Intent classifier (Gemini Flash) → Route by intent:
  │   ├─ precision   → Weaviate search → 1 agent → answer
  │   ├─ exploratory → Weaviate search → rerank → 5 parallel agents → merge
  │   ├─ exhaustive  → Weaviate search → rerank → 8 parallel agents → merge
  │   ├─ visual_audit → Weaviate + Gemini Vision → deep page analysis
  │   └─ hybrid      → Weaviate → Neo4j Cypher → structured extraction
  ├─ [ACTION:SHOW_COA_UPLOAD] → Show upload UI
  ├─ [ACTION:SHOW_PARAMETER_EXTRACTION] → Show Excel template upload
  └─ Normal text → Conversational response
```

### Frontend Message Flow
```
User types → handleSendMessage() → create streaming placeholder →
  agent.processMessage() → Claude routing (silent) → RAG or direct response →
  stream callback updates UI in real-time → save to DB with references →
  PageReferenceButtons rendered below message → click opens PDF with highlights
```

## Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload-coa` | POST | Upload PDF → Textract → Chunk → Weaviate + Neo4j |
| `/api/chat/coa-rag-v2-stream/{pid}` | POST | Main RAG chat (streaming, visual audit support) |
| `/api/chat/coa-rag-v2/{pid}` | POST | RAG chat (non-streaming) |
| `/api/pdf/{pid}/page/{page_num}` | GET | PDF page as WebP image |
| `/api/tables/{pid}/page/{page_num}` | GET | Table bboxes for PDF page |
| `/api/tables/export` | POST | Export single table to Excel/Word/PDF |
| `/api/tables/export-all` | POST | Export all tables merged |
| `/api/schemas` | GET/POST | Schema CRUD (extraction templates) |
| `/api/schemas/executions/{id}/run` | POST | Run extraction + verification (SSE) |
| `/api/chats` | GET/POST | Chat CRUD |
| `/api/chats/{id}/messages` | POST | Save message |
| `/api/chats/{id}/messages/assistant` | POST | Save assistant message with references |
| `/api/login` | POST | LDAP authentication |

## Configuration

| Service | URL |
|---------|-----|
| Weaviate | `http://10.242.190.53:8080` |
| Neo4j | `bolt://10.242.190.53:7687` (neo4j / ocr@4567) |
| Iliad API | `https://api-epic.ir-gateway.abbvienet.com/iliad` |
| PostgreSQL | `intelligentparsing-ngxp-dev.cimrdaj1f7u6.us-east-1.rds.amazonaws.com` |

## Detailed Documentation

- **Backend architecture**: See `backend/CLAUDE.md` (every service, endpoint, data flow)
- **Frontend architecture**: See `frontend/CLAUDE.md` (every component, service, state flow)
