# Database Schema - Entity Relationship Diagram

> **System:** OCR Chatbot with RAG
> **Database:** PostgreSQL + Elasticsearch
> **Version:** 2.0 (with file rendering support)
> **Created:** January 2026

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                    DATABASE ARCHITECTURE                                    │
│                                                                             │
│                                                                             │
│  ┌──────────────────┐                                                       │
│  │     users        │                                                       │
│  ├──────────────────┤                                                       │
│  │ PK user_id       │                                                       │
│  │    email         │                                                       │
│  │    full_name     │                                                       │
│  └────────┬─────────┘                                                       │
│           │                                                                 │
│           │ 1:N (one user has many chats)                                   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌──────────────────┐                                                       │
│  │     chats        │                                                       │
│  ├──────────────────┤                                                       │
│  │ PK chat_id       │                                                       │
│  │ FK user_id       │                                                       │
│  │ FK active_doc_id │◀────────┐                                             │
│  │    title         │         │                                             │
│  │    summary       │         │                                             │
│  │    message_count │         │                                             │
│  └────────┬─────────┘         │                                             │
│           │                   │                                             │
│           │ 1:N               │                                             │
│           │                   │                                             │
│  ┌────────┴──────────┐        │                                             │
│  │                   │        │                                             │
│  ▼                   ▼        │                                             │
│  ┌──────────────────┐ ┌───────┴──────────┐                                 │
│  │    messages      │ │ chat_documents   │                                 │
│  ├──────────────────┤ ├──────────────────┤                                 │
│  │ PK message_id    │ │ PK id            │                                 │
│  │ FK chat_id       │ │ FK chat_id       │                                 │
│  │ FK document_id   │◀┼─   document_id   │ ← Links to Elasticsearch       │
│  │    role          │ │    document_name │                                 │
│  │    content       │ │    upload_order  │                                 │
│  │    sequence_num  │ │    extraction... │                                 │
│  │                  │ │    ...prompt     │                                 │
│  │ NEW FIELDS:      │ │    page_count    │                                 │
│  │  message_type    │ └──────────────────┘                                 │
│  │  attached_file...│          │                                           │
│  │  generated_file..│          │ Logical Link                              │
│  │  references      │          │ (document_id)                             │
│  └──────────────────┘          │                                           │
│                                │                                           │
│  ══════════════════════════════▼═════════════════════════════════════════  │
│                                                                             │
│                      ELASTICSEARCH INDEX                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    document_chunks                                  │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │ • document_id (keyword)         ← Links back to chat_documents     │   │
│  │ • content (text)                ← For keyword search (BM25)         │   │
│  │ • embedding (vector, 1536-dim)  ← For semantic search (KNN)        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Table Descriptions

### **PostgreSQL Tables**

| Table              | Purpose           | Key Fields                                                                                                      |
| ------------------ | ----------------- | --------------------------------------------------------------------------------------------------------------- |
| **users**          | User accounts     | user_id (PK), email, full_name                                                                                  |
| **chats**          | Chat sessions     | chat_id (PK), user_id (FK), active_document_id, summary                                                         |
| **chat_documents** | Documents in chat | chat_id (FK), document_id, upload_order, extraction_prompt                                                      |
| **messages**       | Chat history      | message*id (PK), chat_id (FK), role, content, **message_type**, \*\*attached_file***\*, **generated*file*\*\*\* |

### **Elasticsearch Index**

| Index               | Purpose            | Key Fields                                               |
| ------------------- | ------------------ | -------------------------------------------------------- |
| **document_chunks** | Searchable content | document_id, content (text), embedding (vector 1536-dim) |

---

## Messages Table (Extended Schema)

### **Core Fields (Existing)**

```sql
message_id                  VARCHAR(50) PRIMARY KEY
chat_id                     VARCHAR(50) NOT NULL
document_id                 VARCHAR(50)
role                        VARCHAR(20) NOT NULL
content                     TEXT NOT NULL
sequence_num                INTEGER
is_summarized               BOOLEAN DEFAULT FALSE
created_at                  TIMESTAMP DEFAULT NOW()
```

### **NEW Fields (For File Rendering)**

```sql
-- Message type (determines UI rendering)
message_type                VARCHAR(20) DEFAULT 'text'
  -- Values: 'text', 'file_upload', 'file_generated', 'system'

-- File upload (PDF uploads)
attached_file_name          VARCHAR(255)
attached_file_size          BIGINT

-- Generated files (Excel outputs)
generated_file_url          VARCHAR(500)
generated_file_name         VARCHAR(255)
generated_file_metadata     JSONB

-- References (for RAG highlighting)
references                  JSONB
```

---

## Relationships

```
users → chats
  • One user has many chats
  • FK: chats.user_id → users.user_id

chats → chat_documents
  • One chat has multiple documents
  • FK: chat_documents.chat_id → chats.chat_id
  • Order: upload_order (1, 2, 3...)

chats → messages
  • One chat has many messages
  • FK: messages.chat_id → chats.chat_id
  • Order: sequence_num (1, 2, 3...)

chat_documents ↔ Elasticsearch document_chunks
  • One document has many chunks
  • Link: chat_documents.document_id = document_chunks.document_id
  • No FK (different databases)
```

