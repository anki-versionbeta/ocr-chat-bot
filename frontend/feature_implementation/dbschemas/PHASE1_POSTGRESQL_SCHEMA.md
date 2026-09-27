# Phase 1: PostgreSQL Schema

> **Database:** `ocr_rag_system`
> **Schema:** `rag`
> **Host:** `intelligentparsing-ngxp-dev.cimrdaj1f7u6.us-east-1.rds.amazonaws.com`
> **Created:** February 2026

---

## Tables Overview

| Table                | Purpose                       | Rows (Est.) |
| -------------------- | ----------------------------- | ----------- |
| `rag.users`          | User accounts                 | 100s        |
| `rag.chats`          | Chat sessions                 | 1000s       |
| `rag.chat_documents` | Documents per chat            | 1000s       |
| `rag.messages`       | Chat messages with references | 10000s      |
| `rag.pdf_page_cache` | Cached PDF page images        | 10000s      |

---

## Table 1: users

```sql
CREATE TABLE rag.users (
    user_id VARCHAR(50) PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

| Column       | Type         | Constraints      | Description            |
| ------------ | ------------ | ---------------- | ---------------------- |
| `user_id`    | VARCHAR(50)  | PK               | Unique user identifier |
| `email`      | VARCHAR(255) | NOT NULL, UNIQUE | User email             |
| `full_name`  | VARCHAR(255) |                  | User display name      |
| `created_at` | TIMESTAMP    | DEFAULT NOW()    | Account creation       |
| `updated_at` | TIMESTAMP    | DEFAULT NOW()    | Last update            |

---

## Table 2: chats

```sql
CREATE TABLE rag.chats (
    chat_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL REFERENCES rag.users(user_id),
    title VARCHAR(255) DEFAULT 'New Chat',
    summary TEXT,
    summary_updated_at TIMESTAMP DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    active_document_id VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_archived BOOLEAN DEFAULT FALSE,
    metadata JSONB
);

CREATE INDEX idx_chats_user_id ON rag.chats(user_id);
CREATE INDEX idx_chats_created_at ON rag.chats(created_at DESC);
```

| Column               | Type         | Constraints        | Description                       |
| -------------------- | ------------ | ------------------ | --------------------------------- |
| `chat_id`            | VARCHAR(50)  | PK                 | Unique chat identifier            |
| `user_id`            | VARCHAR(50)  | FK → users         | Owner of the chat                 |
| `title`              | VARCHAR(255) | DEFAULT 'New Chat' | Chat title                        |
| `summary`            | TEXT         |                    | Summarized old messages           |
| `message_count`      | INTEGER      | DEFAULT 0          | Total messages (auto-incremented) |
| `active_document_id` | VARCHAR(50)  |                    | Currently active document         |
| `created_at`         | TIMESTAMP    | DEFAULT NOW()      | Chat creation                     |
| `updated_at`         | TIMESTAMP    | DEFAULT NOW()      | Last activity (auto-updated)      |
| `is_archived`        | BOOLEAN      | DEFAULT FALSE      | Archive status                    |
| `metadata`           | JSONB        |                    | Additional metadata               |

---

## Table 3: chat_documents

```sql
CREATE TABLE rag.chat_documents (
    id SERIAL PRIMARY KEY,
    chat_id VARCHAR(50) NOT NULL REFERENCES rag.chats(chat_id) ON DELETE CASCADE,
    document_id VARCHAR(50) NOT NULL,
    document_name VARCHAR(255) NOT NULL,
    upload_order INTEGER NOT NULL,
    page_count INTEGER,
    file_size BIGINT,
    file_path VARCHAR(500),
    extraction_done BOOLEAN DEFAULT FALSE,
    extraction_prompt TEXT,
    extraction_result_url VARCHAR(500),
    weaviate_source VARCHAR(100),
    neo4j_indexed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB,
    UNIQUE(chat_id, document_id)
);

