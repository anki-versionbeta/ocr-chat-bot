# Complete Technical ERD - Database Schema

> **Purpose:** Complete technical entity relationship diagram with all implementation details
> **Audience:** Development team
> **Includes:** Cell grounding, bbox coordinates, file rendering, RAG implementation
> **Version:** 2.0 (Technical Implementation)
> **Created:** January 2026

---

## Complete Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                    COMPLETE DATABASE ARCHITECTURE (TECHNICAL)                       │
│                                                                                     │
│                                                                                     │
│  ┌──────────────────────┐                                                           │
│  │       users          │                                                           │
│  ├──────────────────────┤                                                           │
│  │ PK user_id           │                                                           │
│  │    email             │                                                           │
│  │    full_name         │                                                           │
│  │    created_at        │                                                           │
│  │    last_active       │                                                           │
│  └────────┬─────────────┘                                                           │
│           │                                                                         │
│           │ 1:N (one user has many chats)                                           │
│           │                                                                         │
│           ▼                                                                         │
│  ┌──────────────────────┐                                                           │
│  │       chats          │                                                           │
│  ├──────────────────────┤                                                           │
│  │ PK chat_id           │                                                           │
│  │ FK user_id           │                                                           │
│  │ FK active_doc_id     │◀──────────┐                                               │
│  │    title             │           │                                               │
│  │    summary           │           │  (Most recent document)                       │
│  │    message_count     │           │                                               │
│  │    created_at        │           │                                               │
│  │    updated_at        │           │                                               │
│  │    is_archived       │           │                                               │
│  └────────┬─────────────┘           │                                               │
│           │                         │                                               │
│           │ 1:N                     │                                               │
│           │                         │                                               │
│  ┌────────┴──────────┐              │                                               │
│  │                   │              │                                               │
│  ▼                   ▼              │                                               │
│  ┌──────────────────────┐  ┌────────┴─────────────┐                                │
│  │     messages         │  │  chat_documents      │                                │
│  ├──────────────────────┤  ├──────────────────────┤                                │
│  │ PK message_id        │  │ PK id                │                                │
│  │ FK chat_id           │  │ FK chat_id           │                                │
│  │ FK document_id       │◀─┼─   document_id       │ ← Links to Elasticsearch      │
│  │    role              │  │    document_name     │                                │
│  │    content           │  │    upload_order      │ ← (1, 2, 3...)                │
│  │    sequence_num      │  │    extraction_done   │                                │
│  │    is_summarized     │  │    extraction_prompt │ ← Saved for reuse             │
│  │    created_at        │  │    extraction_result │                                │
│  │                      │  │    page_count        │                                │
│  │ FILE RENDERING:      │  │    created_at        │                                │
│  │  message_type        │  └──────────────────────┘                                │
│  │  attached_file_name  │           │                                              │
│  │  attached_file_size  │           │ Logical Link (document_id)                   │
│  │  generated_file_url  │           │                                              │
│  │  generated_file_name │           │                                              │
│  │  generated_file_meta │           │                                              │
│  │  references (JSONB)  │           │                                              │
│  └──────────────────────┘           │                                              │
│                                     │                                              │
│  ════════════════════════════════════▼═══════════════════════════════════════════  │
│                                                                                     │
│                         ELASTICSEARCH INDEX (TECHNICAL)                             │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                          document_chunks                                     │  │
│  ├──────────────────────────────────────────────────────────────────────────────┤  │
│  │                                                                              │  │
│  │  IDENTIFICATION                                                              │  │
│  │  • id (keyword)                    ← Unique chunk ID                        │  │
│  │  • document_id (keyword)           ← Links to chat_documents                │  │
│  │  • page (integer)                  ← Page number                            │  │
│  │  • type (keyword)                  ← "table", "text", "key_value"           │  │
│  │                                                                              │  │
│  │  SEARCH FIELDS                                                               │  │
│  │  • content (text)                  ← For keyword search (BM25)              │  │
│  │  • embedding (dense_vector)        ← For semantic search (1536-dim)         │  │
│  │                                                                              │  │
│  │  TABLE-LEVEL BOUNDING BOX (Normalized 0-1 coordinates)                      │  │
│  │  • bbox_left (float)               ← Table left edge                        │  │
│  │  • bbox_top (float)                ← Table top edge                         │  │
│  │  • bbox_right (float)              ← Table right edge                       │  │
│  │  • bbox_bottom (float)             ← Table bottom edge                      │  │
│  │  • bbox_width (float)              ← Table width                            │  │
│  │  • bbox_height (float)             ← Table height                           │  │
│  │                                                                              │  │
│  │  CELL-LEVEL GROUNDING (JSONB structure)                                     │  │
│  │  • cell_grounding (plain object)   ← Per-cell bbox + text (O(1) lookup)    │  │
│  │    {                                                                         │  │
│  │      "1-31": {                     ← Cell ID (page-cellIndex)               │  │
│  │        "box": {                    ← Cell bounding box                      │  │
│  │          "left": 0.70,             ← Normalized coordinates                 │  │
│  │          "top": 0.45,                                                        │  │
│  │          "right": 0.84,                                                      │  │
│  │          "bottom": 0.52                                                      │  │
│  │        },                                                                    │  │
│  │        "text": "6.1",              ← Cell content                           │  │
│  │        "type": "tableCell",        ← Cell type                              │  │
│  │        "row_index": 3,             ← Optional: row number                   │  │
│  │        "col_index": 1              ← Optional: column number                │  │
│  │      },                                                                      │  │
│  │      "1-32": {...},                ← More cells                             │  │
│  │      "1-33": {...}                                                           │  │
│  │    }                                                                         │  │
│  │                                                                              │  │
│  │  LINE-LEVEL GROUNDING (JSONB structure) - NEW Jan 22                        │  │
│  │  • line_grounding (plain object)   ← Per-line bbox + text (O(1) lookup)    │  │
│  │    {                                                                         │  │
│  │      "2d50afb8-402e-42f4-bb21-3dc5ae7bec61": {  ← Line UUID from Textract  │  │
│  │        "box": {                    ← Line bounding box                      │  │
│  │          "left": 0.08,             ← Normalized coordinates                 │  │
│  │          "top": 0.18,                                                        │  │
│  │          "right": 0.45,                                                      │  │
│  │          "bottom": 0.20                                                      │  │
│  │        },                                                                    │  │
│  │        "text": "Batch #: 1000459079"  ← Line content                        │  │
│  │      },                                                                      │  │
│  │      "d7fbd604-d609-4d69-857d-247a3f591238": {...},  ← More lines          │  │
│  │      "4b990aa0-af96-4369-b90f-dbe02538ed21": {...}                          │  │
│  │    }                                                                         │  │
│  │                                                                              │  │
│  │  MARKDOWN REPRESENTATION                                                     │  │
│  │  • markdown (text)                 ← Markdown with cell IDs                 │  │
│  │    <table id='1-t0'>                                                         │  │
│  │      <tr>                                                                    │  │
│  │        <td id='1-31'>6.1</td>      ← Clickable cell ID                      │  │
│  │      </tr>                                                                   │  │
│  │    </table>                                                                  │  │
│  │                                                                              │  │
│  │  METADATA                                                                    │  │
│  │  • filename (text)                 ← Original PDF name                      │  │
│  │  • process_id (keyword)            ← Session/upload isolation               │  │
│  │  • document_summary (text)         ← GPT-generated summary                  │  │
│  │  • keywords (text)                 ← Extracted keywords                     │  │
│  │  • document_type (keyword)         ← "COA", "HBR", etc.                     │  │
│  │  • chunk_index (integer)           ← Chunk order (0, 1, 2...)              │  │
│  │  • total_chunks (integer)          ← Total chunk count                      │  │
│  │  • created_at (date)               ← Index timestamp                        │  │
│  │                                                                              │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Table Definitions

