# Feature Implementation Documentation

> **Purpose:** Complete technical specifications for OCR Chatbot RAG system features
> **Location:** `/ocr/frontend/feature_implementation/`
> **Last Updated:** January 2026

---

## 📚 Documentation Index

### **Core RAG System**

#### 1. **[COMPLETE_RAG_FLOW_WITH_BBOX.md](./COMPLETE_RAG_FLOW_WITH_BBOX.md)** (9 KB)
- **Summary:** Initial RAG flow with bounding box highlighting
- **Covers:** Basic RAG pipeline, bbox structure, indexing flow
- **Read First:** Foundation document for understanding RAG system

#### 2. **[COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md](./COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md)** (46 KB)
- **Summary:** Enhanced RAG flow with cell-level highlighting
- **Covers:** Cell grounding, precise highlighting, Landing AI comparison
- **Key Addition:** Cell-level bbox vs table-level bbox
- **Schema:** Elasticsearch chunk structure with `cell_grounding` field

---

### **Highlighting System**

#### 3. **[BBOX_HIGHLIGHT_IMPLEMENTATION.md](./BBOX_HIGHLIGHT_IMPLEMENTATION.md)** (30 KB)
- **Summary:** Complete implementation guide for PDF highlighting
- **Covers:** Canvas-based highlighting, coordinate conversion, visual examples
- **Tech Stack:** React Konva, normalized coordinates (0-1)
- **Use Cases:** Table highlight, cell highlight, multi-cell highlight

#### 4. **[TRANSFORMATION_OF_CELL_GROUNDING.md](./TRANSFORMATION_OF_CELL_GROUNDING.md)** (39 KB)
- **Summary:** How Textract blocks transform into cell grounding
- **Covers:** Block parsing, cell ID generation, mapping strategy
- **Source Data:** Actual COA_1000459079_1_blocks.json examples
- **Critical:** Shows how `"1-31"` cell IDs are created from TABLE/CELL blocks

---

### **Search Strategy**

#### 5. **[RAG_QUERY_EXTRACTION_STRATEGY.md](./RAG_QUERY_EXTRACTION_STRATEGY.md)** (42 KB)
- **Summary:** When to use semantic vs keyword vs hybrid search
- **Key Insight:** Q&A uses semantic (top_k), Extraction uses hybrid (no limit)
- **Industry Standard:** Hybrid search (BM25 30% + Vector 70%)
- **Decision Matrix:** Intent classification logic

---

### **Multi-Document Chat**

#### 6. **[MULTI_DOCUMENT_WORKFLOW.md](./MULTI_DOCUMENT_WORKFLOW.md)** (52 KB)
- **Summary:** Multiple documents in same chat window
- **Default Mode:** Multi-document per chat (no separate tabs)
- **Performance:** Keyword detection (~1ms), single Claude call (~1.5s)
- **Schema:** `chats`, `chat_documents`, `messages` tables
- **Key Feature:** "First document", "previous document" detection

#### 7. **[PDF_VIEWER_CHAT_INTEGRATION.md](./PDF_VIEWER_CHAT_INTEGRATION.md)** (70 KB)
- **Summary:** Complete UX flow for PDF viewer panel with lazy loading
- **Default Behavior:** Chat-only view (no PDF loaded initially)
- **Auto-Open:** PDF panel opens when clicking reference button
- **Performance:** Page-level loading (not entire PDF), LRU cache
- **User Control:** Toggle, close, manual document switching

---

### **Chat History**

#### 8. **[CHAT_HISTORY_PRESERVATION.md](./CHAT_HISTORY_PRESERVATION.md)** (40 KB)
- **Summary:** Long-term chat history with summarization
- **Strategy:** Keep last 20 messages, summarize older ones
- **Trigger:** Auto-summarize when message_count > 30
- **Schema:** `messages` table with `is_summarized` flag
- **Performance:** Reduces context length, maintains continuity

#### 9. **[CHAT_HISTORY_IMPLEMENTATION_PLAN.md](./CHAT_HISTORY_IMPLEMENTATION_PLAN.md)** (29 KB)
- **Summary:** Implementation steps for chat history system
- **Covers:** Database setup, API endpoints, frontend components
- **Phases:** MVP → Enhanced → Production-ready

---

## 🎯 Quick Start Guide

### **For Developers New to the Project:**

**Read in this order:**

1. **COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md** - Understand the RAG system
2. **TRANSFORMATION_OF_CELL_GROUNDING.md** - How Textract data becomes chunks
3. **MULTI_DOCUMENT_WORKFLOW.md** - Multi-document chat architecture
4. **PDF_VIEWER_CHAT_INTEGRATION.md** - UI/UX flow for PDF viewer

**Then, based on task:**

- **Implementing highlighting?** → BBOX_HIGHLIGHT_IMPLEMENTATION.md
- **Implementing search?** → RAG_QUERY_EXTRACTION_STRATEGY.md
- **Implementing chat history?** → CHAT_HISTORY_PRESERVATION.md

---

## 🗂️ File Organization

