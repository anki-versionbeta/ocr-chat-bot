# Bounding Box Highlight Implementation

> **Goal:** Interactive PDF viewer with bidirectional highlighting (like Landing AI)
> **Approach:** PDF → Image + Canvas (same as Landing AI, Google, AWS)
> **Works With:** Your existing Textract chunks with bbox
> **Created:** January 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Your Existing Chunks - Compatible!](#your-existing-chunks---compatible)
3. [Two Flows Explained](#two-flows-explained)
4. [Technology Stack](#technology-stack)
5. [Backend Implementation](#backend-implementation)
6. [Frontend Implementation](#frontend-implementation)
7. [Coordinate Conversion](#coordinate-conversion)
8. [Complete Code](#complete-code)

---

## Overview

### What We're Building

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FINAL USER INTERFACE                               │
│                                                                              │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐   │
│  │      PDF VIEWER (Left)      │  │        CHAT + TEXT (Right)          │   │
│  │                             │  │                                     │   │
│  │  ┌───────────────────────┐  │  │  ┌─────────────────────────────┐   │   │
│  │  │                       │  │  │  │ User: What is batch number? │   │   │
│  │  │   Page 2              │  │  │  └─────────────────────────────┘   │   │
│  │  │                       │  │  │                                     │   │
│  │  │  ┌─────────────────┐  │  │  │  ┌─────────────────────────────┐   │   │
│  │  │  │ ░░ HIGHLIGHT ░░ │◀─┼──┼──┼──│ Bot: Batch is 96309DB       │   │   │
│  │  │  │ ░░░░░░░░░░░░░░░ │  │  │  │  │                             │   │   │
│  │  │  └─────────────────┘  │  │  │  │ 📍 References:              │   │   │
│  │  │          │            │  │  │  │ [Page 2] Product Info ←CLICK│   │   │
│  │  │          │            │  │  │  └─────────────────────────────┘   │   │
│  │  │          ▼            │  │  │                                     │   │
│  │  │    CLICK HERE ────────┼──┼──┼──▶ Shows text in markdown          │   │
│  │  │                       │  │  │                                     │   │
│  │  └───────────────────────┘  │  │  ┌─────────────────────────────┐   │   │
│  │                             │  │  │ Extracted Text:              │   │   │
│  │  [◀] Page 2/50 [▶]          │  │  │ **Product:** ATX-101         │   │   │
│  └─────────────────────────────┘  │  │ **Batch:** 96309DB           │   │   │
│                                   │  └─────────────────────────────┘   │   │
│                                   └─────────────────────────────────────┘   │
│                                                                              │
│  FLOW A: Click PDF region → Show text on right (markdown)                   │
│  FLOW B: Click reference → PDF highlights that region                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Your Existing Chunks - Compatible!

### What You Already Have (From Textract + RAG)

```json
// Your chunks in Elasticsearch
{
  "id": "chunk_abc123",
  "content": "Product: ATX-101\nBatch: 96309DB\nManufactured: 2025-01-15",
  "embedding": [0.1, 0.2, ...],
  "type": "table",
  "page": 2,
  "section": "Product Information",
  "bbox_left": 0.08,
  "bbox_top": 0.18,
  "bbox_right": 0.90,
  "bbox_bottom": 0.25
}
```

### Why This Works Perfectly

```
YOUR TEXTRACT BBOX:
─────────────────────────────────────────────────────────────
• Coordinates are normalized (0-1)
• 0.08 means 8% from left edge
• Works at ANY display size - just multiply!

CALCULATION:
─────────────────────────────────────────────────────────────
Image displayed at 1200px width:
  pixelLeft = 0.08 × 1200 = 96px

Image displayed at 800px width:
  pixelLeft = 0.08 × 800 = 64px

Same normalized bbox works at any zoom level!
```

---

## Two Flows Explained

### Flow A: Click PDF → Show Text

```
User clicks on PDF region
        │
        ▼
Get click position (x, y pixels)
        │
        ▼
Convert to normalized: (x/width, y/height)
        │
        ▼
Find chunk where bbox contains click point
        │
        ▼
Display chunk.content as markdown on right panel
```

### Flow B: Click Reference → Highlight PDF

```
User asks question in chat
        │
        ▼
RAG returns chunks with bbox
        │
        ▼
Bot shows answer + reference buttons
        │
        ▼
User clicks "Page 2" reference
        │
        ▼
PDF navigates to page 2
        │
        ▼
Highlight drawn at chunk's bbox coordinates
```

---

## Technology Stack

### Recommended (Same as Landing AI)

```
BACKEND:
─────────────────────────────────────────────────────────────
• Python + PyMuPDF (fitz) - Convert PDF to images
• Store images in S3 or local storage
• Keep using Textract for OCR + bbox
• Elasticsearch for chunks (already have)

FRONTEND:
─────────────────────────────────────────────────────────────
• React
• react-konva OR HTML Canvas - Draw images + highlights
• ReactMarkdown - Display extracted text

WHY IMAGE APPROACH (not PDF.js):
─────────────────────────────────────────────────────────────
✓ Pixel-perfect accuracy
✓ Bbox matches exactly (same image Textract processed)
✓ No font rendering issues
✓ Simpler code
✓ Same approach as Landing AI, Google, AWS
```

### Install Dependencies

```bash
# Backend
pip install PyMuPDF  # For PDF to image

# Frontend
npm install react-konva konva use-image react-markdown
```

---

## Backend Implementation

### 1. Convert PDF to Images (Lazy Loading - On Demand)

```python
# services/pdf_to_images.py
import fitz  # PyMuPDF
import os
from pathlib import Path

def convert_pdf_page_to_image(
    pdf_path: str,
    document_id: str,
    page_num: int,
    output_dir: str = "static/documents",
    dpi: int = 150
) -> dict:
    """
    Convert single PDF page to WebP image on demand.
    Called when user navigates to a page (lazy loading).
    Uses caching - if image exists, return cached path.
    """
    doc = fitz.open(pdf_path)

    # Create output directory
    doc_dir = Path(output_dir) / document_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Check cache first
    image_filename = f"page_{page_num}.webp"
    image_path = doc_dir / image_filename

    if image_path.exists():
        # Return cached image
        pixmap_info = fitz.Pixmap(str(image_path))
        return {
            "page": page_num,
            "url": f"/static/documents/{document_id}/{image_filename}",
            "width": pixmap_info.width,
            "height": pixmap_info.height
        }

    # Not cached - render now
    page = doc[page_num]

    # Render at specified DPI
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix)

    # Save as WebP (good quality, small size)
    pixmap.save(str(image_path))

    page_info = {
        "page": page_num,
        "url": f"/static/documents/{document_id}/{image_filename}",
        "width": pixmap.width,
        "height": pixmap.height
    }

    doc.close()
    return page_info
```

### 2. API Endpoints

```python
# routes/document_routes.py
from flask import Blueprint, jsonify, request

document_bp = Blueprint('documents', __name__)

@document_bp.route('/api/documents/<document_id>/pages/<int:page_num>', methods=['GET'])
def get_page_info(document_id: str, page_num: int):
    """Get page image URL and all chunks (with bbox) for this page"""

    # Get page image info
    page_info = get_document_page(document_id, page_num)

    # Get all chunks on this page (for click detection)
    chunks = get_chunks_by_page(document_id, page_num)

    return jsonify({
        "page": page_num,
        "image_url": page_info["image_url"],
        "width": page_info["width"],
        "height": page_info["height"],
        "regions": [
            {
                "id": chunk["id"],
                "type": chunk["type"],
                "content": chunk["content"],
                "section": chunk.get("section", ""),
                "bbox": {
                    "left": chunk["bbox_left"],
                    "top": chunk["bbox_top"],
                    "right": chunk["bbox_right"],
                    "bottom": chunk["bbox_bottom"]
                }
            }
            for chunk in chunks
        ]
    })


@document_bp.route('/api/documents/<document_id>/chat', methods=['POST'])
def chat_with_document(document_id: str):
    """Handle chat - returns answer with references"""

    data = request.json
    question = data.get('question')
    chat_id = data.get('chat_id')

    # Your existing RAG + Claude flow
    chunks = hybrid_search(question, document_id, intent="QA")

    # Build context and get answer
    context = build_context(chat_id)
    rag_context = "\n".join([f"[Page {c['page']}]: {c['content']}" for c in chunks])

    answer = call_claude(context, rag_context, question)

    # Build references from chunks
    references = [
        {
            "id": f"ref_{i}",
            "page": chunk["page"],
            "section": chunk.get("section", ""),
            "text_snippet": chunk["content"][:100] + "...",
            "bbox": {
                "left": chunk["bbox_left"],
                "top": chunk["bbox_top"],
                "right": chunk["bbox_right"],
                "bottom": chunk["bbox_bottom"]
            }
        }
        for i, chunk in enumerate(chunks[:5])
    ]

    return jsonify({
        "answer": answer,
        "references": references
    })
```

### 3. Get Chunks by Page (for click detection)

```python
# services/chunk_service.py

def get_chunks_by_page(document_id: str, page_num: int) -> list[dict]:
    """
    Get all chunks on a specific page.
    Used for detecting which chunk user clicked.
    """

    # Elasticsearch query
    query = {
        "bool": {
            "must": [
                {"term": {"document_id": document_id}},
                {"term": {"page": page_num}}
            ]
        }
    }

    results = es.search(
        index="document_chunks",
        body={"query": query, "size": 100}
    )

    return [hit["_source"] for hit in results["hits"]["hits"]]
```

---

## Frontend Implementation

### 1. Main App Layout

```tsx
// App.tsx
import { useState, useEffect } from 'react';
import { DocumentViewer } from './components/DocumentViewer';
import { ChatPanel } from './components/ChatPanel';
import { TextDisplay } from './components/TextDisplay';

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Region {
  id: string;
  type: string;
  content: string;
  section: string;
  bbox: BoundingBox;
}

interface Reference {
  id: string;
  page: number;
  section: string;
  text_snippet: string;
  bbox: BoundingBox;
}

export function App() {
  const [documentId] = useState('doc_abc123');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  // Page data
  const [imageUrl, setImageUrl] = useState('');
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 });
  const [regions, setRegions] = useState<Region[]>([]);

  // Highlight state
  const [activeHighlight, setActiveHighlight] = useState<BoundingBox | null>(null);

  // Selected text (from clicking PDF)
  const [selectedRegion, setSelectedRegion] = useState<Region | null>(null);

  // Load page data when page changes
  useEffect(() => {
    loadPageData(documentId, currentPage);
  }, [documentId, currentPage]);

  async function loadPageData(docId: string, page: number) {
    const response = await fetch(`/api/documents/${docId}/pages/${page}`);
    const data = await response.json();

    setImageUrl(data.image_url);
    setImageSize({ width: data.width, height: data.height });
    setRegions(data.regions);
  }

  // FLOW A: User clicks on PDF → Show text
  function handleRegionClick(region: Region) {
    setSelectedRegion(region);
    setActiveHighlight(region.bbox);
  }

  // FLOW B: User clicks reference → Highlight PDF
  function handleReferenceClick(page: number, bbox: BoundingBox) {
    setCurrentPage(page);
    setActiveHighlight(bbox);

    // Clear highlight after 5 seconds
    setTimeout(() => setActiveHighlight(null), 5000);
  }

  return (
    <div className="app-container">

      {/* LEFT: PDF Viewer */}
      <div className="pdf-panel">
        <DocumentViewer
          imageUrl={imageUrl}
          imageWidth={imageSize.width}
          imageHeight={imageSize.height}
          regions={regions}
          highlight={activeHighlight}
          onRegionClick={handleRegionClick}
        />

        {/* Page Navigation */}
        <div className="page-nav">
          <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))}>
            ◀ Prev
          </button>
          <span>Page {currentPage} of {totalPages}</span>
          <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}>
            Next ▶
          </button>
        </div>
      </div>

      {/* RIGHT: Chat + Text Display */}
      <div className="right-panel">

        {/* Chat Section */}
        <ChatPanel
          documentId={documentId}
          onReferenceClick={handleReferenceClick}
        />

        {/* Selected Text Display */}
        {selectedRegion && (
          <TextDisplay region={selectedRegion} />
        )}

      </div>
    </div>
  );
}
```

### 2. Document Viewer (PDF as Image + Canvas)

```tsx
// components/DocumentViewer.tsx
import { useState, useRef, useEffect } from 'react';
import { Stage, Layer, Image as KonvaImage, Rect } from 'react-konva';
import useImage from 'use-image';

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Region {
  id: string;
  type: string;
  content: string;
  bbox: BoundingBox;
}

interface Props {
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  regions: Region[];
  highlight: BoundingBox | null;
  onRegionClick: (region: Region) => void;
}

export function DocumentViewer({
  imageUrl,
  imageWidth,
  imageHeight,
  regions,
  highlight,
  onRegionClick
}: Props) {
  const [image] = useImage(imageUrl);
  const [scale, setScale] = useState(1);
  const [hoveredRegion, setHoveredRegion] = useState<Region | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Calculate scale to fit container
  useEffect(() => {
    if (containerRef.current && imageWidth > 0) {
      const containerWidth = containerRef.current.offsetWidth - 40;
      const newScale = Math.min(containerWidth / imageWidth, 1);
      setScale(newScale);
    }
  }, [imageWidth]);

  // Find region at click point
  function findRegionAtPoint(normalizedX: number, normalizedY: number): Region | null {
    for (const region of regions) {
      const { left, top, right, bottom } = region.bbox;
      if (normalizedX >= left && normalizedX <= right &&
          normalizedY >= top && normalizedY <= bottom) {
        return region;
      }
    }
    return null;
  }

  // Handle click on canvas
  function handleClick(e: any) {
    const stage = e.target.getStage();
    const pos = stage.getPointerPosition();

    // Convert to normalized coordinates
    const normalizedX = pos.x / (imageWidth * scale);
    const normalizedY = pos.y / (imageHeight * scale);

    const region = findRegionAtPoint(normalizedX, normalizedY);
    if (region) {
      onRegionClick(region);
    }
  }

  // Handle hover
  function handleMouseMove(e: any) {
    const stage = e.target.getStage();
    const pos = stage.getPointerPosition();

    const normalizedX = pos.x / (imageWidth * scale);
    const normalizedY = pos.y / (imageHeight * scale);

    const region = findRegionAtPoint(normalizedX, normalizedY);
    setHoveredRegion(region);

    // Change cursor
    stage.container().style.cursor = region ? 'pointer' : 'default';
  }

  // Convert bbox to pixel rect
  function bboxToRect(bbox: BoundingBox) {
    return {
      x: bbox.left * imageWidth * scale,
      y: bbox.top * imageHeight * scale,
      width: (bbox.right - bbox.left) * imageWidth * scale,
      height: (bbox.bottom - bbox.top) * imageHeight * scale,
    };
  }

  const displayWidth = imageWidth * scale;
  const displayHeight = imageHeight * scale;

  return (
    <div ref={containerRef} className="document-viewer">
      <Stage
        width={displayWidth}
        height={displayHeight}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
      >
        <Layer>
          {/* Page Image */}
          <KonvaImage
            image={image}
            width={displayWidth}
            height={displayHeight}
          />

          {/* Hover Highlight (blue, light) */}
          {hoveredRegion && !highlight && (
            <Rect
              {...bboxToRect(hoveredRegion.bbox)}
              fill="rgba(33, 150, 243, 0.15)"
              stroke="#2196F3"
              strokeWidth={1}
            />
          )}

          {/* Active Highlight (yellow, prominent) */}
          {highlight && (
            <Rect
              {...bboxToRect(highlight)}
              fill="rgba(255, 235, 59, 0.35)"
              stroke="#FFC107"
              strokeWidth={2}
              cornerRadius={4}
            />
          )}
        </Layer>
      </Stage>
    </div>
  );
}
```

### 3. Chat Panel with References

```tsx
// components/ChatPanel.tsx
import { useState } from 'react';
import { References } from './References';

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Reference {
  id: string;
  page: number;
  section: string;
  text_snippet: string;
  bbox: BoundingBox;
}

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  references?: Reference[];
}

interface Props {
  documentId: string;
  onReferenceClick: (page: number, bbox: BoundingBox) => void;
}

export function ChatPanel({ documentId, onReferenceClick }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSend() {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: input
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`/api/documents/${documentId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: input })
      });

      const data = await response.json();

      const assistantMessage: Message = {
        id: `msg_${Date.now()}`,
        role: 'assistant',
        content: data.answer,
        references: data.references
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="chat-panel">
      <div className="messages">
        {messages.map(msg => (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="message-content">{msg.content}</div>

            {msg.references && msg.references.length > 0 && (
              <References
                references={msg.references}
                onReferenceClick={onReferenceClick}
              />
            )}
          </div>
        ))}

        {isLoading && <div className="loading">Thinking...</div>}
      </div>

      <div className="input-area">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyPress={e => e.key === 'Enter' && handleSend()}
          placeholder="Ask about this document..."
        />
        <button onClick={handleSend} disabled={isLoading}>
          Send
        </button>
      </div>
    </div>
  );
}
```

### 4. References Component

```tsx
// components/References.tsx
interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Reference {
  id: string;
  page: number;
  section: string;
  text_snippet: string;
  bbox: BoundingBox;
}

interface Props {
  references: Reference[];
  onReferenceClick: (page: number, bbox: BoundingBox) => void;
}

export function References({ references, onReferenceClick }: Props) {
  return (
    <div className="references">
      <div className="references-header">📍 Sources:</div>
      <div className="references-list">
        {references.map(ref => (
          <button
            key={ref.id}
            className="reference-item"
            onClick={() => onReferenceClick(ref.page, ref.bbox)}
          >
            <span className="ref-page">Page {ref.page}</span>
            {ref.section && <span className="ref-section">{ref.section}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
```

### 5. Text Display Component

```tsx
// components/TextDisplay.tsx
import ReactMarkdown from 'react-markdown';

interface Region {
  id: string;
  type: string;
  content: string;
  section: string;
}

interface Props {
  region: Region;
}

export function TextDisplay({ region }: Props) {
  return (
    <div className="text-display">
      <div className="text-header">
        <span className="text-type">{region.type}</span>
        {region.section && <span className="text-section">{region.section}</span>}
      </div>
      <div className="text-content">
        <ReactMarkdown>{region.content}</ReactMarkdown>
      </div>
    </div>
  );
}
```

### 6. CSS Styles

```css
/* styles.css */

.app-container {
  display: flex;
  height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* Left Panel - PDF Viewer */
.pdf-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f0f0f0;
  border-right: 1px solid #ddd;
}

.document-viewer {
  flex: 1;
  overflow: auto;
  padding: 20px;
  display: flex;
  justify-content: center;
}

.page-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 12px;
  background: white;
  border-top: 1px solid #ddd;
}

.page-nav button {
  padding: 8px 16px;
  border: 1px solid #ddd;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

.page-nav button:hover {
  background: #f5f5f5;
}

/* Right Panel - Chat + Text */
.right-panel {
  width: 450px;
  display: flex;
  flex-direction: column;
  background: white;
}

/* Chat Panel */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid #ddd;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
}

.message.user {
  background: #e3f2fd;
  margin-left: 20%;
}

.message.assistant {
  background: #f5f5f5;
}

.input-area {
  display: flex;
  padding: 12px;
  border-top: 1px solid #eee;
}

.input-area input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  margin-right: 8px;
}

.input-area button {
  padding: 10px 20px;
  background: #1976d2;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

/* References */
.references {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #e0e0e0;
}

.references-header {
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
}

.references-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.reference-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}

.reference-item:hover {
  background: #fff8e1;
  border-color: #ffc107;
}

.ref-page {
  font-weight: 500;
  color: #1976d2;
}

.ref-section {
  color: #666;
  font-size: 11px;
}

/* Text Display */
.text-display {
  padding: 16px;
  border-top: 1px solid #ddd;
  max-height: 300px;
  overflow-y: auto;
}

.text-header {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eee;
}

.text-type {
  background: #e3f2fd;
  color: #1976d2;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  text-transform: uppercase;
}

.text-section {
  color: #666;
  font-size: 13px;
}

.text-content {
  font-size: 14px;
  line-height: 1.6;
}

/* Loading */
.loading {
  text-align: center;
  color: #666;
  padding: 20px;
}
```

---

## Coordinate Conversion

### Quick Reference

```
TEXTRACT BBOX (What you have):
─────────────────────────────────────────────────────────────
bbox = { left: 0.08, top: 0.18, right: 0.45, bottom: 0.25 }

Values are normalized 0-1:
• 0.08 = 8% from left edge
• 0.18 = 18% from top edge

TO CONVERT TO PIXELS:
─────────────────────────────────────────────────────────────
Given: image displayed at 1200 × 1600 pixels

pixelX      = 0.08 × 1200 = 96px
pixelY      = 0.18 × 1600 = 288px
pixelWidth  = (0.45 - 0.08) × 1200 = 444px
pixelHeight = (0.25 - 0.18) × 1600 = 112px

Highlight rectangle: x=96, y=288, width=444, height=112
```

### Conversion Function

```typescript
function bboxToPixels(
  bbox: BoundingBox,
  imageWidth: number,
  imageHeight: number,
  scale: number = 1
) {
  return {
    x: bbox.left * imageWidth * scale,
    y: bbox.top * imageHeight * scale,
    width: (bbox.right - bbox.left) * imageWidth * scale,
    height: (bbox.bottom - bbox.top) * imageHeight * scale,
  };
}
```

---

## Summary

### What Works With Your Existing Setup

```
YOUR EXISTING:                      WHAT WE ADD:
─────────────────────────────────   ─────────────────────────────────
✓ Textract extracts bbox            • Convert PDF to images
✓ Chunks stored with bbox           • Canvas-based viewer
✓ RAG returns chunks with bbox      • Click detection on regions
✓ Elasticsearch has all data        • Bidirectional highlighting
```

### Implementation Checklist

```
BACKEND:
[ ] Add PyMuPDF for PDF → Image conversion
[ ] Create /api/documents/{id}/pages/{num} endpoint
[ ] Return regions (chunks) with bbox for each page

FRONTEND:
[ ] Install react-konva, use-image, react-markdown
[ ] Create DocumentViewer component
[ ] Create ChatPanel component
[ ] Create References component
[ ] Create TextDisplay component
[ ] Wire up bidirectional click handling

FLOW A (Click PDF → Show Text):
[ ] Load all regions for current page
[ ] Detect click position
[ ] Find region containing click
[ ] Display content in TextDisplay

FLOW B (Click Reference → Highlight):
[ ] Chat returns references with bbox
[ ] Reference button click
[ ] Navigate to page
[ ] Draw highlight at bbox
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Compatible with: Your existing Textract + Elasticsearch + RAG setup*