### 1. **users** (PostgreSQL)

```sql
CREATE TABLE users (
    user_id             VARCHAR(50) PRIMARY KEY,
    email               VARCHAR(255) UNIQUE NOT NULL,
    full_name           VARCHAR(100),
    created_at          TIMESTAMP DEFAULT NOW(),
    last_active         TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
```

**Purpose:** User account management

---

### 2. **chats** (PostgreSQL)

```sql
CREATE TABLE chats (
    chat_id                     VARCHAR(50) PRIMARY KEY,
    user_id                     VARCHAR(50) NOT NULL,

    -- Active document tracking
    active_document_id          VARCHAR(50),            -- Most recent/selected document

    -- Chat metadata
    title                       VARCHAR(255) DEFAULT 'New Chat',

    -- Chat history summarization
    summary                     TEXT,                   -- Summarized old messages
    summary_updated_at          TIMESTAMP,
    message_count               INTEGER DEFAULT 0,

    -- Timestamps
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW(),
    is_archived                 BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX idx_chats_user ON chats(user_id);
CREATE INDEX idx_chats_updated ON chats(updated_at DESC);
```

**Purpose:** Chat session management with multi-document support

**Key Fields:**
- `active_document_id`: Controls which PDF shows in viewer by default
- `summary`: Compressed history of old messages (for context)
- `message_count`: Triggers summarization when > 30

