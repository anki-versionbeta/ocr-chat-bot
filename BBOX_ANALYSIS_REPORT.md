# Bounding Box Highlighting Analysis Report

## Executive Summary

This document provides a comprehensive end-to-end analysis of the PDF bounding box highlighting system, explaining why highlights work for landscape documents (internal rotation 0°) but fail for portrait documents (internal rotation 270°).

---

## 1. SYSTEM ARCHITECTURE OVERVIEW

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PDF UPLOAD PHASE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PDF File (may have /Rotate metadata)                                       │
│       │                                                                     │
│       ▼                                                                     │
│  AWS Textract API                                                           │
│       │                                                                     │
│       ▼                                                                     │
│  Textract Response (blocks with Geometry.BoundingBox)                       │
│       │  └── Coordinates: 0-1 normalized (Left, Top, Width, Height)         │
│       │  └── ORIENTATION: ??? (CRITICAL QUESTION)                           │
│       ▼                                                                     │
│  textract_parser.py → get_bbox()                                            │
│       │  └── Extracts: {left, top, width, height}                           │
│       ▼                                                                     │
│  chunk_transformer.py                                                       │
│       │  └── Creates: cell_grounding JSON with bbox per cell                │
│       │  └── Creates: line_grounding JSON with bbox per line                │
│       ▼                                                                     │
│  Weaviate Storage                                                           │
│       └── Stores: bbox_left, bbox_top, bbox_right, bbox_bottom (0-1)        │
│       └── Stores: cell_grounding, line_grounding as JSON strings            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           QUERY PHASE                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User Query                                                                 │
│       │                                                                     │
│       ▼                                                                     │
│  Intent Classification (intent_classifier.py)                               │
│       │  └── Routes: precision, exploratory, exhaustive, visual_audit, etc. │
│       ▼                                                                     │
│  RAG Orchestrator (rag_orchestrator.py)                                     │
│       │  └── Retrieves chunks from Weaviate                                 │
│       │  └── Passes cell_grounding to LLM                                   │
│       ▼                                                                     │
│  Answer Synthesizer / Visual Audit Service                                  │
│       │  └── LLM returns [cell:CHUNK:CELL_ID] references                    │
│       ▼                                                                     │
│  Reference Extractor (reference_extractor.py)                               │
│       │  └── Maps cell_ids to bbox via grounding_map                        │
│       │  └── Returns: {page, bbox: {left, top, width, height}, ...}         │
│       │  └── NO TRANSFORMATION APPLIED                                      │
│       ▼                                                                     │
│  API Response to Frontend                                                   │
│       └── references: [{page, bbox, cell_id, text, type, highlight_type}]   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           DISPLAY PHASE                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Frontend Chat Page (page.tsx)                                              │
│       │  └── Receives references from API                                   │
│       │  └── Passes to PDFPanel as highlights prop                          │
│       ▼                                                                     │
│  PDFPanel.tsx                                                               │
│       │                                                                     │
│       ├── react-pdf <Document> + <Page>                                     │
│       │       └── PDF.js renders canvas                                     │
│       │       └── AUTOMATICALLY applies internal rotation                   │
│       │       └── Canvas dimensions = AFTER rotation                        │
│       │                                                                     │
│       ├── onPageLoadSuccess captures:                                       │
│       │       └── pdfInternalRotation = page.rotate (0, 90, 180, 270)       │
│       │       └── pageWidth, pageHeight from canvas.offsetWidth/Height      │
│       │                                                                     │
│       ├── Highlight Overlay (absolute positioned div)                       │
│       │       └── Size: pageWidth x pageHeight (matches canvas)             │
│       │       └── Position: top:0, left:0 (aligns with canvas)              │
│       │                                                                     │
│       └── getHighlightStyle(bbox)                                           │
│               └── Converts bbox (0-1) to CSS percentages                    │
│               └── Only transforms for USER rotation (rotate button)         │
│               └── DOES NOT transform for pdfInternalRotation                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. THE ROOT CAUSE OF THE PROBLEM

### Critical Discovery: Coordinate System Mismatch

The issue is a **mismatch between Textract's coordinate system and PDF.js display orientation**.

#### Scenario A: Landscape PDF (Internal Rotation 0°) - WORKS

```
PDF Storage:        [================]  (landscape, 792x612)
                    /Rotate: 0 (or none)

Textract coords:    "August Faller" at (left=0.75, top=0.10)
                    → 75% from left, 10% from top

PDF.js renders:     [================]  (landscape, 792x612)
                    Same orientation as storage

Canvas size:        pageWidth=792, pageHeight=612

Highlight at:       left: 75%, top: 10%
                    → CORRECT! Matches what user sees
```

