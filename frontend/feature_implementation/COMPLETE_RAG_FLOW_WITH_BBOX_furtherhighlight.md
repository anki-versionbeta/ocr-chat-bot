# Complete RAG Flow with Cell-Level BBox & Markdown Tab

> **Goal:** Add cell-level bbox to table chunks and enable Markdown Tab (Parse view)
> **Builds On:** COMPLETE_RAG_FLOW_WITH_BBOX.md, LANDING_AI_UI_ANALYSIS.md
> **Key Insight:** Textract PROVIDES cell-level bbox - we're just not storing it
> **Created:** January 2026

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Flow Recap](#current-flow-recap)
3. [The Gap: Cell-Level BBox Lost](#the-gap-cell-level-bbox-lost)
4. [Proposed Solution: cell_grounding](#proposed-solution-cell_grounding)
5. [Schema Changes](#schema-changes)
6. [Markdown Tab Feature Design](#markdown-tab-feature-design)
7. [Impact on RAG](#impact-on-rag)
8. [Implementation Steps](#implementation-steps)
9. [Complete Code Examples](#complete-code-examples)

---

## Executive Summary

```
CURRENT STATE:
──────────────────────────────────────────────────────────────────────
• Textract extracts TABLE and CELL blocks with individual bboxes
• Current chunking stores ONLY table-level bbox
• Cell-level bbox data is LOST during processing
• PDF highlighting works at table level only

PROPOSED ENHANCEMENT:
──────────────────────────────────────────────────────────────────────
• Extract and store cell-level bbox from Textract CELL blocks
• Add cell IDs to HTML tables (like Landing AI: <td id="0-j">)
• Store cell_grounding map with per-cell bbox
• Enable Markdown Tab with interactive cell highlighting

WHAT THIS ENABLES:
──────────────────────────────────────────────────────────────────────
• Click individual table cell → Highlight that cell on PDF
• Markdown Tab showing full document with clean table structures
• Same RAG performance (bbox is just metadata)
```

---

## Current Flow Recap

### What Textract Provides (Raw Data)

```
TEXTRACT BLOCK TYPES:
──────────────────────────────────────────────────────────────────────
PAGE        → Full page
LINE        → Text lines
WORD        → Individual words
TABLE       → Table structure (with child CELL references)
CELL        → Individual table cells (with bbox!)
MERGED_CELL → Merged cells (rowspan/colspan)
```

### Actual Textract CELL Block (From Your Data)

```json
{
  "BlockType": "CELL",
  "Id": "d73fb3cd-a426-4f95-8bfe-16f8e8e37ef6",
  "RowIndex": 1,
  "ColumnIndex": 1,
  "RowSpan": 1,
  "ColumnSpan": 1,
  "Geometry": {
    "BoundingBox": {
      "Left": 0.13183587789535522,
      "Top": 0.30583539605140686,
      "Width": 0.17999915778636932,
      "Height": 0.02347850054502487
    }
  },
  "Relationships": [
    {
      "Type": "CHILD",
      "Ids": ["word-id-1", "word-id-2"]
    }
  ]
}
```

**KEY: Each CELL has its own BoundingBox!**

### Current Chunking Output (What We Store)

```json
{
  "id": "chunk_abc123",
  "content": "Product Category | Material Type | Responsible Quality Group\nPharmaceutical | Goods: Finished Goods | Third Party Quality (TPQ)",
  "type": "table",
  "page": 0,
  "section": "Product Information",
  "bbox_left": 0.082,
  "bbox_top": 0.188,
  "bbox_right": 0.910,
  "bbox_bottom": 0.244
}
```

**PROBLEM: Only TABLE-level bbox stored. Cell bboxes are LOST!**

---

## The Gap: Cell-Level BBox Lost

### Visual Comparison

```
WHAT TEXTRACT PROVIDES:                    WHAT WE CURRENTLY STORE:
┌──────────────────────────────────────┐   ┌──────────────────────────────────────┐
│                                      │   │                                      │
│  ┌─────────┬─────────┬──────────┐   │   │  ┌──────────────────────────────┐   │
│  │ Cell 1  │ Cell 2  │ Cell 3   │   │   │  │                              │   │
│  │ bbox:A  │ bbox:B  │ bbox:C   │   │   │  │   ONE BBOX FOR ENTIRE TABLE  │   │
│  ├─────────┼─────────┼──────────┤   │   │  │                              │   │
│  │ Cell 4  │ Cell 5  │ Cell 6   │   │   │  │                              │   │
│  │ bbox:D  │ bbox:E  │ bbox:F   │   │   │  └──────────────────────────────┘   │
│  └─────────┴─────────┴──────────┘   │   │                                      │
│                                      │   │                                      │
│  6 CELL bboxes available             │   │  Cell bboxes LOST!                  │
│                                      │   │                                      │
└──────────────────────────────────────┘   └──────────────────────────────────────┘
```

### Where Cell BBox is Lost

```
CURRENT PROCESSING PIPELINE:
──────────────────────────────────────────────────────────────────────

Textract Output                 Chunking Process                Current Storage
┌────────────────┐             ┌──────────────────┐            ┌──────────────────┐
│ TABLE block    │             │                  │            │                  │
│ • bbox: {...}  │ ───────────▶│  Extract text    │ ──────────▶│  chunk.bbox_*    │
│                │             │  Get TABLE bbox  │            │  (table level)   │
│ CELL blocks    │             │                  │            │                  │
│ • cell1: bbox  │ ──── X ────▶│  CELL bboxes     │            │  CELL bboxes     │
│ • cell2: bbox  │    LOST!    │  NOT extracted   │            │  NOT stored      │
│ • cell3: bbox  │             │                  │            │                  │
└────────────────┘             └──────────────────┘            └──────────────────┘
```

### Impact of the Gap

```
CURRENT BEHAVIOR:
──────────────────────────────────────────────────────────────────────
• User asks about "Pharmaceutical" → RAG finds table chunk
• Click reference → Highlights ENTIRE TABLE
• Cannot highlight specific cell containing "Pharmaceutical"

DESIRED BEHAVIOR (Like Landing AI):
──────────────────────────────────────────────────────────────────────
• User asks about "Pharmaceutical" → RAG finds table chunk
• Click reference → Can highlight SPECIFIC CELL
• Markdown Tab → Click cell → Highlights that exact cell on PDF
```

---

## Proposed Solution: cell_grounding

### Target Output Format (Like Landing AI)

```json
{
  "id": "chunk_abc123",
  "markdown": "<table id=\"0-f\">\n<tr><td id=\"0-g\">Product Category</td><td id=\"0-h\">Material Type</td><td id=\"0-i\">Responsible Quality Group</td></tr>\n<tr><td id=\"0-j\">Pharmaceutical</td><td id=\"0-k\">Goods: Finished Goods</td><td id=\"0-l\">Third Party Quality (TPQ)</td></tr>\n</table>",
  "content": "Product Category | Material Type | Responsible Quality Group\nPharmaceutical | Goods: Finished Goods | Third Party Quality (TPQ)",
  "type": "table",
  "page": 0,
  "bbox_left": 0.082,
  "bbox_top": 0.188,
  "bbox_right": 0.910,
  "bbox_bottom": 0.244,
  "cell_grounding": {
    "0-f": {
      "box": {"left": 0.088, "top": 0.193, "right": 0.905, "bottom": 0.240},
      "type": "table"
    },
    "0-g": {
      "box": {"left": 0.088, "top": 0.193, "right": 0.272, "bottom": 0.214},
      "type": "tableCell",
      "row": 0,
      "col": 0
    },
    "0-h": {
      "box": {"left": 0.272, "top": 0.193, "right": 0.625, "bottom": 0.214},
      "type": "tableCell",
      "row": 0,
      "col": 1
    },
    "0-i": {
      "box": {"left": 0.625, "top": 0.193, "right": 0.905, "bottom": 0.214},
      "type": "tableCell",
      "row": 0,
      "col": 2
    },
    "0-j": {
      "box": {"left": 0.088, "top": 0.214, "right": 0.272, "bottom": 0.240},
      "type": "tableCell",
      "row": 1,
      "col": 0
    },
    "0-k": {
      "box": {"left": 0.272, "top": 0.214, "right": 0.625, "bottom": 0.240},
      "type": "tableCell",
      "row": 1,
      "col": 1
    },
    "0-l": {
      "box": {"left": 0.625, "top": 0.214, "right": 0.905, "bottom": 0.240},
      "type": "tableCell",
      "row": 1,
      "col": 2
    }
  }
}
```

### Cell ID Naming Convention

```
CELL ID FORMAT: {page}-{sequence}
──────────────────────────────────────────────────────────────────────

Page 0, Table 1:  0-1, 0-2, 0-3, ...
Page 0, Table 2:  0-f, 0-g, 0-h, ... (hex sequence continues)
Page 1, Table 1:  1-1, 1-2, 1-3, ...

Alternative (More Readable):
──────────────────────────────────────────────────────────────────────
Page 0, Table 1:  t0-r0c0, t0-r0c1, t0-r1c0, ...
                  (table-row-col format)
```

### Data Flow with Cell Grounding

```
NEW PROCESSING PIPELINE:
──────────────────────────────────────────────────────────────────────

Textract Output                 Enhanced Chunking               New Storage
┌────────────────┐             ┌──────────────────┐            ┌──────────────────┐
│ TABLE block    │             │                  │            │                  │
│ • bbox: {...}  │ ───────────▶│  Extract text    │ ──────────▶│  chunk.bbox_*    │
│                │             │  Get TABLE bbox  │            │  (table level)   │
│ CELL blocks    │             │                  │            │                  │
│ • cell1: bbox  │ ───────────▶│  Generate IDs    │ ──────────▶│  cell_grounding  │
│ • cell2: bbox  │  PRESERVED! │  Map cell bboxes │            │  (per-cell bbox) │
│ • cell3: bbox  │             │  Build HTML+IDs  │            │  markdown (HTML) │
└────────────────┘             └──────────────────┘            └──────────────────┘
```

---

## Schema Changes

### Elasticsearch Mapping Update

```json
{
  "mappings": {
    "properties": {
      "id": { "type": "keyword" },
      "document_id": { "type": "keyword" },
      "content": { "type": "text", "analyzer": "standard" },
      "embedding": { "type": "dense_vector", "dims": 1024 },
      "type": { "type": "keyword" },
      "page": { "type": "integer" },
      "section": { "type": "text" },

      "bbox_left": { "type": "float" },
      "bbox_top": { "type": "float" },
      "bbox_right": { "type": "float" },
      "bbox_bottom": { "type": "float" },

      "markdown": { "type": "text", "index": false },

      "cell_grounding": {
        "type": "object",
        "enabled": false
      }
    }
  }
}
```

### Key Schema Notes

```
FIELD DETAILS:
──────────────────────────────────────────────────────────────────────

markdown (NEW):
• Stores HTML representation with cell IDs
• "index": false → Not searchable (just for display)
• Only for "table" type chunks

cell_grounding (NEW):
• Stores per-cell bbox mapping
• "enabled": false → Stored but not indexed
• Only for "table" type chunks
• Structure: { "cell_id": { "box": {...}, "type": "tableCell", "row": N, "col": N } }

STORAGE INCREASE:
──────────────────────────────────────────────────────────────────────
• Average table: 6 cells = ~600 bytes additional
• Large table: 50 cells = ~5KB additional
• Estimate: 10-20% storage increase for documents with many tables
```

### Database Schema (If Using PostgreSQL)

```sql
-- Add new columns to chunks table (if using relational DB)
ALTER TABLE document_chunks
ADD COLUMN markdown TEXT,
ADD COLUMN cell_grounding JSONB;

-- Index for type filtering (optional optimization)
CREATE INDEX idx_chunks_type ON document_chunks(type);
```

---

## Markdown Tab Feature Design

### UI Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Document: COA_ATX101.pdf                                                    │
├───────────────────────────────────┬─────────────────────────────────────────┤
│                                   │                                         │
│         PDF VIEWER                │     [Chat] [Markdown] [Export]          │
│                                   │     ─────── ════════                    │
│   ┌───────────────────────────┐   │                                         │
│   │                           │   │     MARKDOWN TAB (Parse View)           │
│   │                           │   │     ════════════════════════            │
│   │      Page Image           │   │                                         │
│   │                           │   │     ┌─────────────────────────────┐     │
│   │   ┌─────────────────┐     │   │  1  │ ## Document Header          │     │
│   │   │ ░░ HIGHLIGHT ░░ │◀────┼───┼─────│ Product Shipment Auth Form  │     │
│   │   │ ░░░░░░░░░░░░░░░ │     │   │     └─────────────────────────────┘     │
│   │   └─────────────────┘     │   │                                         │
│   │                           │   │     ┌─────────────────────────────┐     │
│   │                           │   │  2  │ This executed Shipment...   │     │
│   └───────────────────────────┘   │     └─────────────────────────────┘     │
│                                   │                                         │
│   [◀] Page 1/5 [▶]                │     ┌─────────────────────────────┐     │
│                                   │  3  │ ┌───────┬───────┬─────────┐ │     │
│                                   │     │ │Product│Material│Quality  │◀─CLICK│
│                                   │     │ │ Cat.  │ Type   │ Group   │ │     │
│                                   │     │ ├───────┼───────┼─────────┤ │     │
│                                   │     │ │Pharma │Goods  │TPQ      │ │     │
│                                   │     │ └───────┴───────┴─────────┘ │     │
│                                   │     └─────────────────────────────┘     │
│                                   │                                         │
└───────────────────────────────────┴─────────────────────────────────────────┘

INTERACTION:
• Click block number (1, 2, 3) → Highlight entire block on PDF
• Click table cell → Highlight that specific cell on PDF
• Hover over element → Light highlight preview
```

### Markdown Tab Features

```
FEATURE LIST:
──────────────────────────────────────────────────────────────────────

1. Block Numbers (Like Landing AI)
   • Each chunk gets a number (1, 2, 3...)
   • Click number → Navigate to that region on PDF
   • Hover number → Preview highlight

2. Rendered Tables
   • Tables displayed as actual HTML tables (not markdown text)
   • Each cell is clickable
   • Cell hover → Light highlight on PDF
   • Cell click → Strong highlight + scroll to location

3. Text Blocks
   • Clean markdown rendering
   • Click anywhere → Highlight source region

4. Copy Functionality
   • Copy individual block
   • Copy entire document markdown
   • Copy table as markdown/CSV

5. Search Within
   • Search text in markdown view
   • Jump to matching blocks
```

### Component Structure

```tsx
// Markdown Tab Components
──────────────────────────────────────────────────────────────────────

<MarkdownTab>
  ├── <MarkdownHeader>
  │     ├── Search input
  │     └── Copy all button
  │
  ├── <BlockList>
  │     ├── <Block number={1} type="text">
  │     │     └── <MarkdownContent />
  │     │
  │     ├── <Block number={2} type="table">
  │     │     └── <InteractiveTable>
  │     │           └── <TableCell id="0-j" onClick={highlight} />
  │     │
  │     └── <Block number={3} type="text">
  │           └── <MarkdownContent />
  │
  └── <ScrollToTopButton />
```

---

## Impact on RAG

### No Impact on Search Performance

```
WHY RAG IS UNAFFECTED:
──────────────────────────────────────────────────────────────────────

1. Search Uses These Fields:
   • content (text) → Full-text search
   • embedding (vector) → Semantic search
   • document_id, page, type → Filters

2. New Fields NOT Used for Search:
   • markdown → index: false (display only)
   • cell_grounding → enabled: false (metadata only)

3. Same Query, Same Results:
   ┌──────────────────────────────────────────────────────────────┐
   │  BEFORE (Current):                                           │
   │  User: "What is the product category?"                       │
   │  → Search "content" field                                    │
   │  → Return chunk with bbox_* fields                           │
   │  → Highlight table on PDF                                    │
   ├──────────────────────────────────────────────────────────────┤
   │  AFTER (Enhanced):                                           │
   │  User: "What is the product category?"                       │
   │  → Search "content" field (SAME)                             │
   │  → Return chunk with bbox_* AND cell_grounding               │
   │  → Can highlight specific cell "Pharmaceutical"              │
   └──────────────────────────────────────────────────────────────┘
```

### What Changes

```
CHANGES IN RESPONSE DATA:
──────────────────────────────────────────────────────────────────────

Before (Current Response):
{
  "answer": "The product category is Pharmaceutical",
  "references": [{
    "page": 0,
    "bbox": {"left": 0.082, "top": 0.188, "right": 0.910, "bottom": 0.244},
    "type": "table"
    // Can only highlight ENTIRE TABLE
  }]
}

After (Enhanced Response):
{
  "answer": "The product category is Pharmaceutical",
  "references": [{
    "page": 0,
    "bbox": {"left": 0.082, "top": 0.188, "right": 0.910, "bottom": 0.244},
    "type": "table",
    "cell_id": "0-j",  // NEW: Specific cell reference
    "cell_bbox": {"left": 0.088, "top": 0.214, "right": 0.272, "bottom": 0.240}
    // Can highlight SPECIFIC CELL
  }]
}
```

### Enhanced Reference Detection (Optional)

```python
def find_cell_reference(answer_text: str, chunk: dict) -> str | None:
    """
    Optionally: Detect which cell contains the answer text.
    This enables cell-level highlighting in chat references.
    """
    if chunk["type"] != "table" or "cell_grounding" not in chunk:
        return None

    # Parse the markdown table
    # Find cell containing answer text
    # Return cell_id

    # Example: answer contains "Pharmaceutical"
    # Find cell with "Pharmaceutical" → return "0-j"

    return cell_id
```

---

## Implementation Steps

### Phase 1: Backend - Enhanced Chunking

```
STEP 1.1: Extract Cell BBox from Textract
──────────────────────────────────────────────────────────────────────
• Parse TABLE blocks and their CELL children
• Map CELL block IDs to their bbox
• Build row/column structure from RowIndex/ColumnIndex

STEP 1.2: Generate Cell IDs
──────────────────────────────────────────────────────────────────────
• Create unique ID for each cell: "{page}-{sequence}"
• Maintain mapping: cell_id → bbox

STEP 1.3: Build HTML with Cell IDs
──────────────────────────────────────────────────────────────────────
• Generate table HTML: <table id="..."><tr><td id="...">
• Include rowspan/colspan attributes
• Store as "markdown" field

STEP 1.4: Create cell_grounding Map
──────────────────────────────────────────────────────────────────────
• Build object: { "cell_id": { "box": {...}, "type": "tableCell", ... } }
• Include table-level grounding too
```

### Phase 2: Backend - API Updates

```
STEP 2.1: Update Chunk Response
──────────────────────────────────────────────────────────────────────
• Include markdown and cell_grounding in responses
• Add endpoint for full document markdown

STEP 2.2: Add Document Markdown Endpoint
──────────────────────────────────────────────────────────────────────
GET /api/documents/{document_id}/markdown

Response:
{
  "document_id": "doc_123",
  "page_count": 5,
  "blocks": [
    {
      "number": 1,
      "type": "text",
      "page": 0,
      "markdown": "## Document Header...",
      "bbox": {...}
    },
    {
      "number": 2,
      "type": "table",
      "page": 0,
      "markdown": "<table id='0-f'>...</table>",
      "bbox": {...},
      "cell_grounding": {...}
    }
  ]
}
```

### Phase 3: Frontend - Markdown Tab

```
STEP 3.1: Create Tab Component
──────────────────────────────────────────────────────────────────────
• Add "Markdown" tab alongside "Chat"
• Load document markdown on tab switch

STEP 3.2: Render Block List
──────────────────────────────────────────────────────────────────────
• Display numbered blocks
• Render text as markdown
• Render tables as interactive HTML

STEP 3.3: Implement Interactions
──────────────────────────────────────────────────────────────────────
• Block number click → Highlight on PDF + navigate
• Table cell click → Highlight specific cell
• Hover effects for preview
```

### Phase 4: Integration

```
STEP 4.1: Wire Up Highlighting
──────────────────────────────────────────────────────────────────────
• Pass cell_grounding to DocumentViewer
• Support both table-level and cell-level highlights

STEP 4.2: Sync Navigation
──────────────────────────────────────────────────────────────────────
• Scroll markdown view when PDF navigates
• Scroll PDF when clicking markdown blocks
```

---

## Complete Code Examples

### 1. Enhanced Table Chunking (Python)

```python
# services/enhanced_chunking.py

def process_table_with_cells(
    table_block: dict,
    all_blocks: dict,
    page_num: int,
    table_index: int
) -> dict:
    """
    Process a TABLE block with cell-level bbox extraction.
    """

    # Get all CELL blocks for this table
    cell_ids = []
    for rel in table_block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            cell_ids = rel["Ids"]
            break

    # Build cell structure
    cells = {}
    for cell_id in cell_ids:
        cell_block = all_blocks.get(cell_id)
        if cell_block and cell_block["BlockType"] == "CELL":
            row = cell_block["RowIndex"]
            col = cell_block["ColumnIndex"]

            # Get cell text
            cell_text = extract_cell_text(cell_block, all_blocks)

            # Get cell bbox
            bbox = cell_block["Geometry"]["BoundingBox"]

            cells[(row, col)] = {
                "text": cell_text,
                "bbox": {
                    "left": bbox["Left"],
                    "top": bbox["Top"],
                    "right": bbox["Left"] + bbox["Width"],
                    "bottom": bbox["Top"] + bbox["Height"]
                },
                "rowspan": cell_block.get("RowSpan", 1),
                "colspan": cell_block.get("ColumnSpan", 1)
            }

    # Build HTML with cell IDs
    html, cell_grounding = build_table_html(
        cells=cells,
        page_num=page_num,
        table_index=table_index
    )

    # Build plain text content (for search)
    content = build_table_text(cells)

    # Get table-level bbox
    table_bbox = table_block["Geometry"]["BoundingBox"]

    return {
        "type": "table",
        "page": page_num,
        "content": content,
        "markdown": html,
        "bbox_left": table_bbox["Left"],
        "bbox_top": table_bbox["Top"],
        "bbox_right": table_bbox["Left"] + table_bbox["Width"],
        "bbox_bottom": table_bbox["Top"] + table_bbox["Height"],
        "cell_grounding": cell_grounding
    }


def build_table_html(
    cells: dict,
    page_num: int,
    table_index: int
) -> tuple[str, dict]:
    """
    Build HTML table with cell IDs and cell_grounding map.
    """

    # Find table dimensions
    max_row = max(r for r, c in cells.keys())
    max_col = max(c for r, c in cells.keys())

    # Generate table ID
    table_id = f"{page_num}-t{table_index}"

    cell_grounding = {}
    html_rows = []
    cell_counter = 0

    for row in range(1, max_row + 1):
        row_cells = []
        for col in range(1, max_col + 1):
            if (row, col) not in cells:
                continue

            cell = cells[(row, col)]

            # Generate cell ID
            cell_id = f"{page_num}-{hex(cell_counter)[2:]}"
            cell_counter += 1

            # Build cell grounding entry
            cell_grounding[cell_id] = {
                "box": cell["bbox"],
                "type": "tableCell",
                "row": row - 1,
                "col": col - 1
            }

            # Build HTML attributes
            attrs = [f'id="{cell_id}"']
            if cell["rowspan"] > 1:
                attrs.append(f'rowspan="{cell["rowspan"]}"')
            if cell["colspan"] > 1:
                attrs.append(f'colspan="{cell["colspan"]}"')

            row_cells.append(f'<td {" ".join(attrs)}>{cell["text"]}</td>')

        if row_cells:
            html_rows.append(f'<tr>{"".join(row_cells)}</tr>')

    # Add table-level grounding
    table_bbox = calculate_table_bbox(cells)
    cell_grounding[table_id] = {
        "box": table_bbox,
        "type": "table"
    }

    html = f'<table id="{table_id}">\n{"".join(html_rows)}\n</table>'

    return html, cell_grounding


def extract_cell_text(cell_block: dict, all_blocks: dict) -> str:
    """Extract text content from a CELL block."""

    text_parts = []

    for rel in cell_block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for child_id in rel["Ids"]:
                child_block = all_blocks.get(child_id)
                if child_block:
                    if child_block["BlockType"] == "WORD":
                        text_parts.append(child_block.get("Text", ""))
                    elif child_block["BlockType"] == "LINE":
                        text_parts.append(child_block.get("Text", ""))

    return " ".join(text_parts)
```

### 2. Document Markdown API Endpoint

```python
# routes/document_routes.py

@document_bp.route('/api/documents/<document_id>/markdown', methods=['GET'])
def get_document_markdown(document_id: str):
    """
    Get full document markdown with all blocks for Markdown Tab.
    """

    # Get all chunks for document, ordered by page and position
    chunks = get_all_chunks_ordered(document_id)

    blocks = []
    for i, chunk in enumerate(chunks):
        block = {
            "number": i + 1,
            "id": chunk["id"],
            "type": chunk["type"],
            "page": chunk["page"],
            "bbox": {
                "left": chunk["bbox_left"],
                "top": chunk["bbox_top"],
                "right": chunk["bbox_right"],
                "bottom": chunk["bbox_bottom"]
            }
        }

        if chunk["type"] == "table":
            block["markdown"] = chunk.get("markdown", chunk["content"])
            block["cell_grounding"] = chunk.get("cell_grounding", {})
        else:
            block["markdown"] = chunk["content"]

        blocks.append(block)

    return jsonify({
        "document_id": document_id,
        "page_count": get_document_page_count(document_id),
        "blocks": blocks
    })
```

### 3. Markdown Tab Component (React)

```tsx
// components/MarkdownTab.tsx

import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Block {
  number: number;
  id: string;
  type: 'text' | 'table' | 'title';
  page: number;
  markdown: string;
  bbox: BoundingBox;
  cell_grounding?: Record<string, {
    box: BoundingBox;
    type: string;
    row?: number;
    col?: number;
  }>;
}

interface Props {
  documentId: string;
  onHighlight: (page: number, bbox: BoundingBox) => void;
}

export function MarkdownTab({ documentId, onHighlight }: Props) {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredBlock, setHoveredBlock] = useState<number | null>(null);

  useEffect(() => {
    loadDocumentMarkdown();
  }, [documentId]);

  async function loadDocumentMarkdown() {
    setLoading(true);
    try {
      const response = await fetch(`/api/documents/${documentId}/markdown`);
      const data = await response.json();
      setBlocks(data.blocks);
    } finally {
      setLoading(false);
    }
  }

  function handleBlockClick(block: Block) {
    onHighlight(block.page, block.bbox);
  }

  function handleCellClick(block: Block, cellId: string) {
    if (block.cell_grounding && block.cell_grounding[cellId]) {
      const cellInfo = block.cell_grounding[cellId];
      onHighlight(block.page, cellInfo.box);
    }
  }

  if (loading) {
    return <div className="markdown-loading">Loading document...</div>;
  }

  return (
    <div className="markdown-tab">
      <div className="markdown-header">
        <h3>Document Parse View</h3>
        <button className="copy-all-btn">Copy All</button>
      </div>

      <div className="markdown-blocks">
        {blocks.map(block => (
          <div
            key={block.id}
            className={`markdown-block ${hoveredBlock === block.number ? 'hovered' : ''}`}
            onMouseEnter={() => setHoveredBlock(block.number)}
            onMouseLeave={() => setHoveredBlock(null)}
          >
            <div
              className="block-number"
              onClick={() => handleBlockClick(block)}
              title="Click to highlight on PDF"
            >
              {block.number}
            </div>

            <div className="block-content">
              {block.type === 'table' ? (
                <InteractiveTable
                  html={block.markdown}
                  cellGrounding={block.cell_grounding || {}}
                  onCellClick={(cellId) => handleCellClick(block, cellId)}
                />
              ) : (
                <div onClick={() => handleBlockClick(block)}>
                  <ReactMarkdown>{block.markdown}</ReactMarkdown>
                </div>
              )}
            </div>

            <div className="block-meta">
              Page {block.page + 1} • {block.type}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 4. Interactive Table Component

```tsx
// components/InteractiveTable.tsx

import { useRef, useEffect } from 'react';

interface BoundingBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

interface Props {
  html: string;
  cellGrounding: Record<string, { box: BoundingBox; type: string }>;
  onCellClick: (cellId: string) => void;
}

export function InteractiveTable({ html, cellGrounding, onCellClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Add click handlers to all cells with IDs
    const cells = containerRef.current.querySelectorAll('td[id], th[id]');

    cells.forEach(cell => {
      const cellId = cell.getAttribute('id');
      if (cellId && cellGrounding[cellId]) {
        cell.classList.add('interactive-cell');

        cell.addEventListener('click', (e) => {
          e.stopPropagation();
          onCellClick(cellId);
        });

        cell.addEventListener('mouseenter', () => {
          cell.classList.add('cell-hover');
        });

        cell.addEventListener('mouseleave', () => {
          cell.classList.remove('cell-hover');
        });
      }
    });

    // Cleanup
    return () => {
      cells.forEach(cell => {
        cell.replaceWith(cell.cloneNode(true));
      });
    };
  }, [html, cellGrounding, onCellClick]);

  return (
    <div
      ref={containerRef}
      className="interactive-table"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
```

### 5. CSS Styles for Markdown Tab

```css
/* styles/markdown-tab.css */

.markdown-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--gray-50);
}

.markdown-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--gray-200);
  background: white;
}

.markdown-header h3 {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--gray-800);
}

.markdown-blocks {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
}

.markdown-block {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding: var(--space-3);
  background: white;
  border-radius: var(--radius-lg);
  border: 1px solid var(--gray-200);
  transition: all 0.15s ease;
}

.markdown-block.hovered {
  border-color: var(--primary-300);
  box-shadow: 0 0 0 3px var(--primary-50);
}

.block-number {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gray-100);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--gray-600);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.block-number:hover {
  background: var(--primary-100);
  color: var(--primary-700);
}

.block-content {
  flex: 1;
  min-width: 0;
}

.block-meta {
  font-size: var(--text-xs);
  color: var(--gray-400);
  align-self: flex-end;
}

/* Interactive Table Styles */
.interactive-table {
  overflow-x: auto;
}

.interactive-table table {
  border-collapse: collapse;
  width: 100%;
  font-size: var(--text-sm);
}

.interactive-table td,
.interactive-table th {
  border: 1px solid var(--gray-200);
  padding: var(--space-2) var(--space-3);
  text-align: left;
}

.interactive-table th {
  background: var(--gray-50);
  font-weight: 600;
}

.interactive-cell {
  cursor: pointer;
  transition: background 0.15s ease;
}

.interactive-cell:hover,
.cell-hover {
  background: var(--highlight-hover) !important;
}

.interactive-cell:active {
  background: var(--highlight-active) !important;
}

/* Copy button */
.copy-all-btn {
  padding: var(--space-2) var(--space-3);
  background: white;
  border: 1px solid var(--gray-300);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.copy-all-btn:hover {
  background: var(--gray-50);
  border-color: var(--gray-400);
}
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  COMPLETE ENHANCEMENT SUMMARY                                               │
│  ═══════════════════════════════════════════════════════════════════════   │
│                                                                             │
│  THE GAP:                                                                   │
│  • Textract provides cell-level bbox (CELL blocks)                         │
│  • Current chunking loses this data                                        │
│  • Only table-level bbox stored                                            │
│                                                                             │
│  THE SOLUTION:                                                              │
│  • Extract cell bbox during chunking                                       │
│  • Generate cell IDs (page-sequence format)                                │
│  • Build HTML with cell IDs (<td id="0-j">)                               │
│  • Store cell_grounding map with per-cell bbox                            │
│                                                                             │
│  NEW FIELDS:                                                                │
│  • markdown: HTML table with cell IDs                                      │
│  • cell_grounding: { "cell_id": { box, type, row, col } }                 │
│                                                                             │
│  MARKDOWN TAB FEATURE:                                                      │
│  • Numbered blocks (1, 2, 3...)                                            │
│  • Click block number → Highlight on PDF                                   │
│  • Click table cell → Highlight that cell on PDF                          │
│  • Full document parse view (like Landing AI)                              │
│                                                                             │
│  RAG IMPACT:                                                                │
│  • NONE - bbox is metadata only                                            │
│  • Search uses content + embedding (unchanged)                             │
│  • New fields not indexed                                                  │
│                                                                             │
│  STORAGE IMPACT:                                                            │
│  • ~10-20% increase for documents with many tables                         │
│  • cell_grounding stored but not indexed                                   │
│                                                                             │
│  IMPLEMENTATION PHASES:                                                     │
│  • Phase 1: Enhanced chunking (extract cell bbox)                          │
│  • Phase 2: API updates (document markdown endpoint)                       │
│  • Phase 3: Markdown Tab UI component                                      │
│  • Phase 4: Integration (bidirectional highlighting)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Builds On: COMPLETE_RAG_FLOW_WITH_BBOX.md, LANDING_AI_UI_ANALYSIS.md*
*Compatible With: BBOX_HIGHLIGHT_IMPLEMENTATION.md, MULTI_DOCUMENT_WORKFLOW.md*