---

### 3. **chat_documents** (PostgreSQL)

```sql
CREATE TABLE chat_documents (
    id                          SERIAL PRIMARY KEY,
    chat_id                     VARCHAR(50) NOT NULL,
    document_id                 VARCHAR(50) NOT NULL,   -- Links to Elasticsearch
    document_name               VARCHAR(255),
    upload_order                INTEGER,                -- 1, 2, 3... (determines "first", "previous")

    -- Extraction tracking
    extraction_done             BOOLEAN DEFAULT FALSE,
    extraction_prompt           TEXT,                   -- Saved prompt for reuse
    extraction_result_url       VARCHAR(500),           -- Excel download URL
    extraction_row_count        INTEGER,

    -- Metadata
    page_count                  INTEGER,
    created_at                  TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
);

CREATE INDEX idx_chat_documents_chat ON chat_documents(chat_id);
CREATE INDEX idx_chat_documents_order ON chat_documents(chat_id, upload_order DESC);
CREATE UNIQUE INDEX idx_chat_documents_unique ON chat_documents(chat_id, document_id);
```

**Purpose:** Track multiple documents in one chat

**Key Features:**
- `upload_order`: Enables "first document", "previous document" detection
- `extraction_prompt`: Saved for suggesting to next document upload
- `extraction_result_url`: Persistent download link for generated Excel

---

### 4. **messages** (PostgreSQL) - COMPLETE SCHEMA

```sql
CREATE TABLE messages (
    message_id                  VARCHAR(50) PRIMARY KEY,
    chat_id                     VARCHAR(50) NOT NULL,
    document_id                 VARCHAR(50),            -- Which document this message is about

    -- Core message fields
    role                        VARCHAR(20) NOT NULL,   -- 'user', 'assistant', 'system'
    content                     TEXT NOT NULL,
    sequence_num                INTEGER,                -- Message order (1, 2, 3...)

    -- Chat history management
    is_summarized               BOOLEAN DEFAULT FALSE,  -- Whether included in summary
    created_at                  TIMESTAMP DEFAULT NOW(),

    -- ═══════════════════════════════════════════════════════════════
    -- FILE RENDERING FIELDS (For UI display)
    -- ═══════════════════════════════════════════════════════════════

    message_type                VARCHAR(20) DEFAULT 'text',
    -- Values: 'text', 'file_upload', 'file_generated', 'system'

    -- File upload fields (PDF uploads by user)
    attached_file_name          VARCHAR(255),           -- "COA_001.pdf"
    attached_file_size          BIGINT,                 -- bytes

    -- Generated file fields (Excel outputs by system)
    generated_file_url          VARCHAR(500),           -- "/downloads/extraction.xlsx"
    generated_file_name         VARCHAR(255),           -- "COA_001_extraction.xlsx"
    generated_file_metadata     JSONB,                  -- {"row_count": 25, "columns": 8}

    -- ═══════════════════════════════════════════════════════════════
    -- RAG HIGHLIGHTING REFERENCES
    -- ═══════════════════════════════════════════════════════════════

    references                  JSONB,
    -- Structure:
    -- [
    --   {
    --     "page": 1,
    --     "bbox": {
    --       "left": 0.13, "top": 0.30,
    --       "right": 0.84, "bottom": 0.70
    --     },
    --     "cell_ids": ["1-31", "1-32"],      -- Optional: specific cells
    --     "chunk_id": "chunk_001",            -- Links to Elasticsearch
    --     "relevance_score": 0.87
    --   }
    -- ]

    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,

    CONSTRAINT messages_type_check CHECK (
        message_type IN ('text', 'file_upload', 'file_generated', 'system')
    )
);

CREATE INDEX idx_messages_chat ON messages(chat_id);
CREATE INDEX idx_messages_sequence ON messages(chat_id, sequence_num);
CREATE INDEX idx_messages_type ON messages(message_type);
```

