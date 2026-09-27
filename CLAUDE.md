# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OCR Chatbot is a document intelligence system that extracts and analyzes data from Certificate of Analysis (COA) and Handwritten Batch Records (HBR) using AWS Textract OCR and Claude AI. The application consists of a FastAPI backend and Next.js frontend, processing PDFs through advanced OCR and LLM analysis to produce structured Excel outputs. **NEW**: Includes RAG (Retrieval-Augmented Generation) chat interface for conversational queries about extracted COA data.

## Architecture

### Backend (Python/FastAPI)

- **Main Application**: `backend/app.py` - FastAPI server with LDAP authentication, file upload handling, document processing orchestration, and RAG chat endpoint
- **Textract Services**: `backend/textractservices/` - Document processing pipeline
  - `textract_single.py` - AWS Textract integration for OCR extraction
  - `gpt_excel_extractor.py` - Claude 3.7 Sonnet integration for intelligent data extraction
  - `final_with_endotoxins.py` - Advanced validation and parameter variation detection
  - `hbr_multiagent.py` - Multi-agent system for HBR processing with feedback loop (uses Claude 3.7 Sonnet)
  - `hbr_multiagent_api.py` - API wrapper for multi-agent HBR system

- **RAG Integration**: `backend/Ruben_AI_Chatbot-main/dependency/` - RAG chatbot components
  - `agents/hybrid_search.py` - Hybrid search combining BM25 lexical (30%) and semantic vector search (70%)
  - `agents/question_rephraser.py` - **IMPROVED**: Generates 3-5 question variations for better search recall (uses Claude 3.7 Sonnet, no ReAct agent)
  - `services/iliad_service.py` - Iliad/Elasticsearch integration for document storage and vector search
  - `services/embedding_service.py` - Text embedding generation using OpenAI text-embedding-3-large

### Frontend (Next.js/TypeScript)

- **Chat Interface**: `frontend/src/app/chat/page.tsx` - Main interactive chat UI with COA RAG integration
  - Displays extraction status cards when COA processing completes
  - Status cards include "Download Results" and "Chat with Data" action buttons
  - **Chat with Data** opens RAG-powered conversation interface for querying indexed COA content
  - Tracks extraction state via `extractionStatus` object in messages

- **Agent Service**: `frontend/src/services/agent.ts` - AI chatbot with conversation management and document type detection
- **File Utilities**: `frontend/src/services/fileUtils.ts` - File upload and processing utilities
- **API Routes**: `frontend/src/app/api/chat/` - Next.js API routes for file uploads

---

## Processing Pipelines

### COA Workflow (Complete Pipeline)

#### Phase 1: Extraction & Analysis
```
User uploads PDF →
├─ AWS Textract extracts text/tables/key-value pairs (15-40% progress)
├─ GPT-4o mini generates summary and keywords
├─ Claude 3.7 Sonnet analyzes data structure (40-60% progress)
├─ Advanced validation checks parameter variations (60-80% progress)
└─ Enhanced Excel report generated (80-100% progress)
```

#### Phase 2: RAG Indexing (Background, after Excel generation)
```
blocks.json (Textract output) →
├─ Extract raw text from LINE blocks
├─ Add product info from extraction results
├─ Split into chunks (1000 chars, 200 overlap) using RecursiveCharacterTextSplitter
├─ Generate embeddings using text-embedding-3-large (via Iliad API)
├─ Index in Elasticsearch/Iliad with custom fields:
│   ├─ filename: Original PDF name
│   ├─ process_id: Unique identifier for session isolation
│   ├─ document_summary: GPT-generated summary
│   ├─ keywords: Extracted keywords
│   ├─ document_type: "COA"
│   ├─ chunk_text: The actual text content
│   ├─ chunk_vector: Embedding vector (1536 dimensions)
│   ├─ chunk_index: Position in document (0, 1, 2...)
│   └─ total_chunks: Total number of chunks
└─ Store in user-specific source: coa_{username}
```

