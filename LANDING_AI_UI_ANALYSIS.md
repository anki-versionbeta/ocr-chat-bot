# Landing AI UI Analysis & OCR Chatbot Enhancement Plan

> **Document Purpose:** Analysis of Landing AI's Agentic Document Extraction UI to inform improvements for the AbbVie OCR Chatbot
> **Created:** January 2026
> **Status:** Initial Analysis

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Landing AI UI Analysis](#landing-ai-ui-analysis)
   - [Chat Feature](#1-chat-feature)
   - [Extract Feature](#2-extract-feature)
   - [Parse Feature - Markdown View](#3-parse-feature---markdown-view)
   - [Parse Feature - JSON View](#4-parse-feature---json-view)
3. [Key Data Structure Insight](#key-data-structure-insight)
4. [Comparison: Current OCR Chatbot vs Landing AI](#comparison-current-ocr-chatbot-vs-landing-ai)
5. [Implementation Plan](#implementation-plan)
   - [Backend Transformation](#step-1-backend-transformation)
   - [Frontend UI Components](#step-2-frontend-ui-components)
6. [Feasibility Assessment](#feasibility-assessment)
7. [Beyond Landing AI - Proposed Enhancements](#beyond-landing-ai---proposed-enhancements)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Next Steps](#next-steps)

---

## Executive Summary

This document analyzes Landing AI's Agentic Document Extraction interface to identify best practices and UI patterns that can be applied to improve the AbbVie OCR Chatbot. The analysis reveals that Landing AI's success comes from a well-structured JSON format that includes:

- **Bounding box coordinates** for visual grounding
- **Type classification** (table vs text)
- **Markdown rendering** for clean display
- **Unique identifiers** for linking UI elements to PDF locations

**Key Finding:** AWS Textract already provides all the raw data needed (bounding boxes, table structure, text content). The improvement requires transforming this data into a Landing AI-style format and building corresponding frontend components.

---

## Landing AI UI Analysis

### 1. Chat Feature

**Screenshot Reference:** `chat feature - landing ai.png`

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────────────┐
│  SAF_HL4689_to.pdf  [↓]     < 1 / 1 >    Parse Split Extract Chat│
├─────────────────────────────┬───────────────────────────────────┤
│                             │                                   │
│     PDF DOCUMENT VIEWER     │         CHAT PANEL                │
│         (~55% width)        │         (~45% width)              │
│                             │                                   │
│  ┌───────────────────────┐  │  User: What is the product name...│
│  │                       │  │                                   │
│  │  Product Shipment     │  │  AI: The product name is          │
│  │  Authorization Form   │  │      Deoxycholic Acid Injection...│
│  │                       │  │                                   │
│  │  [Tables & Content]   │  │  Visual reference for the answer: │
│  │                       │  │                                   │
│  │                       │  │  ┌─────────────────────────────┐  │
│  │                       │  │  │ Page 1, table, cell  |  →   │  │
│  │                       │  │  │ Page 1, table, cell  |  →   │  │
│  │                       │  │  │ Page 1, table, cell  |  →   │  │
│  │                       │  │  │ 4. table  →                 │  │
│  │                       │  │  └─────────────────────────────┘  │
│  └───────────────────────┘  │                                   │
│                             │  ┌─────────────────────────────┐  │
│                             │  │ Type your question      [↑] │  │
│                             │  └─────────────────────────────┘  │
└─────────────────────────────┴───────────────────────────────────┘
```

**Key UI Components:**

| Component | Description | Purpose |
|-----------|-------------|---------|
| **Side-by-Side Layout** | PDF viewer (left) + Chat panel (right) | Allows simultaneous document viewing and interaction |
| **Visual References** | Clickable links: "Page 1, table, cell \| →" | Direct navigation to source location in PDF |
| **Clean AI Response** | Structured text answer | Easy to read extracted information |
| **Simple Input** | "Type your question" field | Intuitive user interaction |
| **Navigation Tabs** | Parse, Split, Preview, Extract, Chat | Feature switching |

**What Makes It Effective:**
- Visual references create trust (user can verify answers)
- Side-by-side eliminates context switching
- Clickable links provide instant source verification
- Clean, professional appearance

---

### 2. Extract Feature

**Screenshot Reference:** `extract feature - landing ai.png`

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│  Parse  Split  Preview  [Extract]  Chat                      </> Code  │
├─────────────────────┬─────────────────────┬─────────────────────────────┤
│                     │      SCHEMA         │    EXTRACTED RESULTS        │
│   PDF VIEWER        │                     │                             │
│                     │  facilities Object ▼│    Results are up to date   │
│  ┌───────────────┐  │                     │                             │
│  │               │  │  attachedDocuments  │    Data                     │
│  │   Document    │  │    String ▼         │    {                        │
│  │   with        │  │                     │      "facilities": {        │
│  │   highlighted │  │  contractFacility   │        "attachedDocuments": │
│  │   section     │  │    Name  String ▼   │          "CofA, CofC",      │
│  │   [9.text]    │  │                     │        "contractFacility":  │
│  │               │  │  productInfo        │          "Hospira, Inc.",   │
│  │               │  │    Object ▼         │        ...                  │
│  │               │  │                     │      },                     │
│  │               │  │  + Children         │      "productInfo": {       │
│  └───────────────┘  │                     │        "productName": "..." │
│                     │  [Run Schema]       │      }                      │
│                     │                     │    }                        │
└─────────────────────┴─────────────────────┴─────────────────────────────┘
```

**Key UI Components:**

| Component | Description | Purpose |
|-----------|-------------|---------|
| **Schema Panel** | Expandable field definitions with types | Define what to extract |
| **Field Types** | String, Object, + Children | Structured data modeling |
| **Run Schema Button** | Execute extraction | Trigger extraction based on schema |
| **Extracted Results** | JSON with syntax highlighting | View extracted data |
| **PDF Highlight** | Green label "9.text" on selected region | Visual feedback of extraction source |
| **Clear Selection** | Reset button | Remove current selection |

**What Makes It Effective:**
- Schema-driven approach (define once, extract many)
- Real-time JSON output with syntax highlighting
- Visual feedback showing exactly what was selected
- Expandable/collapsible sections for complex schemas

---

### 3. Parse Feature - Markdown View

**Screenshot Reference:** `parse feature - landing ai.png`

**Layout Structure:**
```
┌─────────────────────────────────────────────────────────────────┐
│  [Parse]  Split  Preview  Extract  Chat              </> Code   │
├─────────────────────────────┬───────────────────────────────────┤
│                             │  [Markdown]  JSON         [↓] [□] │
│     PDF VIEWER              │                                   │
│                             │  1 - Table                        │
│                             │  ┌────────────┬────────────────┐  │
│                             │  │Doc Type    │ Dept - Site    │  │
│                             │  ├────────────┼────────────────┤  │
│                             │  │Form        │ PQA - Global   │  │
│                             │  └────────────┴────────────────┘  │
│                             │                                   │
│                             │  2 - Text                         │
│                             │  "This executed Shipment Auth..." │
│                             │                                   │
│                             │  3 - Table                        │
│                             │  ┌──────────┬──────────┬───────┐  │
│                             │  │Product   │Material  │Batch  │  │
│                             │  ├──────────┼──────────┼───────┤  │
│                             │  │ATX-101   │96309DB   │HL4689 │  │
│                             │  └──────────┴──────────┴───────┘  │
│                             │                                   │
│                             │  4 - Table                        │
│                             │  5 - Table                        │
│                             │  6 - Table                        │
└─────────────────────────────┴───────────────────────────────────┘
```

**Key UI Components:**

| Component | Description | Purpose |
|-----------|-------------|---------|
| **Markdown/JSON Toggle** | Switch between views | Different output formats |
| **Numbered Blocks** | "1 - Table", "2 - Text", etc. | Clear content organization |
| **Rendered Tables** | Actual HTML tables, not plain text | Readable table structure |
| **Text Blocks** | Paragraph content | Non-tabular content |
| **Download/Copy Icons** | Export options | Data portability |

**What Makes It Effective:**
- Tables rendered as actual tables (not plain text)
- Clear numbering and type labeling
- Easy distinction between tables and text
- Toggle between human-readable and machine-readable formats

---

### 4. Parse Feature - JSON View

**Screenshot Reference:** `parse feature json content - landing ai.png`

**This is the KEY insight - the data structure that powers everything:**

```json
{
  "markdown": "<a id='b5ae6bdd-2f96-4c62-9b23-15da72b795b9'></a>\n\n<table id=\"0-1\">\n<tr><td id=\"0-2\" rowspan=\"3\">abbvie (logo)</td><td id=\"0-3\">Document Type</td>...",
  "chunks": [
    {
      "markdown": "<a id='b5ae6bdd-2f96-4c62-9b23-15da72b795b9'></a>\n\n<table id=\"0-1\"...",
      "type": "table",
      "id": "b5ae6bdd-2f96-4c62-9b23-15da72b795b9",
      "grounding": {
        "box": {
          "left": 0.0838296115398407,
          "top": 0.04175157845020294,
          "right": 0.9110537767410278,
          "bottom": 0.11955341696739197
        }
      },
      "page": 0
    },
    {
      "markdown": "<a id='ecc69ad6-26b2-4af4-86a2-1d5e23586cfd'></a>\n\nThis executed Shipment Authorization Form serves as authorization from Allergan (an AbbVie Company) to ship the material listed below.",
      "type": "text",
      "id": "ecc69ad6-26b2-4af4-86a2-1d5e23586cfd",
      "grounding": {
        "box": {
          "left": 0.08240249752998352,
          "top": 0.14016859233379364,
          "right": 0.9113848209381104,
          "bottom": 0.17690898478031158
        }
      },
      "page": 0
    },
    {
      "markdown": "<a id='b5dd280e-80e2-4dcf-a5e3-c7704671ab12'></a>\n\n<table id=\"0-f\">...",
      "type": "table",
      "id": "b5dd280e-80e2-4dcf-a5e3-c7704671ab12",
      "grounding": {
        "box": {
          "left": ...,
          "top": ...,
          "right": ...,
          "bottom": ...
        }
      },
      "page": 0
    }
  ]
}
```

**Critical Data Structure Elements:**

| Field | Type | Description |
|-------|------|-------------|
| `markdown` | string | HTML/Markdown content with embedded anchor IDs |
| `type` | string | "table" or "text" - content classification |
| `id` | string | UUID for unique identification and linking |
| `grounding.box` | object | Bounding box coordinates for PDF highlighting |
| `grounding.box.left` | float | Left edge (0-1 normalized) |
| `grounding.box.top` | float | Top edge (0-1 normalized) |
| `grounding.box.right` | float | Right edge (0-1 normalized) |
| `grounding.box.bottom` | float | Bottom edge (0-1 normalized) |
| `page` | int | Page number (0-indexed) |

**Why This Structure is Powerful:**
1. **Bounding boxes enable visual grounding** - Can highlight exact regions in PDF
2. **Type classification** - Different rendering for tables vs text
3. **Unique IDs** - Link chat references to PDF locations
4. **Markdown content** - Ready for display with proper formatting
5. **Page tracking** - Navigate to correct page

---

## Key Data Structure Insight

### The Magic Formula

Landing AI's effectiveness comes from this transformation:

```
Raw Document → Structured Chunks with Grounding → Interactive UI
```

Each chunk contains:
1. **Content** (markdown) - What to display
2. **Type** (table/text) - How to render it
3. **Location** (grounding.box) - Where it is in the document
4. **Identity** (id) - How to reference it

### Comparison with AWS Textract

**AWS Textract Output:**
```json
{
  "BlockType": "TABLE",
  "Id": "abc123",
  "Geometry": {
    "BoundingBox": {
      "Left": 0.083,
      "Top": 0.041,
      "Width": 0.828,
      "Height": 0.078
    }
  },
  "Page": 1
}
```

**Landing AI Equivalent:**
```json
{
  "type": "table",
  "id": "abc123",
  "grounding": {
    "box": {
      "left": 0.083,
      "top": 0.041,
      "right": 0.911,   // left + width
      "bottom": 0.119   // top + height
    }
  },
  "page": 0  // 0-indexed
}
```

**Key Transformation:**
- `Width` → `right` (calculated as `left + width`)
- `Height` → `bottom` (calculated as `top + height`)
- `Page` → 0-indexed instead of 1-indexed

---

## Comparison: Current OCR Chatbot vs Landing AI

| Feature | Current OCR Chatbot | Landing AI | Gap |
|---------|---------------------|------------|-----|
| **Layout** | Chat only | Side-by-side PDF + Chat | Need to add PDF viewer |
| **Bounding Boxes** | Data exists (Textract) but unused | Visual highlighting | Need to implement overlay |
| **Table Display** | Plain text | Rendered HTML tables | Need table component |
| **Visual References** | None | Clickable links to PDF | Need reference system |
| **Content Types** | All text | Classified (table/text) | Need type detection |
| **JSON Structure** | Textract raw format | Clean chunks format | Need transformation |
| **Parse View** | Not available | Markdown/JSON toggle | Need to build |
| **Extract Schema** | Not available | Schema-driven extraction | Future enhancement |

---

## Implementation Plan

### Step 1: Backend Transformation

**File:** `backend/textract_transformer.py` (new file)

**Purpose:** Transform AWS Textract JSON to Landing AI-style format

```python
import uuid
from typing import List, Dict, Any

def transform_textract_to_landing_format(blocks_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform AWS Textract blocks to Landing AI-style format with:
    - Bounding box coordinates (left, top, right, bottom)
    - Type classification (table, text)
    - Markdown content
    - Unique IDs
    - Page numbers
    """
    chunks = []
    blocks = blocks_json.get('Blocks', [])

    # Create lookup for blocks by ID
    block_lookup = {block['Id']: block for block in blocks}

    # Process TABLE blocks
    for block in blocks:
        if block['BlockType'] == 'TABLE':
            chunk = process_table_block(block, block_lookup)
            chunks.append(chunk)

    # Process LINE blocks (group into text chunks)
    text_chunks = process_line_blocks(blocks)
    chunks.extend(text_chunks)

    # Sort by page and vertical position
    chunks.sort(key=lambda x: (x['page'], x['grounding']['box']['top']))

    return {"chunks": chunks}


def process_table_block(table_block: Dict, block_lookup: Dict) -> Dict:
    """
    Process a TABLE block and its child CELL blocks
    """
    bbox = table_block['Geometry']['BoundingBox']

    # Extract table structure
    table_structure = extract_table_structure(table_block, block_lookup)

    # Build markdown representation
    markdown = build_table_markdown(table_structure, table_block['Id'])

    return {
        "markdown": markdown,
        "type": "table",
        "id": table_block['Id'],
        "grounding": {
            "box": {
                "left": bbox['Left'],
                "top": bbox['Top'],
                "right": bbox['Left'] + bbox['Width'],
                "bottom": bbox['Top'] + bbox['Height']
            }
        },
        "page": table_block.get('Page', 1) - 1,  # Convert to 0-indexed
        "table_structure": table_structure
    }


def extract_table_structure(table_block: Dict, block_lookup: Dict) -> Dict:
    """
    Extract headers and rows from TABLE block
    """
    cells = []

    # Get child cell IDs
    for relationship in table_block.get('Relationships', []):
        if relationship['Type'] == 'CHILD':
            for cell_id in relationship['Ids']:
                cell_block = block_lookup.get(cell_id)
                if cell_block and cell_block['BlockType'] == 'CELL':
                    cells.append({
                        'row': cell_block['RowIndex'],
                        'col': cell_block['ColumnIndex'],
                        'text': get_cell_text(cell_block, block_lookup),
                        'bbox': cell_block['Geometry']['BoundingBox']
                    })

    # Organize into grid
    if not cells:
        return {"headers": [], "rows": []}

    max_row = max(cell['row'] for cell in cells)
    max_col = max(cell['col'] for cell in cells)

    grid = [['' for _ in range(max_col)] for _ in range(max_row)]
    cell_bboxes = [[None for _ in range(max_col)] for _ in range(max_row)]

    for cell in cells:
        row_idx = cell['row'] - 1
        col_idx = cell['col'] - 1
        grid[row_idx][col_idx] = cell['text']
        cell_bboxes[row_idx][col_idx] = cell['bbox']

    # First row as headers
    headers = grid[0] if grid else []

    # Remaining rows as data
    rows = []
    for i in range(1, len(grid)):
        row_data = {}
        for j, header in enumerate(headers):
            row_data[header] = grid[i][j] if j < len(grid[i]) else ''
            row_data[f'{header}_bbox'] = cell_bboxes[i][j]
        rows.append(row_data)

    return {
        "headers": headers,
        "rows": rows,
        "cell_bboxes": cell_bboxes
    }


def get_cell_text(cell_block: Dict, block_lookup: Dict) -> str:
    """
    Get text content from a CELL block
    """
    text_parts = []
    for relationship in cell_block.get('Relationships', []):
        if relationship['Type'] == 'CHILD':
            for child_id in relationship['Ids']:
                child_block = block_lookup.get(child_id)
                if child_block and 'Text' in child_block:
                    text_parts.append(child_block['Text'])
    return ' '.join(text_parts)


def build_table_markdown(table_structure: Dict, table_id: str) -> str:
    """
    Build HTML table markdown with anchor ID
    """
    headers = table_structure.get('headers', [])
    rows = table_structure.get('rows', [])

    html = f"<a id='{table_id}'></a>\n\n"
    html += "<table>\n"

    # Header row
    html += "  <thead>\n    <tr>\n"
    for header in headers:
        html += f"      <th>{header}</th>\n"
    html += "    </tr>\n  </thead>\n"

    # Data rows
    html += "  <tbody>\n"
    for row in rows:
        html += "    <tr>\n"
        for header in headers:
            value = row.get(header, '')
            html += f"      <td>{value}</td>\n"
        html += "    </tr>\n"
    html += "  </tbody>\n"

    html += "</table>"

    return html


def process_line_blocks(blocks: List[Dict]) -> List[Dict]:
    """
    Group consecutive LINE blocks into text chunks
    """
    text_chunks = []
    current_chunk_lines = []
    current_bbox = None
    current_page = None

    line_blocks = [b for b in blocks if b['BlockType'] == 'LINE']
    line_blocks.sort(key=lambda x: (x.get('Page', 1), x['Geometry']['BoundingBox']['Top']))

    for block in line_blocks:
        page = block.get('Page', 1)
        bbox = block['Geometry']['BoundingBox']

        # Start new chunk if page changes or large vertical gap
        if current_page is not None and (page != current_page or
            (current_bbox and bbox['Top'] - (current_bbox['Top'] + current_bbox['Height']) > 0.05)):
            if current_chunk_lines:
                text_chunks.append(create_text_chunk(current_chunk_lines, current_bbox, current_page))
            current_chunk_lines = []
            current_bbox = None

        current_chunk_lines.append(block['Text'])
        current_page = page

        # Expand bounding box
        if current_bbox is None:
            current_bbox = bbox.copy()
        else:
            current_bbox['Top'] = min(current_bbox['Top'], bbox['Top'])
            current_bbox['Left'] = min(current_bbox['Left'], bbox['Left'])
            right = max(current_bbox['Left'] + current_bbox['Width'], bbox['Left'] + bbox['Width'])
            bottom = max(current_bbox['Top'] + current_bbox['Height'], bbox['Top'] + bbox['Height'])
            current_bbox['Width'] = right - current_bbox['Left']
            current_bbox['Height'] = bottom - current_bbox['Top']

    # Don't forget last chunk
    if current_chunk_lines:
        text_chunks.append(create_text_chunk(current_chunk_lines, current_bbox, current_page))

    return text_chunks


def create_text_chunk(lines: List[str], bbox: Dict, page: int) -> Dict:
    """
    Create a text chunk from grouped lines
    """
    chunk_id = str(uuid.uuid4())
    text = '\n'.join(lines)

    return {
        "markdown": f"<a id='{chunk_id}'></a>\n\n{text}",
        "type": "text",
        "id": chunk_id,
        "grounding": {
            "box": {
                "left": bbox['Left'],
                "top": bbox['Top'],
                "right": bbox['Left'] + bbox['Width'],
                "bottom": bbox['Top'] + bbox['Height']
            }
        },
        "page": page - 1  # Convert to 0-indexed
    }
```

---

### Step 2: Frontend UI Components

**Required Components:**

#### A. Side-by-Side Layout Container
```tsx
// components/DocumentViewer.tsx
interface DocumentViewerProps {
  pdfUrl: string;
  chunks: Chunk[];
  activeChunkId?: string;
  onChunkClick: (chunkId: string) => void;
}
```

#### B. PDF Viewer with Bounding Box Overlay
```tsx
// components/PDFViewerWithOverlay.tsx
interface PDFViewerProps {
  pdfUrl: string;
  highlights: BoundingBox[];
  currentPage: number;
  onPageChange: (page: number) => void;
}

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
  color?: string;
}
```

#### C. Table Renderer Component
```tsx
// components/TableRenderer.tsx
interface TableRendererProps {
  tableStructure: {
    headers: string[];
    rows: Record<string, string>[];
  };
  highlightCells?: string[];
  onCellClick?: (row: number, col: number) => void;
}
```

#### D. Parse Results Panel
```tsx
// components/ParseResultsPanel.tsx
interface ParseResultsPanelProps {
  chunks: Chunk[];
  viewMode: 'markdown' | 'json';
  onViewModeChange: (mode: 'markdown' | 'json') => void;
  onChunkHover: (chunkId: string) => void;
}
```

#### E. Visual Reference Links (for Chat)
```tsx
// components/VisualReference.tsx
interface VisualReferenceProps {
  references: {
    chunkId: string;
    page: number;
    type: 'table' | 'text' | 'cell';
    label: string;
  }[];
  onReferenceClick: (chunkId: string) => void;
}
```

---

## Feasibility Assessment

### What AWS Textract Already Provides

| Data Point | Available in Textract | Notes |
|------------|----------------------|-------|
| Bounding Boxes | ✅ Yes | In `Geometry.BoundingBox` |
| Table Structure | ✅ Yes | TABLE + CELL blocks with relationships |
| Text Content | ✅ Yes | LINE blocks with text |
| Page Numbers | ✅ Yes | `Page` field on blocks |
| Unique IDs | ✅ Yes | `Id` field on each block |
| Row/Column Indices | ✅ Yes | On CELL blocks |

### What Needs to Be Built

| Component | Effort | Complexity |
|-----------|--------|------------|
| Backend Transformer | 1-2 days | Medium |
| PDF Viewer Integration | 2-3 days | Medium |
| Bounding Box Overlay | 2-3 days | Medium-High |
| Table Renderer | 1-2 days | Low |
| Parse View (Markdown/JSON) | 1-2 days | Low |
| Visual References in Chat | 2-3 days | Medium |
| Side-by-Side Layout | 1 day | Low |

**Total Estimated Effort:** 10-16 days

### Verdict: **YES, This is Achievable**

All required data is available from AWS Textract. The implementation requires:
1. Data transformation (backend)
2. UI component development (frontend)
3. Integration and testing

---

## Beyond Landing AI - Proposed Enhancements

### Improvements Over Landing AI

| Landing AI Feature | Our Enhancement | Benefit |
|-------------------|-----------------|---------|
| Static bounding boxes | **Animated highlight** with pulse effect | More intuitive visual feedback |
| Single document view | **Multi-COA comparison** | Compare batches side-by-side |
| Generic tables | **COA-specific formatting** | Pass/Fail coloring, spec validation |
| Basic chat | **Domain-aware chat** | Understands pharma terminology |
| Manual schema | **Auto-detected COA schema** | Pre-built extraction for COAs |
| No validation | **Specification validation** | Highlight out-of-spec results |
| Plain JSON | **Interactive JSON tree** | Expand/collapse, search, copy |

### AbbVie-Specific Enhancements

1. **COA Template Recognition**
   - Auto-detect COA type (Product Shipment, Test Results, etc.)
   - Pre-populate extraction schema

2. **Specification Validation**
   - Compare results against specifications
   - Visual indicators (green=pass, red=fail)

3. **Batch Tracking Integration**
   - Link to internal batch systems
   - Show related documents

4. **Audit Trail**
   - Log all extractions and queries
   - Export for compliance

5. **Multi-Language Support**
   - Handle COAs from different regions

---

## Implementation Roadmap

### Phase 1: Backend Foundation (Week 1-2)
- [ ] Create `textract_transformer.py`
- [ ] Transform Textract JSON to Landing AI format
- [ ] Store transformed data alongside raw Textract
- [ ] Update API endpoints to return new format
- [ ] Unit tests for transformation

### Phase 2: Basic UI Layout (Week 2-3)
- [ ] Implement side-by-side layout component
- [ ] Integrate PDF viewer (react-pdf or pdf.js)
- [ ] Create basic table renderer component
- [ ] Add Markdown/JSON toggle view

### Phase 3: Bounding Box Integration (Week 3-4)
- [ ] Implement PDF overlay layer
- [ ] Draw bounding boxes on PDF
- [ ] Add hover/click interactions
- [ ] Sync highlighting between panels

### Phase 4: Chat Enhancement (Week 4-5)
- [ ] Add visual references to AI responses
- [ ] Implement reference click → PDF navigation
- [ ] Show source chunks in responses
- [ ] Add confidence indicators

### Phase 5: Polish & Testing (Week 5-6)
- [ ] Performance optimization
- [ ] Mobile responsiveness
- [ ] Accessibility compliance
- [ ] User testing with AbbVie employees
- [ ] Bug fixes and refinements

---

## Next Steps

### Immediate Actions

1. **Review this analysis** with stakeholders
2. **Decide on implementation phases** - which features first?
3. **Set up development environment** for frontend changes
4. **Create backend branch** for transformer implementation

### Questions to Resolve

1. Should we implement Parse/Extract features like Landing AI, or focus only on Chat?
2. What PDF viewer library to use? (react-pdf, pdf.js, or commercial)
3. Do we need the schema-based extraction (Extract feature)?
4. Priority: Speed to market vs feature completeness?

### Resources Needed

- Frontend developer (React/TypeScript)
- Backend developer (Python)
- UI/UX review
- Test COA documents (various formats)

---

## Appendix: Reference Screenshots

1. `chat feature - landing ai.png` - Chat interface with visual references
2. `extract feature - landing ai.png` - Schema-based extraction
3. `parse feature - landing ai.png` - Markdown view of parsed content
4. `parse feature json content - landing ai.png` - JSON structure with bounding boxes

---

---

## Addendum: Text Grouping Solution (Claude Vision Approach)

> **Added:** January 2026
> **Context:** Solution for grouping text/paragraph content in Parse view for all AbbVie documents (not just COA)

---

### The Problem Clarified

| Content Type | Grouping Solution |
|--------------|-------------------|
| **Tables** | Use Textract TABLE + CELL blocks directly (already grouped) |
| **Text/Paragraphs** | Need intelligent grouping (this section addresses this) |

**Where grouping matters:**
- **Parse View (Static Markdown):** YES - need to display document structure
- **Chat Window:** NO - Claude naturally understands and responds intelligently

---

### The Challenge with Raw Textract Output

Textract gives us LINE-by-LINE text:

```
Line 1: "CONFIDENTIAL"
Line 2: "AbbVie Inc."
Line 3: "Product Specification Sheet"
Line 4: "Document Number"
Line 5: "PSS-2024-001"
Line 6: "Effective Date"
Line 7: "January 15, 2024"
Line 8: "This document describes the specifications for"
Line 9: "the manufacturing process of Product X."
```

**What we want to display:**

```
[1 - Text]
CONFIDENTIAL
AbbVie Inc.
Product Specification Sheet

[2 - Text]
Document Number: PSS-2024-001

[3 - Text]
Effective Date: January 15, 2024

[4 - Text]
This document describes the specifications for the manufacturing process of Product X.
```

---

### Solution: Claude Vision Page-by-Page Processing

**Key Insight:** Send each page as an **IMAGE** to Claude. Claude visually understands:
- What's a heading (bigger font, bold)
- What's a label-value pair (pattern recognition)
- What's a paragraph (text flow)
- What belongs together (visual proximity)

**This is BETTER than position-based grouping because Claude sees the actual visual layout.**

---

### Architecture: Async Parallel Processing

```
Document Upload (e.g., 200 pages)
              ↓
      Split into page images
              ↓
┌─────────────────────────────────────────────────────────────┐
│           PARALLEL PROCESSING (20 async agents)             │
│                                                             │
│  Agent 1: Page 1     Agent 2: Page 2     Agent 3: Page 3   │
│  Agent 4: Page 4     Agent 5: Page 5     Agent 6: Page 6   │
│  ...                 ...                 ...                │
│  Agent 19: Page 19   Agent 20: Page 20                     │
│                                                             │
│  ──── Batch 1 complete, start Batch 2 (Pages 21-40) ────   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
              ↓
      All 200 pages processed in ~2 minutes
              ↓
      Store grouped chunks with bounding boxes
              ↓
      Document ready for Parse View & Chat
```

---

### What Claude Sees (Image-Based Understanding)

When Claude receives a page image, it visually understands the structure:

```
┌─────────────────────────────────────────┐
│  PRODUCT SPECIFICATION                  │ ← Claude sees: HEADING (big, bold)
│                                         │
│  Document Number: PSS-2024-001          │ ← Claude sees: label-value pair
│  Effective Date: Jan 15, 2024           │ ← Claude sees: label-value pair
│                                         │
│  This document describes the            │ ← Claude sees: PARAGRAPH
│  specifications for the                 │    (multiple lines, same style,
│  manufacturing process.                 │     text flows together)
│                                         │
│  ┌───────────┬───────────┬───────────┐  │
│  │ Test      │ Result    │ Spec      │  │ ← SKIP: Textract handles tables
│  ├───────────┼───────────┼───────────┤  │
│  │ pH        │ 7.2       │ 6.5-7.5   │  │
│  └───────────┴───────────┴───────────┘  │
└─────────────────────────────────────────┘
```

**Claude returns structured grouping:**

```json
{
  "chunks": [
    {
      "type": "heading",
      "text": "PRODUCT SPECIFICATION",
      "lines": [1]
    },
    {
      "type": "label-value",
      "label": "Document Number",
      "value": "PSS-2024-001",
      "lines": [2]
    },
    {
      "type": "label-value",
      "label": "Effective Date",
      "value": "Jan 15, 2024",
      "lines": [3]
    },
    {
      "type": "paragraph",
      "text": "This document describes the specifications for the manufacturing process.",
      "lines": [4, 5, 6]
    }
  ]
}
```

---

### Processing Flow

```
ONE TIME (during document upload):
══════════════════════════════════
1. Textract processes document → blocks.json
2. For each page (in parallel):
   ├─ Extract TABLE chunks from Textract (with cell structure)
   └─ Send page IMAGE to Claude for TEXT grouping
3. Merge table chunks + text chunks
4. Store everything with bounding boxes
5. Document ready ✓

EVERY TIME (user opens Parse View):
════════════════════════════════════
Load stored chunks → instant display (no processing)

EVERY TIME (user asks in Chat):
════════════════════════════════════
RAG retrieves relevant chunks → Claude answers
(Grouping already done - zero impact on chat)
```

---

### Performance Estimates

| Document Size | Parallel Agents | Processing Time |
|---------------|-----------------|-----------------|
| 20 pages | 20 agents | ~6-8 seconds |
| 50 pages | 20 agents | ~15-20 seconds |
| 100 pages | 20 agents | ~30-40 seconds |
| 200 pages | 20 agents | ~1.5-2 minutes |

**Cost Estimate:**
- Claude Vision: ~$0.01-0.02 per page
- 200 pages = ~$2-4 (one-time cost per document)

---

### Why This Approach Works for All AbbVie Documents

| Document Type | Tables | Text/Paragraphs |
|---------------|--------|-----------------|
| COA (Certificate of Analysis) | Textract | Claude Vision |
| Product Specifications | Textract | Claude Vision |
| Batch Records | Textract | Claude Vision |
| SOPs | Textract | Claude Vision |
| Any AbbVie Document | Textract | Claude Vision |

**Universal solution** - not limited to COA documents.

---

### Summary: Grouping Solution

| Question | Answer |
|----------|--------|
| Is async parallel processing possible? | **YES** |
| Can 20 agents process simultaneously? | **YES** |
| 200 pages in ~2 minutes? | **YES** |
| One-time processing during upload? | **YES** |
| Works for all document types? | **YES** |
| Chat functionality impacted? | **NO - zero impact** |
| Tables need Claude? | **NO - Textract handles** |
| Text grouping quality? | **Excellent (Claude Vision)** |

---

### Implementation Notes

1. **Page Image Generation:** Convert PDF pages to images (PNG/JPEG) for Claude Vision
2. **Parallel Processing:** Use async/await with concurrency limit (20 agents)
3. **Merge Strategy:** Combine Textract table chunks + Claude text chunks, sort by position
4. **Storage:** Store final grouped chunks with bounding boxes in existing data structure
5. **Fallback:** If Claude Vision fails for a page, fall back to position-based grouping

---

---

## Addendum 2: Simplified Approach Using Textract LAYOUT Feature

> **Added:** January 2026
> **Context:** Simplified solution leveraging AWS Textract's LAYOUT feature for pre-grouped text

---

### Key Discovery: Textract LAYOUT Already Does Grouping!

AWS Textract has a **LAYOUT feature** that automatically:
- ✅ Understands reading order
- ✅ Groups paragraphs together
- ✅ Keeps headings separate
- ✅ Handles multi-column layouts
- ✅ Preserves logical document structure

**This eliminates the need for complex grouping logic!**

---

### How Textract LAYOUT Works

```python
import textractcaller as tc
from textractcaller.t_call import call_textract, Textract_Features
from textractprettyprinter.t_pretty_print import get_text_from_layout_json

# Call Textract with LAYOUT feature
layout_textract_json = call_textract(
    input_document=input_document,
    features=[Textract_Features.LAYOUT]
)

# Get layout-aware linearized text
layout_text = get_text_from_layout_json(textract_json=layout_textract_json)[1]
print(layout_text)
```

**Output (already grouped and ordered):**
```
PHOTONICS FOR A BETTER WORLD

UNESCO ENDORSES INTERNATIONAL DAY OF LIGHT

First celebration in 2018 will become an annual
reminder of photonics-enabled technologies

The executive board of the United Nations Educational,
Scientific, and Cultural Organization (UNESCO) has endorsed
a proposal to establish an annual International Day of Light
(IDL) as an extension of the highly successful International Year of
Light and Light-based Technologies (IYL 2015).
```

**Notice:** Text is already logically grouped - headings separate, paragraphs together, reading order correct!

---

### Simplified Flow

```
PDF Upload
     ↓
Textract with LAYOUT feature
     ↓
Get layout-aware text (ALREADY GROUPED!)
     ↓
For each page (parallel async):
     ├─ Input: Page image + Layout text
     └─ Claude returns: Formatted markdown
     ↓
Store formatted chunks with bounding boxes
     ↓
Done!
```

---

### What Claude Does (Simple Formatting Only)

**Input to Claude:**
1. Page image (for visual reference)
2. Layout text from Textract (already grouped)

**Task:** Just add markdown formatting

**Example Input (Layout text):**
```
PHOTONICS FOR A BETTER WORLD

UNESCO ENDORSES INTERNATIONAL DAY OF LIGHT

First celebration in 2018 will become an annual
reminder of photonics-enabled technologies

The executive board of the United Nations Educational...
```

**Claude Output (Formatted markdown):**
```markdown
# PHOTONICS FOR A BETTER WORLD

## UNESCO ENDORSES INTERNATIONAL DAY OF LIGHT

*First celebration in 2018 will become an annual reminder of photonics-enabled technologies*

The executive board of the United Nations Educational, Scientific, and Cultural Organization (UNESCO) has endorsed a proposal to establish an annual International Day of Light...
```

**Claude looks at the image and decides:**
- "PHOTONICS FOR A BETTER WORLD" → Big heading → `#`
- "UNESCO ENDORSES..." → Subheading → `##`
- "First celebration..." → Subtitle/emphasis → `*italics*`
- Rest → Normal paragraph text

---

### Comparison: Old Approach vs New Approach

| Aspect | Old Approach (Complex) | New Approach (Simple) |
|--------|------------------------|----------------------|
| **Text Extraction** | Textract LINE blocks | Textract LAYOUT |
| **Grouping** | Claude figures out grouping | Textract already grouped |
| **What Claude Does** | Group + Format | Format only |
| **Complexity** | High | Low |
| **Data Sent to Claude** | Image + Lines + Positions | Image + Layout text |
| **Claude's Task** | Complex reasoning | Simple formatting |

---

### Final Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────┐
│                    DOCUMENT UPLOAD                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              AWS TEXTRACT PROCESSING                        │
│                                                             │
│  Features: [LAYOUT, TABLES]                                 │
│                                                             │
│  Output:                                                    │
│  ├─ layout_text → Pre-grouped, reading-order text          │
│  └─ tables → TABLE + CELL blocks with structure            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│           PARALLEL PROCESSING (20 async agents)             │
│                                                             │
│  For each page:                                             │
│  ├─ TABLES: Extract structure from Textract (no Claude)    │
│  └─ TEXT: Send image + layout_text → Claude formats it     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                 STORE FORMATTED CHUNKS                      │
│                                                             │
│  {                                                          │
│    "markdown": "# Heading\n\nParagraph text...",           │
│    "type": "text",                                          │
│    "grounding": { "box": {...} },                          │
│    "page": 0                                                │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              READY FOR PARSE VIEW & CHAT                    │
└─────────────────────────────────────────────────────────────┘
```

---

### Summary: Why This is Better

| Question | Answer |
|----------|--------|
| Who does grouping? | **Textract LAYOUT** (not Claude) |
| What does Claude do? | **Only formatting** (add #, ##, *, etc.) |
| Is it simpler? | **YES - much simpler** |
| Less Claude processing? | **YES - simpler task = faster + cheaper** |
| Same quality output? | **YES - possibly better** (Textract is optimized for this) |
| Still works for all documents? | **YES - LAYOUT works on any document** |

---

### Implementation Change

**Before (Complex):**
```python
# Send lines + positions, ask Claude to group
claude_input = {
    "image": page_image,
    "lines": textract_lines_with_positions,
    "task": "Group these lines and format as markdown"
}
```

**After (Simple):**
```python
# Send pre-grouped text, ask Claude to just format
layout_text = get_text_from_layout_json(textract_json)

claude_input = {
    "image": page_image,
    "layout_text": layout_text,
    "task": "Add markdown formatting (headers, bold, etc.) based on visual appearance"
}
```

---

*Document Version: 1.2*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
*Addendum 2: Simplified Textract LAYOUT Approach*