**Purpose:** Complete message storage with file rendering and RAG highlighting

**Message Types:**

| Type | Use Case | UI Rendering | Example |
|------|----------|--------------|---------|
| `text` | Normal Q&A | Show text + references with highlight buttons | "What is the batch number?" |
| `file_upload` | PDF upload | Show file card with name, size, timestamp | "Uploaded COA_001.pdf (2.4 MB)" |
| `file_generated` | Excel output | Show download button + metadata | "Generated extraction with 25 rows" |
| `system` | Notifications | Show system message (grayed out) | "Document indexed successfully", "Switched to COA_002.pdf" |

---

### 5. **document_chunks** (Elasticsearch) - COMPLETE SCHEMA

```json
{
  "mappings": {
    "properties": {
      // ═══════════════════════════════════════════════════════════════
      // IDENTIFICATION
      // ═══════════════════════════════════════════════════════════════
      "id": {"type": "keyword"},
      "document_id": {"type": "keyword"},
      "page": {"type": "integer"},
      "type": {"type": "keyword"},  // "table", "text", "key_value"

      // ═══════════════════════════════════════════════════════════════
      // SEARCH FIELDS
      // ═══════════════════════════════════════════════════════════════
      "content": {
        "type": "text",
        "analyzer": "standard",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 1536,
        "index": true,
        "similarity": "cosine"
      },

      // ═══════════════════════════════════════════════════════════════
      // TABLE-LEVEL BOUNDING BOX (Normalized 0-1)
      // ═══════════════════════════════════════════════════════════════
      "bbox_left": {"type": "float"},
      "bbox_top": {"type": "float"},
      "bbox_right": {"type": "float"},
      "bbox_bottom": {"type": "float"},
      "bbox_width": {"type": "float"},
      "bbox_height": {"type": "float"},

      // ═══════════════════════════════════════════════════════════════
      // CELL-LEVEL GROUNDING (CRITICAL FOR PRECISE HIGHLIGHTING)
      // ═══════════════════════════════════════════════════════════════
      // Structure: Plain JSON object with cell IDs as keys
      // Example: {"1-31": {"box": {...}, "text": "6.1", "type": "tableCell"}}
      // NOT nested type - stored as-is for O(1) lookup by cell_id
      "cell_grounding": {
        "type": "object",
        "enabled": false  // Don't index, just store (not searchable)
      },

      // ═══════════════════════════════════════════════════════════════
      // LINE-LEVEL GROUNDING (NEW Jan 22 - SAME PATTERN AS CELL GROUNDING)
      // ═══════════════════════════════════════════════════════════════
      // Structure: Plain JSON object with line UUIDs as keys
      // Example: {"2d50afb8-...": {"box": {...}, "text": "Batch #: 1000459079"}}
      // NOT nested type - stored as-is for O(1) lookup by line_id
      // Used for precise line-level highlighting in text chunks
      "line_grounding": {
        "type": "object",
        "enabled": false  // Don't index, just store (not searchable)
      },

      // ═══════════════════════════════════════════════════════════════
      // MARKDOWN REPRESENTATION (For Markdown Tab UI)
      // ═══════════════════════════════════════════════════════════════
      "markdown": {
        "type": "text",
        "index": false  // Don't search, just store
      },

      // ═══════════════════════════════════════════════════════════════
      // METADATA
      // ═══════════════════════════════════════════════════════════════
      "filename": {"type": "text"},
      "process_id": {"type": "keyword"},        // Session isolation
      "document_summary": {"type": "text"},
      "keywords": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "document_type": {"type": "keyword"},     // "COA", "HBR"
      "layout_type": {"type": "keyword"},       // "SECTION_HEADER", "TEXT", "FOOTER", "TITLE" (from LAYOUT blocks)
      "chunk_index": {"type": "integer"},       // Reading order (0, 1, 2...) - preserves document flow
      "total_chunks": {"type": "integer"},
      "created_at": {"type": "date"}
    }
  }
}
```

---

