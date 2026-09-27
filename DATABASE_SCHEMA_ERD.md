# Database Schema - Entity Relationship Diagram

> **System:** OCR Chatbot with RAG (Retrieval-Augmented Generation)
> **Database:** PostgreSQL (relational) + Elasticsearch (vector search)
> **Version:** 1.0
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
│  │    created_at    │                                                       │
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
│  │    created_at    │         │                                             │
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
│  │    content       │ │    upload_order  │ ← (1, 2, 3...)                 │
│  │    sequence_num  │ │    extraction... │ ← Saved extraction prompt      │
│  │    is_summarized │ │    ...prompt     │                                 │
│  │    created_at    │ │    page_count    │                                 │
│  └──────────────────┘ │    created_at    │                                 │
│                       └────────┬─────────┘                                 │
│                                │                                           │
│                                │ Logical Link                              │
│                                │ (document_id)                             │
│                                │                                           │
│  ══════════════════════════════▼═══════════════════════════════════════   │
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

| Table | Purpose | Key Fields |
|-------|---------|------------|
| **users** | User accounts | user_id (PK), email, full_name |
| **chats** | Chat sessions | chat_id (PK), user_id (FK), active_document_id, summary |
| **chat_documents** | Documents in chat | chat_id (FK), document_id, upload_order, extraction_prompt |
| **messages** | Chat history | message_id (PK), chat_id (FK), role, content, sequence_num |

### **Elasticsearch Index**

| Index | Purpose | Key Fields |
|-------|---------|------------|
| **document_chunks** | Searchable content | document_id, content (text), embedding (vector 1536-dim) |

---

## Relationships

```
users → chats
  • One user can have many chats
  • Relationship: 1:N
  • Foreign Key: chats.user_id → users.user_id

chats → chat_documents
  • One chat can have multiple documents
  • Relationship: 1:N
  • Foreign Key: chat_documents.chat_id → chats.chat_id
  • Order: upload_order (1, 2, 3...)

chats → messages
  • One chat has many messages
  • Relationship: 1:N
  • Foreign Key: messages.chat_id → chats.chat_id

chat_documents ↔ Elasticsearch document_chunks
  • One document has many chunks
  • Relationship: 1:N (logical, no FK)
  • Link: chat_documents.document_id = document_chunks.document_id
```

---

## Multi-Document Chat with Prompt Reuse

### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  MULTI-DOCUMENT WORKFLOW (Same Chat)                                        │
│                                                                             │
│  Step 1: User uploads COA_001.pdf                                           │
│  ─────────────────────────────────────────────────────────────────────────│
│  • Create chat_documents record:                                            │
│    - document_id: "doc_001"                                                 │
│    - upload_order: 1                                                        │
│    - extraction_prompt: NULL (not extracted yet)                            │
│                                                                             │
│  • Update chats:                                                            │
│    - active_document_id = "doc_001"                                         │
│                                                                             │
│                                                                             │
│  Step 2: User asks "Extract Sample Summary to Excel"                        │
│  ─────────────────────────────────────────────────────────────────────────│
│  • System performs extraction on doc_001                                    │
│  • Saves prompt to database:                                                │
│    UPDATE chat_documents                                                    │
│    SET extraction_prompt = "Extract Sample Summary to Excel",              │
│        extraction_done = TRUE                                               │
│    WHERE document_id = "doc_001"                                            │
│                                                                             │
│  • Returns Excel file                                                       │
│                                                                             │
│                                                                             │
│  Step 3: User uploads COA_002.pdf (SAME CHAT)                              │
│  ─────────────────────────────────────────────────────────────────────────│
│  • Create chat_documents record:                                            │
│    - document_id: "doc_002"                                                 │
│    - upload_order: 2                                                        │
│    - extraction_prompt: NULL                                                │
│                                                                             │
│  • Update chats:                                                            │
│    - active_document_id = "doc_002" (now active)                            │
│                                                                             │
│                                                                             │
│  Step 4: System suggests previous prompt                                    │
│  ─────────────────────────────────────────────────────────────────────────│
│  Query:                                                                     │
│  SELECT extraction_prompt FROM chat_documents                               │
│  WHERE chat_id = "chat_123"                                                 │
│    AND extraction_prompt IS NOT NULL                                        │
│  ORDER BY upload_order DESC                                                 │
│  LIMIT 1                                                                    │
│                                                                             │
│  Returns: "Extract Sample Summary to Excel"                                 │
│                                                                             │
│  UI shows:                                                                  │
│  ┌─────────────────────────────────────────────────────────┐               │
│  │ 📄 COA_002.pdf uploaded                                │               │
│  │                                                         │               │
│  │ Previous extraction prompt:                             │               │
│  │ "Extract Sample Summary to Excel"                       │               │
│  │                                                         │               │
│  │ [Run Same Extraction] [Modify Prompt]                   │               │
│  └─────────────────────────────────────────────────────────┘               │
│                                                                             │
│                                                                             │
│  Step 5: User clicks [Run Same Extraction]                                  │
│  ─────────────────────────────────────────────────────────────────────────│
│  • System uses saved prompt on doc_002                                      │
│  • No need to retype!                                                       │
│  • Consistent extraction format                                             │
│                                                                             │
│  UPDATE chat_documents                                                      │
│  SET extraction_prompt = "Extract Sample Summary to Excel",                │
│      extraction_done = TRUE                                                 │
│  WHERE document_id = "doc_002"                                              │
│                                                                             │
│  • Returns Excel file with same structure                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Example

```
1. User uploads COA_001.pdf
   ↓
2. Store in chat_documents:
   • document_id: "doc_001"
   • upload_order: 1
   • extraction_prompt: NULL
   ↓
3. Process with Textract → Extract text
   ↓
4. Generate embeddings
   ↓
5. Store in Elasticsearch:
   • document_id: "doc_001"
   • content: "Test results..."
   • embedding: [0.1, 0.2, ...]
   ↓
6. User: "Extract Sample Summary to Excel"
   ↓
7. System performs extraction
   ↓
8. Save prompt:
   UPDATE chat_documents
   SET extraction_prompt = "Extract Sample Summary to Excel"
   WHERE document_id = "doc_001"
   ↓
9. User uploads COA_002.pdf
   ↓
10. System checks previous prompt:
    SELECT extraction_prompt FROM chat_documents
    WHERE chat_id = "chat_123"
    ORDER BY upload_order DESC LIMIT 1
    ↓
11. Suggest: "Extract Sample Summary to Excel"
    ↓
12. User confirms → Apply same prompt to doc_002
    ↓
13. Consistent Excel output!
```

---

## Key Benefits

```
✓ Multi-Document in One Chat
  • Upload multiple PDFs to same conversation
  • Tracked by upload_order (1, 2, 3...)
  • No need to create separate chats

✓ Prompt Reuse
  • First document: User types extraction prompt
  • Second document: System suggests same prompt
  • Saves time, ensures consistency

✓ Active Document Tracking
  • active_document_id points to most recent upload
  • Used for RAG queries
  • Automatically updates on new upload

✓ Chat History
  • All messages stored with sequence_num
  • Old messages summarized (summary field)
  • Last 20 messages kept unsummarized
```

---

*Document Version: 1.0*
*Created: January 2026*
*For: Manager Review & Architecture Design*
*Key Feature: Multi-document chat with automatic prompt reuse*
