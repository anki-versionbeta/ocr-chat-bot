# Multi-Document Chat Workflow

> **Goal:** Multiple documents in same chat window with efficient RAG
> **Default:** Multi-document per chat (same chat for same document type)
> **Additional Feature:** Project/Folder for organized batch processing
> **Created:** January 2026

---

## Table of Contents

1. [Concept Overview](#concept-overview)
2. [Database Schema](#database-schema)
3. [Default Flow: Multi-Document Chat](#default-flow-multi-document-chat)
4. [Efficient RAG Solution](#efficient-rag-solution)
5. [Additional Feature: Projects/Folders](#additional-feature-projectsfolders)
6. [UI Design](#ui-design)
7. [API Endpoints](#api-endpoints)
8. [Implementation Code](#implementation-code)

---

## Concept Overview

### Two Modes

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  DEFAULT: Multi-Document Chat                                           │
│  ════════════════════════════                                           │
│                                                                         │
│  💬 COA Analysis (Single Chat Window)                                   │
│      ├── 📄 COA_001.pdf (doc_001) ← first                              │
│      ├── 📄 COA_002.pdf (doc_002)                                      │
│      └── 📄 COA_003.pdf (doc_003) ← active (most recent)               │
│                                                                         │
│  • Multiple documents in ONE chat                                       │
│  • RAG uses active document by default                                  │
│  • User can ask: "first doc", "previous", "all docs"                   │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ADDITIONAL: Project/Folder (Optional)                                  │
│  ═════════════════════════════════════                                  │
│                                                                         │
│  📁 COA Processing (Project)                                            │
│      ├── Default Prompt: "Extract Sample Summary..."                    │
│      │                                                                  │
│      └── 💬 COA Analysis (Chat inside project)                         │
│              ├── 📄 COA_001.pdf                                        │
│              ├── 📄 COA_002.pdf                                        │
│              └── 📄 COA_003.pdf                                        │
│                                                                         │
│  • Saved extraction prompt                                              │
│  • Organized by document type                                           │
│  • Same multi-doc chat inside project                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why This Approach

| Aspect | Benefit |
|--------|---------|
| **No repeated prompts** | Same extraction prompt reused |
| **Single chat window** | All related docs in one place |
| **Efficient RAG** | Single Claude call, keyword detection |
| **Optional organization** | Projects for users who want structure |

---

## Database Schema

### Complete Schema

```sql
-- ═══════════════════════════════════════════════════════════════════════
-- USERS
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE users (
    user_id             VARCHAR(50) PRIMARY KEY,
    email               VARCHAR(255) UNIQUE,
    name                VARCHAR(100),
    created_at          TIMESTAMP DEFAULT NOW(),
    last_active         TIMESTAMP
);


-- ═══════════════════════════════════════════════════════════════════════
-- PROJECTS (Optional - for folder feature)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE projects (
    project_id                  VARCHAR(50) PRIMARY KEY,
    user_id                     VARCHAR(50) NOT NULL,
    name                        VARCHAR(255) NOT NULL,
    default_extraction_prompt   TEXT,           -- Saved prompt for this project
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX idx_projects_user ON projects(user_id);


-- ═══════════════════════════════════════════════════════════════════════
-- CHATS (Can be standalone or inside a project)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE chats (
    chat_id                     VARCHAR(50) PRIMARY KEY,
    user_id                     VARCHAR(50) NOT NULL,
    project_id                  VARCHAR(50),            -- NULL if standalone chat
    title                       VARCHAR(255) DEFAULT 'New Chat',

    -- Active document for RAG
    active_document_id          VARCHAR(50),            -- Most recent document

    -- Chat history summarization
    summary                     TEXT,
    summary_updated_at          TIMESTAMP,
    message_count               INTEGER DEFAULT 0,

    -- Timestamps
    created_at                  TIMESTAMP DEFAULT NOW(),
    updated_at                  TIMESTAMP DEFAULT NOW(),
    is_archived                 BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
);

CREATE INDEX idx_chats_user ON chats(user_id);
CREATE INDEX idx_chats_project ON chats(project_id);


-- ═══════════════════════════════════════════════════════════════════════
-- CHAT_DOCUMENTS (Multiple documents per chat)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE chat_documents (
    id                          SERIAL PRIMARY KEY,
    chat_id                     VARCHAR(50) NOT NULL,
    document_id                 VARCHAR(50) NOT NULL,   -- ID in Elasticsearch
    document_name               VARCHAR(255),
    upload_order                INTEGER,                -- 1, 2, 3... (sequence)

    -- Extraction status for this document
    extraction_done             BOOLEAN DEFAULT FALSE,
    extraction_prompt           TEXT,                   -- Prompt used
    extraction_result_url       VARCHAR(500),           -- Excel download URL
    extraction_row_count        INTEGER,

    created_at                  TIMESTAMP DEFAULT NOW(),

    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE
);

CREATE INDEX idx_chat_documents_chat ON chat_documents(chat_id);
CREATE INDEX idx_chat_documents_order ON chat_documents(chat_id, upload_order DESC);


-- ═══════════════════════════════════════════════════════════════════════
-- MESSAGES (Chat history)
-- ═══════════════════════════════════════════════════════════════════════
CREATE TABLE messages (
    message_id                  VARCHAR(50) PRIMARY KEY,
    chat_id                     VARCHAR(50) NOT NULL,
    document_id                 VARCHAR(50),            -- Which doc this message is about (optional)
    role                        VARCHAR(20) NOT NULL,   -- 'user' or 'assistant'
    content                     TEXT NOT NULL,
    sequence_num                INTEGER,
    is_summarized               BOOLEAN DEFAULT FALSE,
    created_at                  TIMESTAMP DEFAULT NOW(),

    -- Message rendering (for UI display)
    message_type                VARCHAR(20) DEFAULT 'text',  -- 'text', 'file_upload', 'file_generated', 'system'

    -- File upload fields (when user uploads PDF)
    attached_file_name          VARCHAR(255),
    attached_file_size          BIGINT,                      -- bytes

    -- Generated file fields (when bot generates Excel)
    generated_file_url          VARCHAR(500),
    generated_file_name         VARCHAR(255),
    generated_file_metadata     JSONB,                       -- {"row_count": 25}

    -- References (for RAG answers with highlighting)
    references                  JSONB,                       -- [{"page": 1, "bbox": {...}}]

    FOREIGN KEY (chat_id) REFERENCES chats(chat_id) ON DELETE CASCADE,
    CONSTRAINT messages_type_check CHECK (message_type IN ('text', 'file_upload', 'file_generated', 'system'))
);

CREATE INDEX idx_messages_chat ON messages(chat_id);
CREATE INDEX idx_messages_sequence ON messages(chat_id, sequence_num);
```

### Schema Relationships

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  users                                                                  │
│    │                                                                    │
│    ├──< projects (optional)                                             │
│    │       │                                                            │
│    │       │   ┌── default_extraction_prompt                           │
│    │       │                                                            │
│    │       └──< chats (chats inside project)                           │
│    │                                                                    │
│    └──< chats (standalone chats - no project)                          │
│          │                                                              │
│          │   ┌── active_document_id                                    │
│          │   ├── summary                                               │
│          │                                                              │
│          ├──< chat_documents (multiple docs per chat)                  │
│          │       │                                                      │
│          │       ├── doc_001 (COA_001.pdf) - upload_order: 1           │
│          │       ├── doc_002 (COA_002.pdf) - upload_order: 2           │
│          │       └── doc_003 (COA_003.pdf) - upload_order: 3 [ACTIVE]  │
│          │                                                              │
│          └──< messages                                                  │
│                  │                                                      │
│                  ├── msg_001 (about doc_001)                           │
│                  ├── msg_002 (about doc_001)                           │
│                  ├── msg_003 (about doc_002)                           │
│                  └── msg_004 (general question)                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Default Flow: Multi-Document Chat

### User Flow

```
STEP 1: User clicks "+ New Chat"
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    New chat created (chat_id generated)
        │
        ▼
STEP 2: User uploads first document (COA_001.pdf)
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • Document processed → stored in Elasticsearch (document_id: doc_001)
    • chat_documents record created (upload_order: 1)
    • active_document_id = doc_001
        │
        ▼
STEP 3: User asks "Extract Sample Summary to Excel"
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • RAG query on doc_001 (active)
    • Claude extracts → Excel generated
    • extraction_prompt saved in chat_documents
        │
        ▼
STEP 4: User uploads second document (COA_002.pdf) - SAME CHAT
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • Document processed → stored in Elasticsearch (document_id: doc_002)
    • chat_documents record created (upload_order: 2)
    • active_document_id = doc_002 (updated!)
        │
        ▼
STEP 5: User asks "Extract same data" or clicks "Run extraction"
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • Previous extraction_prompt suggested (from last doc)
    • RAG query on doc_002 (active)
    • Same format Excel generated
        │
        ▼
STEP 6: User asks "What was batch in first document?"
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • Keyword detection: "first" → doc_001
    • RAG query on doc_001
    • Claude answers from first document
```

---

## Efficient RAG Solution

### Performance Target

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  EFFICIENT SOLUTION: ~1.6 seconds total                                │
│  ═══════════════════════════════════════                                │
│                                                                         │
│  1. DB Query (chat + documents)         ~50ms                           │
│  2. Keyword detection (no Claude)       ~1ms                            │
│  3. Elasticsearch RAG                   ~100ms                          │
│  4. ONE Claude call                     ~1500ms                         │
│  ─────────────────────────────────────────────                          │
│  TOTAL:                                 ~1.65 seconds                   │
│                                                                         │
│  ✅ NO extra Claude call for document detection                         │
│  ✅ Single Claude call for answer                                       │
│  ✅ Same speed as single-document chat                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Flow Diagram

```
USER: "What is batch number?"
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Get chat + all documents (ONE query)               ~50ms       │
│─────────────────────────────────────────────────────────────────────────│
│                                                                         │
│  SELECT c.*, cd.document_id, cd.document_name, cd.upload_order         │
│  FROM chats c                                                           │
│  LEFT JOIN chat_documents cd ON c.chat_id = cd.chat_id                 │
│  WHERE c.chat_id = 'chat_123'                                          │
│  ORDER BY cd.upload_order ASC                                           │
│                                                                         │
│  Returns:                                                               │
│  • active_document_id: doc_003                                         │
│  • documents: [doc_001, doc_002, doc_003]                              │
│  • summary: "User analyzed COA documents..."                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Keyword detection for target document              ~1ms        │
│─────────────────────────────────────────────────────────────────────────│
│                                                                         │
│  "first", "initial"    → doc_001 (first uploaded)                      │
│  "previous", "before"  → doc_002 (second to last)                      │
│  "all", "compare"      → [doc_001, doc_002, doc_003]                   │
│  (default)             → doc_003 (active)                              │
│                                                                         │
│  Result: target_doc = doc_003 (no keyword detected)                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Elasticsearch RAG (hybrid search)                  ~100ms      │
│─────────────────────────────────────────────────────────────────────────│
│                                                                         │
│  {                                                                      │
│    "query": {                                                           │
│      "bool": {                                                          │
│        "must": [{"term": {"document_id": "doc_003"}}],                 │
│        "should": [                                                      │
│          {"match": {"content": "batch number"}},                       │
│          {"knn": {"embedding": query_vector, "k": 5}}                  │
│        ]                                                                │
│      }                                                                  │
│    }                                                                    │
│  }                                                                      │
│                                                                         │
│  Returns: chunks with content + bbox                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ STEP 4: ONE Claude call with full context                  ~1500ms     │
│─────────────────────────────────────────────────────────────────────────│
│                                                                         │
│  SYSTEM PROMPT:                                                         │
│  "Documents in chat:                                                    │
│   1. COA_001.pdf                                                       │
│   2. COA_002.pdf                                                       │
│   3. COA_003.pdf [ACTIVE]                                              │
│   Currently answering from: COA_003.pdf"                               │
│                                                                         │
│  + Summary (previous context)                                           │
│  + Last 20 messages                                                     │
│  + RAG results                                                          │
│  + User question                                                        │
│                                                                         │
│  Claude responds: "The batch number is 96309DB..."                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Keyword Detection Logic

```python
def detect_target_document(message: str, doc_ids: list, active_doc_id: str):
    """
    Quick keyword detection - NO Claude call needed!
    Handles 95%+ of cases efficiently
    """
    msg = message.lower()

    # First document
    if any(w in msg for w in ["first", "initial", "earliest", "1st", "original"]):
        return doc_ids[0]

    # Second document
    elif any(w in msg for w in ["second", "2nd"]):
        return doc_ids[1] if len(doc_ids) > 1 else doc_ids[-1]

    # Third document
    elif any(w in msg for w in ["third", "3rd"]):
        return doc_ids[2] if len(doc_ids) > 2 else doc_ids[-1]

    # Previous document
    elif any(w in msg for w in ["previous", "before", "earlier", "last one", "prior"]):
        return doc_ids[-2] if len(doc_ids) > 1 else doc_ids[-1]

    # All documents
    elif any(w in msg for w in ["all", "compare", "every", "both", "across"]):
        return doc_ids  # Return all for multi-doc query

    # Default: active (most recent) document
    else:
        return active_doc_id
```

---

## Additional Feature: Projects/Folders

### When to Use Projects

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  USE STANDALONE CHAT (Default):                                        │
│  ──────────────────────────────                                         │
│  • Quick one-off document analysis                                      │
│  • Ad-hoc extraction                                                    │
│  • No need for saved prompts                                            │
│                                                                         │
│  USE PROJECT (Additional):                                              │
│  ─────────────────────────                                              │
│  • Processing same document type regularly                              │
│  • Want to save extraction prompt                                       │
│  • Need organized folder structure                                      │
│  • Team sharing (future feature)                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Project Flow

```
STEP 1: User clicks "+ New Project"
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    ┌─────────────────────────────────────────┐
    │ Create Project                          │
    │                                         │
    │ Name: COA Processing                    │
    │                                         │
    │ Default Extraction Prompt:              │
    │ ┌─────────────────────────────────────┐ │
    │ │ Extract Sample Summary tables with  │ │
    │ │ columns: Sample ID, Concentration,  │ │
    │ │ pH, Temperature                     │ │
    │ └─────────────────────────────────────┘ │
    │                                         │
    │ [Create]                                │
    └─────────────────────────────────────────┘
        │
        ▼
STEP 2: Project created, user uploads document
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • New chat created INSIDE project
    • Document uploaded to chat
    • Extraction prompt auto-suggested from project
        │
        ▼
STEP 3: User clicks "Run" - extraction with saved prompt
─────────────────────────────────────────────────────────────────────────
        │
        ▼
    • Same prompt used every time
    • Consistent output format
    • No retyping needed!
```

---

## UI Design

### Main Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LOGO                                                   [User] [Settings]│
├────────────────────┬────────────────────────────────────────────────────┤
│                    │                                                    │
│     SIDEBAR        │                    MAIN CONTENT                    │
│     (240px)        │                                                    │
│                    │                                                    │
│  [+ New Chat]      │                                                    │
│  [+ New Project]   │                                                    │
│                    │                                                    │
│  ──────────────    │                                                    │
│                    │                                                    │
│  RECENT CHATS      │                                                    │
│                    │                                                    │
│  💬 COA Analysis   │ ← Standalone chat (multi-doc)                     │
│  💬 Invoice Review │                                                    │
│                    │                                                    │
│  ──────────────    │                                                    │
│                    │                                                    │
│  PROJECTS          │                                                    │
│                    │                                                    │
│  📁 COA Processing │ ← Project with saved prompt                       │
│   └─ 💬 Batch 1    │ ← Chat inside project                             │
│                    │                                                    │
│  📁 Invoices       │                                                    │
│                    │                                                    │
└────────────────────┴────────────────────────────────────────────────────┘
```

### Chat View (Multi-Document)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  💬 COA Analysis                                         [⚙️] [📥]      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Documents in this chat:                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 📄 COA_001.pdf (Jan 15)                                         │   │
│  │ 📄 COA_002.pdf (Jan 18)                                         │   │
│  │ 📄 COA_003.pdf (Jan 20) ← Active                    [+ Add Doc] │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  [User]: Extract Sample Summary tables to Excel                         │
│          📄 Using: COA_001.pdf                                         │
│                                                                         │
│  [Bot]: ✅ Extracted 25 rows from COA_001.pdf                          │
│         [📥 Download Excel]                                             │
│                                                                         │
│  [System]: 📄 COA_002.pdf uploaded                                     │
│                                                                         │
│  [User]: Extract same data                                              │
│          📄 Using: COA_002.pdf (active)                                │
│                                                                         │
│  [Bot]: ✅ Extracted 30 rows from COA_002.pdf                          │
│         [📥 Download Excel]                                             │
│                                                                         │
│  [User]: What was batch number in first document?                       │
│                                                                         │
│  [Bot]: In COA_001.pdf (first document), the batch number is 96309DB   │
│         📍 Page 2                                                       │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Type message...                                           [Send] │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Project View (with Saved Prompt)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📁 COA Processing                                       [⚙️ Settings]  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Default Extraction Prompt:                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ "Extract Sample Summary tables with columns:                    │   │
│  │  Sample ID, Concentration, pH, Temperature"                 ✏️  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ─────────────────────────────────────────────────────────────────────  │
│                                                                         │
│  Chats in this project:                                                 │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ 💬 Batch 1      │  │ 💬 Batch 2      │  │ [+ New Chat]    │        │
│  │                 │  │                 │  │                 │        │
│  │ 3 documents     │  │ 2 documents     │  │                 │        │
│  │ Last: Jan 20    │  │ Last: Jan 18    │  │                 │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Chats

```
POST   /api/chats                           Create new chat
GET    /api/chats                           List user's chats
GET    /api/chats/{chat_id}                 Get chat with documents
DELETE /api/chats/{chat_id}                 Delete chat
```

### Documents in Chat

```
POST   /api/chats/{chat_id}/documents       Upload document to chat
GET    /api/chats/{chat_id}/documents       List documents in chat
DELETE /api/chats/{chat_id}/documents/{id}  Remove document from chat
```

### Messages

```
GET    /api/chats/{chat_id}/messages        Get chat messages
POST   /api/chats/{chat_id}/messages        Send message (Q&A or extraction)
```

### Projects (Additional Feature)

```
POST   /api/projects                        Create new project
GET    /api/projects                        List user's projects
GET    /api/projects/{project_id}           Get project with chats
PATCH  /api/projects/{project_id}           Update project (name, prompt)
DELETE /api/projects/{project_id}           Delete project
POST   /api/projects/{project_id}/chats     Create chat inside project
```

### Request/Response Examples

```
POST /api/chats/{chat_id}/documents
─────────────────────────────────────────────────────────────
Request:
{
  "file": <uploaded PDF>
}

Response:
{
  "document_id": "doc_003",
  "document_name": "COA_003.pdf",
  "upload_order": 3,
  "is_active": true,
  "previous_extraction_prompt": "Extract Sample Summary..."  // From last doc
}


POST /api/chats/{chat_id}/messages
─────────────────────────────────────────────────────────────
Request:
{
  "content": "What was batch in first document?"
}

Response:
{
  "message_id": "msg_123",
  "role": "assistant",
  "content": "In COA_001.pdf (first document), the batch number is 96309DB",
  "document_used": "doc_001",
  "references": [
    {
      "page": 2,
      "bbox": {"left": 0.08, "top": 0.18, "right": 0.45, "bottom": 0.25}
    }
  ]
}
```

---

## Implementation Code

### Process Message (Efficient Solution)

```python
import uuid
from datetime import datetime

def process_message(chat_id: str, user_message: str):
    """
    EFFICIENT: Single Claude call, keyword-based document detection
    Total latency: ~1.6 seconds
    """

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: Get chat + all documents (ONE query) - ~50ms
    # ═══════════════════════════════════════════════════════════════

    chat_data = db.execute("""
        SELECT
            c.chat_id, c.summary, c.active_document_id, c.project_id,
            p.default_extraction_prompt,
            array_agg(cd.document_id ORDER BY cd.upload_order) as doc_ids,
            array_agg(cd.document_name ORDER BY cd.upload_order) as doc_names
        FROM chats c
        LEFT JOIN projects p ON c.project_id = p.project_id
        LEFT JOIN chat_documents cd ON c.chat_id = cd.chat_id
        WHERE c.chat_id = %s
        GROUP BY c.chat_id, p.project_id
    """, [chat_id]).fetchone()

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: Keyword detection for target document - ~1ms
    # ═══════════════════════════════════════════════════════════════

    target_doc_ids = detect_target_document(
        message=user_message,
        doc_ids=chat_data.doc_ids,
        active_doc_id=chat_data.active_document_id
    )

    # Handle single doc or multiple docs
    if isinstance(target_doc_ids, list):
        document_ids = target_doc_ids
    else:
        document_ids = [target_doc_ids]

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: RAG search in Elasticsearch - ~100ms
    # ═══════════════════════════════════════════════════════════════

    rag_results = elasticsearch_hybrid_search(
        query=user_message,
        document_ids=document_ids
    )

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: Build prompt with document context
    # ═══════════════════════════════════════════════════════════════

    doc_list = build_document_list(
        doc_names=chat_data.doc_names,
        doc_ids=chat_data.doc_ids,
        active_doc_id=chat_data.active_document_id
    )

    system_prompt = f"""You are a document assistant.

Documents in this chat:
{doc_list}

Currently answering from: {get_active_doc_name(chat_data)}

If user asks about specific document, mention which document you're referencing."""

    # Get last 20 messages
    messages = get_recent_messages(chat_id, limit=20)

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: ONE Claude call - ~1500ms
    # ═══════════════════════════════════════════════════════════════

    claude_messages = []

    # Add summary if exists
    if chat_data.summary:
        claude_messages.append({
            "role": "user",
            "content": f"Previous conversation context:\n{chat_data.summary}"
        })
        claude_messages.append({
            "role": "assistant",
            "content": "I understand the context. How can I help?"
        })

    # Add recent messages
    claude_messages.extend(messages)

    # Add RAG results + current question
    claude_messages.append({
        "role": "user",
        "content": f"""Document content:
{format_rag_results(rag_results)}

Question: {user_message}"""
    })

    response = call_claude(
        system=system_prompt,
        messages=claude_messages
    )

    # ═══════════════════════════════════════════════════════════════
    # STEP 6: Save message and return
    # ═══════════════════════════════════════════════════════════════

    save_message(chat_id, "user", user_message)
    save_message(chat_id, "assistant", response, document_id=document_ids[0])

    return {
        "content": response,
        "document_used": document_ids,
        "references": extract_references(rag_results)
    }


def detect_target_document(message: str, doc_ids: list, active_doc_id: str):
    """
    Quick keyword detection - NO Claude call needed!
    """
    if not doc_ids:
        return active_doc_id

    msg = message.lower()

    # First document
    if any(w in msg for w in ["first", "initial", "earliest", "1st", "original"]):
        return doc_ids[0]

    # Second document
    elif any(w in msg for w in ["second", "2nd"]):
        return doc_ids[1] if len(doc_ids) > 1 else doc_ids[-1]

    # Previous document
    elif any(w in msg for w in ["previous", "before", "earlier", "prior"]):
        return doc_ids[-2] if len(doc_ids) > 1 else doc_ids[-1]

    # All documents
    elif any(w in msg for w in ["all", "compare", "every", "both", "across"]):
        return doc_ids  # Return all

    # Default: active document
    else:
        return active_doc_id


def upload_document(chat_id: str, file) -> dict:
    """
    Upload document to chat and set as active
    """

    # Process document (Textract, chunking, Elasticsearch)
    document_id = process_and_store_document(file)

    # Get current document count for upload_order
    count = db.execute(
        "SELECT COUNT(*) FROM chat_documents WHERE chat_id = %s",
        [chat_id]
    ).fetchone()[0]

    # Add to chat_documents
    db.execute("""
        INSERT INTO chat_documents (chat_id, document_id, document_name, upload_order)
        VALUES (%s, %s, %s, %s)
    """, [chat_id, document_id, file.filename, count + 1])

    # Update active document
    db.execute("""
        UPDATE chats SET active_document_id = %s, updated_at = NOW()
        WHERE chat_id = %s
    """, [document_id, chat_id])

    # Get previous extraction prompt (if any)
    prev_prompt = db.execute("""
        SELECT extraction_prompt FROM chat_documents
        WHERE chat_id = %s AND extraction_prompt IS NOT NULL
        ORDER BY upload_order DESC LIMIT 1
    """, [chat_id]).fetchone()

    return {
        "document_id": document_id,
        "document_name": file.filename,
        "upload_order": count + 1,
        "is_active": True,
        "previous_extraction_prompt": prev_prompt[0] if prev_prompt else None
    }
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  MULTI-DOCUMENT CHAT WORKFLOW                                           │
│  ════════════════════════════                                           │
│                                                                         │
│  DEFAULT: Multi-Document Chat                                           │
│  • Multiple documents in ONE chat window                                │
│  • Upload docs → becomes active                                         │
│  • RAG uses active document by default                                  │
│  • Keyword detection for "first", "previous", "all"                    │
│  • Single Claude call (~1.6s latency)                                  │
│                                                                         │
│  ADDITIONAL: Project/Folder                                             │
│  • Saved extraction prompt                                              │
│  • Organized structure                                                  │
│  • Same multi-doc chat inside project                                   │
│                                                                         │
│  EFFICIENCY:                                                            │
│  • ONE DB query (chat + documents join)                                │
│  • Keyword detection (no Claude)                                        │
│  • ONE Elasticsearch query                                              │
│  • ONE Claude call                                                      │
│  • Total: ~1.6 seconds                                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 2.0*
*Last Updated: January 2026*
*Approach: Multi-Document Chat (Default) + Project/Folder (Additional)*