## Data Flow Examples

### Example 1: File Upload Message

```sql
-- User uploads COA_001.pdf
INSERT INTO messages (
    message_id, chat_id, role, message_type, content,
    attached_file_name, attached_file_size, sequence_num
) VALUES (
    'msg_001', 'chat_123', 'user', 'file_upload',
    'Uploaded COA document',
    'COA_001.pdf', 1234567, 1
);
```

**UI Renders:**
```
[User] 📎
┌────────────────────────┐
│ 📄 COA_001.pdf        │
│ 1.2 MB • 2 mins ago   │
└────────────────────────┘
```

---

### Example 2: RAG Answer with Cell Highlighting

```sql
-- Bot answers with cell-level references
INSERT INTO messages (
    message_id, chat_id, role, message_type, content,
    document_id, references, sequence_num
) VALUES (
    'msg_002', 'chat_123', 'assistant', 'text',
    'The pH value is 6.1',
    'doc_001',
    '[{
        "page": 1,
        "bbox": {"left": 0.13, "top": 0.30, "right": 0.84, "bottom": 0.70},
        "cell_ids": ["1-31"],
        "chunk_id": "chunk_001",
        "relevance_score": 0.92
    }]'::jsonb,
    2
);
```

**UI Renders:**
```
[Bot] The pH value is 6.1
      📍 [Page 1] ← Click to highlight cell "1-31"
```

**When user clicks [Page 1]:**
1. Load PDF page 1
2. Lookup cell_grounding["1-31"] from Elasticsearch
3. Draw yellow rectangle at coordinates (0.70, 0.45, 0.84, 0.52)
4. Scroll to cell in view

---

### Example 3: Generated File Message

```sql
-- System generates Excel extraction
INSERT INTO messages (
    message_id, chat_id, role, message_type, content,
    generated_file_url, generated_file_name, generated_file_metadata,
    sequence_num
) VALUES (
    'msg_003', 'chat_123', 'assistant', 'file_generated',
    'Extracted 25 rows from COA document',
    '/downloads/COA_001_extraction.xlsx',
    'COA_001_extraction.xlsx',
    '{"row_count": 25, "columns": 8, "size_kb": 32}'::jsonb,
    3
);
```

**UI Renders:**
```
[Bot] Extracted 25 rows from COA document

┌────────────────────────────────┐
│ 📊 COA_001_extraction.xlsx    │
│ 25 rows • 32 KB               │
│ [⬇ Download Excel]            │
└────────────────────────────────┘
```

---

## Hybrid Search Implementation

### RAG Query Flow with Cell Highlighting

```
User: "What is the pH value?"
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Question Rephrasing                                     │
│─────────────────────────────────────────────────────────────────│
│ Original: "What is the pH value?"                               │
│ Variations: ["pH value", "pH level", "pH measurement",          │
│              "acidity", "potential hydrogen"]                   │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Hybrid Search (for each variation)                      │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│ Lexical Search (30% weight):                                    │
│ {                                                               │
│   "multi_match": {                                              │
│     "query": "pH value",                                        │
│     "fields": [                                                 │
│       "content^1.0",                                            │
│       "keywords^2.5",                                           │
│       "document_summary^2.0"                                    │
│     ]                                                           │
│   }                                                             │
│ }                                                               │
│                                                                 │
│ Semantic Search (70% weight):                                   │
│ {                                                               │
│   "script_score": {                                             │
│     "query": {...},                                             │
│     "script": {                                                 │
│       "source": "cosineSimilarity(...) * 0.7 + 1.0"            │
│     }                                                           │
│   }                                                             │
│ }                                                               │
│                                                                 │
│ Filter: {"match": {"process_id": "uuid"}}                      │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Retrieved Chunks (with cell grounding)                  │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│ Chunk 1 (Score: 0.92):                                          │
│ {                                                               │
│   "content": "Test Name | Results\npH | 6.1",                  │
│   "page": 1,                                                    │
│   "bbox_left": 0.13,                                            │
│   "bbox_top": 0.30,                                             │
│   "cell_grounding": {                                           │
│     "1-31": {                                                   │
│       "box": {"left": 0.70, "top": 0.45, ...},                 │
│       "text": "6.1",                                            │
│       "type": "tableCell"                                       │
│     }                                                           │
│   }                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Claude Response Generation                              │
│─────────────────────────────────────────────────────────────────│
│ Context: "Test Name | Results\npH | 6.1"                       │
│ Answer: "The pH value is 6.1"                                   │
│                                                                 │
│ References: [                                                   │
│   {                                                             │
│     "page": 1,                                                  │
│     "bbox": {...},                                              │
│     "cell_ids": ["1-31"],  ← Precise cell for highlighting     │
│     "chunk_id": "chunk_001"                                     │
│   }                                                             │
│ ]                                                               │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Save Message with References                            │
│─────────────────────────────────────────────────────────────────│
│ INSERT INTO messages (                                          │
│   role: 'assistant',                                            │
│   content: 'The pH value is 6.1',                               │
│   references: [{page: 1, cell_ids: ["1-31"], ...}]             │
│ );                                                              │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Frontend Rendering                                      │
│─────────────────────────────────────────────────────────────────│
│ UI: "The pH value is 6.1 📍 [Page 1]"                          │
│                                                                 │
│ On click [Page 1]:                                              │
│ 1. Fetch chunk_001 from Elasticsearch                           │
│ 2. Get cell_grounding["1-31"].box                               │
│ 3. Draw yellow box at (0.70, 0.45, 0.84, 0.52)                 │
│ 4. Scroll cell into view                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Multi-Document Workflow

```
STEP 1: Upload COA_001.pdf
─────────────────────────────────────────────────────────────────
• chat_documents: (upload_order: 1, extraction_prompt: NULL)
• chats.active_document_id = "doc_001"
• Message: (message_type: 'file_upload')

