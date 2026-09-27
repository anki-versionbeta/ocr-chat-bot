# Chat History Implementation Plan

> **Goal:** Implement chat history preservation with summarization
> **Approach:** Phased implementation - simple first, add features gradually

---

## CRITICAL: High Priority Fixes (Read First!)

### Issue 1: Sequence Number Race Condition

```
PROBLEM: Concurrent requests can get SAME sequence number

SCENARIO:
─────────────────────────────────────────────────────────────
TIME     REQUEST A                    REQUEST B
─────────────────────────────────────────────────────────────
T1       Read message_count = 30
T2                                    Read message_count = 30
T3       sequence_num = 31            sequence_num = 31  ← SAME!
T4       INSERT message (seq 31)
T5                                    INSERT message (seq 31) ← DUPLICATE!
─────────────────────────────────────────────────────────────

RESULT: Two messages have same sequence_num = 31
        Chat message ORDER is BROKEN!

WHEN THIS HAPPENS:
- User clicks send button twice quickly
- User message + bot response insert close together
- Network retry sends duplicate request


FIX: Use database transaction with row lock (FOR UPDATE)
─────────────────────────────────────────────────────────────

def save_message(chat_id, role, content):
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # Use transaction with lock to prevent race condition
    with db.transaction():
        # Lock the chat row - other requests WAIT here
        result = db.execute(
            "SELECT message_count FROM chats WHERE chat_id = %s FOR UPDATE",
            [chat_id]
        )

        sequence_num = result.message_count + 1

        # Insert message with guaranteed unique sequence
        db.execute("""
            INSERT INTO messages (message_id, chat_id, role, content, sequence_num, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, [message_id, chat_id, role, content, sequence_num])

        # Update count
        db.execute(
            "UPDATE chats SET message_count = %s, updated_at = NOW() WHERE chat_id = %s",
            [sequence_num, chat_id]
        )

    # Transaction commits here, lock released
    return message_id
```

### Issue 2: Prevent Double Summarization

```
PROBLEM: Multiple summarizations could run at same time for same chat

SCENARIO:
─────────────────────────────────────────────────────────────
Message 31 arrives → Triggers summarization A
Message 32 arrives quickly → Triggers summarization B

Both try to summarize and mark same messages = conflict
─────────────────────────────────────────────────────────────


FIX: Simple lock to prevent double-run
─────────────────────────────────────────────────────────────

def update_summary(chat_id):
    # Simple lock - skip if already summarizing this chat
    lock_key = f"summarize:{chat_id}"

    if not acquire_lock(lock_key, timeout=60):
        return  # Another summarization running, skip this one

    try:
        chat = get_chat(chat_id)
        summarize_up_to = chat.message_count - 20

        old_messages = get_unsummarized_messages(chat_id, summarize_up_to)

        if old_messages:
            new_summary = generate_summary(chat_id, old_messages)
            save_summary(chat_id, new_summary)
            mark_messages_summarized(chat_id, summarize_up_to)
    finally:
        release_lock(lock_key)


NOTE: User sending messages DURING summarization is FINE!
      - Summary is just context, not source of truth
      - RAG provides accurate data regardless
      - Slightly delayed summary doesn't affect answer quality
```

### Issue 3: Summary Growing Too Large

```
PROBLEM: Summary keeps growing with each update

SCENARIO:
─────────────────────────────────────────────────────────────
Messages 1-10:   Summary v1 = 200 tokens
Messages 11-30:  Summary v2 = v1 + new = 400 tokens
Messages 31-60:  Summary v3 = v2 + new = 700 tokens
Messages 61-100: Summary v4 = v3 + new = 1000 tokens
... keeps growing!
─────────────────────────────────────────────────────────────

RESULT: Summary itself becomes huge, defeats the purpose


FIX: Set max summary length, re-summarize if too long
─────────────────────────────────────────────────────────────

MAX_SUMMARY_TOKENS = REDACTED

def generate_summary(chat_id, new_messages):
    existing_summary = get_chat_summary(chat_id)

    prompt = f"""Summarize this conversation. Include:
- Main topics discussed
- Key data values (product names, batch numbers, dates)
- User's goals and outcomes
- Important issues resolved

IMPORTANT: Keep summary under 400 words. Be concise.

{f"Previous context: {existing_summary}" if existing_summary else ""}

New messages to include:
"""
    for msg in new_messages:
        prompt += f"[{msg.role}]: {msg.content}\n"

    prompt += "\nProvide a concise summary (max 400 words):"

    summary = call_claude_for_summary(prompt)

    # Safety check: if summary too long, summarize the summary
    if count_tokens(summary) > MAX_SUMMARY_TOKENS:
        summary = condense_summary(summary)

    return summary


def condense_summary(long_summary):
    prompt = f"""This summary is too long. Condense it to under 300 words
while keeping the most important information:

{long_summary}

Condensed summary:"""

    return call_claude_for_summary(prompt)
```