CREATE INDEX idx_chat_documents_chat_id ON rag.chat_documents(chat_id);
CREATE INDEX idx_chat_documents_order ON rag.chat_documents(chat_id, upload_order);
```

| Column                  | Type         | Constraints   | Description                |
| ----------------------- | ------------ | ------------- | -------------------------- |
| `id`                    | SERIAL       | PK            | Auto-increment ID          |
| `chat_id`               | VARCHAR(50)  | FK → chats    | Parent chat                |
| `document_id`           | VARCHAR(50)  | NOT NULL      | Unique document ID (UUID)  |
| `document_name`         | VARCHAR(255) | NOT NULL      | Original filename          |
| `upload_order`          | INTEGER      | NOT NULL      | Order in chat (1, 2, 3...) |
| `page_count`            | INTEGER      |               | Total pages                |
| `file_size`             | BIGINT       |               | File size in bytes         |
| `file_path`             | VARCHAR(500) |               | Storage path               |
| `extraction_done`       | BOOLEAN      | DEFAULT FALSE | Extraction completed       |
| `extraction_prompt`     | TEXT         |               | Saved prompt for reuse     |
| `extraction_result_url` | VARCHAR(500) |               | Excel download URL         |
| `weaviate_source`       | VARCHAR(100) |               | Weaviate source name       |
| `neo4j_indexed`         | BOOLEAN      | DEFAULT FALSE | Neo4j indexing done        |
| `created_at`            | TIMESTAMP    | DEFAULT NOW() | Upload time                |
| `metadata`              | JSONB        |               | Additional metadata        |

---

## Table 4: messages

```sql
CREATE TABLE rag.messages (
    message_id VARCHAR(50) PRIMARY KEY,
    chat_id VARCHAR(50) NOT NULL REFERENCES rag.chats(chat_id) ON DELETE CASCADE,
    document_id VARCHAR(50),
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text' CHECK (message_type IN ('text', 'file_upload', 'file_generated', 'system')),
    attached_file_name VARCHAR(255),
    attached_file_size BIGINT,
    generated_file_url VARCHAR(500),
    generated_file_name VARCHAR(255),
    generated_file_metadata JSONB,
    references JSONB,
    is_summarized BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_chat_id ON rag.messages(chat_id);
CREATE INDEX idx_messages_sequence ON rag.messages(chat_id, sequence_num);
```

| Column                    | Type         | Constraints   | Description                   |
| ------------------------- | ------------ | ------------- | ----------------------------- |
| `message_id`              | VARCHAR(50)  | PK            | Unique message ID             |
| `chat_id`                 | VARCHAR(50)  | FK → chats    | Parent chat                   |
| `document_id`             | VARCHAR(50)  |               | Related document              |
| `role`                    | VARCHAR(20)  | CHECK         | 'user', 'assistant', 'system' |
| `content`                 | TEXT         | NOT NULL      | Message content               |
| `sequence_num`            | INTEGER      | NOT NULL      | Order in chat                 |
| `message_type`            | VARCHAR(20)  | CHECK         | Rendering type                |
| `attached_file_name`      | VARCHAR(255) |               | Uploaded file name            |
| `attached_file_size`      | BIGINT       |               | Uploaded file size            |
| `generated_file_url`      | VARCHAR(500) |               | Generated file URL            |
| `generated_file_name`     | VARCHAR(255) |               | Generated file name           |
| `generated_file_metadata` | JSONB        |               | File metadata                 |
| `references`              | JSONB        |               | RAG references with bbox      |
| `is_summarized`           | BOOLEAN      | DEFAULT FALSE | Included in summary           |
| `created_at`              | TIMESTAMP    | DEFAULT NOW() | Message time                  |

### References JSONB Structure

```json
{
  "references": [
    {
      "page": 1,
      "chunk_id": "chunk_001",
      "cell_ids": ["1-29", "1-30"],
      "bbox": {
        "left": 0.31,
        "top": 0.45,
        "right": 0.5,
        "bottom": 0.48
      },
      "relevance_score": 0.92
    }
  ]
}
```

---

## Table 5: pdf_page_cache

```sql
CREATE TABLE rag.pdf_page_cache (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(50) NOT NULL,
    page_num INTEGER NOT NULL,
    image_path VARCHAR(500) NOT NULL,
    image_format VARCHAR(10) DEFAULT 'webp',
    width INTEGER,
    height INTEGER,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    last_accessed TIMESTAMP DEFAULT NOW(),
    UNIQUE(document_id, page_num)
);

CREATE INDEX idx_pdf_cache_document ON rag.pdf_page_cache(document_id);
CREATE INDEX idx_pdf_cache_accessed ON rag.pdf_page_cache(last_accessed);
```

| Column          | Type         | Constraints    | Description        |
| --------------- | ------------ | -------------- | ------------------ |
| `id`            | SERIAL       | PK             | Auto-increment ID  |
| `document_id`   | VARCHAR(50)  | NOT NULL       | Parent document    |
| `page_num`      | INTEGER      | NOT NULL       | Page number        |
| `image_path`    | VARCHAR(500) | NOT NULL       | Cached image path  |
| `image_format`  | VARCHAR(10)  | DEFAULT 'webp' | Image format       |
| `width`         | INTEGER      |                | Image width        |
| `height`        | INTEGER      |                | Image height       |
| `file_size`     | INTEGER      |                | File size in bytes |
| `created_at`    | TIMESTAMP    | DEFAULT NOW()  | Cache creation     |
| `last_accessed` | TIMESTAMP    | DEFAULT NOW()  | Last access time   |

---

## Triggers

### 1. Auto-update `updated_at` on chats

```sql
CREATE OR REPLACE FUNCTION rag.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER update_chats_updated_at
    BEFORE UPDATE ON rag.chats
    FOR EACH ROW
    EXECUTE FUNCTION rag.update_updated_at_column();
```

### 2. Auto-increment `message_count` on new message

```sql
CREATE OR REPLACE FUNCTION rag.increment_message_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE rag.chats SET message_count = message_count + 1 WHERE chat_id = NEW.chat_id;
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

CREATE TRIGGER increment_chat_message_count
    AFTER INSERT ON rag.messages
    FOR EACH ROW
    EXECUTE FUNCTION rag.increment_message_count();
```

---

## Entity Relationship Diagram

```
┌─────────────────┐
│     users       │
├─────────────────┤
│ PK user_id      │
│    email        │
│    full_name    │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────┐       ┌─────────────────────┐
│     chats       │       │   pdf_page_cache    │
├─────────────────┤       ├─────────────────────┤
│ PK chat_id      │       │ PK id               │
│ FK user_id      │       │    document_id      │
│    title        │       │    page_num         │
│    summary      │       │    image_path       │
│    message_count│       └─────────────────────┘
│    active_doc_id│
└────────┬────────┘
         │ 1:N
    ┌────┴────┐
    │         │
    ▼         ▼
┌─────────────────┐    ┌─────────────────────┐
│ chat_documents  │    │     messages        │
├─────────────────┤    ├─────────────────────┤
│ PK id           │    │ PK message_id       │
│ FK chat_id      │    │ FK chat_id          │
│    document_id  │◄───┤    document_id      │
│    document_name│    │    role             │
│    upload_order │    │    content          │
│    extraction...|    │    message_type     │
└─────────────────┘    │    references (JSON)│
                       └─────────────────────┘
```

---

## Verification Query

```sql
-- Check all tables
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'rag'
ORDER BY table_name;

-- Check triggers
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_schema = 'rag';

-- Check functions
SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = 'rag';

-- Quick count
SELECT
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'rag') AS tables,
    (SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema = 'rag') AS triggers,
    (SELECT COUNT(*) FROM information_schema.routines WHERE routine_schema = 'rag') AS functions;
```

---

_Document Version: 1.0_
_Created: February 2026_
_Phase: 1 of 3_
