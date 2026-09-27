# Message Rendering System - File Upload & Download Support

> **Purpose:** How file uploads (PDF) and generated files (Excel) are stored and rendered in chat history
> **Aligns With:** MULTI_DOCUMENT_WORKFLOW.md (extended messages schema)
> **Created:** January 2026

---

## Overview

**Like ChatGPT/Claude:** When users upload files or generate Excel outputs, these appear as special message types in the chat history that persist across sessions.

---

## Extended Messages Schema

See **MULTI_DOCUMENT_WORKFLOW.md** for complete schema. Key additions:

```sql
-- Message rendering fields
message_type                VARCHAR(20) DEFAULT 'text'
attached_file_name          VARCHAR(255)  
attached_file_size          BIGINT
generated_file_url          VARCHAR(500)
generated_file_name         VARCHAR(255)
generated_file_metadata     JSONB
references                  JSONB
```

---

## Message Types

### **1. text (Normal Q&A)**

```sql
INSERT INTO messages (
    role: 'user',
    message_type: 'text',
    content: 'What is the pH value?'
);
```

**UI:**
```
[User] What is the pH value?
[Bot] The pH value is 6.1 📍 [Page 1]
```

---

### **2. file_upload (PDF Upload)**

```sql
INSERT INTO messages (
    role: 'user',
    message_type: 'file_upload',
    content: 'Uploaded document',
    attached_file_name: 'COA_001.pdf',
    attached_file_size: 1234567
);
```

**UI:**
```
[User] 📎
┌────────────────────────┐
│ 📄 COA_001.pdf        │
│ 1.2 MB • 2 mins ago   │
└────────────────────────┘
```

---

### **3. file_generated (Excel Output)**

```sql
INSERT INTO messages (
    role: 'assistant',
    message_type: 'file_generated',
    content: 'Extracted 25 rows',
    generated_file_url: '/downloads/extraction.xlsx',
    generated_file_name: 'COA_001_extraction.xlsx',
    generated_file_metadata: '{"row_count": 25}'
);
```

**UI:**
```
[Bot] Extracted 25 rows

┌────────────────────────┐
│ 📊 COA_001_extraction.xlsx │
│ 25 rows • 32 KB       │
│ [⬇ Download Excel]    │
└────────────────────────┘
```

---

### **4. system (System Notifications)**

```sql
INSERT INTO messages (
    role: 'system',
    message_type: 'system',
    content: 'Processing complete'
);
```

**UI:**
```
───────────────────────────
ℹ️ Processing complete
───────────────────────────
```

---

## Frontend Rendering

```tsx
function MessageRenderer({ message }) {
  switch (message.message_type) {
    case 'file_upload':
      return <FileUploadCard file={message.attached_file_name} />
    case 'file_generated':
      return <FileDownloadCard url={message.generated_file_url} />
    case 'system':
      return <SystemNotification text={message.content} />
    case 'text':
    default:
      return <TextMessage content={message.content} />
  }
}
```

---

## Complete Flow

```
1. User uploads COA_001.pdf
   → message_type: 'file_upload'
   → Shows file card in UI

2. User: "Extract to Excel"
   → message_type: 'text'
   → Shows text message

3. Bot generates Excel
   → message_type: 'file_generated'
   → Shows download button

4. User reopens chat next day
   → All messages still there
   → Download button still works
```

---

*See MULTI_DOCUMENT_WORKFLOW.md for complete database schema*