---

## Quick Reference: IDs Explained

```
┌─────────────────────────────────────────────────────────────┐
│  ID TYPES                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  user_id:    Identifies the user (from your auth system)    │
│              Example: "user_john123" or from OAuth          │
│              One user can have MANY chats                   │
│                                                             │
│  chat_id:    Identifies ONE conversation/tab (UNIQUE)       │
│              Example: "chat_a1b2c3d4e5f6"                    │
│              Generated when user clicks "+ New Chat"        │
│              UNIQUE - never repeats                         │
│              One chat has MANY messages                     │
│                                                             │
│  message_id: Identifies ONE message (UNIQUE)                │
│              Example: "msg_x9y8z7w6v5"                       │
│              Generated for each user/assistant message      │
│              UNIQUE - never repeats                         │
│                                                             │
│  document_id: Identifies uploaded document (from your RAG)  │
│              Links chat to the document being analyzed      │
│                                                             │
└─────────────────────────────────────────────────────────────┘

RELATIONSHIPS:
──────────────
user_id (1) ──────< chat_id (many)      One user has many chats
chat_id (1) ──────< message_id (many)   One chat has many messages
chat_id (1) ──────── document_id (1)    One chat has one document
```

### How To Generate Unique IDs:

```python
import uuid

def generate_chat_id():
    return f"chat_{uuid.uuid4().hex[:12]}"
    # Result: "chat_a1b2c3d4e5f6"

def generate_message_id():
    return f"msg_{uuid.uuid4().hex[:12]}"
    # Result: "msg_x9y8z7w6v5u4"
```

---

## Phase 1: Basic Chat Storage (Do This First!)

**Time:** 1-2 days
**Goal:** Save and load chats - nothing fancy yet

### What To Build:

```
1. Database tables (just 2 tables)
2. Save messages to database
3. Load messages when user opens chat
4. Basic chat tabs in UI
```

### Database (Phase 1 - Simple)

```sql
-- Table 1: chats
CREATE TABLE chats (
    chat_id         VARCHAR(50) PRIMARY KEY,
    user_id         VARCHAR(50),
    title           VARCHAR(255) DEFAULT 'New Chat',
    document_id     VARCHAR(50),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

-- Table 2: messages
CREATE TABLE messages (
    message_id      VARCHAR(50) PRIMARY KEY,
    chat_id         VARCHAR(50),
    role            VARCHAR(20),
    content         TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
);

-- Index for faster queries
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_chats_user_id ON chats(user_id);
```

### Backend Functions (Phase 1)

```python
import uuid
from datetime import datetime

# 1. Create new chat
def create_chat(user_id, document_id=None):
    chat_id = f"chat_{uuid.uuid4().hex[:12]}"

    # INSERT INTO chats (chat_id, user_id, document_id, created_at, updated_at)
    # VALUES (chat_id, user_id, document_id, NOW(), NOW())

    return chat_id


# 2. Save message
def save_message(chat_id, role, content):
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # INSERT INTO messages (message_id, chat_id, role, content, created_at)
    # VALUES (message_id, chat_id, role, content, NOW())

    # UPDATE chats SET updated_at = NOW() WHERE chat_id = chat_id

    return message_id


# 3. Get all messages for a chat (for display)
def get_messages(chat_id):
    # SELECT * FROM messages
    # WHERE chat_id = chat_id
    # ORDER BY created_at ASC

    return messages


# 4. Get user's chats (for sidebar/tabs)
def get_user_chats(user_id):
    # SELECT * FROM chats
    # WHERE user_id = user_id
    # ORDER BY updated_at DESC

    return chats


# 5. Get last N messages for Claude
def get_recent_messages(chat_id, limit=10):
    # SELECT * FROM messages
    # WHERE chat_id = chat_id
    # ORDER BY created_at DESC
    # LIMIT limit

    return messages  # Remember to reverse for correct order!
```