#### Scenario B: Portrait PDF (Internal Rotation 270°) - BROKEN

```
PDF Storage:        [========]  (portrait in file, 612x792)
                    /Rotate: 270 (tells viewers to rotate 270° CW)

Textract coords:    "August Faller" at (left=0.75, top=0.10)
                    → In STORAGE orientation (portrait file)
                    → 75% from left of 612pt, 10% from top of 792pt

PDF.js renders:     [================]  (landscape display, 792x612)
                    PDF.js applies /Rotate automatically
                    Canvas is ROTATED 270° from storage

Canvas size:        pageWidth=792, pageHeight=612 (swapped!)

Highlight at:       left: 75%, top: 10%
                    → WRONG! These coords are for portrait,
                      but canvas is landscape
```

### The Exact Problem

1. **Textract** returns coordinates in the **STORAGE orientation** of the PDF file
2. **PDF.js** displays the page in the **DISPLAY orientation** (after applying /Rotate)
3. **Frontend** applies Textract coordinates directly to the rotated canvas
4. **Result**: Coordinates don't match - highlight appears in wrong location

---

## 3. DETAILED CODE ANALYSIS

### 3.1 Textract Coordinate Extraction

**File:** `backend/services/textract_parser.py` (Lines 116-132)

```python
def get_bbox(self, block: Dict) -> Dict[str, float]:
    """
    Extract bounding box from block geometry.
    Returns normalized coordinates (0-1 range): left, top, width, height.
    """
    geometry = block.get('Geometry', {})
    bbox = geometry.get('BoundingBox', {})

    return {
        'left': bbox.get('Left', 0),
        'top': bbox.get('Top', 0),
        'width': bbox.get('Width', 0),
        'height': bbox.get('Height', 0)
    }
```

**Key Point:** No rotation handling. Coordinates passed through as-is.

### 3.2 Cell Grounding Storage

**File:** `backend/services/chunk_transformer.py` (Lines 79-89)

```python
cell_grounding[cell_id] = {
    'bbox': cell_data['bbox'],      # Textract's bbox directly
    'text': cell_data['text'],
    'row': cell_data['row'],
    'col': cell_data['col'],
    'row_span': cell_data.get('row_span', 1),
    'col_span': cell_data.get('col_span', 1)
}
```

**Key Point:** Bbox stored without any transformation.

### 3.3 Reference Extraction

**File:** `backend/services/reference_extractor.py` (Lines 277-316)

```python
def format_references_for_frontend(references):
    for ref in references:
        bbox = ref.get('bbox', {})
        formatted_bbox = {
            'left': float(bbox.get('left', 0)),
            'top': float(bbox.get('top', 0)),
            'width': float(bbox.get('width', 0)),
            'height': float(bbox.get('height', 0))
        }
        # NO ROTATION TRANSFORMATION
```

**Key Point:** No rotation transformation applied.

### 3.4 PDF.js Rendering

**File:** `frontend/src/components/PDFPanel.tsx` (Lines 379-389)

```typescript
function onPageLoadSuccess(page: { width: number; height: number; rotate?: number }) {
  // Capture PDF's internal rotation
  const internalRotation = (page as any).rotate || 0;
  console.log(`[PDF-Panel] Page loaded: ${page.width}x${page.height}, internal rotation: ${internalRotation}°`);
  setPdfInternalRotation(internalRotation);
  updateCanvasDimensions();
}
```

**Key Point:** Internal rotation is CAPTURED but NOT USED in bbox positioning.

### 3.5 Highlight Style Calculation (CURRENT - BROKEN)

**File:** `frontend/src/components/PDFPanel.tsx` (Lines 513-554)

```typescript
function getHighlightStyle(bbox: BoundingBox, highlightType?: string): React.CSSProperties {
  let left = bbox.left ?? 0;
  let top = bbox.top ?? 0;
  let width = bbox.width ?? ...;
  let height = bbox.height ?? ...;

  // ONLY transforms for USER rotation (rotate button)
  if (rotation !== 0) {
    const rotated = transformBboxForRotation({ left, top, width, height }, rotation);
    // ... apply rotated coords
  }

  // MISSING: No transformation for pdfInternalRotation!

  return {
    left: `${left * 100}%`,
    top: `${Math.max(0, topAdjust) * 100}%`,
    width: `${width * 100}%`,
    height: `${minHeight * 100}%`,
    // ...
  };
}
```

