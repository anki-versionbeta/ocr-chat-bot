# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ruben AI Chatbot is a Flask-based RAG (Retrieval-Augmented Generation) chatbot for document processing and question-answering. It uses hybrid search combining BM25 lexical search with semantic vector search for optimal document retrieval, integrates with Iliad API for document storage, AWS Textract for OCR, and Claude/GPT models for natural language understanding.

## Architecture

The application follows a modular architecture with three main layers:

### 1. Backend Core (`dependency/` folder)

All backend logic resides in the `dependency/` folder with three sub-modules:

#### Agents (`dependency/agents/`)
AI-powered agents that orchestrate search and question processing using LangChain's ReAct framework:

- **`hybrid_search.py`**: Core search engine combining lexical (BM25) and semantic (vector) search
  - Lexical weight: 30% (searches across `chunk_text`, `filename`, `keywords`, `summary`)
  - Semantic weight: 70% (cosine similarity on embeddings)
  - Elasticsearch DSL queries with script scoring
  - Returns top 10 results with highlights

- **`question_rephraser.py`**: Uses Claude 3.7 Sonnet to rephrase user questions into 3-5 search query variations for better retrieval coverage

- **`information_retriever.py`**: ReAct agent that retrieves information from Iliad sources using search tools

#### Processors (`dependency/processors/`)
Document processing modules for text and table extraction:

- **`text_processor.py`**:
  - AWS Textract integration for OCR (PDFs converted to images at 150 DPI)
  - Parallel processing of PDF pages using ThreadPoolExecutor
  - LLM-based summarization and keyword extraction
  - RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
  - ⚠️ **Security Note**: Contains hardcoded AWS credentials (lines 17-18, 62-63)

- **`table_processor.py`**:
  - Uses img2table library with AWS Textract OCR
  - Detects implicit rows and borderless tables
  - Converts tables to DataFrames and generates structured text descriptions
  - LLM analysis for table metadata and descriptions
  - ⚠️ **Security Note**: Contains hardcoded AWS credentials (lines 24-25)

#### Services (`dependency/services/`)
External API integrations:

- **`iliad_service.py`**: Complete Iliad API wrapper
  - Document upload/delete operations
  - Source management with custom fields
  - Hybrid search with Elasticsearch DSL
  - RAG query endpoint integration
  - Uses text-embedding-ada-002 for embeddings

- **`embedding_service.py`**: Text embedding generation via Iliad API
  - Supports batch processing (default batch_size=32)
  - Returns embeddings as list of float vectors

### 2. Main Application (`app.py`)

Flask application with the following key features:

- **Session Management**: Server-side sessions stored in Dataiku managed folder
- **Document Upload Pipeline**:
  1. DOCX → PDF conversion via pypandoc
  2. Large PDF chunking (10MB chunks, configurable via `CHUNK_SIZE`)
  3. Text extraction with AWS Textract
  4. Table extraction for supported formats
  5. Automatic summary and keyword generation
  6. Upload to Iliad with custom fields
  7. Cleanup of chunked files

- **Chat Pipeline**:
  1. Question received
  2. Hybrid search against selected documents
  3. Results filtered by filename
  4. Context building from top matches
  5. Chat history integration (up to 10 messages)
  6. LLM response generation with source citations

- **LLM Configuration**:
  - Primary: Claude 3.7 Sonnet (`claude-3-7-sonnet-20250219`)
  - Fallback: GPT-4o-mini via Azure OpenAI
  - Configurable via `IliadRequest` class

### 3. Frontend
- `index.html`: UI with Tailwind CSS
- `script.js`: Client-side interactions
- `style.css`: Custom styling

## Running the Application