### Flow (Phase 1)

```
USER SENDS MESSAGE:

1. Save user message
   → INSERT INTO messages

2. Get last 10 messages
   → SELECT FROM messages ORDER BY created_at DESC LIMIT 10

3. Query RAG
   → Get document chunks from Elasticsearch

4. Call Claude
   → Send (last 10 messages + RAG + question)

5. Save assistant response
   → INSERT INTO messages

6. Return response to user

THAT'S IT FOR PHASE 1!
```

### What You DON'T Do in Phase 1:

```
❌ No summarization yet
❌ No complex metadata
❌ No sequence numbers
❌ Just save and load messages
```

### Phase 1 Checklist:

```
[ ] Create chats table in database
[ ] Create messages table in database
[ ] Backend: create_chat() function
[ ] Backend: save_message() function
[ ] Backend: get_messages() function
[ ] Backend: get_user_chats() function
[ ] Backend: get_recent_messages() function
[ ] Update chat endpoint to save messages
[ ] Frontend: Show chat tabs/list
[ ] Frontend: "+ New Chat" button
[ ] Frontend: Load messages when clicking chat
[ ] Test: Create chat, send messages, reload page, messages still there
```

---

## Phase 2: Add More Messages Support

**Time:** 1 day
**Goal:** Support longer conversations with last 20 messages

### Changes from Phase 1:

```
BEFORE (Phase 1): Send last 10 messages to Claude
AFTER (Phase 2):  Send last 20 messages to Claude

Just change the LIMIT:

def get_recent_messages(chat_id, limit=20):  # Changed from 10 to 20
    # SELECT * FROM messages
    # WHERE chat_id = chat_id
    # ORDER BY created_at DESC
    # LIMIT 20
```

### Add Message Count:

```sql
-- Add to chats table
ALTER TABLE chats ADD COLUMN message_count INTEGER DEFAULT 0;
```

```python
# Update save_message function
def save_message(chat_id, role, content):
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # INSERT INTO messages...

    # UPDATE chats SET
    #   message_count = message_count + 1,
    #   updated_at = NOW()
    # WHERE chat_id = chat_id

    return message_id
```

### Phase 2 Checklist:

```
[ ] Add message_count column to chats table
[ ] Update save_message to increment count
[ ] Change limit from 10 to 20 messages
[ ] Test: Send 25 messages, verify last 20 sent to Claude
```

---

## Phase 3: Add Summarization

**Time:** 2-3 days
**Goal:** Summarize old messages when chat gets long

### Database Changes:

```sql
-- Add columns to chats table
ALTER TABLE chats ADD COLUMN summary TEXT;
ALTER TABLE chats ADD COLUMN summary_updated_at TIMESTAMP;

-- Add columns to messages table
ALTER TABLE messages ADD COLUMN sequence_num INTEGER;
ALTER TABLE messages ADD COLUMN is_summarized BOOLEAN DEFAULT FALSE;

-- Index for faster queries
CREATE INDEX idx_messages_sequence ON messages(chat_id, sequence_num);
```

### Updated Save Message (with sequence):

```python
def save_message(chat_id, role, content):
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # Get current message count for sequence number
    # SELECT message_count FROM chats WHERE chat_id = chat_id
    sequence_num = current_count + 1

    # INSERT INTO messages (message_id, chat_id, role, content, sequence_num, created_at)
    # VALUES (message_id, chat_id, role, content, sequence_num, NOW())

    # UPDATE chats SET message_count = sequence_num, updated_at = NOW()
    # WHERE chat_id = chat_id

    return message_id
```

### Summarization Logic:

```python
def process_message(chat_id, user_message):
    """Main function that handles each user message"""

    # 1. Save user message
    save_message(chat_id, "user", user_message)

    # 2. Get chat info
    chat = get_chat(chat_id)

    # 3. Check if summarization needed (threshold: 30 messages)
    if chat.message_count > 30:
        maybe_update_summary(chat_id, chat.message_count)

    # 4. Build context for Claude
    context = build_context(chat_id)

    # 5. Query RAG
    rag_results = query_rag(user_message, chat.document_id)

    # 6. Call Claude
    response = call_claude(context, rag_results, user_message)

    # 7. Save assistant response
    save_message(chat_id, "assistant", response)

    return response


def maybe_update_summary(chat_id, message_count):
    """Update summary if there are unsummarized old messages"""

    # Calculate how many messages should be summarized
    # Keep last 20 fresh, summarize the rest
    summarize_up_to = message_count - 20

    # Get unsummarized messages
    # SELECT * FROM messages
    # WHERE chat_id = chat_id
    #   AND sequence_num <= summarize_up_to
    #   AND is_summarized = FALSE
    # ORDER BY sequence_num ASC

    old_messages = get_unsummarized_messages(chat_id, summarize_up_to)

    if len(old_messages) > 0:
        # Generate new summary
        new_summary = generate_summary(chat_id, old_messages)

        # Save summary to chat
        # UPDATE chats SET summary = new_summary, summary_updated_at = NOW()
        # WHERE chat_id = chat_id

        # Mark messages as summarized
        # UPDATE messages SET is_summarized = TRUE
        # WHERE chat_id = chat_id AND sequence_num <= summarize_up_to


def generate_summary(chat_id, messages):
    """Use Claude to generate a summary of old messages"""

    # Get existing summary (if any)
    existing_summary = get_chat_summary(chat_id)

    prompt = f"""Summarize this conversation. Include:
- Main topics discussed
- Key data/values mentioned (product names, batch numbers, dates)
- User's goals and any issues resolved
- Important outcomes

{f"Previous summary: {existing_summary}" if existing_summary else ""}

New messages to summarize:
"""

    for msg in messages:
        prompt += f"[{msg.role}]: {msg.content}\n"

    prompt += "\nProvide a concise but complete summary:"

    # Call Claude for summary (use a smaller/cheaper model if available)
    summary = call_claude_for_summary(prompt)

    return summary


def build_context(chat_id):
    """Build the context to send to Claude"""

    chat = get_chat(chat_id)

    # Get last 20 unsummarized messages
    # SELECT * FROM messages
    # WHERE chat_id = chat_id AND is_summarized = FALSE
    # ORDER BY sequence_num DESC LIMIT 20
    recent_messages = get_recent_unsummarized(chat_id, limit=20)

    # Reverse to get correct chronological order
    recent_messages = list(reversed(recent_messages))

    return {
        "summary": chat.summary,  # Could be None if no summary yet
        "recent_messages": recent_messages
    }
```

### Summary Generation Prompt Template:

```python
SUMMARY_PROMPT = """Summarize this conversation concisely. Include:

1. CONTEXT: What document/product is being analyzed
2. KEY DATA: Important values discussed (batch numbers, dates, etc.)
3. ACTIVITIES: What the user did (extractions, exports, etc.)
4. ISSUES: Any problems encountered and if they were resolved
5. TOPICS: Main topics covered

Keep the summary informative but concise (under 200 words).

{previous_summary}

Messages to summarize:
{messages}

Summary:"""
```

### Phase 3 Checklist:

```
[ ] Add summary and summary_updated_at columns to chats
[ ] Add sequence_num and is_summarized columns to messages
[ ] Update save_message() to include sequence_num
[ ] Create maybe_update_summary() function
[ ] Create generate_summary() function
[ ] Create build_context() function
[ ] Update main chat flow to use summarization
[ ] Test: Send 35 messages
[ ] Test: Verify summary is created after message 31
[ ] Test: Verify Claude receives summary + last 20 messages
[ ] Test: Verify old messages marked as is_summarized = TRUE
```

---

## Phase 4: Polish & Optimize

**Time:** 1-2 days
**Goal:** Add nice features and optimize

### Feature 1: Auto-Generate Chat Title

```python
def auto_generate_title(chat_id, first_message):
    """Generate a short title from the first message"""

    prompt = f"""Generate a short title (3-5 words) for a chat that starts with:
"{first_message}"

Just return the title, nothing else. No quotes."""

    title = call_claude(prompt)

    # UPDATE chats SET title = title WHERE chat_id = chat_id

    return title

# Call this after saving the first message in a chat
```

### Feature 2: Delete Chat

```python
def delete_chat(chat_id, user_id):
    """Delete a chat and all its messages"""

    # Verify ownership
    # SELECT user_id FROM chats WHERE chat_id = chat_id

    if chat_owner != user_id:
        raise PermissionError("Not your chat")

    # DELETE FROM messages WHERE chat_id = chat_id
    # DELETE FROM chats WHERE chat_id = chat_id

    return True
```

