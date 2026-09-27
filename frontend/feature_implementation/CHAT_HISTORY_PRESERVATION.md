# Chat History Preservation & Sending to Claude

> **Document Purpose:** Complete architecture for preserving chat history, managing sessions, and efficiently sending context to Claude
> **Approach:** Summarization (Option B - Threshold Based) + Last 20 Messages + RAG
> **Compatible With:** MULTI_DOCUMENT_WORKFLOW.md (multi-document per chat)
> **Created:** January 2026
> **Updated:** January 2026

---

## Table of Contents

1. [Chat Structure Overview](#chat-structure-overview)
2. [Database Schema](#database-schema)
3. [Session & Chat Management](#session--chat-management)
4. [Summarization Strategy](#summarization-strategy)
5. [Sending to Claude](#sending-to-claude)
6. [Complete Flow](#complete-flow)
7. [API Endpoints](#api-endpoints)

---

## Chat Structure Overview

### How Chats Are Organized

```
USER (logged in)
    │
    ├── Chat 1: "COA Analysis - ATX-101"      ← Each tab = 1 Chat
    │   ├── Message 1
    │   ├── Message 2
    │   └── ... 50 messages
    │
    ├── Chat 2: "Sample Summary Extraction"   ← Another tab
    │   ├── Message 1
    │   └── ... 30 messages
    │
    └── Chat 3: "Batch Comparison"            ← Another tab
        └── ... messages
```

### Key Concepts

| Term | Description | Example |
|------|-------------|---------|
| **User** | The logged-in person | user_id: "usr_abc123" |
| **Chat** | One conversation tab | chat_id: "chat_xyz789" |
| **Session** | Active browser session | session_id: "sess_123" (optional) |
| **Message** | Single Q or A | message_id: "msg_001" |
| **Summary** | Compressed old messages | "User discussed ATX-101..." |

### Visual Structure

```
┌─────────────────────────────────────────────────────────────┐
│  USER INTERFACE                                             │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │  Chat 1  │ │  Chat 2  │ │  Chat 3  │  ← Tabs            │
│  │ (active) │ │          │ │    +     │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  Chat 1 Messages:                                   │   │
│  │                                                     │   │
│  │  [User]: What is the batch number?                  │   │
│  │  [Bot]: The batch number is 96309DB...              │   │
│  │  [User]: Show me expiry date                        │   │
│  │  [Bot]: The expiry date is 2026-01-15...            │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Type your message...                          [Send]│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### Table 1: `users`

```
┌─────────────────────────────────────────────────────────────┐
│  users                                                      │
├─────────────────────────────────────────────────────────────┤
│  user_id         VARCHAR(50)   PRIMARY KEY                  │
│  email           VARCHAR(255)  UNIQUE                       │
│  name            VARCHAR(100)                               │
│  created_at      TIMESTAMP     DEFAULT NOW()                │
│  last_active     TIMESTAMP                                  │
└─────────────────────────────────────────────────────────────┘
```

### Table 2: `chats` (Each Tab)

```
┌─────────────────────────────────────────────────────────────┐
│  chats                                                      │
├─────────────────────────────────────────────────────────────┤
│  chat_id             VARCHAR(50)   PRIMARY KEY              │
│  user_id             VARCHAR(50)   FOREIGN KEY → users      │
│  project_id          VARCHAR(50)   FOREIGN KEY → projects   │
│                                    (NULL if standalone)     │
│  title               VARCHAR(255)  "COA Analysis"           │
│  active_document_id  VARCHAR(50)   Most recent document     │
│  summary             TEXT          Compressed old messages  │
│  summary_updated     TIMESTAMP     When summary last updated│
│  message_count       INTEGER       Total messages in chat   │
│  created_at          TIMESTAMP     DEFAULT NOW()            │
│  updated_at          TIMESTAMP     Last activity            │
│  is_archived         BOOLEAN       DEFAULT FALSE            │
└─────────────────────────────────────────────────────────────┘

NOTE: Multiple documents per chat are stored in chat_documents table.
      See MULTI_DOCUMENT_WORKFLOW.md for complete schema.
```

### Table 2b: `chat_documents` (Multiple Documents per Chat)

```
┌─────────────────────────────────────────────────────────────┐
│  chat_documents                                             │
├─────────────────────────────────────────────────────────────┤
│  id                  SERIAL        PRIMARY KEY              │
│  chat_id             VARCHAR(50)   FOREIGN KEY → chats      │
│  document_id         VARCHAR(50)   ID in Elasticsearch      │
│  document_name       VARCHAR(255)  "COA_001.pdf"            │
│  upload_order        INTEGER       1, 2, 3... (sequence)    │
│  extraction_done     BOOLEAN       DEFAULT FALSE            │
│  extraction_prompt   TEXT          Prompt used              │
│  created_at          TIMESTAMP     DEFAULT NOW()            │
└─────────────────────────────────────────────────────────────┘

WHY SEPARATE TABLE:
• Documents persist even after chat summarization
• Never lose track of which documents are in chat
• upload_order determines "first", "previous", etc.
```

### Table 3: `messages` (Each Message)

```
┌─────────────────────────────────────────────────────────────┐
│  messages                                                   │
├─────────────────────────────────────────────────────────────┤
│  message_id      VARCHAR(50)   PRIMARY KEY                  │
│  chat_id         VARCHAR(50)   FOREIGN KEY → chats          │
│  document_id     VARCHAR(50)   Which doc this msg is about  │
│                                (optional - for tracking)    │
│  role            VARCHAR(20)   "user" or "assistant"        │
│  content         TEXT          The actual message           │
│  created_at      TIMESTAMP     DEFAULT NOW()                │
│  sequence_num    INTEGER       Order in conversation (1,2,3)│
│  is_summarized   BOOLEAN       DEFAULT FALSE                │
│  metadata        JSONB         Extra info (see below)       │
└─────────────────────────────────────────────────────────────┘
```

### Message Metadata (JSONB)

```json
{
    "tokens_used": 150,
    "rag_chunks_used": ["chunk_id_1", "chunk_id_2"],
    "pages_referenced": [2, 5, 7],
    "processing_time_ms": 1200,
    "model_used": "claude-sonnet-4-20250514",
    "had_error": false
}
```

---

## Session & Chat Management

### When User Opens App (New Browser Session)

```
USER OPENS APP
      │
      ▼
┌─────────────────────────────────────────┐
│ 1. Authenticate user                    │
│    → Get user_id                        │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 2. Load user's chats                    │
│    SELECT * FROM chats                  │
│    WHERE user_id = ?                    │
│    ORDER BY updated_at DESC             │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 3. Display chat tabs                    │
│    - Show recent chats as tabs          │
│    - Show "+ New Chat" button           │
└─────────────────────────────────────────┘
```

### When User Creates New Chat

```
USER CLICKS "+ New Chat"
      │
      ▼
┌─────────────────────────────────────────┐
│ 1. Generate new chat_id                 │
│    chat_id = "chat_" + uuid()           │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 2. Insert into database                 │
│                                         │
│    INSERT INTO chats (                  │
│      chat_id,                           │
│      user_id,                           │
│      title,        -- "New Chat"        │
│      document_id,  -- NULL initially    │
│      summary,      -- NULL initially    │
│      message_count -- 0                 │
│    )                                    │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 3. User uploads document (optional)     │
│    → Update document_id, document_name  │
│    → Process document into RAG          │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 4. Auto-generate title after 1st message│
│    "What is batch number?" → "Batch     │
│    Number Query"                        │
└─────────────────────────────────────────┘
```

### When User Clicks Existing Chat Tab

```
USER CLICKS "Chat 1" TAB
      │
      ▼
┌─────────────────────────────────────────┐
│ 1. Get chat_id from tab                 │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 2. Load chat details                    │
│                                         │
│    SELECT * FROM chats                  │
│    WHERE chat_id = ?                    │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 3. Load messages for display            │
│                                         │
│    SELECT * FROM messages               │
│    WHERE chat_id = ?                    │
│    ORDER BY sequence_num ASC            │
└─────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────┐
│ 4. Display in UI                        │
│    - Show all messages in chat window   │
│    - User can scroll through history    │
└─────────────────────────────────────────┘
```

---

## Summarization Strategy

### Option B: Threshold-Based Summarization

```
RULE: When message_count > 30, summarize oldest (count - 20)
      Always keep last 20 messages fresh
```

### When To Trigger Summarization

```
AFTER EACH NEW MESSAGE:
      │
      ▼
┌─────────────────────────────────────────┐
│ Check: message_count > 30?              │
│                                         │
│ NO  → Do nothing, use all messages      │
│                                         │
│ YES → Trigger summarization             │
└─────────────────────────────────────────┘
```

### Summarization Process

```
EXAMPLE: Chat has 45 messages

STEP 1: Identify messages to summarize
────────────────────────────────────────
Messages to summarize: 1 to 25 (45 - 20 = 25)
Messages to keep: 26 to 45 (last 20)

STEP 2: Get messages to summarize
────────────────────────────────────────
SELECT content, role FROM messages
WHERE chat_id = ?
  AND sequence_num <= 25
  AND is_summarized = FALSE
ORDER BY sequence_num ASC

STEP 3: Generate summary using Claude
────────────────────────────────────────
Prompt to Claude:
"Summarize this conversation. Capture:
 1. Key topics and important data points
 2. User requests and outcomes
 3. Which documents were discussed (by name/ID)
 4. Key findings PER document

 Keep it concise (max 500 tokens) but preserve document references.

 Conversation:
 [User]: What is the batch number?
 [Assistant]: The batch number is 96309DB...
 ..."

IMPORTANT: Document IDs are stored separately in chat_documents table,
so they won't be lost. But summary should mention which doc had what info.

STEP 4: Save summary
────────────────────────────────────────
UPDATE chats
SET summary = 'User analyzed COA for ATX-101...',
    summary_updated = NOW()
WHERE chat_id = ?

STEP 5: Mark messages as summarized
────────────────────────────────────────
UPDATE messages
SET is_summarized = TRUE
WHERE chat_id = ?
  AND sequence_num <= 25
```

### Summary Content Example

```
GOOD SUMMARY EXAMPLE (Multi-Document):
─────────────────────────────────────────────────────────────
"Conversation context:
- User is analyzing multiple COA documents
- Processing COA files for batch comparison

Documents analyzed:
1. COA_001.pdf (ATX-101)
   - Batch: 96309DB
   - Expiry: 2026-01-15
   - Extracted Sample Summary tables (pages 5-10)

2. COA_002.pdf (ATX-102)
   - Batch: 96310DB
   - Expiry: 2026-02-20
   - Extracted same tables for comparison

User activities:
- Compared batch numbers across documents
- Exported combined data to Excel
- Asked about storage conditions (both docs: 2-8°C)

Topics covered: batch comparison, expiry dates, storage conditions,
Sample Summary extraction, Excel export"
─────────────────────────────────────────────────────────────

NOTE: Even if summary loses some detail, chat_documents table
always has the complete document list with IDs.
```

---

## Sending to Claude

### What Gets Sent For Each User Message

```
USER SENDS: "What was that batch number?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  BUILD CONTEXT                                              │
│                                                             │
│  1. SYSTEM PROMPT (with document list)                      │
│     "You are an OCR document assistant.                     │
│      Documents in this chat:                                │
│      1. COA_001.pdf                                         │
│      2. COA_002.pdf                                         │
│      3. COA_003.pdf [ACTIVE]                                │
│      Currently answering from: COA_003.pdf"                 │
│                                                             │
│  2. SUMMARY (if exists)                                     │
│     Load from chats.summary                                 │
│                                                             │
│  3. LAST 20 MESSAGES                                        │
│     SELECT * FROM messages                                  │
│     WHERE chat_id = ? AND is_summarized = FALSE             │
│     ORDER BY sequence_num DESC LIMIT 20                     │
│                                                             │
│  4. RAG RESULTS (from target document)                      │
│     - Use keyword detection for "first", "previous", "all"  │
│     - Default: active_document_id                           │
│     - Query Elasticsearch with document filter              │
│                                                             │
│  5. CURRENT QUESTION                                        │
│     "What was that batch number?"                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘

DOCUMENT LIST SOURCE:
─────────────────────────────────────────────────────────────
SELECT document_name FROM chat_documents
WHERE chat_id = ? ORDER BY upload_order ASC

This list is ALWAYS included in system prompt so Claude knows
which documents are available, even after summarization.
```

### Prompt Structure to Claude

```
┌─────────────────────────────────────────────────────────────┐
│  MESSAGES ARRAY TO CLAUDE API                               │
│                                                             │
│  [                                                          │
│    {                                                        │
│      "role": "system",                                      │
│      "content": "You are an OCR document assistant.         │
│                                                             │
│                  Documents in this chat:                    │
│                  1. COA_001.pdf                             │
│                  2. COA_002.pdf                             │
│                  3. COA_003.pdf [ACTIVE]                    │
│                                                             │
│                  Currently answering from: COA_003.pdf      │
│                                                             │
│                  If user asks about 'first document',       │
│                  'previous', or 'all documents', answer     │
│                  accordingly. Mention which document        │
│                  you're referencing in your response."      │
│    },                                                       │
│                                                             │
│    {                                                        │
│      "role": "user",                                        │
│      "content": "=== CONVERSATION SUMMARY ===               │
│                  User analyzed COA_001.pdf: batch 96309DB   │
│                  User analyzed COA_002.pdf: batch 96310DB   │
│                  Extracted tables from both documents.      │
│                  ==="                                       │
│    },                                                       │
│                                                             │
│    // Last 20 messages as alternating user/assistant        │
│    {"role": "user", "content": "Show me page 7"},           │
│    {"role": "assistant", "content": "Page 7 contains..."},  │
│    {"role": "user", "content": "What's the temperature?"},  │
│    {"role": "assistant", "content": "Temperature is 25°C"}, │
│    ... (more messages) ...                                  │
│                                                             │
│    {                                                        │
│      "role": "user",                                        │
│      "content": "=== DOCUMENT CONTEXT (RAG) ===             │
│                  [COA_003.pdf - Page 2]: Product: ATX-103   │
│                  [COA_003.pdf - Page 3]: Batch: 96311DB     │
│                  ===                                        │
│                                                             │
│                  User Question: What was that batch number?"│
│    }                                                        │
│  ]                                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Token Estimation

```
┌─────────────────────────────────────────────────────────────┐
│  COMPONENT               │ ESTIMATED TOKENS                 │
│──────────────────────────│──────────────────────────────────│
│  System prompt           │ ~100 tokens                      │
│  Summary                 │ ~200 tokens                      │
│  Last 20 messages        │ ~1500 tokens (avg 75 per msg)    │
│  RAG results             │ ~500 tokens                      │
│  Current question        │ ~30 tokens                       │
│──────────────────────────│──────────────────────────────────│
│  TOTAL                   │ ~2,330 tokens per request        │
│                                                             │
│  vs ALL messages (100)   │ ~7,500 tokens                    │
│  SAVINGS                 │ ~70% token reduction!            │
└─────────────────────────────────────────────────────────────┘
```

---

## Complete Flow

### Flow Diagram: User Sends a Message

```
USER: "What was that batch number?"
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 1: SAVE USER MESSAGE                                 │
│                                                           │
│ INSERT INTO messages (                                    │
│   message_id, chat_id, role, content, sequence_num        │
│ ) VALUES (                                                │
│   'msg_xxx', 'chat_123', 'user',                          │
│   'What was that batch number?', 46                       │
│ )                                                         │
│                                                           │
│ UPDATE chats SET message_count = 46, updated_at = NOW()   │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 2: CHECK IF SUMMARIZATION NEEDED                     │
│                                                           │
│ message_count (46) > 30? → YES                            │
│ messages_to_summarize = 46 - 20 = 26                      │
│                                                           │
│ Need to summarize messages 1-26                           │
│ (if not already summarized)                               │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 3: UPDATE SUMMARY (if needed)                        │
│                                                           │
│ Get unsummarized messages (sequence_num <= 26)            │
│ Generate summary using Claude                             │
│ Save to chats.summary                                     │
│ Mark messages as is_summarized = TRUE                     │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 4: BUILD CONTEXT FOR CLAUDE                          │
│                                                           │
│ A. Get summary from chats table                           │
│ B. Get last 20 messages (is_summarized = FALSE)           │
│ C. Query RAG (Elasticsearch) for relevant chunks          │
│ D. Combine all into prompt                                │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 5: CALL CLAUDE API                                   │
│                                                           │
│ Send: system + summary + last 20 + RAG + question         │
│ Receive: Claude's response                                │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 6: SAVE ASSISTANT MESSAGE                            │
│                                                           │
│ INSERT INTO messages (                                    │
│   message_id, chat_id, role, content, sequence_num        │
│ ) VALUES (                                                │
│   'msg_yyy', 'chat_123', 'assistant',                     │
│   'The batch number is 96309DB...', 47                    │
│ )                                                         │
│                                                           │
│ UPDATE chats SET message_count = 47, updated_at = NOW()   │
└───────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────┐
│ STEP 7: RETURN RESPONSE TO USER                           │
│                                                           │
│ Display in chat UI                                        │
└───────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Get User's Chats (Load Tabs)

```
GET /api/chats

Response:
{
  "chats": [
    {
      "chat_id": "chat_abc123",
      "title": "COA Analysis - ATX-101",
      "document_name": "COA_ATX101.pdf",
      "message_count": 45,
      "updated_at": "2026-01-20T10:30:00Z"
    },
    {
      "chat_id": "chat_def456",
      "title": "Sample Summary Extraction",
      "document_name": "Sample_Report.pdf",
      "message_count": 12,
      "updated_at": "2026-01-19T15:00:00Z"
    }
  ]
}
```

### 2. Create New Chat

```
POST /api/chats

Request:
{
  "project_id": "proj_123"         // optional - if inside a project
}

Response:
{
  "chat_id": "chat_xyz789",
  "title": "New Chat",
  "project_id": null,              // or "proj_123" if in project
  "created_at": "2026-01-20T12:00:00Z"
}

NOTE: Documents are added via POST /api/chats/{chat_id}/documents
      See MULTI_DOCUMENT_WORKFLOW.md for document upload API
```

### 3. Get Chat Messages (Load Chat Content)

```
GET /api/chats/{chat_id}/messages

Response:
{
  "chat_id": "chat_abc123",
  "title": "COA Analysis",
  "project_id": null,
  "active_document_id": "doc_003",
  "documents": [
    {
      "document_id": "doc_001",
      "document_name": "COA_001.pdf",
      "upload_order": 1
    },
    {
      "document_id": "doc_002",
      "document_name": "COA_002.pdf",
      "upload_order": 2
    },
    {
      "document_id": "doc_003",
      "document_name": "COA_003.pdf",
      "upload_order": 3,
      "is_active": true
    }
  ],
  "summary": "User analyzed multiple COA documents...",
  "messages": [
    {
      "message_id": "msg_001",
      "role": "user",
      "content": "What is the batch number?",
      "document_id": "doc_001",
      "created_at": "2026-01-15T10:00:00Z"
    },
    {
      "message_id": "msg_002",
      "role": "assistant",
      "content": "The batch number is 96309DB...",
      "document_id": "doc_001",
      "created_at": "2026-01-15T10:00:05Z"
    }
  ]
}
```

### 4. Send Message (Main Chat Endpoint)

```
POST /api/chats/{chat_id}/messages

Request:
{
  "content": "What was that batch number?"
}

Response:
{
  "user_message": {
    "message_id": "msg_046",
    "role": "user",
    "content": "What was that batch number?",
    "created_at": "2026-01-20T12:00:00Z"
  },
  "assistant_message": {
    "message_id": "msg_047",
    "role": "assistant",
    "content": "The batch number in COA_003.pdf is 96311DB.",
    "document_used": "doc_003",
    "created_at": "2026-01-20T12:00:02Z",
    "references": [
      {
        "page": 2,
        "bbox": {"left": 0.08, "top": 0.18, "right": 0.45, "bottom": 0.25}
      }
    ],
    "metadata": {
      "pages_referenced": [2],
      "rag_chunks_used": 2,
      "tokens_used": 2350
    }
  }
}

KEYWORD DETECTION:
─────────────────────────────────────────────────────────────
"first document"  → Uses doc_001
"previous"        → Uses doc_002 (second to last)
"all documents"   → Queries all docs
(default)         → Uses active_document_id (doc_003)

See MULTI_DOCUMENT_WORKFLOW.md for detect_target_document() function
```

### 5. Delete Chat

```
DELETE /api/chats/{chat_id}

Response:
{
  "success": true,
  "message": "Chat deleted successfully"
}
```

### 6. Rename Chat

```
PATCH /api/chats/{chat_id}

Request:
{
  "title": "ATX-101 Batch Analysis"
}

Response:
{
  "chat_id": "chat_abc123",
  "title": "ATX-101 Batch Analysis",
  "updated_at": "2026-01-20T12:05:00Z"
}
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  DATABASE                                                   │
│  ════════                                                   │
│  users → chats → messages                                   │
│              └→ chat_documents (multiple docs per chat)     │
│                  (with summary in chats table)              │
│                                                             │
│  RAG (Elasticsearch)                                        │
│  ════════════════════                                       │
│  Document chunks with embeddings + bbox                     │
│                                                             │
│  MULTI-DOCUMENT SUPPORT                                     │
│  ═════════════════════════                                  │
│  • chat_documents table stores all docs per chat            │
│  • active_document_id tracks most recent                    │
│  • Keyword detection: "first", "previous", "all"            │
│  • Document list always in system prompt                    │
│                                                             │
│  SUMMARIZATION STRATEGY                                     │
│  ═════════════════════════                                  │
│  When messages > 30:                                        │
│    - Summarize oldest (count - 20)                          │
│    - Keep last 20 fresh                                     │
│    - Document IDs preserved in chat_documents table         │
│                                                             │
│  SENDING TO CLAUDE                                          │
│  ═════════════════════                                      │
│  System prompt (with doc list) + Summary + Last 20 +        │
│  RAG results + Question                                     │
│                                                             │
│  TOKEN SAVINGS                                              │
│  ═════════════                                              │
│  ~70% reduction compared to sending all messages            │
│                                                             │
│  LATENCY (~1.6 seconds)                                     │
│  ═══════════════════════                                    │
│  DB query: ~50ms                                            │
│  Keyword detection: ~1ms (no Claude call!)                  │
│  Elasticsearch: ~100ms                                      │
│  Claude: ~1500ms                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

*Document Version: 2.0*
*Last Updated: January 2026*
*Compatible: MULTI_DOCUMENT_WORKFLOW.md, BBOX_HIGHLIGHT_IMPLEMENTATION.md*