**Key Implementation Details:**
- **Chunking**: RecursiveCharacterTextSplitter with chunk_size=1000, overlap=200
- **Embedding Model**: text-embedding-3-large (1536 dimensions, via Iliad API)
- **Source Naming**: `coa_{username}` or `coa_bapatar` for user isolation
- **Process ID**: Each upload gets unique UUID for document isolation
- **Background Task**: Indexing happens async, doesn't block Excel generation

#### Phase 3: RAG Chat ("Chat with Data" Feature)
```
User asks question →
├─ QuestionRephraser generates 3-5 query variations
│   Example: "batch number" → ["lot number", "batch ID", "manufacturing batch", ...]
│   Uses Claude 3.7 Sonnet with COA-specific terminology
│
├─ HybridSearch performs weighted search (for EACH variation):
│   ├─ Lexical Search (30% weight): BM25 on chunk_text, keywords, summary, filename
│   └─ Semantic Search (70% weight): Cosine similarity on chunk_vector embeddings
│
├─ Filter results by process_id (isolate this specific document)
│   Uses: {"must": [{"match": {"process_id": "uuid"}}, {"multi_match": {...}}]}
│
├─ Retrieve top 5 relevant chunks with scores
│
└─ Claude 3.7 Sonnet generates answer using:
    ├─ Retrieved chunks as context
    ├─ User's original question
    └─ Returns structured answer with source citations
```

**Authentication Flow:**
```
Frontend Request →
├─ Backend tries: http://gprd-auth:8010/auth.service/auth/token
├─ On 401: Falls back to hardcoded JWT token
├─ Adds x-user-token header to all Iliad API calls
└─ Required for: source creation, document upload, search operations
```

---

### HBR Workflow (Handwritten Batch Records)

```
User uploads HBR PDF + Target List Excel →
├─ Multi-agent system processes with Claude 3.7 Sonnet (hbr_multiagent.py)
├─ Extracts requested parameters from specified pages
├─ User provides feedback on missing/incorrect parameters
├─ System re-processes with user hints
└─ Returns updated Excel with extracted values
```

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
5. Generate embeddings via Iliad API:
   ```python
   embedding_service.embed_text(chunks)  # Returns list of 1536-dim vectors
   ```
6. Create/verify Iliad source with custom fields
7. Upload each chunk individually with metadata
8. Store source name in `progress_store` and `results_store` for persistence

**Custom Fields Schema:**
```python
{
    "filename": {"type": "text"},           # Searchable
    "process_id": {"type": "text"},         # For session isolation
    "document_summary": {"type": "text"},   # Searchable
    "keywords": {"type": "text"},           # Searchable
    "document_type": {"type": "text"},      # "COA"
    "chunk_text": {"type": "text"},         # Main searchable content
    "chunk_index": {"type": "integer"},     # Chunk order
    "total_chunks": {"type": "integer"}     # Total count
}
```

### 2. Search Pipeline (app.py lines 2609-2820)

**Endpoint:** `POST /api/chat/coa-rag/{process_id}`

**Flow:**
```python
# Step 1: Question Rephrasing
rephrased_questions = await question_rephraser.rephrase(user_message)
# Returns: ["What is the batch number?", "What is the lot number?", ...]

# Step 2: Hybrid Search (for each variation)
for question in rephrased_questions:
    search_query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"process_id": process_id}},  # Isolate document
                    {
                        "multi_match": {
                            "query": question,
                            "fields": ["chunk_text", "keywords", "document_summary"]
                        }
                    }
                ]
            }
        },
        "size": 5
    }

    # POST to Iliad with authentication
    response = requests.post(
        f"{ILIAD_URL}/api/v1/sources/{source_name}/search",
        headers={"x-api-key": ILIAD_API_KEY, "x-user-token": token},
        json={"search": search_query}  # MUST wrap in "search" field
    )

# Step 3: Collect and deduplicate results
# Combines results from all variations, removes duplicates by chunk_text

# Step 4: Claude Response Generation
prompt = f"""You are analyzing a Certificate of Analysis (COA) document.

Document: {original_filename}

Context from the document (retrieved via hybrid search):
{combined_context}

User Question: {user_message}

Please provide a helpful, accurate answer based on the context above."""

response = requests.post(
    f"{ILIAD_URL}/api/v1/chat/claude-3.7-sonnet",
    headers={"x-api-key": ILIAD_API_KEY},
    json={"messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
)
```