---

## Message Types Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  MULTI-DOCUMENT CHAT WITH FILE RENDERING                                    │
│                                                                             │
│  Step 1: User uploads COA_001.pdf                                           │
│  ───────────────────────────────────────────────────────────────────────   │
│  • Create chat_documents (upload_order: 1)                                  │
│  • Create message (message_type: 'file_upload')                             │
│  • UI shows file card: 📄 COA_001.pdf                                      │
│                                                                             │
│  Step 2: User asks "What is the pH?"                                        │
│  ───────────────────────────────────────────────────────────────────────   │
│  • Create message (message_type: 'text')                                    │
│  • RAG searches Elasticsearch                                               │
│  • Bot responds with references                                             │
│  • UI shows: "pH is 6.1" + [Page 1] button                                 │
│                                                                             │
│  Step 3: User asks "Extract to Excel"                                       │
│  ───────────────────────────────────────────────────────────────────────   │
│  • Create message (message_type: 'text')                                    │
│  • System extracts data → Generate Excel                                    │
│  • Create message (message_type: 'file_generated')                          │
│  • UI shows download button: 📊 [Download Excel]                           │
│  • Save extraction_prompt in chat_documents                                 │
│                                                                             │
│  Step 4: User uploads COA_002.pdf (SAME CHAT)                              │
│  ───────────────────────────────────────────────────────────────────────   │
│  • Create chat_documents (upload_order: 2)                                  │
│  • Update active_document_id = "doc_002"                                    │
│  • Suggest previous extraction_prompt                                       │
│  • User reuses prompt → consistent output                                   │
│                                                                             │
│  Step 5: User reopens chat (Next day)                                       │
│  ───────────────────────────────────────────────────────────────────────   │
│  • Load all messages ordered by sequence_num                                │
│  • Render based on message_type:                                            │
│    - file_upload → Show file card                                           │
│    - file_generated → Show download button                                  │
│    - text → Show text + references                                          │
│  • All files still accessible!                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

```
✓ Multi-Document Chat
  • Multiple PDFs in one chat
  • Tracked by upload_order

✓ File Upload History
  • PDF uploads saved as messages
  • message_type: 'file_upload'
  • Shows file card in UI

✓ Generated File Download
  • Excel outputs saved as messages
  • message_type: 'file_generated'
  • Download button always works

✓ Prompt Reuse
  • extraction_prompt saved in chat_documents
  • Suggested for next document
  • Consistent extraction format

✓ RAG with Highlighting
  • references field stores bbox data
  • Links to Elasticsearch chunks
  • Click button → highlight PDF

✓ Chat History
  • All messages ordered by sequence_num
  • Old messages summarized (summary field)
  • Persistent across sessions
```

---

## Data Storage Example

```sql
-- Chat with 2 documents
INSERT INTO chats VALUES ('chat_123', 'user_001', 'doc_002', 'COA Analysis', NULL, 6);

-- Document 1
INSERT INTO chat_documents VALUES (1, 'chat_123', 'doc_001', 'COA_001.pdf', 1,
    'Extract Sample Summary', TRUE);

-- Document 2
INSERT INTO chat_documents VALUES (2, 'chat_123', 'doc_002', 'COA_002.pdf', 2,
    'Extract Sample Summary', TRUE);

-- Messages
INSERT INTO messages VALUES ('msg_001', 'chat_123', 'user', 'file_upload',
    'Uploaded', 'COA_001.pdf', 1234567, NULL, NULL, NULL, NULL, 1);

INSERT INTO messages VALUES ('msg_002', 'chat_123', 'user', 'text',
    'Extract Sample Summary', NULL, NULL, NULL, NULL, NULL, NULL, 2);

INSERT INTO messages VALUES ('msg_003', 'chat_123', 'assistant', 'file_generated',
    'Extracted 25 rows', NULL, NULL, '/downloads/excel_001.xlsx',
    'COA_001_extraction.xlsx', '{"row_count":25}', NULL, 3);

INSERT INTO messages VALUES ('msg_004', 'chat_123', 'user', 'file_upload',
    'Uploaded', 'COA_002.pdf', 1456789, NULL, NULL, NULL, NULL, 4);

INSERT INTO messages VALUES ('msg_005', 'chat_123', 'assistant', 'file_generated',
    'Extracted 30 rows', NULL, NULL, '/downloads/excel_002.xlsx',
    'COA_002_extraction.xlsx', '{"row_count":30}', NULL, 5);
```

**UI Renders:**

```
[User] 📎 COA_001.pdf
[User] Extract Sample Summary
[Bot] Extracted 25 rows [⬇ Download Excel]
[User] 📎 COA_002.pdf
[Bot] Extracted 30 rows [⬇ Download Excel]
```

---

_Document Version: 2.0_
_Created: January 2026_
_Schema aligned with: MULTI_DOCUMENT_WORKFLOW.md, MESSAGE_RENDERING_SYSTEM.md_