```
frontend/feature_implementation/
├── README.md                                          ← You are here
│
├── Core RAG System
│   ├── COMPLETE_RAG_FLOW_WITH_BBOX.md                ← Basic RAG flow
│   └── COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md  ← Enhanced with cells
│
├── Highlighting
│   ├── BBOX_HIGHLIGHT_IMPLEMENTATION.md              ← Canvas implementation
│   └── TRANSFORMATION_OF_CELL_GROUNDING.md           ← Textract → Cell IDs
│
├── Search
│   └── RAG_QUERY_EXTRACTION_STRATEGY.md              ← Hybrid search strategy
│
├── Multi-Document
│   ├── MULTI_DOCUMENT_WORKFLOW.md                    ← Multi-doc architecture
│   └── PDF_VIEWER_CHAT_INTEGRATION.md                ← PDF panel UX
│
└── Chat History
    ├── CHAT_HISTORY_PRESERVATION.md                  ← Summarization strategy
    └── CHAT_HISTORY_IMPLEMENTATION_PLAN.md           ← Implementation steps
```

---

## 📊 Schema Summary

### **PostgreSQL Tables**

```sql
-- Core tables (from MULTI_DOCUMENT_WORKFLOW.md)
chats
  ├── chat_id (PK)
  ├── user_id
  ├── active_document_id  ← Controls which PDF shows
  └── summary             ← Summarized old messages

chat_documents
  ├── chat_id (FK)
  ├── document_id         ← Links to Elasticsearch
  ├── document_name
  └── upload_order        ← Determines "first", "previous"

messages
  ├── message_id (PK)
  ├── chat_id (FK)
  ├── document_id         ← Which doc this message is about
  ├── content
  └── is_summarized       ← Whether included in summary
```

### **Elasticsearch Index**

```json
// From COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md
{
  "document_chunks": {
    "id": "chunk_001",
    "document_id": "doc_123",
    "page": 1,
    "type": "table",

    // For RAG search
    "content": "Test Name | Results\npH | 6.1",
    "embedding": [0.1, 0.2, ...],

    // For table highlighting
    "bbox_left": 0.13,
    "bbox_top": 0.30,
    "bbox_right": 0.84,
    "bbox_bottom": 0.70,

    // For cell highlighting
    "cell_grounding": {
      "1-31": {
        "box": {"left": 0.70, "top": 0.45, ...},
        "text": "6.1",
        "type": "tableCell"
      }
    },

    // For markdown tab
    "markdown": "<table id='1-t0'><td id='1-31'>6.1</td></table>"
  }
}
```

---

## 🔑 Key Concepts

### **Cell Grounding**
- **Definition:** Per-cell bounding boxes stored in Elasticsearch chunks
- **Format:** `{"cell_id": {"box": {...}, "text": "...", "type": "tableCell"}}`
- **Purpose:** Enables precise cell-level highlighting (not just entire table)
- **Document:** TRANSFORMATION_OF_CELL_GROUNDING.md

### **Hybrid Search**
- **Definition:** Combines keyword (BM25) and semantic (vector) search
- **Ratio:** 30% keyword + 70% semantic
- **When:** Q&A uses top_k=10, Extraction uses no limit
- **Document:** RAG_QUERY_EXTRACTION_STRATEGY.md

### **Active Document**
- **Definition:** Most recently uploaded or referenced document in chat
- **Storage:** `chats.active_document_id`
- **Purpose:** Determines which PDF loads by default
- **Document:** MULTI_DOCUMENT_WORKFLOW.md

### **Lazy Loading**
- **Definition:** Load PDF pages on-demand, not upfront
- **Strategy:** Current page immediately, adjacent pages in background
- **Cache:** LRU cache with max 20 pages
- **Document:** PDF_VIEWER_CHAT_INTEGRATION.md

### **Chat Summarization**
- **Trigger:** When message_count > 30
- **Strategy:** Summarize messages 1-10, keep last 20 unsummarized
- **Storage:** `chats.summary` field
- **Document:** CHAT_HISTORY_PRESERVATION.md

---

## 🚀 Implementation Priority

### **Phase 1: Core RAG (Complete)**
- ✅ Textract processing
- ✅ Elasticsearch indexing
- ✅ Basic RAG search
- ✅ Table-level bbox

### **Phase 2: Enhanced Highlighting (In Progress)**
- 🔄 Cell grounding extraction
- 🔄 Cell-level highlighting
- ⏳ Markdown tab with clickable cells
- ⏳ Multi-cell highlight support

### **Phase 3: Multi-Document (Planned)**
- ⏳ Multi-document chat schema
- ⏳ Document switching UI
- ⏳ Keyword detection ("first", "previous")
- ⏳ PDF viewer lazy loading

### **Phase 4: Chat History (Planned)**
- ⏳ Message summarization
- ⏳ Long conversation support
- ⏳ Summary regeneration on edit

---

## 📞 Contact & Maintenance

**Document Owner:** Development Team
**Review Cycle:** Every 2 weeks
**Version Control:** All documents in Git
**Feedback:** Create issue in repository

---

## 🔗 Related Documentation

**Main Project:**
- `/ocr/CLAUDE.md` - Overall project documentation
- `/ocr/RAG_ARCHITECTURE.md` - High-level RAG architecture

**Other Features:**
- `/ocr/UI_UX_ENHANCEMENTS.md` - General UI improvements
- `/ocr/LANDING_AI_UI_ANALYSIS.md` - Landing AI comparison

**Backend:**
- `/ocr/backend/app.py` - Main FastAPI application
- `/ocr/backend/textractservices/` - Document processing

**Frontend:**
- `/ocr/frontend/src/app/chat/page.tsx` - Chat interface
- `/ocr/frontend/src/services/agent.ts` - Agent service

---

*Last Updated: January 22, 2026*
*Total Documentation: 9 files, 360+ KB*
*Lines of Documentation: ~8,000 lines*