### 3. Hybrid Search Weights (Ruben_AI_Chatbot-main/dependency/agents/hybrid_search.py)

```python
# Lexical Search (30% weight) - BM25 keyword matching
{
    "multi_match": {
        "query": question,
        "fields": [
            "chunk_text^1.0",      # Base weight
            "chunk_text^1.5",      # Phrase match with slop=2
            "keywords^2.5",        # Keywords heavily weighted
            "document_summary^2.0",# Summary moderately weighted
            "filename^2.0"         # Filename moderately weighted
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

### 4. Document Isolation Strategy

Each COA upload gets a unique `process_id` (UUID). Documents are filtered using:
```elasticsearch
{"match": {"process_id": "specific-uuid-here"}}
```

This ensures:
- Multiple uploads of same file remain isolated
- Users only see their specific document's data
- No cross-contamination between different uploads
- Session-specific chat history

---

## Models Used

### LLM Models (via Iliad API Gateway)

| Use Case | Model | Endpoint | Purpose |
|----------|-------|----------|---------|
| **COA Data Extraction** | Claude 3.7 Sonnet | `/api/v1/chat/claude-3.7-sonnet` | Analyze Excel tables and extract structured data |
| **Advanced Validation** | Claude 3.7 Sonnet | `/api/v1/chat/claude-3.7-sonnet` | Detect parameter variations and validate test results |
| **HBR Multi-Agent** | Claude 3.7 Sonnet | `/api/v1/chat/claude-3.7-sonnet` | Extract parameters from handwritten batch records |
| **RAG Chat Responses** | Claude 3.7 Sonnet | `/api/v1/chat/claude-3.7-sonnet` | Generate answers from retrieved context |
| **Question Rephrasing** | Claude 3.7 Sonnet | `/anthropic/v1/messages` | Generate query variations for better search |
| **Summary Generation** | GPT-4o mini | `/api/v1/chat/gpt-4o-mini-global` | Quick document summaries |
| **Keyword Extraction** | GPT-4o mini | `/api/v1/chat/gpt-4o-mini-global` | Extract keywords from documents |

**Important:** Model endpoint format is `claude-3.7-sonnet` (with dot), NOT `claude-3-7-sonnet` (with hyphens).

### Embedding Models

| Model | Dimensions | Use Case | API Endpoint |
|-------|-----------|----------|--------------|
| **text-embedding-3-large** | 1536 | Document indexing & search | Iliad `/api/v1/embeddings` |

---

## Key API Endpoints

### COA Processing
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload-coa` | POST | Upload COA PDF for extraction |
| `/coa-result/{process_id}` | GET | Get extraction results |
| `/api/chat/coa-rag/{process_id}` | POST | **NEW** - Chat with indexed COA data |

### Progress Tracking
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload-progress-stream/{process_id}` | GET | Server-Sent Events for real-time progress |
| `/cancel-process/{process_id}` | POST | Cancel ongoing processing |

### HBR Processing
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload-hbr-multiagent` | POST | Upload HBR with multi-agent system |
| `/hbr-result/{process_id}` | GET | Get HBR extraction results |
| `/hbr-feedback` | POST | Submit missing parameter feedback |
| `/hbr-reprocess` | POST | Reprocess with user feedback |

### Utilities
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/login` | POST | LDAP authentication |
| `/api/check-auth` | GET | Verify session |
| `/download/{file_name}` | GET | Download processed files |
| `/routes` | GET | List all available endpoints |
| `/active-processes` | GET | Debug: show active processes |

---

## Development Commands

### Backend Setup

```bash
cd backend
python install_dependencies.py  # Install Python dependencies
python app.py                    # Start FastAPI server (localhost:5000)
```

### Frontend Setup

```bash
cd frontend
npm install                      # Install Node.js dependencies
npm run dev                      # Start Next.js dev server (localhost:3000)
npm run build                    # Build for production
npm run lint                     # Run ESLint
```

### Testing RAG System

```bash
# Test Iliad search
python backend/test_iliad_search.py coa_bapatar <process_id> "What is the batch number?"