### Feature 3: Rename Chat

```python
def rename_chat(chat_id, user_id, new_title):
    """Rename a chat"""

    # Verify ownership first

    # UPDATE chats SET title = new_title WHERE chat_id = chat_id

    return True
```

### Feature 4: Archive Old Chats

```python
def archive_chat(chat_id, user_id):
    """Archive a chat (hide from main list)"""

    # UPDATE chats SET is_archived = TRUE WHERE chat_id = chat_id

def get_user_chats(user_id, include_archived=False):
    """Get user's chats, optionally including archived"""

    # SELECT * FROM chats
    # WHERE user_id = user_id
    #   AND (is_archived = FALSE OR include_archived = TRUE)
    # ORDER BY updated_at DESC
```

### Phase 4 Checklist:

```
[ ] Add is_archived column to chats table
[ ] Implement auto_generate_title()
[ ] Implement delete_chat()
[ ] Implement rename_chat()
[ ] Implement archive_chat()
[ ] Frontend: Rename button/modal
[ ] Frontend: Delete button with confirmation
[ ] Frontend: Archive option
[ ] Test all new features
```

---

## Timeline Summary

```
┌─────────────────────────────────────────────────────────────┐
│  IMPLEMENTATION TIMELINE                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WEEK 1:                                                    │
│  ────────                                                   │
│  Day 1-2: Phase 1 (Basic storage)                           │
│           - Database tables                                 │
│           - Save/load messages                              │
│           - Basic chat tabs                                 │
│                                                             │
│  Day 3:   Phase 2 (Last 20 messages)                        │
│           - Add message_count                               │
│           - Change limit to 20                              │
│                                                             │
│  WEEK 2:                                                    │
│  ────────                                                   │
│  Day 1-3: Phase 3 (Summarization)                           │
│           - Add summary columns                             │
│           - Summarization logic                             │
│           - Test with long conversations                    │
│                                                             │
│  Day 4-5: Phase 4 (Polish)                                  │
│           - Auto-title                                      │
│           - Delete/rename/archive                           │
│           - UI polish                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing Checklist

### Phase 1 Tests:

```
[ ] Create new chat - verify chat_id generated
[ ] Send message - verify saved to database
[ ] Reload page - verify messages still there
[ ] Create multiple chats - verify all appear in tabs
[ ] Click different tabs - verify correct messages load
```

### Phase 2 Tests:

```
[ ] Send 25 messages
[ ] Verify message_count = 25 in chats table
[ ] Verify Claude receives last 20 messages only
```

### Phase 3 Tests:

```
[ ] Send 35 messages
[ ] Verify summary created after message 31
[ ] Verify messages 1-15 marked as is_summarized = TRUE
[ ] Verify Claude receives: summary + messages 16-35
[ ] Continue to 50 messages - verify summary updates
[ ] Verify Claude still receives: updated summary + last 20
```

### Phase 4 Tests:

```
[ ] First message auto-generates title
[ ] Can rename chat
[ ] Can delete chat (messages also deleted)
[ ] Can archive chat (hidden from list)
[ ] Archived chats accessible when needed
```

---

## Final Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  USER SENDS MESSAGE                                         │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────────┐                                        │
│  │ Save to DB      │                                        │
│  └────────┬────────┘                                        │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │ Check count >30 │────▶│ Update Summary  │               │
│  └────────┬────────┘     └─────────────────┘               │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────┐     ┌─────────────────┐               │
│  │ Build Context   │────▶│ Query RAG       │               │
│  │ (Summary + 20)  │     │ (Elasticsearch) │               │
│  └────────┬────────┘     └────────┬────────┘               │
│           │                       │                         │
│           └───────────┬───────────┘                         │
│                       ▼                                     │
│              ┌─────────────────┐                            │
│              │ Call Claude     │                            │
│              │ (Context + RAG) │                            │
│              └────────┬────────┘                            │
│                       │                                     │
│                       ▼                                     │
│              ┌─────────────────┐                            │
│              │ Save Response   │                            │
│              └────────┬────────┘                            │
│                       │                                     │
│                       ▼                                     │
│              ┌─────────────────┐                            │
│              │ Return to User  │                            │
│              └─────────────────┘                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