STEP 2: Extract to Excel
─────────────────────────────────────────────────────────────────
• User: "Extract Sample Summary"
• System extracts → Excel generated
• UPDATE chat_documents SET extraction_prompt = "Extract Sample Summary"
• Message: (message_type: 'file_generated', generated_file_url: "...")

STEP 3: Upload COA_002.pdf (SAME CHAT)
─────────────────────────────────────────────────────────────────
• chat_documents: (upload_order: 2, extraction_prompt: NULL)
• chats.active_document_id = "doc_002" (updated!)
• Message: (message_type: 'file_upload')

STEP 4: System suggests previous prompt
─────────────────────────────────────────────────────────────────
• Query: SELECT extraction_prompt FROM chat_documents
         WHERE chat_id = 'chat_123' AND extraction_prompt IS NOT NULL
         ORDER BY upload_order DESC LIMIT 1
• Result: "Extract Sample Summary"
• UI: [Run Same Extraction] [Modify Prompt]

STEP 5: User asks "What was batch in first document?"
─────────────────────────────────────────────────────────────────
• Keyword detection: "first" → doc_001 (upload_order: 1)
• RAG query on doc_001 chunks
• Claude answers from first document
• References include doc_001 cell_ids
```

---

## Key Relationships

```
users (1) ──→ (N) chats
chats (1) ──→ (N) chat_documents
chats (1) ──→ (N) messages
chat_documents (document_id) ←→ Elasticsearch document_chunks (document_id)
messages.references.chunk_id ←→ Elasticsearch document_chunks.id
messages.references.cell_ids ←→ Elasticsearch cell_grounding.cell_id
```

---

## Schema Validation Checklist

✅ **PostgreSQL Tables:**
- users: Standard fields
- chats: Active document tracking, summarization
- chat_documents: Multi-document support, prompt reuse
- messages: File rendering + RAG references

✅ **Elasticsearch Index:**
- Basic: document_id, content, embedding
- Table bbox: left, top, right, bottom, width, height
- Cell grounding: Plain JSON object with cell_id keys → {box, text, type, row, col}
- Markdown: HTML with cell IDs for clickable highlighting
- Metadata: filename, process_id, keywords, summary

✅ **Relationships:**
- PostgreSQL foreign keys enforced
- Elasticsearch document_id links logically (no FK)
- messages.references.cell_ids link to cell_grounding keys

✅ **Implementation Ready:**
- All fields have proper types
- Indexes defined for performance
- Constraints ensure data integrity
- JSONB fields for flexible nested data

---

*Document Version: 2.0 (Complete Technical Implementation)*
*Created: January 22, 2026*
*Includes: Cell grounding, file rendering, multi-document support, RAG highlighting*
