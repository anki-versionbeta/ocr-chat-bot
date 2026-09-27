# RAG Architecture: Generalized Document Processing

> **Document Purpose:** Complete architecture for document processing, embedding, chunking, and retrieval
> **Created:** January 2026
> **Principle:** Generalized extraction for all documents, Claude only when specific processing required

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Document Processing Flow](#document-processing-flow)
3. [Chunking Strategy](#chunking-strategy)
4. [Embedding Model Selection](#embedding-model-selection)
5. [Vector Storage](#vector-storage)
6. [Query Flow](#query-flow)
7. [When Claude Is Involved](#when-claude-is-involved)
8. [Implementation Details](#implementation-details)

---

## Architecture Overview

### Core Principle

```
┌─────────────────────────────────────────────────────────────────┐
│                     GENERALIZED APPROACH                        │
│                                                                 │
│  • Textract extracts ALL documents the same way                │
│  • Layout-aware chunking preserves structure                   │
│  • NVIDIA NV-Embed-v2 creates embeddings                       │
│  • Vector DB stores everything with metadata                   │
│  • RAG handles Q&A queries                                     │
│                                                                 │
│  Claude ONLY involved when:                                    │
│  • User requests specific data extraction                      │
│  • User wants Excel/structured output                          │
│  • Complex processing beyond Q&A                               │
└─────────────────────────────────────────────────────────────────┘
```

### High-Level Architecture

```
                        DOCUMENT UPLOAD
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS TEXTRACT                                 │
│                                                                 │
│  Features: LAYOUT + TABLES + FORMS                             │
│  Output: Structured document with bounding boxes               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               LAYOUT-AWARE CHUNKING                             │
│                                                                 │
│  • Tables → Keep whole (never split)                           │
│  • Titles → Separate chunks                                    │
│  • Text → Split at sentence boundaries                         │
│  • Add context (document, page, section)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              NVIDIA NV-Embed-v2                                 │
│                                                                 │
│  • 4096 dimensions                                             │
│  • Task-specific instructions                                  │
│  • Best-in-class retrieval accuracy                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 VECTOR DATABASE                                 │
│                                                                 │
│  Store: embedding + content + metadata                         │
│  Metadata: page, type, bbox, document_id, section             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                      READY FOR QUERIES
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   Q&A (RAG)     │             │  EXTRACTION     │
    │                 │             │  (Claude)       │
    │  User asks      │             │                 │
    │  question →     │             │  User requests  │
    │  RAG retrieves  │             │  specific data  │
    │  → Answer       │             │  → Find pages   │
    │                 │             │  → Claude       │
    │  NO Claude      │             │  extracts →     │
    │  needed!        │             │  Excel output   │
    └─────────────────┘             └─────────────────┘
```

---

## Document Processing Flow

### Step 1: Document Upload

```
User uploads document (PDF, 1-500 pages)
                    │
                    ▼
         Validate file format
                    │
                    ▼
         Store original in S3/storage
                    │
                    ▼
         Trigger processing pipeline
```

### Step 2: Textract Processing

```python
from textractor import Textractor
from textractor.data.constants import TextractFeatures

extractor = Textractor(region_name="us-east-1")

document = extractor.analyze_document(
    file_source="document.pdf",
    features=[
        TextractFeatures.LAYOUT,      # Reading order, titles, headers
        TextractFeatures.TABLES,      # Table structure
        TextractFeatures.FORMS,       # Key-value pairs
        TextractFeatures.SIGNATURES   # Signature detection
    ],
    save_image=True  # Keep page images for later use
)
```

**Output:**
- Structured document object
- Every element has bounding box
- Tables with cell-level data
- Reading order preserved
- Page images saved

### Step 3: Layout-Aware Chunking

```
Textract Output
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  FOR EACH PAGE:                                             │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   TABLES    │  │   TITLES    │  │    TEXT     │         │
│  │             │  │             │  │             │         │
│  │ Keep whole  │  │ Separate    │  │ Split at    │         │
│  │ as 1 chunk  │  │ chunks      │  │ sentences   │         │
│  │             │  │             │  │ if > 200    │         │
│  │ + bbox      │  │ + bbox      │  │ tokens      │         │
│  │ + structure │  │             │  │ + bbox      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐                          │
│  │ KEY-VALUES  │  │   LISTS     │                          │
│  │             │  │             │                          │
│  │ Keep pairs  │  │ Keep items  │                          │
│  │ together    │  │ together    │                          │
│  │ + bbox      │  │ + bbox      │                          │
│  └─────────────┘  └─────────────┘                          │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
Add Context to Each Chunk
      │
      ▼
Ready for Embedding
```

### Step 4: Embedding Generation

```
Chunks with Context
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  NVIDIA NV-Embed-v2                                         │
│                                                             │
│  Instruction: "Represent this pharmaceutical/technical      │
│               document chunk for retrieval"                 │
│                                                             │
│  Input: chunk.content_with_context                          │
│  Output: 4096-dimension embedding vector                    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
Store in Vector Database
```

### Step 5: Vector Storage

```
┌─────────────────────────────────────────────────────────────┐
│  VECTOR DATABASE RECORD                                     │
│                                                             │
│  {                                                          │
│    "id": "chunk-uuid-123",                                  │
│    "embedding": [0.1, 0.2, ...],  // 4096 dimensions       │
│    "content": "| pH | 7.2 | 6.5-7.5 |...",                 │
│    "content_with_context": "Document: COA...\nPage: 5...", │
│    "metadata": {                                            │
│      "document_id": "doc-456",                              │
│      "document_name": "COA_Batch_123.pdf",                 │
│      "page": 5,                                             │
│      "type": "table",                                       │
│      "section": "Sample Summary",                           │
│      "bbox": {                                              │
│        "left": 0.08,                                        │
│        "top": 0.14,                                         │
│        "right": 0.92,                                       │
│        "bottom": 0.45                                       │
│      },                                                     │
│      "table_structure": {                                   │
│        "rows": 5,                                           │
│        "cols": 3,                                           │
│        "headers": ["Test", "Result", "Spec"]               │
│      }                                                      │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Chunking Strategy

### Rules by Content Type

| Content Type | Chunking Rule | Max Size | Keep Together |
|--------------|---------------|----------|---------------|
| **Tables** | NEVER split | No limit | Entire table + headers |
| **Titles** | Separate chunk | N/A | Just the title |
| **Section Headers** | Separate chunk | N/A | Just the header |
| **Paragraphs** | Split if > 200 tokens | 200 tokens | Sentence boundaries |
| **Key-Value Pairs** | Keep together | N/A | Key + Value |
| **Lists** | Keep items together | 300 tokens | List context |
| **Figures/Captions** | Keep together | N/A | Figure + caption |

### Contextual Enhancement

Each chunk gets context added for better retrieval:

```python
def add_context_to_chunk(chunk, document_name, all_chunks):
    """
    Add context to improve retrieval accuracy by 15-20%
    """
    context_parts = [
        f"Document: {document_name}",
        f"Page: {chunk['page']}",
        f"Content Type: {chunk['type']}"
    ]

    # Add section context (nearest title above this chunk)
    if chunk['type'] != 'title':
        section = find_nearest_title_above(all_chunks, chunk['page'], chunk['bbox']['top'])
        if section:
            context_parts.append(f"Section: {section}")

    # Add table context if it's a table
    if chunk['type'] == 'table' and 'table_structure' in chunk:
        headers = chunk['table_structure'].get('headers', [])
        if headers:
            context_parts.append(f"Table columns: {', '.join(headers)}")

    context = "\n".join(context_parts)

    chunk['content_with_context'] = f"{context}\n\nContent:\n{chunk['content']}"

    return chunk
```

**Example Output:**

```
Document: COA_Batch_HL4689.pdf
Page: 5
Content Type: table
Section: Sample Summary
Table columns: Test Parameter, Result, Specification

Content:
| Test Parameter | Result | Specification |
|----------------|--------|---------------|
| pH             | 7.2    | 6.5-7.5       |
| Concentration  | 10.5   | 8.0-12.0      |
| Purity         | 99.2%  | ≥98.0%        |
```

---

## Embedding Model Selection

### Recommendation: NVIDIA NV-Embed-v2

| Criteria | NV-Embed-v2 | OpenAI Large | OpenAI Small |
|----------|-------------|--------------|--------------|
| **Dimensions** | 4096 | 3072 | 1536 |
| **MTEB Rank** | #1 | #5 | #12 |
| **Technical Docs** | Excellent | Good | Okay |
| **Cost (self-hosted)** | ~$0 | N/A | N/A |
| **Cost (API)** | N/A | $0.13/1M | $0.02/1M |
| **Task Instructions** | ✅ Yes | ❌ No | ❌ No |

### Why NV-Embed-v2?

```
✅ #1 on MTEB benchmark (best retrieval accuracy)
✅ 4096 dimensions (captures more semantic nuance)
✅ Task-specific instructions (unique feature)
✅ Better for technical/pharmaceutical documents
✅ FREE if self-hosted on your infrastructure
✅ Works with any vector database
```

### Task-Specific Instructions (Key Feature)

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('nvidia/NV-Embed-v2')

# For indexing documents (storage)
doc_instruction = "Represent this pharmaceutical document chunk for retrieval"
doc_embeddings = model.encode(
    chunks,
    prompt=doc_instruction
)

# For searching (queries)
query_instruction = "Represent this question for retrieving relevant pharmaceutical documents"
query_embedding = model.encode(
    "What is the pH value in the Sample Summary?",
    prompt=query_instruction
)
```

### Alternative: If Self-Hosting Not Possible

| Scenario | Recommendation |
|----------|----------------|
| Can self-host GPU | NVIDIA NV-Embed-v2 |
| No GPU, need best quality | OpenAI text-embedding-3-large |
| No GPU, cost-sensitive | OpenAI text-embedding-3-small |
| Scientific/medical docs | Voyage AI voyage-large-2 |

---

## Vector Storage

### Recommended: PostgreSQL + pgvector

```sql
-- Enable pgvector extension
CREATE EXTENSION vector;

-- Create chunks table
CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),

    -- Content
    content TEXT NOT NULL,
    content_with_context TEXT NOT NULL,

    -- Embedding (4096 dimensions for NV-Embed-v2)
    embedding vector(4096),

    -- Metadata
    page INTEGER NOT NULL,
    chunk_type VARCHAR(50) NOT NULL,  -- 'table', 'title', 'text', 'key_value'
    section_title TEXT,

    -- Bounding box for visual references
    bbox_left FLOAT,
    bbox_top FLOAT,
    bbox_right FLOAT,
    bbox_bottom FLOAT,

    -- Table-specific metadata (NULL for non-tables)
    table_rows INTEGER,
    table_cols INTEGER,
    table_headers TEXT[],

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for fast similarity search
CREATE INDEX ON document_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### Query for Similarity Search

```sql
-- Find similar chunks
SELECT
    id,
    content,
    page,
    chunk_type,
    bbox_left, bbox_top, bbox_right, bbox_bottom,
    1 - (embedding <=> $1) AS similarity
FROM document_chunks
WHERE document_id = $2
ORDER BY embedding <=> $1
LIMIT 10;
```

---

## Query Flow

### Type 1: Q&A Query (No Claude)

```
User: "What is the pH value in the COA?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Embed Query                                        │
│                                                             │
│  Instruction: "Represent this question for retrieving..."   │
│  Query embedding → 4096 dimensions                          │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Vector Similarity Search                           │
│                                                             │
│  Find top 5-10 most similar chunks                          │
│  Returns: chunks with page numbers and bounding boxes       │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Generate Answer (Claude or other LLM)              │
│                                                             │
│  Prompt:                                                    │
│  "Based on the following document excerpts, answer the      │
│   question: What is the pH value in the COA?                │
│                                                             │
│   Context:                                                  │
│   [Chunk 1 - Page 5, Table]                                │
│   | pH | 7.2 | 6.5-7.5 |                                   │
│   ..."                                                      │
│                                                             │
│  Answer: "The pH value is 7.2 (specification: 6.5-7.5)"    │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Return with Visual References                      │
│                                                             │
│  Response: {                                                │
│    "answer": "The pH value is 7.2...",                     │
│    "references": [                                          │
│      {                                                      │
│        "page": 5,                                           │
│        "type": "table",                                     │
│        "bbox": {"left": 0.08, "top": 0.14, ...},           │
│        "label": "Page 5, Table"                            │
│      }                                                      │
│    ]                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
```

### Type 2: Extraction Query (Claude Involved)

```
User: "Extract all Sample Summary concentrations to Excel"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Classify Intent                                    │
│                                                             │
│  Quick Claude call to determine:                            │
│  - Is this Q&A or Extraction?                              │
│  - What search terms to use?                               │
│  - What data to extract?                                   │
│                                                             │
│  Result: {                                                  │
│    "intent": "extraction",                                  │
│    "search_terms": ["Sample Summary"],                      │
│    "extract_fields": ["concentration", "range"],           │
│    "output_format": "excel"                                │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Find Relevant Pages (RAG Search)                   │
│                                                             │
│  Query: "Sample Summary table concentration"                │
│  Results:                                                   │
│    - Page 5 (score: 0.95)                                   │
│    - Page 45 (score: 0.93)                                  │
│    - Page 89 (score: 0.91)                                  │
│    - ... (20 pages total)                                   │
│                                                             │
│  Unique pages: [5, 45, 89, 134, ...]                       │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Claude Extraction (Async Parallel)                 │
│                                                             │
│  Process 15 pages at a time (parallel)                      │
│                                                             │
│  For each page:                                             │
│    Input: Page image + extraction prompt                    │
│    Output: {"concentration": "10.5", "range": "8-12"}      │
│                                                             │
│  20 pages ÷ 15 parallel = ~10-15 seconds total             │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Consolidate + Generate Excel                       │
│                                                             │
│  Combine all results:                                       │
│  | Page | Sample | Concentration | Range    |              │
│  |------|--------|---------------|----------|              │
│  | 5    | 1      | 10.5          | 8-12     |              │
│  | 45   | 2      | 11.2          | 8-12     |              │
│  | 89   | 3      | 10.8          | 8-12     |              │
│                                                             │
│  Generate Excel file → Return download link                 │
└─────────────────────────────────────────────────────────────┘
```

---

## When Claude Is Involved

### Claude NOT Needed (Generalized RAG)

| Task | Handled By |
|------|------------|
| Q&A questions | RAG retrieval + simple LLM answer |
| "What is the pH?" | RAG |
| "Show me the test results" | RAG |
| "Find batch number" | RAG |
| Visual references | Stored bounding boxes |
| Table display | Stored table structure |

### Claude IS Needed (Specific Processing)

| Task | Why Claude Needed |
|------|-------------------|
| "Extract all X to Excel" | Systematic extraction across pages |
| "Compare batch A vs B" | Complex reasoning |
| "Summarize all deviations" | Aggregation + analysis |
| "Format this as markdown" | Text formatting |
| "Group label-value pairs" | Visual understanding |
| Custom extraction templates | Flexible parsing |

### Decision Flow

```
User Input
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│  INTENT CLASSIFIER                                          │
│                                                             │
│  Keywords indicating extraction:                            │
│  • "extract", "export", "excel", "csv"                     │
│  • "all", "every", "list all"                              │
│  • "to file", "download", "generate"                       │
│  • "compare", "summarize across"                           │
│                                                             │
│  Keywords indicating Q&A:                                   │
│  • "what is", "where is", "show me"                        │
│  • "find", "tell me"                                       │
│  • Single value questions                                  │
└─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────┐          ┌─────────────┐
│   Q&A       │          │ EXTRACTION  │
│             │          │             │
│ RAG Search  │          │ RAG finds   │
│     ↓       │          │ pages       │
│ LLM Answer  │          │     ↓       │
│     ↓       │          │ Claude      │
│ Visual Refs │          │ extracts    │
│             │          │     ↓       │
│ NO Claude   │          │ Excel/JSON  │
│ extraction  │          │             │
└─────────────┘          └─────────────┘
```

---

## Implementation Details

### Complete Chunking Function

```python
def create_chunks_from_textract(document, document_name):
    """
    Create layout-aware chunks from Textract document
    """
    chunks = []

    for page in document.pages:
        page_num = page.page_num

        # 1. Process Tables (NEVER split)
        for table in page.tables:
            chunk = {
                "content": table.to_markdown(),
                "type": "table",
                "page": page_num,
                "bbox": {
                    "left": table.bbox.x,
                    "top": table.bbox.y,
                    "right": table.bbox.x + table.bbox.width,
                    "bottom": table.bbox.y + table.bbox.height
                },
                "table_structure": {
                    "rows": table.row_count,
                    "cols": table.column_count,
                    "headers": [cell.text for cell in table.rows[0].cells] if table.rows else []
                }
            }
            chunks.append(chunk)

        # 2. Process Titles (separate chunks)
        for title in page.page_layout.titles:
            chunk = {
                "content": title.text,
                "type": "title",
                "page": page_num,
                "bbox": {
                    "left": title.bbox.x,
                    "top": title.bbox.y,
                    "right": title.bbox.x + title.bbox.width,
                    "bottom": title.bbox.y + title.bbox.height
                }
            }
            chunks.append(chunk)

        # 3. Process Section Headers
        for header in page.page_layout.section_headers:
            chunk = {
                "content": header.text,
                "type": "section_header",
                "page": page_num,
                "bbox": {
                    "left": header.bbox.x,
                    "top": header.bbox.y,
                    "right": header.bbox.x + header.bbox.width,
                    "bottom": header.bbox.y + header.bbox.height
                }
            }
            chunks.append(chunk)

        # 4. Process Text Blocks (split if too long)
        for text_block in page.page_layout.text:
            text = text_block.text
            token_count = REDACTED

            if token_count <= 200:
                # Small enough, keep together
                chunk = {
                    "content": text,
                    "type": "text",
                    "page": page_num,
                    "bbox": {
                        "left": text_block.bbox.x,
                        "top": text_block.bbox.y,
                        "right": text_block.bbox.x + text_block.bbox.width,
                        "bottom": text_block.bbox.y + text_block.bbox.height
                    }
                }
                chunks.append(chunk)
            else:
                # Split at sentence boundaries
                sentences = split_sentences(text)
                current_chunk_text = ""

                for sentence in sentences:
                    if len((current_chunk_text + " " + sentence).split()) <= 200:
                        current_chunk_text += " " + sentence
                    else:
                        if current_chunk_text.strip():
                            chunk = {
                                "content": current_chunk_text.strip(),
                                "type": "text",
                                "page": page_num,
                                "bbox": {
                                    "left": text_block.bbox.x,
                                    "top": text_block.bbox.y,
                                    "right": text_block.bbox.x + text_block.bbox.width,
                                    "bottom": text_block.bbox.y + text_block.bbox.height
                                }
                            }
                            chunks.append(chunk)
                        current_chunk_text = sentence

                # Don't forget last chunk
                if current_chunk_text.strip():
                    chunk = {
                        "content": current_chunk_text.strip(),
                        "type": "text",
                        "page": page_num,
                        "bbox": {
                            "left": text_block.bbox.x,
                            "top": text_block.bbox.y,
                            "right": text_block.bbox.x + text_block.bbox.width,
                            "bottom": text_block.bbox.y + text_block.bbox.height
                        }
                    }
                    chunks.append(chunk)

        # 5. Process Key-Value Pairs
        for kv in page.key_values:
            chunk = {
                "content": f"{kv.key.text}: {kv.value.text}",
                "type": "key_value",
                "page": page_num,
                "bbox": {
                    "left": kv.bbox.x,
                    "top": kv.bbox.y,
                    "right": kv.bbox.x + kv.bbox.width,
                    "bottom": kv.bbox.y + kv.bbox.height
                }
            }
            chunks.append(chunk)

    # Add context to all chunks
    chunks = add_context_to_all_chunks(chunks, document_name)

    return chunks


def add_context_to_all_chunks(chunks, document_name):
    """
    Add document/section context to each chunk
    """
    # Sort chunks by page and vertical position
    sorted_chunks = sorted(chunks, key=lambda x: (x['page'], x['bbox']['top']))

    # Track current section title
    current_sections = {}  # page -> section title

    for chunk in sorted_chunks:
        page = chunk['page']

        # Update section if this is a title
        if chunk['type'] in ['title', 'section_header']:
            current_sections[page] = chunk['content']

        # Build context
        context_parts = [
            f"Document: {document_name}",
            f"Page: {page}",
            f"Type: {chunk['type']}"
        ]

        # Add section context
        section = current_sections.get(page)
        if section and chunk['type'] not in ['title', 'section_header']:
            context_parts.append(f"Section: {section}")

        # Add table info
        if chunk['type'] == 'table' and 'table_structure' in chunk:
            headers = chunk['table_structure'].get('headers', [])
            if headers:
                context_parts.append(f"Table columns: {', '.join(headers)}")

        chunk['content_with_context'] = "\n".join(context_parts) + f"\n\nContent:\n{chunk['content']}"

    return sorted_chunks
```

### Embedding Function

```python
from sentence_transformers import SentenceTransformer
import numpy as np

# Initialize model (do once at startup)
embed_model = SentenceTransformer('nvidia/NV-Embed-v2')

def create_embeddings(chunks, batch_size=32):
    """
    Create embeddings for all chunks using NV-Embed-v2
    """
    # Document embedding instruction
    doc_instruction = "Represent this pharmaceutical/technical document chunk for retrieval"

    # Get all texts to embed
    texts = [chunk['content_with_context'] for chunk in chunks]

    # Create embeddings in batches
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = embed_model.encode(
            batch,
            prompt=doc_instruction,
            normalize_embeddings=True
        )
        all_embeddings.extend(embeddings)

    # Add embeddings to chunks
    for chunk, embedding in zip(chunks, all_embeddings):
        chunk['embedding'] = embedding.tolist()

    return chunks


def create_query_embedding(query):
    """
    Create embedding for a search query
    """
    query_instruction = "Represent this question for retrieving relevant pharmaceutical/technical documents"

    embedding = embed_model.encode(
        query,
        prompt=query_instruction,
        normalize_embeddings=True
    )

    return embedding.tolist()
```

### RAG Search Function

```python
def search_similar_chunks(query, document_id, top_k=10, threshold=0.7):
    """
    Search for similar chunks using vector similarity
    """
    # Create query embedding
    query_embedding = create_query_embedding(query)

    # Search in vector database
    results = db.execute("""
        SELECT
            id,
            content,
            content_with_context,
            page,
            chunk_type,
            section_title,
            bbox_left, bbox_top, bbox_right, bbox_bottom,
            table_headers,
            1 - (embedding <=> %s::vector) AS similarity
        FROM document_chunks
        WHERE document_id = %s
          AND 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, [query_embedding, document_id, query_embedding, threshold, query_embedding, top_k])

    return [
        {
            "id": row.id,
            "content": row.content,
            "page": row.page,
            "type": row.chunk_type,
            "section": row.section_title,
            "bbox": {
                "left": row.bbox_left,
                "top": row.bbox_top,
                "right": row.bbox_right,
                "bottom": row.bbox_bottom
            },
            "similarity": row.similarity
        }
        for row in results
    ]
```

---

## Summary

### Generalized Pipeline (All Documents)

```
Upload → Textract → Chunk → Embed → Store → Ready for RAG
```

**No Claude involved in the generalized pipeline!**

### When Claude Gets Involved

| Scenario | Claude Role |
|----------|-------------|
| Extraction to Excel | Process specific pages found by RAG |
| Complex aggregation | Analyze across multiple chunks |
| Text formatting | Format grouped content as markdown |
| Custom templates | Flexible extraction based on user prompts |

### Key Decisions

| Component | Choice | Reason |
|-----------|--------|--------|
| **Embedding** | NVIDIA NV-Embed-v2 | Best accuracy, task-specific, free self-hosted |
| **Chunking** | Layout-aware | Preserves tables, adds context |
| **Vector DB** | PostgreSQL + pgvector | Simple, reliable, good performance |
| **Search** | Semantic (vector) | Handles variations, fast |
| **Claude** | Only for extraction/processing | Cost-effective, targeted use |

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