# Test process ID search
python backend/test_process_search.py

# Test Claude endpoint
python backend/test_claude_fix.py

# Test question rephrasing
python backend/test_rephraser.py
```

---

## Configuration

### Environment Variables

Backend uses `.env` file (not in repo) for:
- AWS credentials (Textract API)
- Claude API key and URL
- LDAP credentials
- JWT secret keys

### Hardcoded Configuration (backend/app.py)

```python
# Iliad API
ILIAD_URL = "https://api-epic.ir-gateway.abbvienet.com/iliad"
ILIAD_API_KEY = REDACTED

# Authentication fallback token (JWT)
USER_TOKEN = REDACTED

# Text Chunking
chunk_size = 1000
chunk_overlap = 200

# Embedding Model
embedding_model = "text-embedding-3-large"
```

### AWS Configuration

- `backend/textractservices/textract_single.py:30-65` - Boto3 session configuration
- Uses `TEXTRACT_ENV` environment variable to switch between local credentials and IAM roles
- S3 bucket: `ost-intelligent-parsing-prod`

---

## Important Implementation Details

### Progress Tracking

- `progress_store` dictionary tracks active processes by process_id
- Server-Sent Events (SSE) stream real-time progress via `/upload-progress-stream/{process_id}`
- Progress stages: `uploading`, `extracting`, `analyzing`, `completed`, `error`, `cancelled`
- **Cleanup:** Progress entries older than 1 hour are automatically removed

### Metadata Persistence

**Problem:** `progress_store` gets cleared after 1 hour, losing RAG source information.

**Solution:** Store RAG metadata in BOTH stores:
```python
# Temporary (clears after 1 hour)
progress_store[process_id]["iliad_source"] = source_name

# Permanent
results_store[process_id]["iliad_source"] = source_name
```

**RAG Chat Lookup:**
1. Check `progress_store` first (recent uploads)
2. Fallback to `results_store` (older uploads)
3. Return 404 if not found in either

### File Storage

- All uploaded files: `backend/temp/`
- HBR results: `backend/temp/hbr_results/`
- Files served via `/download/{file_name}` endpoint
- Temporary files cleaned up on completion or cancellation

### Authentication Flow

```python
def get_auth_token():
    """Fetch JWT token from auth service"""
    try:
        response = requests.get("http://gprd-auth:8010/auth.service/auth/token")
        if response.status_code == 200:
            return response.json().get("token")
    except:
        pass

    # Fallback to hardcoded token
    return "eyJqa3UiOiJodHRwOi8v..." # Long-lived JWT
```

**Token Usage:**
- Required for: Iliad source creation, document upload, search operations
- Sent as `x-user-token` header
- Cached per request to avoid multiple auth calls

### Iliad API Requirements

**Critical:** Iliad search API requires specific format:

```python
# ❌ WRONG - Direct query
requests.post(url, json=search_query)

# ✅ CORRECT - Wrapped in "search" field
requests.post(url, json={"search": search_query})

# ✅ CORRECT - Must include x-user-token header
headers = {
    "x-api-key": ILIAD_API_KEY,
    "x-user-token": user_token  # REQUIRED
}
```

---

## Code Style and Conventions

### Python (Backend)

- Use `async def` for I/O operations, `def` for pure functions
- Type hints required for function signatures
- Descriptive variable names with `snake_case`
- Extensive logging: `logger.info()`, `logger.warning()`, `logger.error()`
- Early returns for error handling

### TypeScript (Frontend)

- PascalCase for components, camelCase for functions/variables
- Strict TypeScript - avoid `any` types
- React functional components with hooks
- Tailwind CSS for styling

### Specific Patterns

- **Background Tasks**: Use FastAPI's `BackgroundTasks` for long operations
- **Progress Callbacks**: `progress_callback(progress: int, message: str)`
- **Error Messages**: User-friendly messages + technical details in logs

---

## Common Development Workflows

### Adding New Document Type

1. Create processing function in `backend/textractservices/`
2. Add endpoint in `backend/app.py`
3. Update agent system prompt in `frontend/src/services/agent.ts`
4. Add UI trigger in `frontend/src/app/chat/page.tsx`

### Modifying COA Pipeline

Pipeline stages:
1. **Textract (15-40%)**: OCR extraction
2. **GPT Analysis (40-60%)**: LLM processing
3. **Validation (60-80%)**: Advanced checks
4. **Finalization (80-100%)**: Report generation
5. **RAG Indexing (Background)**: Elasticsearch indexing

Update progress callbacks when adding steps.

### Debugging RAG Issues

```python
# Check if document was indexed
GET /active-processes  # See if process_id exists