```bash
# Install dependencies
pip install flask flask-caching flask-session werkzeug
pip install boto3 pypandoc pandas aiofiles aiohttp
pip install langchain langchain-openai langchain-anthropic langchain-core
pip install PyPDF2 pymupdf img2table dataiku

# Configure environment variables in app.py:
# - ILIAD_API_KEY
# - ILIAD_URL
# - USER_TOKEN

# Start Flask server
python app.py
```

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/upload` | POST | Upload single document to a source |
| `/upload_folder` | POST | Upload multiple documents |
| `/list_sources` | GET | List sources (filtered for 'reuben') |
| `/list_source_documents` | POST | List documents in a source |
| `/delete_document` | DELETE | Delete document from source |
| `/api/chat` | POST | Chat with documents using hybrid search |
| `/clear_session` | POST | Clear chat session |

## Document Processing Flow

```
Upload → Format Validation → DOCX Conversion (if needed) →
PDF Chunking (>10MB) → Text Extraction (Textract) →
Table Extraction → Metadata Generation (summary, keywords) →
Iliad Upload with Custom Fields → Cleanup Chunks
```

## Search & Retrieval Architecture

### Hybrid Search Implementation
The system uses a weighted combination of search strategies:

**Lexical Component (30% weight):**
- Match query against `chunk_text` (boost: 1.0x lexical_weight)
- Match phrase with slop=2 (boost: 1.5x lexical_weight)
- Match against `keywords` (boost: 2.5x lexical_weight)
- Match against `summary` (boost: 2.0x lexical_weight)
- Match against `filename` (boost: 2.0x lexical_weight)

**Semantic Component (70% weight):**
- Cosine similarity between query embedding and `chunk_vector`
- Uses text-embedding-3-large model
- Script score: `cosineSimilarity(queryVector, 'chunk_vector') * 0.7 + 1.0`

### Chat Response Generation
Uses LangChain prompt template with:
- Retrieved document chunks with scores
- Chat history (last 10 messages)
- Step-by-step reasoning instructions
- Source citation requirements

## Configuration & Environment

### Dataiku Integration
- Session storage: `/app/dataiku_data/.../cxAIoVwi` (Flask_Session folder)
- Upload folder: `/app/dataiku_data/.../XPh740vs`
- Chunked files: Dataiku folder "Chunked_files"

### Required Services
- **Iliad API**: Document storage, embeddings, RAG queries
- **AWS Textract**: OCR for images and PDFs
- **Anthropic API**: Claude models (via Iliad gateway)
- **Azure OpenAI** (optional): GPT models as fallback

### Custom Fields in Iliad Sources
Documents are indexed with these custom fields:
- `filename` (text)
- `document_summary` (text)
- `keywords` (text)
- `has_tables` (boolean)
- `table_count` (integer)
- `table_name` (text)
- `table_columns` (text)
- `is_table_data` (boolean)
- `subject` (text)

## Development Notes

### Modifying Search Weights
Edit `dependency/agents/hybrid_search.py`:
```python
lexical_weight: float = 0.3    # Line 25
semantic_weight: float = 0.7   # Line 26
```

### Changing Document Chunk Size
Edit `app.py`:
```python
CHUNK_SIZE = 10 * 1024 * 1024  # Line 49 (currently 10MB)
```

### Adding New Document Processors
1. Create processor in `dependency/processors/`
2. Initialize in `app.py` service initialization section
3. Integrate in `process_document_with_auto_metadata()` function

### Model Configuration
Change LLM models in:
- `app.py`: Main chat model (line 93)
- `dependency/agents/question_rephraser.py`: Rephraser model (line 25)
- `dependency/agents/information_retriever.py`: Retriever model (line 37)
- `dependency/processors/text_processor.py`: Text processing model (line 35)

## Security Considerations

⚠️ **Critical**: AWS credentials are hardcoded in:
- `dependency/processors/text_processor.py` (lines 17-18, 62-63)
- `dependency/processors/table_processor.py` (lines 24-25)

These should be moved to environment variables before deployment.

## Testing

1. Verify Iliad API connectivity
2. Upload test PDFs with tables through web UI
3. Select uploaded files and query with questions
4. Check hybrid search returns relevant results with proper scoring
5. Verify table extraction for PDF/image files
6. Test chat history maintains context across multiple queries