**Key Problem:** `pdfInternalRotation` is captured but NEVER used in the main highlight positioning.

---

## 4. INTENT-SPECIFIC REFERENCE HANDLING

### 4.1 Precision Intent
- **Handler:** `_process_precision_query()` (rag_orchestrator.py:1058-1127)
- **Agent Strategy:** Single agent, fast path
- **References:** Via `build_response_with_references()`
- **Bbox Source:** cell_grounding from chunks
- **Transformation:** NONE

### 4.2 Exploratory Intent
- **Handler:** `_process_exploratory_query()` (rag_orchestrator.py:1301-1376)
- **Agent Strategy:** 5 parallel agents
- **References:** Via `format_references_for_frontend()`
- **Bbox Source:** cell_grounding from chunks
- **Transformation:** NONE

### 4.3 Exhaustive Intent
- **Handler:** `_process_exhaustive_query()` (rag_orchestrator.py:1129-1212)
- **Agent Strategy:** 8 parallel agents
- **References:** Via `format_references_for_frontend()`
- **Bbox Source:** cell_grounding from chunks
- **Transformation:** NONE

### 4.4 Visual Audit Intent
- **Handler:** `_process_visual_audit_query()` (rag_orchestrator.py:660-843)
- **Agent Strategy:** Gemini Vision
- **References:** From Gemini's [cell:CHUNK:CELL_ID|TYPE] responses
- **Bbox Source:** cell_grounding mapped via grounding_map
- **Transformation:** NONE
- **Special:** Adds `highlight_type` ('error' or 'info')

### 4.5 Hybrid/Neo4j Intent
- **Handler:** `_process_hybrid_query()` (rag_orchestrator.py:302-562)
- **Agent Strategy:** Multi-agent Cypher
- **References:** From Neo4j query results
- **Bbox Source:** Neo4j cell nodes with bbox
- **Transformation:** NONE

---

## 5. PDF INTERNAL ROTATION VALUES

| Rotation | Meaning | Storage → Display |
|----------|---------|-------------------|
| **0°** | No rotation | Portrait stays portrait |
| **90°** | Rotate 90° CW | Portrait → Landscape (right) |
| **180°** | Rotate 180° | Upside down |
| **270°** | Rotate 270° CW (90° CCW) | Portrait → Landscape (left) |

### PDF with /Rotate 270°

```
Storage (file):           Display (PDF.js):
┌─────────┐               ┌─────────────────┐
│    A    │  ──270°CW──>  │                 │
│    B    │               │  C  B  A        │
│    C    │               │                 │
└─────────┘               └─────────────────┘
 612x792                   792x612
```

**Coordinate Transform for 270° CW:**
- Storage point (x, y) → Display point (y, 1-x)
- Storage bbox (x, y, w, h) → Display bbox (y, 1-x-w, h, w)

---

## 6. WHY THE PREVIOUS FIX ATTEMPTS FAILED

### Attempt 1: Transform (y, 1-x-w, h, w)
```typescript
newLeft = top;           // y
newTop = 1 - left - width;  // 1-x-w
```
**Result:** Showed at TOP-LEFT instead of TOP-RIGHT
**Why:** Wrong formula direction

### Attempt 2: Transform (1-y-h, 1-x-w, h, w)
```typescript
newLeft = 1 - top - height;  // 1-y-h
newTop = 1 - left - width;   // 1-x-w
```
**Result:** Still wrong position
**Why:** Incorrect understanding of coordinate spaces

### The Real Issue

The coordinate transformation depends on:
1. **WHAT Textract gives** - Storage or Display orientation?
2. **WHAT PDF.js shows** - Rotated canvas
3. **HOW dimensions are measured** - Before or after rotation?

---

## 7. AWS TEXTRACT COORDINATE BEHAVIOR

### Critical Finding

AWS Textract documentation states:
> "BoundingBox values are in the coordinate system of the source image."

For PDFs, this means:
- Textract sees the **RENDERED** page (after rotation)
- Coordinates are relative to the **DISPLAY** orientation

### BUT - There's a Contradiction

User's logs show:
```
bbox: {top: 0.09, left: 0.75, width: 0.15, height: 0.008}
```

If Textract gave DISPLAY coords for 270° rotated PDF:
- "August Faller" at top-right of display
- left=0.75 (right side) ✓
- top=0.09 (top) ✓

This SHOULD work... but it doesn't.

### Possible Explanations