# Check source metadata
print(progress_store[process_id])
print(results_store[process_id])

# Test search directly
python backend/test_iliad_search.py coa_bapatar <process_id> "test query"

# Check Iliad source documents
GET /api/v1/sources/coa_bapatar/documents  # Requires x-user-token
```

---

## Critical Path Files

### Backend
- `backend/app.py:1270-1520` - RAG indexing pipeline
- `backend/app.py:2609-2820` - RAG chat endpoint
- `backend/app.py:538-680` - COA upload endpoint
- `backend/textractservices/gpt_excel_extractor.py` - Core LLM extraction logic
- `backend/Ruben_AI_Chatbot-main/dependency/agents/question_rephraser.py` - Query expansion
- `backend/Ruben_AI_Chatbot-main/dependency/agents/hybrid_search.py` - Search algorithm

### Frontend
- `frontend/src/app/chat/page.tsx:1290` - RAG chat API call
- `frontend/src/app/chat/page.tsx:2354-2441` - Extraction status display with "Chat with Data" button
- `frontend/src/services/fileUtils.ts:407` - COA upload handler

---

## Dependencies

### Backend Critical Dependencies

```
fastapi==0.109.0          # Web framework
boto3==1.34.0             # AWS SDK for Textract
pandas==2.2.0             # Data processing
openpyxl==3.1.2           # Excel file generation
ldap3==2.9.1              # Authentication
PyMuPDF==1.23.5           # PDF processing
langchain                 # RAG framework
langchain-anthropic       # Claude integration
requests                  # HTTP client
```

### Frontend Critical Dependencies

```
next@^13.4.19             # React framework
axios@^1.6.0              # HTTP client
react@^18.3.1             # UI library
tailwindcss@^3            # Styling
```

---

## Known Issues and Limitations

1. **Hardcoded Credentials**: AWS credentials and API keys in code
2. **No Formal Tests**: Application relies on manual testing
3. **Authentication Token Expiry**: Fallback JWT token expires 2026-06-12
4. **Progress Store Cleanup**: Entries cleared after 1 hour (fixed by dual-store approach)
5. **No Rate Limiting**: API endpoints lack rate limiting
6. **Single User Token**: All users share same Iliad authentication token
7. **No Pagination**: Search returns max 5 results, no pagination

---

## Recent Changes (2025-11-06)

### ✅ Implemented RAG Chat System
- Full Iliad integration with authentication
- Hybrid search (BM25 + semantic)
- Process ID-based document isolation
- Question rephrasing for better recall

### ✅ Fixed Issues
- QuestionRephraser parsing errors (removed ReAct agent, direct Claude calls)
- Claude API endpoint format (`claude-3.7-sonnet` not `claude-3-7-sonnet`)
- Iliad search query wrapping (must wrap in `{"search": ...}`)
- Process ID filtering (use `match` not `term` query)
- Metadata persistence (store in both progress_store and results_store)
- Authentication fallback (JWT token when auth service fails)

### 📝 Documentation
- Created `CLEANUP_ANALYSIS.md` - Lists unused endpoints and cleanup recommendations
- Created test scripts for debugging RAG components

---

## Security Considerations

**⚠️ CRITICAL**:
- `backend/textractservices/textract_single.py` contains hardcoded AWS credentials
- API keys hardcoded in `backend/app.py`
- JWT tokens with long expiry (2026-06-12)
- No API rate limiting
- Authentication disabled on some endpoints

These should be addressed before production deployment.