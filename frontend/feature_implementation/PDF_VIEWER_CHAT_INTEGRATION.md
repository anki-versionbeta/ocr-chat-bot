# PDF Viewer & Chat Integration - Complete UX Flow

> **Purpose:** Define UI/UX flow for PDF viewer panel with lazy loading and multi-document support
> **Builds On:** MULTI_DOCUMENT_WORKFLOW.md, BBOX_HIGHLIGHT_IMPLEMENTATION.md, CHAT_HISTORY_PRESERVATION.md
> **Schema:** Aligned with chats, chat_documents, messages tables
> **Created:** January 2026

---

## Table of Contents

1. [Design Principles](#design-principles)
2. [UI States & Transitions](#ui-states--transitions)
3. [Database Schema Alignment](#database-schema-alignment)
4. [Component Architecture](#component-architecture)
5. [User Flows](#user-flows)
6. [Performance Strategy](#performance-strategy)
7. [API Endpoints](#api-endpoints)
8. [Implementation Code](#implementation-code)
9. [Testing Scenarios](#testing-scenarios)

---

## Design Principles

### Core Philosophy

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  GUIDING PRINCIPLES                                             │
│  ═══════════════════                                            │
│                                                                 │
│  1. CHAT-FIRST                                                  │
│     • Default view is chat-only (like ChatGPT)                 │
│     • PDF is optional enhancement, not requirement             │
│                                                                 │
│  2. LAZY LOADING                                                │
│     • Load PDF only when user clicks reference                 │
│     • Load pages on-demand (not entire document)               │
│     • One document in memory at a time                         │
│                                                                 │
│  3. AUTOMATIC INTELLIGENCE                                      │
│     • System determines active document (keyword detection)    │
│     • Auto-switches PDF when referencing different docs       │
│     • User doesn't need to manually select documents           │
│                                                                 │
│  4. USER CONTROL                                                │
│     • Can close PDF panel anytime                              │
│     • Can manually switch documents via chips                  │
│     • Can toggle PDF panel on/off                              │
│                                                                 │
│  5. PERFORMANCE FIRST                                           │
│     • Fast initial load (no PDF blocking)                      │
│     • Page-level loading (not entire PDF)                      │
│     • Caching strategy for viewed pages                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## UI States & Transitions

### State 1: Chat-Only (Default)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  💬 COA Analysis                                   [User] [Settings] [▶]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Documents in this chat:                                                │
│  ┌──────────┬──────────┬──────────┐                                    │
│  │📄COA_001│📄COA_002│📄COA_003●│ ← Active indicator (no PDF loaded) │
│  │  Jan 15 │  Jan 18 │  Jan 20  │                                     │
│  └──────────┴──────────┴──────────┘                                    │
│                                                                         │
│  ───────────────────────────────────────────────────────────────────── │
│                                                                         │
│  [User]: What is the pH value?                                          │
│                                                                         │
│  [Bot]: The pH value in COA_003.pdf is 6.1                             │
│                                                                         │
│         📍 References:                                                  │
│         [COA_003.pdf - Page 2] ← Click to open PDF viewer              │
│                                                                         │
│  ───────────────────────────────────────────────────────────────────── │
│                                                                         │
│  [Type your message...]                                        [Send ▶]│
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

CHARACTERISTICS:
─────────────────────────────────────────────────────────────────────────
• Full width chat interface
• No PDF loaded in memory
• Fast, responsive
• Reference buttons visible and clickable
• Toggle button [▶] in header to manually open PDF
```

---

### State 2: Split View (PDF + Chat)

```
┌──────────────────────────┬──────────────────────────────────────────────┐
│   PDF VIEWER (40%)       │          CHAT (60%)                          │
│   Lazy loaded            │                                              │
├──────────────────────────┤  💬 COA Analysis              [Close PDF ✕] │
│                          │                                              │
│ ┌──────────────────────┐ │  Documents:                                  │
│ │ 📄 COA_003.pdf       │ │  📄COA_001  📄COA_002  📄COA_003●           │
│ │                      │ │                         └─ Viewing           │
│ │ Page 2/50            │ │                                              │
│ │                      │ │ ───────────────────────────────────────────│
│ │  ┌────────────────┐  │ │                                              │
│ │  │   Table        │  │ │ [User]: What is the pH value?                │
│ │  │  ┌──────────┐  │  │ │                                              │
│ │  │  │░░░ 6.1 ░░│◀─┼──┼─│ [Bot]: The pH value is 6.1                  │
│ │  │  │░░░░░░░░░░│  │  │ │        📍 References:                       │
│ │  │  └──────────┘  │  │ │        [COA_003.pdf - Page 2] ← Highlighted │
│ │  │                │  │ │                                              │
│ │  └────────────────┘  │ │ [Type message...]                  [Send ▶] │
│ │    ↑ Cell highlight  │ │                                              │
│ │                      │ │                                              │
│ │ [◀ Prev] [Next ▶]    │ │                                              │
│ └──────────────────────┘ │                                              │
│                          │                                              │
└──────────────────────────┴──────────────────────────────────────────────┘

CHARACTERISTICS:
─────────────────────────────────────────────────────────────────────────
• PDF panel slides in from left (300ms animation)
• Only COA_003.pdf loaded (active document)
• Only Page 2 loaded initially (not all 50 pages)
• Cell-level highlight at bbox coordinates
• Chat remains fully functional
• Close button [✕] closes PDF panel
```

---

### State 3: Document Switching

```
USER ACTION: Clicks 📄 COA_001 chip
                │
                ▼
SYSTEM RESPONSE:
┌──────────────────────────┬──────────────────────────────────────────────┐
│   PDF VIEWER             │          CHAT                                │
├──────────────────────────┤                                              │
│                          │  Documents:                                  │
│ ┌──────────────────────┐ │  📄COA_001●  📄COA_002  📄COA_003           │
│ │ 📄 COA_001.pdf       │ │      └─ Now viewing                          │
│ │                      │ │                                              │
│ │ Page 1/45            │ │ ───────────────────────────────────────────│
│ │                      │ │                                              │
│ │ [Document content]   │ │ [User]: What was batch in first document?   │
│ │                      │ │                                              │
│ │                      │ │ [Bot]: In COA_001.pdf, the batch number     │
│ │                      │ │        is 96309DB                            │
│ │                      │ │        📍 [COA_001.pdf - Page 2]            │
│ │                      │ │                                              │
│ └──────────────────────┘ │                                              │
└──────────────────────────┴──────────────────────────────────────────────┘

TRANSITION LOGIC:
─────────────────────────────────────────────────────────────────────────
1. Unload COA_003.pdf from memory
2. Clear page cache for COA_003
3. Load COA_001.pdf Page 1 (default page)
4. Update active document indicator
5. Transition time: ~200ms
```

---

## Database Schema Alignment

### Tables Used (From Existing Schema)

```sql
-- ═════════════════════════════════════════════════════════════════
-- TABLE 1: chats
-- ═════════════════════════════════════════════════════════════════
-- Purpose: Store chat sessions
-- Used for: Getting active_document_id, document list

CREATE TABLE chats (
    chat_id              VARCHAR(50) PRIMARY KEY,
    user_id              VARCHAR(50),
    active_document_id   VARCHAR(50),     -- ← Controls which PDF loads
    summary              TEXT,
    message_count        INTEGER,
    created_at           TIMESTAMP,
    updated_at           TIMESTAMP
);


-- ═════════════════════════════════════════════════════════════════
-- TABLE 2: chat_documents
-- ═════════════════════════════════════════════════════════════════
-- Purpose: Track multiple documents per chat
-- Used for: Document chips, switching PDFs

CREATE TABLE chat_documents (
    id                   SERIAL PRIMARY KEY,
    chat_id              VARCHAR(50),
    document_id          VARCHAR(50),     -- ← Links to Elasticsearch chunks
    document_name        VARCHAR(255),    -- ← Displayed in chips
    upload_order         INTEGER,         -- ← Determines "first", "previous"
    created_at           TIMESTAMP
);


-- ═════════════════════════════════════════════════════════════════
-- TABLE 3: messages
-- ═════════════════════════════════════════════════════════════════
-- Purpose: Store chat history
-- Used for: Displaying conversation, references

CREATE TABLE messages (
    message_id           VARCHAR(50) PRIMARY KEY,
    chat_id              VARCHAR(50),
    document_id          VARCHAR(50),     -- ← Which doc message refers to
    role                 VARCHAR(20),
    content              TEXT,
    sequence_num         INTEGER,
    created_at           TIMESTAMP
);
```

### Query Patterns for PDF Viewer

```sql
-- ═════════════════════════════════════════════════════════════════
-- QUERY 1: Get chat with documents (on page load)
-- ═════════════════════════════════════════════════════════════════
SELECT
    c.chat_id,
    c.active_document_id,
    c.title,
    cd.document_id,
    cd.document_name,
    cd.upload_order
FROM chats c
LEFT JOIN chat_documents cd ON c.chat_id = cd.chat_id
WHERE c.chat_id = 'chat_123'
ORDER BY cd.upload_order ASC;

-- Returns:
-- {
--   chat_id: "chat_123",
--   active_document_id: "doc_003",
--   documents: [
--     {id: "doc_001", name: "COA_001.pdf", order: 1},
--     {id: "doc_002", name: "COA_002.pdf", order: 2},
--     {id: "doc_003", name: "COA_003.pdf", order: 3}
--   ]
-- }


-- ═════════════════════════════════════════════════════════════════
-- QUERY 2: Update active document (when user switches)
-- ═════════════════════════════════════════════════════════════════
UPDATE chats
SET active_document_id = 'doc_001',
    updated_at = NOW()
WHERE chat_id = 'chat_123';


-- ═════════════════════════════════════════════════════════════════
-- QUERY 3: Get document metadata (for PDF loading)
-- ═════════════════════════════════════════════════════════════════
SELECT
    document_id,
    document_name
FROM chat_documents
WHERE chat_id = 'chat_123'
  AND document_id = 'doc_003';

-- Returns:
-- {
--   document_id: "doc_003",
--   document_name: "COA_003.pdf"
-- }
```

---

## Component Architecture

### Frontend Component Tree

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  <ChatPage>                                                     │
│    │                                                            │
│    ├── <ChatHeader>                                             │
│    │     ├── title: "COA Analysis"                             │
│    │     ├── <DocumentChips>                                    │
│    │     │     ├── chips: documents[]                          │
│    │     │     ├── activeDocId: string                         │
│    │     │     └── onSwitchDoc(docId)                          │
│    │     │                                                      │
│    │     └── <TogglePDFButton>                                  │
│    │           ├── isPDFOpen: boolean                          │
│    │           └── onToggle()                                   │
│    │                                                            │
│    ├── <MainContent> layout={isPDFOpen ? 'split' : 'full'}    │
│    │     │                                                      │
│    │     ├── {isPDFOpen && (                                    │
│    │     │     <PDFPanel>                                       │
│    │     │       ├── documentId: string                        │
│    │     │       ├── currentPage: number                       │
│    │     │       ├── highlightBbox: BBox | null                │
│    │     │       ├── onPageChange(page)                        │
│    │     │       └── onClose()                                 │
│    │     │         │                                            │
│    │     │         ├── <PDFViewer>                              │
│    │     │         │     ├── <Canvas> (image + bbox overlay)   │
│    │     │         │     └── pageImage: string                 │
│    │     │         │                                            │
│    │     │         └── <PDFControls>                            │
│    │     │               ├── [◀ Prev]                          │
│    │     │               ├── "Page X/Y"                        │
│    │     │               └── [Next ▶]                          │
│    │     │   )}                                                │
│    │     │                                                      │
│    │     └── <ChatPanel>                                        │
│    │           ├── messages: Message[]                         │
│    │           ├── onSendMessage(text)                         │
│    │           └── <MessageList>                                │
│    │                 └── <Message>                              │
│    │                       ├── content: string                 │
│    │                       ├── role: 'user' | 'assistant'     │
│    │                       └── <References>                     │
│    │                             └── <ReferenceButton>          │
│    │                                   ├── docName: string     │
│    │                                   ├── page: number        │
│    │                                   └── onClick() → Open PDF│
│    │                                                            │
│    └── <ChatInput>                                              │
│          ├── value: string                                     │
│          ├── onChange(text)                                    │
│          └── onSend()                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### State Management

```typescript
// Main state in ChatPage component
interface ChatPageState {
  // Chat data
  chatId: string
  messages: Message[]

  // Document data (from chat_documents table)
  documents: Document[]
  activeDocumentId: string

  // PDF viewer state
  isPDFOpen: boolean
  currentPDFPage: number
  currentHighlight: BoundingBox | null

  // Loading state
  isLoadingPDF: boolean
  isLoadingMessages: boolean
}

interface Document {
  id: string              // document_id from chat_documents
  name: string            // document_name from chat_documents
  uploadOrder: number     // upload_order from chat_documents
  pageCount: number       // total pages (from backend)
}

interface Message {
  id: string              // message_id from messages table
  chatId: string
  documentId: string      // Which doc this message refers to
  role: 'user' | 'assistant'
  content: string
  references?: Reference[]
  createdAt: string
}

interface Reference {
  id: string
  documentId: string      // Which document
  documentName: string    // For display
  page: number
  bbox: BoundingBox       // Table-level bbox
  cellBbox?: BoundingBox  // Cell-level bbox (if available)
}

interface BoundingBox {
  left: number            // Normalized 0-1
  top: number
  right: number
  bottom: number
}
```

---

## User Flows

### Flow 1: First-Time User (No PDF Loaded)

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: User opens chat                                         │
├─────────────────────────────────────────────────────────────────┤
│ URL: /chat/chat_123                                             │
│                                                                 │
│ Frontend:                                                       │
│ 1. GET /api/chats/chat_123                                     │
│    Returns: { chatId, activeDocumentId, documents: [...] }     │
│ 2. GET /api/chats/chat_123/messages                            │
│    Returns: { messages: [...] }                                │
│ 3. Render chat-only view (no PDF)                              │
│                                                                 │
│ State:                                                          │
│ • isPDFOpen: false                                             │
│ • activeDocumentId: "doc_003"                                  │
│ • documents: [doc_001, doc_002, doc_003]                       │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: User asks question                                      │
├─────────────────────────────────────────────────────────────────┤
│ User: "What is the pH value?"                                   │
│                                                                 │
│ Frontend:                                                       │
│ POST /api/chats/chat_123/messages                              │
│ { content: "What is the pH value?" }                           │
│                                                                 │
│ Backend (from MULTI_DOCUMENT_WORKFLOW.md):                     │
│ 1. Detect target document (no keyword → use active_doc)       │
│ 2. Hybrid search in Elasticsearch (doc_003)                    │
│ 3. Call Claude with context                                    │
│ 4. Extract cell reference from answer                          │
│ 5. Return message with references                              │
│                                                                 │
│ Response:                                                       │
│ {                                                               │
│   messageId: "msg_001",                                        │
│   role: "assistant",                                           │
│   content: "The pH value is 6.1",                              │
│   references: [{                                                │
│     documentId: "doc_003",                                     │
│     documentName: "COA_003.pdf",                               │
│     page: 2,                                                   │
│     bbox: {left: 0.13, top: 0.30, ...},                       │
│     cellBbox: {left: 0.70, top: 0.45, ...}                    │
│   }]                                                            │
│ }                                                               │
│                                                                 │
│ UI Update:                                                      │
│ • Message appears in chat                                      │
│ • Reference button rendered: [COA_003.pdf - Page 2]           │
│ • PDF still NOT loaded (stays fast)                            │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: User clicks reference button                           │
├─────────────────────────────────────────────────────────────────┤
│ User clicks: [COA_003.pdf - Page 2]                           │
│                                                                 │
│ Frontend:                                                       │
│ handleReferenceClick(reference) {                              │
│   // Check if PDF panel open                                   │
│   if (!isPDFOpen) {                                            │
│     openPDFPanel()  // Slide-in animation                      │
│   }                                                             │
│                                                                 │
│   // Check if different document                               │
│   if (reference.documentId !== activeDocumentId) {            │
│     switchDocument(reference.documentId)                       │
│   }                                                             │
│                                                                 │
│   // Load specific page                                        │
│   loadPDFPage(reference.documentId, reference.page)           │
│                                                                 │
│   // Set highlight                                             │
│   setHighlight(reference.cellBbox || reference.bbox)          │
│ }                                                               │
│                                                                 │
│ API Call:                                                       │
│ GET /api/documents/doc_003/pages/2/image                       │
│ Returns: { imageUrl: "/static/doc_003/page_2.webp" }          │
│                                                                 │
│ State Update:                                                   │
│ • isPDFOpen: true                                              │
│ • currentPDFPage: 2                                            │
│ • currentHighlight: {left: 0.70, top: 0.45, ...}              │
│                                                                 │
│ UI Transition:                                                  │
│ • PDF panel slides in (300ms)                                  │
│ • Page 2 image loads                                           │
│ • Yellow highlight box drawn at cellBbox coordinates           │
└─────────────────────────────────────────────────────────────────┘
```

---

### Flow 2: Multi-Document Reference

```
┌─────────────────────────────────────────────────────────────────┐
│ SCENARIO: User asks about first document                        │
├─────────────────────────────────────────────────────────────────┤
│ User: "What was the batch number in the first document?"       │
│                                                                 │
│ Backend (from MULTI_DOCUMENT_WORKFLOW.md):                     │
│ 1. Keyword detection: "first" → doc_001 (upload_order: 1)     │
│ 2. RAG search in doc_001                                       │
│ 3. Claude generates answer                                     │
│ 4. Returns reference to doc_001                                │
│                                                                 │
│ Response:                                                       │
│ {                                                               │
│   content: "In COA_001.pdf (first document), batch is 96309DB",│
│   references: [{                                                │
│     documentId: "doc_001",  ← Different from active doc_003   │
│     documentName: "COA_001.pdf",                               │
│     page: 2                                                    │
│   }]                                                            │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│ User clicks: [COA_001.pdf - Page 2]                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ System detects: reference.documentId !== activeDocumentId      │
│ ("doc_001" !== "doc_003")                                      │
│                                                                 │
│ Action Sequence:                                                │
│ 1. If PDF open: Unload current PDF (doc_003)                  │
│ 2. Update active document in state                             │
│ 3. Load new PDF (doc_001)                                      │
│ 4. Navigate to page 2                                          │
│ 5. Highlight bbox                                              │
│ 6. Update document chip indicator                              │
│                                                                 │
│ API Calls:                                                      │
│ 1. PATCH /api/chats/chat_123                                   │
│    { activeDocumentId: "doc_001" }  ← Update in database      │
│ 2. GET /api/documents/doc_001/pages/2/image                    │
│    Returns: image for doc_001 page 2                           │
│                                                                 │
│ UI Update:                                                      │
│ • Document chip changes: 📄COA_001● (now active)              │
│ • PDF viewer updates to show COA_001.pdf                       │
│ • Page 2 displayed with highlight                              │
└─────────────────────────────────────────────────────────────────┘
```

---

### Flow 3: Manual Document Switching

```
┌─────────────────────────────────────────────────────────────────┐
│ SCENARIO: User clicks document chip                             │
├─────────────────────────────────────────────────────────────────┤
│ PDF is open showing COA_003.pdf                                │
│ User clicks: 📄 COA_002 chip                                   │
│                                                                 │
│ handleChipClick(documentId: "doc_002") {                       │
│   // Update active document                                    │
│   setActiveDocumentId("doc_002")                               │
│                                                                 │
│   // Update in database                                        │
│   await updateActiveDocument(chatId, "doc_002")                │
│                                                                 │
│   // If PDF open, reload with new document                     │
│   if (isPDFOpen) {                                             │
│     unloadCurrentPDF()                                         │
│     loadPDF("doc_002", page: 1)  // Default to page 1         │
│   }                                                             │
│ }                                                               │
│                                                                 │
│ Transition:                                                     │
│ • COA_003.pdf unloads                                          │
│ • COA_002.pdf page 1 loads                                     │
│ • Active indicator moves to COA_002 chip                       │
│ • No highlight (user manually switched, not from reference)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Performance Strategy

### Lazy Loading Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  LOADING PRIORITY SYSTEM                                        │
│  ══════════════════════                                         │
│                                                                 │
│  TIER 1: IMMEDIATE (0ms - Blocking)                            │
│  ────────────────────────────────────────────────────────────  │
│  • Chat messages                                                │
│  • Document chips                                               │
│  • Current message input                                        │
│                                                                 │
│  TIER 2: ON-DEMAND (200ms - User triggered)                    │
│  ────────────────────────────────────────────────────────────  │
│  • PDF page image (only when reference clicked)                │
│  • Current page only (not all pages)                            │
│  • Bbox coordinates (already in Elasticsearch)                 │
│                                                                 │
│  TIER 3: BACKGROUND (1000ms+ - Preemptive)                     │
│  ────────────────────────────────────────────────────────────  │
│  • Next page (page + 1)                                        │
│  • Previous page (page - 1)                                    │
│  • Only after current page fully rendered                       │
│                                                                 │
│  TIER 4: DEFERRED (Never unless needed)                        │
│  ────────────────────────────────────────────────────────────  │
│  • All other pages                                             │
│  • Only loaded when user navigates to them                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Page Loading Implementation

```typescript
// Page cache with LRU eviction
class PDFPageCache {
  private cache = new Map<string, string>()
  private maxSize = 20  // Max 20 pages in memory

  // Generate cache key
  private getCacheKey(docId: string, page: number): string {
    return `${docId}_page_${page}`
  }

  // Get page from cache or load
  async getPage(docId: string, page: number): Promise<string> {
    const key = this.getCacheKey(docId, page)

    // Check cache
    if (this.cache.has(key)) {
      console.log(`Cache HIT: ${key}`)
      return this.cache.get(key)!
    }

    // Load from backend
    console.log(`Cache MISS: ${key} - Loading from backend`)
    const imageUrl = await this.loadPageFromBackend(docId, page)

    // Add to cache (with size limit)
    if (this.cache.size >= this.maxSize) {
      // Remove oldest entry (first in map)
      const firstKey = this.cache.keys().next().value
      this.cache.delete(firstKey)
      console.log(`Cache EVICTED: ${firstKey}`)
    }

    this.cache.set(key, imageUrl)
    return imageUrl
  }

  // Load page from backend
  private async loadPageFromBackend(docId: string, page: number): Promise<string> {
    const response = await fetch(`/api/documents/${docId}/pages/${page}/image`)
    const data = await response.json()
    return data.imageUrl
  }

  // Clear cache for document (when switching)
  clearDocument(docId: string) {
    for (const key of this.cache.keys()) {
      if (key.startsWith(docId)) {
        this.cache.delete(key)
      }
    }
  }

  // Preload adjacent pages (background)
  async preloadAdjacentPages(docId: string, currentPage: number, totalPages: number) {
    const pagesToPreload = [
      currentPage - 1,  // Previous page
      currentPage + 1   // Next page
    ].filter(p => p > 0 && p <= totalPages)

    // Load in background (don't await)
    pagesToPreload.forEach(page => {
      this.getPage(docId, page).catch(err => {
        console.warn(`Failed to preload page ${page}:`, err)
      })
    })
  }
}

// Usage in component
const pageCache = new PDFPageCache()

async function loadPDFPage(docId: string, page: number) {
  setIsLoadingPage(true)

  try {
    // Load current page (waits)
    const imageUrl = await pageCache.getPage(docId, page)
    setCurrentPageImage(imageUrl)

    // Preload adjacent pages (background, no wait)
    setTimeout(() => {
      pageCache.preloadAdjacentPages(docId, page, totalPages)
    }, 500)

  } catch (error) {
    console.error('Failed to load page:', error)
    setPageError(error.message)
  } finally {
    setIsLoadingPage(false)
  }
}
```

### Document Switching Optimization

```typescript
// Efficient document switching
async function switchDocument(newDocId: string) {
  // 1. Update state immediately (optimistic)
  setActiveDocumentId(newDocId)

  // 2. Clear old document from cache
  pageCache.clearDocument(currentDocumentId)

  // 3. Update database (async, no wait)
  updateActiveDocumentInDB(chatId, newDocId).catch(err => {
    console.error('Failed to update active doc:', err)
    // Could rollback on error, but not critical
  })

  // 4. Load new document page 1
  if (isPDFOpen) {
    await loadPDFPage(newDocId, 1)
  }

  // Total transition time: ~200ms (perceived instant)
}
```

---

## API Endpoints

### New Endpoints Required

```
┌─────────────────────────────────────────────────────────────────┐
│  PDF IMAGE ENDPOINTS                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  GET /api/documents/:documentId/pages/:pageNum/image            │
│  ────────────────────────────────────────────────────────────  │
│  Purpose: Get single page as image (WebP/PNG)                  │
│  Returns: { imageUrl, width, height }                          │
│                                                                 │
│  Implementation:                                                │
│  • Check if image already generated (cached on disk)           │
│  • If not, convert PDF page to image using PyMuPDF             │
│  • Store in /static/documents/{docId}/page_{num}.webp         │
│  • Return static file URL                                      │
│                                                                 │
│  Example Response:                                              │
│  {                                                              │
│    "imageUrl": "/static/documents/doc_003/page_2.webp",       │
│    "width": 1200,                                              │
│    "height": 1600                                              │
│  }                                                              │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  GET /api/documents/:documentId/metadata                        │
│  ────────────────────────────────────────────────────────────  │
│  Purpose: Get document info (page count, size, etc.)           │
│  Returns: { documentId, name, pageCount, uploadedAt }         │
│                                                                 │
│  Implementation:                                                │
│  • Query chat_documents table                                  │
│  • Get page count from PDF metadata (stored during upload)    │
│                                                                 │
│  Example Response:                                              │
│  {                                                              │
│    "documentId": "doc_003",                                    │
│    "documentName": "COA_003.pdf",                              │
│    "pageCount": 50,                                            │
│    "uploadedAt": "2026-01-20T10:30:00Z"                        │
│  }                                                              │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PATCH /api/chats/:chatId                                       │
│  ────────────────────────────────────────────────────────────  │
│  Purpose: Update active document                                │
│  Body: { activeDocumentId: "doc_001" }                         │
│  Returns: { success: true }                                    │
│                                                                 │
│  Implementation:                                                │
│  UPDATE chats                                                   │
│  SET active_document_id = 'doc_001',                           │
│      updated_at = NOW()                                        │
│  WHERE chat_id = 'chat_123'                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Existing Endpoints (From Other Docs)

```
From MULTI_DOCUMENT_WORKFLOW.md:
─────────────────────────────────────────────────────────────────
GET    /api/chats/:chatId
GET    /api/chats/:chatId/messages
POST   /api/chats/:chatId/messages
POST   /api/chats/:chatId/documents

From CHAT_HISTORY_PRESERVATION.md:
─────────────────────────────────────────────────────────────────
GET    /api/chats
POST   /api/chats
DELETE /api/chats/:chatId
```

---

## Implementation Code

### Backend: PDF Page Image Conversion

```python
# services/pdf_image_service.py

import fitz  # PyMuPDF
from pathlib import Path
import os

class PDFImageService:
    def __init__(self):
        self.static_dir = Path("static/documents")
        self.static_dir.mkdir(parents=True, exist_ok=True)

    def get_page_image(self, document_id: str, page_num: int) -> dict:
        """
        Get single page as image.
        Generates on-demand and caches on disk.
        """

        # Check if image already exists
        image_path = self.static_dir / document_id / f"page_{page_num}.webp"

        if image_path.exists():
            # Already generated, return URL
            return {
                "imageUrl": f"/static/documents/{document_id}/page_{page_num}.webp",
                "cached": True
            }

        # Get PDF path
        pdf_path = self.get_pdf_path(document_id)

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {document_id}")

        # Generate image
        doc = fitz.open(pdf_path)

        if page_num < 1 or page_num > len(doc):
            raise ValueError(f"Invalid page number: {page_num}")

        # Get page
        page = doc[page_num - 1]  # 0-indexed

        # Render at 150 DPI (good quality, reasonable size)
        zoom = 150 / 72
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)

        # Ensure output directory exists
        image_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as WebP (good compression)
        pixmap.save(str(image_path))

        width = pixmap.width
        height = pixmap.height

        doc.close()

        return {
            "imageUrl": f"/static/documents/{document_id}/page_{page_num}.webp",
            "width": width,
            "height": height,
            "cached": False
        }

    def get_pdf_path(self, document_id: str) -> str:
        """Get PDF file path from document_id"""
        # Query database or file system
        # This depends on your storage strategy
        return f"temp/{document_id}.pdf"

    def pregenerate_pages(self, document_id: str, page_range: list[int]):
        """
        Pregenerate multiple pages (background task).
        Useful for initial upload processing.
        """
        for page_num in page_range:
            try:
                self.get_page_image(document_id, page_num)
            except Exception as e:
                print(f"Failed to pregenerate page {page_num}: {e}")


# routes/document_routes.py

from fastapi import APIRouter, HTTPException
from services.pdf_image_service import PDFImageService

router = APIRouter()
pdf_service = PDFImageService()

@router.get("/api/documents/{document_id}/pages/{page_num}/image")
async def get_page_image(document_id: str, page_num: int):
    """
    Get single page as image.
    Returns cached image if available, generates otherwise.
    """
    try:
        result = pdf_service.get_page_image(document_id, page_num)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/documents/{document_id}/metadata")
async def get_document_metadata(document_id: str):
    """
    Get document metadata (page count, name, etc.)
    """
    # Query database
    doc = db.execute("""
        SELECT document_id, document_name, created_at
        FROM chat_documents
        WHERE document_id = %s
        LIMIT 1
    """, [document_id]).fetchone()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get page count from PDF
    pdf_path = pdf_service.get_pdf_path(document_id)
    doc_pdf = fitz.open(pdf_path)
    page_count = len(doc_pdf)
    doc_pdf.close()

    return {
        "documentId": doc.document_id,
        "documentName": doc.document_name,
        "pageCount": page_count,
        "uploadedAt": doc.created_at.isoformat()
    }


@router.patch("/api/chats/{chat_id}")
async def update_chat(chat_id: str, body: dict):
    """
    Update chat properties (e.g., active_document_id)
    """
    active_doc_id = body.get("activeDocumentId")

    if active_doc_id:
        db.execute("""
            UPDATE chats
            SET active_document_id = %s,
                updated_at = NOW()
            WHERE chat_id = %s
        """, [active_doc_id, chat_id])

    return {"success": True}
```

---

### Frontend: PDFPanel Component

```tsx
// components/PDFPanel.tsx

import { useState, useEffect, useRef } from 'react'
import { Canvas, Layer, Rect, Image as KonvaImage } from 'react-konva'
import useImage from 'use-image'

interface BoundingBox {
  left: number
  top: number
  right: number
  bottom: number
}

interface PDFPanelProps {
  documentId: string
  documentName: string
  initialPage?: number
  highlightBbox?: BoundingBox | null
  onClose: () => void
  onPageChange?: (page: number) => void
}

export function PDFPanel({
  documentId,
  documentName,
  initialPage = 1,
  highlightBbox,
  onClose,
  onPageChange
}: PDFPanelProps) {
  const [currentPage, setCurrentPage] = useState(initialPage)
  const [pageCount, setPageCount] = useState(0)
  const [imageUrl, setImageUrl] = useState<string>('')
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [image] = useImage(imageUrl)
  const containerRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)

  // Load document metadata on mount
  useEffect(() => {
    loadDocumentMetadata()
  }, [documentId])

  // Load page when documentId or currentPage changes
  useEffect(() => {
    loadPage(currentPage)
  }, [documentId, currentPage])

  // Calculate scale to fit container
  useEffect(() => {
    if (containerRef.current && imageSize.width > 0) {
      const containerWidth = containerRef.current.offsetWidth - 40
      const newScale = Math.min(containerWidth / imageSize.width, 1)
      setScale(newScale)
    }
  }, [imageSize])

  async function loadDocumentMetadata() {
    try {
      const response = await fetch(`/api/documents/${documentId}/metadata`)
      const data = await response.json()
      setPageCount(data.pageCount)
    } catch (err) {
      console.error('Failed to load document metadata:', err)
    }
  }

  async function loadPage(page: number) {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch(`/api/documents/${documentId}/pages/${page}/image`)

      if (!response.ok) {
        throw new Error(`Failed to load page: ${response.statusText}`)
      }

      const data = await response.json()
      setImageUrl(data.imageUrl)
      setImageSize({ width: data.width, height: data.height })

      // Notify parent of page change
      onPageChange?.(page)

      // Preload adjacent pages in background
      setTimeout(() => {
        preloadAdjacentPages(page)
      }, 500)

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load page')
    } finally {
      setIsLoading(false)
    }
  }

  async function preloadAdjacentPages(page: number) {
    // Preload previous and next page
    const pagesToPreload = [page - 1, page + 1].filter(
      p => p > 0 && p <= pageCount
    )

    pagesToPreload.forEach(async p => {
      try {
        await fetch(`/api/documents/${documentId}/pages/${p}/image`)
      } catch (err) {
        // Ignore preload errors
      }
    })
  }

  function handlePrevPage() {
    if (currentPage > 1) {
      setCurrentPage(currentPage - 1)
    }
  }

  function handleNextPage() {
    if (currentPage < pageCount) {
      setCurrentPage(currentPage + 1)
    }
  }

  // Convert bbox to pixel coordinates
  function bboxToRect(bbox: BoundingBox) {
    return {
      x: bbox.left * imageSize.width * scale,
      y: bbox.top * imageSize.height * scale,
      width: (bbox.right - bbox.left) * imageSize.width * scale,
      height: (bbox.bottom - bbox.top) * imageSize.height * scale
    }
  }

  const displayWidth = imageSize.width * scale
  const displayHeight = imageSize.height * scale

  return (
    <div className="pdf-panel">
      {/* Header */}
      <div className="pdf-header">
        <div className="pdf-title">
          📄 {documentName}
        </div>
        <button className="close-btn" onClick={onClose}>
          ✕
        </button>
      </div>

      {/* Content */}
      <div ref={containerRef} className="pdf-content">
        {isLoading && (
          <div className="pdf-loading">
            <div className="spinner" />
            <p>Loading page {currentPage}...</p>
          </div>
        )}

        {error && (
          <div className="pdf-error">
            <p>❌ {error}</p>
            <button onClick={() => loadPage(currentPage)}>Retry</button>
          </div>
        )}

        {!isLoading && !error && image && (
          <Stage width={displayWidth} height={displayHeight}>
            <Layer>
              {/* Page Image */}
              <KonvaImage
                image={image}
                width={displayWidth}
                height={displayHeight}
              />

              {/* Highlight Overlay */}
              {highlightBbox && (
                <Rect
                  {...bboxToRect(highlightBbox)}
                  fill="rgba(255, 235, 59, 0.35)"
                  stroke="#FFC107"
                  strokeWidth={2}
                  cornerRadius={4}
                />
              )}
            </Layer>
          </Stage>
        )}
      </div>

      {/* Controls */}
      <div className="pdf-controls">
        <button
          className="nav-btn"
          onClick={handlePrevPage}
          disabled={currentPage <= 1}
        >
          ◀ Prev
        </button>

        <span className="page-info">
          Page {currentPage} of {pageCount}
        </span>

        <button
          className="nav-btn"
          onClick={handleNextPage}
          disabled={currentPage >= pageCount}
        >
          Next ▶
        </button>
      </div>
    </div>
  )
}
```

---

### Frontend: ChatPage Integration

```tsx
// app/chat/page.tsx

import { useState, useEffect } from 'react'
import { PDFPanel } from '@/components/PDFPanel'
import { DocumentChips } from '@/components/DocumentChips'
import { ChatPanel } from '@/components/ChatPanel'

export default function ChatPage({ params }: { params: { chatId: string } }) {
  const { chatId } = params

  // Chat data
  const [messages, setMessages] = useState([])
  const [documents, setDocuments] = useState([])
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null)

  // PDF viewer state
  const [isPDFOpen, setIsPDFOpen] = useState(false)
  const [pdfPage, setPdfPage] = useState(1)
  const [pdfHighlight, setPdfHighlight] = useState<BoundingBox | null>(null)

  // Load chat on mount
  useEffect(() => {
    loadChatData()
  }, [chatId])

  async function loadChatData() {
    try {
      // Get chat with documents
      const response = await fetch(`/api/chats/${chatId}`)
      const data = await response.json()

      setDocuments(data.documents)
      setActiveDocumentId(data.activeDocumentId)

      // Load messages
      const messagesResponse = await fetch(`/api/chats/${chatId}/messages`)
      const messagesData = await messagesResponse.json()

      setMessages(messagesData.messages)
    } catch (error) {
      console.error('Failed to load chat:', error)
    }
  }

  // Handle reference click (from chat message)
  function handleReferenceClick(reference: Reference) {
    // If different document, switch it
    if (reference.documentId !== activeDocumentId) {
      switchDocument(reference.documentId)
    }

    // Open PDF panel if closed
    if (!isPDFOpen) {
      setIsPDFOpen(true)
    }

    // Navigate to page and highlight
    setPdfPage(reference.page)
    setPdfHighlight(reference.cellBbox || reference.bbox)
  }

  // Switch document (from chip click)
  async function switchDocument(documentId: string) {
    setActiveDocumentId(documentId)

    // Update in database
    await fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ activeDocumentId: documentId })
    })

    // If PDF open, reload with new document
    if (isPDFOpen) {
      setPdfPage(1)  // Default to page 1
      setPdfHighlight(null)  // Clear highlight
    }
  }

  // Toggle PDF panel
  function togglePDFPanel() {
    if (isPDFOpen) {
      setIsPDFOpen(false)
    } else {
      // Open with active document
      setIsPDFOpen(true)
      setPdfPage(1)
    }
  }

  const activeDocument = documents.find(d => d.id === activeDocumentId)

  return (
    <div className="chat-page">
      {/* Header */}
      <div className="chat-header">
        <h1>💬 {chatTitle}</h1>

        <DocumentChips
          documents={documents}
          activeDocumentId={activeDocumentId}
          onSwitchDocument={switchDocument}
        />

        <button className="toggle-pdf-btn" onClick={togglePDFPanel}>
          {isPDFOpen ? 'Close PDF ✕' : 'View PDF ▶'}
        </button>
      </div>

      {/* Main Content */}
      <div className={`main-content ${isPDFOpen ? 'split' : 'full'}`}>
        {/* PDF Panel (conditional) */}
        {isPDFOpen && activeDocument && (
          <PDFPanel
            documentId={activeDocument.id}
            documentName={activeDocument.name}
            initialPage={pdfPage}
            highlightBbox={pdfHighlight}
            onClose={() => setIsPDFOpen(false)}
            onPageChange={setPdfPage}
          />
        )}

        {/* Chat Panel */}
        <ChatPanel
          chatId={chatId}
          messages={messages}
          onReferenceClick={handleReferenceClick}
          onSendMessage={handleSendMessage}
        />
      </div>
    </div>
  )
}
```

---

## Testing Scenarios

### Test Case 1: First-Time Load Performance

```
Scenario: User opens chat for first time
─────────────────────────────────────────────────────────────────
Expected:
• Chat loads in < 1 second
• No PDF loaded (fast)
• Document chips visible
• Messages displayed

Test:
1. Open /chat/chat_123
2. Measure time to first paint
3. Verify no PDF API calls made
4. Verify messages rendered

Success Criteria:
✓ Time to interactive < 1s
✓ No PDF images loaded
✓ All messages visible
```

---

### Test Case 2: Reference Click Performance

```
Scenario: User clicks reference button
─────────────────────────────────────────────────────────────────
Expected:
• PDF panel opens smoothly (300ms)
• Page loads in < 500ms
• Highlight appears immediately
• No page flicker

Test:
1. Click [Page 2] reference
2. Measure panel open time
3. Measure image load time
4. Verify highlight position

Success Criteria:
✓ Panel animation smooth
✓ Image loads < 500ms
✓ Highlight accurate (within 5px)
```

---

### Test Case 3: Document Switching

```
Scenario: User switches between 3 documents
─────────────────────────────────────────────────────────────────
Expected:
• Switch completes in < 300ms
• Previous document unloaded
• New document page 1 shown
• No memory leak

Test:
1. Load COA_001.pdf
2. Switch to COA_002.pdf
3. Switch to COA_003.pdf
4. Monitor memory usage

Success Criteria:
✓ Each switch < 300ms
✓ Memory stays < 200MB
✓ Cache eviction works
```

---

### Test Case 4: Multi-Document Reference

```
Scenario: User asks about first document while viewing third
─────────────────────────────────────────────────────────────────
Expected:
• System detects "first" keyword
• PDF switches to first document automatically
• Page navigates to referenced page
• Highlight shows correct cell

Test:
1. Viewing COA_003.pdf
2. Ask "What was pH in first document?"
3. Click reference
4. Verify switches to COA_001.pdf

Success Criteria:
✓ Correct document loaded
✓ Correct page shown
✓ Correct cell highlighted
```

---

### Test Case 5: Cache Effectiveness

```
Scenario: User navigates back and forth between pages
─────────────────────────────────────────────────────────────────
Expected:
• Cached pages load instantly
• Uncached pages load < 500ms
• Preloading works for adjacent pages

Test:
1. Load page 5
2. Go to page 6 (should preload during step 1)
3. Go back to page 5 (should be cached)
4. Measure load times

Success Criteria:
✓ Cached page: < 50ms
✓ Preloaded page: < 100ms
✓ Cold page: < 500ms
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  PDF VIEWER INTEGRATION - KEY POINTS                            │
│  ═══════════════════════════════════════════════════════════   │
│                                                                 │
│  DEFAULT BEHAVIOR:                                              │
│  • Chat-only view (fast, clean)                                │
│  • PDF loads on-demand (click reference)                       │
│  • One document in memory at a time                             │
│                                                                 │
│  MULTI-DOCUMENT:                                                │
│  • Document chips show all uploaded docs                       │
│  • Active document tracked in database                         │
│  • Auto-switch when referencing different doc                  │
│  • Manual switch via chip click                                │
│                                                                 │
│  PERFORMANCE:                                                   │
│  • Page-level loading (not entire PDF)                         │
│  • LRU cache (max 20 pages)                                    │
│  • Preload adjacent pages (background)                         │
│  • Unload old document when switching                          │
│                                                                 │
│  USER CONTROL:                                                  │
│  • Toggle button to open/close PDF                             │
│  • Close button in PDF panel                                   │
│  • Reference buttons auto-open PDF                             │
│  • Manual document switching via chips                         │
│                                                                 │
│  SCHEMA ALIGNMENT:                                              │
│  ✓ Uses chats.active_document_id                               │
│  ✓ Uses chat_documents.upload_order                            │
│  ✓ Uses messages.document_id                                   │
│  ✓ Elasticsearch cell_grounding for highlights                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Compatible With: MULTI_DOCUMENT_WORKFLOW.md, BBOX_HIGHLIGHT_IMPLEMENTATION.md, CHAT_HISTORY_PRESERVATION.md*
*Schema: Aligned with chats, chat_documents, messages tables*