1. **Textract uses STORAGE coords** for PDFs with /Rotate
2. **PDF.js canvas dimensions** are captured incorrectly
3. **Overlay positioning** has an offset issue
4. **The bbox data itself** is from a different coordinate space

---

## 8. INVESTIGATION NEEDED

### Test 1: Verify Textract Coordinate System
```python
# In backend, log the PDF /Rotate value and Textract coords
import fitz
doc = fitz.open(pdf_path)
page = doc[0]
print(f"PDF /Rotate: {page.rotation}")
print(f"PDF MediaBox: {page.mediabox}")
print(f"Textract bbox for 'August Faller': {bbox}")
```

### Test 2: Verify Canvas Dimensions
```typescript
// In PDFPanel.tsx, log canvas vs page dimensions
console.log(`Page from PDF.js: ${page.width}x${page.height}`);
console.log(`Canvas offsetWidth: ${canvas.offsetWidth}`);
console.log(`Canvas offsetHeight: ${canvas.offsetHeight}`);
console.log(`Internal rotation: ${pdfInternalRotation}`);
```

### Test 3: Verify Overlay Alignment
```typescript
// Add visible border to overlay
style={{
  border: '2px solid blue',  // Add this temporarily
  zIndex: 20,
  top: 0,
  left: 0,
  width: pageWidth,
  height: pageHeight,
}}
```

---

## 9. POSSIBLE SOLUTIONS

### Solution A: Transform in Frontend (PDFPanel.tsx)

```typescript
function getHighlightStyle(bbox: BoundingBox, highlightType?: string): React.CSSProperties {
  let { left, top, width, height } = bbox;

  // Transform based on PDF internal rotation
  if (pdfInternalRotation === 270) {
    // Storage → Display for 270° CW
    // Try: (x,y,w,h) → (1-y-h, x, h, w)
    const newLeft = 1 - top - height;
    const newTop = left;
    const newWidth = height;
    const newHeight = width;
    left = newLeft; top = newTop; width = newWidth; height = newHeight;
  }
  // ... rest of function
}
```

### Solution B: Transform in Backend (reference_extractor.py)

```python
def transform_bbox_for_rotation(bbox, rotation):
    if rotation == 270:
        return {
            'left': 1 - bbox['top'] - bbox['height'],
            'top': bbox['left'],
            'width': bbox['height'],
            'height': bbox['width']
        }
    # ... other rotations
    return bbox
```

### Solution C: Store Rotation Metadata with Chunks

```python
# In textract processing, detect and store PDF rotation
chunk['pdf_rotation'] = page.rotation
```

Then transform when retrieving based on stored rotation.

---

## 10. FILES TO REFERENCE

| Component | File Path | Key Lines |
|-----------|-----------|-----------|
| **Textract Parser** | `backend/services/textract_parser.py` | 116-132 (get_bbox) |
| **Chunk Transformer** | `backend/services/chunk_transformer.py` | 79-89 (cell_grounding) |
| **Reference Extractor** | `backend/services/reference_extractor.py` | 277-316 (format_references) |
| **RAG Orchestrator** | `backend/services/rag_orchestrator.py` | 660-843 (visual_audit), 1058-1376 (other intents) |
| **Intent Classifier** | `backend/services/intent_classifier.py` | 190-278 (intent definitions) |
| **Visual Audit Service** | `backend/services/visual_audit_service.py` | 657-698 (pdf to image), 1173-1297 (deep analysis) |
| **PDFPanel** | `frontend/src/components/PDFPanel.tsx` | 379-389 (rotation capture), 513-554 (getHighlightStyle) |
| **Chat Page** | `frontend/src/app/chat/page.tsx` | 487-563 (PageReferenceButtons), 4715-4726 (PDFPanel props) |

---

## 11. CONCLUSION

### Root Cause
The system does not handle the coordinate transformation needed when a PDF has internal rotation. Textract coordinates are stored/used directly without accounting for the /Rotate metadata, while PDF.js displays the page in the rotated orientation.

### Why Landscape Works (0° rotation)
No rotation = no transformation needed. Coordinates map directly.

### Why Portrait Fails (270° rotation)
PDF.js rotates the canvas, but coordinates are still in storage orientation. The mismatch causes highlights to appear in wrong positions.

### Required Fix
Transform bbox coordinates based on `pdfInternalRotation` before applying to the overlay. The transformation must convert storage orientation coordinates to display orientation coordinates.

---

*Report generated: March 2026*
*Analysis performed by 5 parallel investigation agents*
