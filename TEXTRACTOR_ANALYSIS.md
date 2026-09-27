# AWS Textractor Library Analysis

> **Document Purpose:** Understanding what AWS Textractor provides vs what requires Claude Vision
> **Created:** January 2026
> **Related:** LANDING_AI_UI_ANALYSIS.md

---

## Table of Contents

1. [Overview](#overview)
2. [What Textractor Provides](#what-textractor-provides)
   - [Bounding Boxes](#1-bounding-boxes)
   - [Reading Order (LAYOUT)](#2-reading-order-layout-feature)
   - [Layout Type Detection](#3-layout-type-detection-titles-headers-etc)
   - [Table Structure](#4-table-structure)
   - [Visualization](#5-built-in-visualization)
3. [What Textractor Does NOT Provide](#what-textractor-does-not-provide)
4. [Textractor vs Claude Vision](#textractor-vs-claude-vision-comparison)
5. [Practical Usage for Landing AI-Style UI](#practical-usage-for-landing-ai-style-ui)
6. [Code Examples](#code-examples)

---

## Overview

**Textractor** is AWS's Python library for working with Amazon Textract responses. It simplifies parsing and provides useful abstractions.

**Key Insight:** Textractor is excellent for STRUCTURE (bounding boxes, tables, reading order) but does NOT do SEMANTIC GROUPING (understanding label-value pairs, formatting as markdown).

---

## What Textractor Provides

### 1. Bounding Boxes

**Every element in Textractor has geometry coordinates:**

```python
# Get a table
table = document.tables[0]

# Access its bounding box
table.bbox
# Returns: BoundingBox(x=0.08, y=0.14, width=0.82, height=0.25)

# Every cell also has bbox
for row in table.rows:
    for cell in row.cells:
        print(cell.text, cell.bbox)

# Output:
# "pH"       BoundingBox(x=0.08, y=0.14, width=0.15, height=0.05)
# "7.2"      BoundingBox(x=0.25, y=0.14, width=0.15, height=0.05)
# "6.5-7.5"  BoundingBox(x=0.42, y=0.14, width=0.20, height=0.05)
```

**How this helps:**
- ✅ Get exact coordinates for EVERY element
- ✅ Can draw highlights on PDF at these positions
- ✅ Can create Landing AI-style visual references
- ✅ Link chat responses to specific document locations

**Coordinate Format:**
- Values are normalized (0 to 1)
- `x=0.08` means 8% from left edge
- `y=0.14` means 14% from top edge
- To convert to pixels: `pixel_x = x * page_width`

---

### 2. Reading Order (LAYOUT Feature)

**The Problem Without LAYOUT:**

Multi-column documents read incorrectly:
```
# Wrong order (without LAYOUT):
Column 1 Line 1
Column 2 Line 1    ← Jumps to wrong column!
Column 1 Line 2
Column 2 Line 2
```

**With LAYOUT Feature:**

Text comes in correct human reading order:
```
# Correct order (with LAYOUT):
Column 1 Line 1
Column 1 Line 2
Column 1 Line 3
Column 2 Line 1    ← Correct! Finishes column 1 first
Column 2 Line 2
```

**How to enable:**
```python
document = extractor.analyze_document(
    file_source="document.pdf",
    features=[TextractFeatures.LAYOUT]  # Enable LAYOUT
)
```

**How this helps:**
- ✅ Text comes out in human reading order
- ✅ No jumbled content from multi-column documents
- ✅ Paragraphs stay together (not split across columns)
- ✅ Better chunks for RAG

---

### 3. Layout Type Detection (Titles, Headers, etc.)

**Textractor identifies different layout element TYPES:**

```python
page = document.pages[0]

# Get all titles (big headings)
titles = page.page_layout.titles
# Returns: ["PRODUCT SPECIFICATION", "CERTIFICATE OF ANALYSIS"]

# Get section headers
section_headers = page.page_layout.section_headers
# Returns: ["1. Product Information", "2. Test Results"]

# Get page headers (like "CONFIDENTIAL" at top)
headers = page.page_layout.headers
# Returns: ["CONFIDENTIAL", "AbbVie Inc."]

# Get footers
footers = page.page_layout.footers
# Returns: ["Page 1 of 5", "Document ID: ABC123"]

# Get text paragraphs
text_blocks = page.page_layout.text
# Returns: [paragraph1, paragraph2, ...]

# Get figures
figures = page.page_layout.figures
# Returns: [figure1, figure2, ...]

# Get key-value pairs (forms)
key_values = page.page_layout.key_values
# Returns: [kv1, kv2, ...]

# Get lists
lists = page.page_layout.lists
# Returns: [list1, list2, ...]

# Get page numbers
page_numbers = page.page_layout.page_numbers
# Returns: ["1", "Page 1 of 5"]
```

**Each element has bounding box:**
```python
title = page.page_layout.titles[0]
print(title.text)  # "PRODUCT SPECIFICATION"
print(title.bbox)  # BoundingBox(x=0.2, y=0.05, width=0.6, height=0.08)
```

**How this helps:**
- ✅ Know what's a title vs body text
- ✅ Can filter out headers/footers
- ✅ Can extract just tables or just text
- ✅ Build document structure map

---

### 4. Table Structure

**Textractor provides full table structure:**

```python
# Get all tables
tables = document.tables

# Access a specific table
table = tables[0]

# Get table properties
table.bbox           # Bounding box of entire table
table.row_count      # Number of rows
table.column_count   # Number of columns

# Iterate through rows and cells
for row in table.rows:
    for cell in row.cells:
        print(f"Row {cell.row_index}, Col {cell.column_index}: {cell.text}")
        print(f"  Bbox: {cell.bbox}")
        print(f"  Is header: {cell.is_column_header}")

# Export to different formats
table.to_markdown()  # Markdown table
table.to_html()      # HTML table
table.to_pandas()    # Pandas DataFrame
table.to_csv()       # CSV format
```

**Example Output:**
```python
table.to_markdown()
# | Test Parameter | Result | Specification |
# |----------------|--------|---------------|
# | pH             | 7.2    | 6.5-7.5       |
# | Density        | 1.05   | 1.00-1.10     |
```

**How this helps:**
- ✅ Full table structure with rows/columns
- ✅ Cell-level bounding boxes
- ✅ Header detection
- ✅ Direct export to markdown/HTML
- ✅ Easy to render as interactive table

---

### 5. Built-in Visualization

**Textractor can draw bounding boxes on images:**

```python
# Visualize all layouts on a page
document.pages[0].layouts.visualize()

# Visualize just tables
document.tables.visualize()

# Visualize just titles
document.pages[0].page_layout.titles.visualize()

# Visualize key-values
document.key_values.visualize()

# Visualize checkboxes
document.checkboxes.visualize()

# Search and visualize matching words
words = document.search_words("pH", top_k=10)
words.visualize()  # Highlights all "pH" occurrences!
```

**How this helps:**
- ✅ Quick debugging/testing
- ✅ Can generate highlighted images
- ✅ Built-in overlay without custom code

---

## What Textractor Does NOT Provide

### 1. Semantic Text Grouping

**Textractor gives:**
```
Line 1: "Document Number"
Line 2: "PSS-2024-001"
Line 3: "Effective Date"
Line 4: "January 15, 2024"
```

**Textractor does NOT know:**
```
"Document Number" + "PSS-2024-001" should be grouped as:
"Document Number: PSS-2024-001"
```

**Why:** Textractor extracts text positionally but doesn't understand that "Document Number" is a LABEL and "PSS-2024-001" is its VALUE.

---

### 2. Markdown Formatting

**Textractor can identify a title exists, but doesn't format it:**

```python
title = page.page_layout.titles[0]
title.text  # Returns: "PRODUCT SPECIFICATION"

# Textractor does NOT automatically add:
# "# PRODUCT SPECIFICATION"  ← No markdown formatting
```

**The `to_markdown()` method only works for TABLES, not general text.**

---

### 3. Understanding Visual Relationships

**Example document:**
```
┌─────────────────────────────────────────┐
│  Document Number    PSS-2024-001        │  ← Same visual line
│  Effective Date     January 15, 2024    │  ← Same visual line
└─────────────────────────────────────────┘
```

**Textractor sees:**
```
Line 1: "Document Number"
Line 2: "PSS-2024-001"
Line 3: "Effective Date"
Line 4: "January 15, 2024"
```

**Textractor does NOT understand:**
- "Document Number" and "PSS-2024-001" are on the SAME visual line
- They form a label-value pair
- They should be displayed together

---

## Textractor vs Claude Vision Comparison

| Feature | Textractor | Claude Vision |
|---------|------------|---------------|
| **Bounding boxes** | ✅ YES | ❌ No (doesn't extract) |
| **Reading order** | ✅ YES (LAYOUT) | ❌ No |
| **Table structure** | ✅ YES (cells, rows, cols) | ⚠️ Can describe but not structured |
| **Title detection** | ✅ YES (identifies titles) | ✅ YES |
| **Text extraction** | ✅ YES (accurate OCR) | ✅ YES (but we use Textract) |
| **Label-value grouping** | ❌ NO | ✅ YES (visual understanding) |
| **Markdown formatting** | ❌ NO (tables only) | ✅ YES |
| **Semantic understanding** | ❌ NO | ✅ YES |
| **"What belongs together"** | ❌ NO | ✅ YES |

---

## Practical Usage for Landing AI-Style UI

### What We Use Textractor For:

```
✅ PDF highlighting (bounding boxes for every element)
✅ "Page 2, Table 1, Cell 3" references (precise locations)
✅ Table structure (rows, columns, cells with bbox)
✅ Identifying titles vs body text (layout types)
✅ Reading order for RAG chunks (LAYOUT feature)
✅ Quick visualization for debugging
```

### What We Use Claude Vision For:

```
✅ "Document Number: PSS-001" grouping (label + value on same line)
✅ Markdown formatting (# ## ** etc.)
✅ Understanding what text belongs together visually
✅ Converting layout text to user-friendly display
```

---

## Code Examples

### Complete Document Processing

```python
from textractor import Textractor
from textractor.data.constants import TextractFeatures

# Initialize
extractor = Textractor(region_name="us-east-1")

# Process document with all features
document = extractor.analyze_document(
    file_source="COA.pdf",
    features=[
        TextractFeatures.LAYOUT,     # Reading order, titles, headers
        TextractFeatures.TABLES,     # Table structure
        TextractFeatures.FORMS,      # Key-value pairs
        TextractFeatures.SIGNATURES  # Signature detection
    ],
    save_image=True  # Keep images for visualization
)

# Access structured data
for page in document.pages:
    print(f"=== Page {page.page_num} ===")

    # Titles
    for title in page.page_layout.titles:
        print(f"Title: {title.text}")
        print(f"  Bbox: {title.bbox}")

    # Tables
    for table in page.tables:
        print(f"Table: {table.row_count} rows x {table.column_count} cols")
        print(f"  Bbox: {table.bbox}")
        print(table.to_markdown())

    # Text blocks
    for text in page.page_layout.text:
        print(f"Text: {text.text[:50]}...")
        print(f"  Bbox: {text.bbox}")
```

### Building Landing AI-Style JSON

```python
def build_landing_ai_chunks(document):
    """Convert Textractor document to Landing AI-style chunks"""
    chunks = []

    for page in document.pages:
        page_num = page.page_num - 1  # 0-indexed

        # Process tables
        for table in page.tables:
            bbox = table.bbox
            chunk = {
                "markdown": table.to_markdown(),
                "type": "table",
                "id": f"table-{page_num}-{len(chunks)}",
                "grounding": {
                    "box": {
                        "left": bbox.x,
                        "top": bbox.y,
                        "right": bbox.x + bbox.width,
                        "bottom": bbox.y + bbox.height
                    }
                },
                "page": page_num,
                "table_structure": {
                    "headers": [cell.text for cell in table.rows[0].cells],
                    "rows": [
                        {cell.text for cell in row.cells}
                        for row in table.rows[1:]
                    ]
                }
            }
            chunks.append(chunk)

        # Process titles
        for title in page.page_layout.titles:
            bbox = title.bbox
            chunk = {
                "markdown": f"# {title.text}",  # Add markdown heading
                "type": "title",
                "id": f"title-{page_num}-{len(chunks)}",
                "grounding": {
                    "box": {
                        "left": bbox.x,
                        "top": bbox.y,
                        "right": bbox.x + bbox.width,
                        "bottom": bbox.y + bbox.height
                    }
                },
                "page": page_num
            }
            chunks.append(chunk)

        # Process text blocks (these need Claude for grouping)
        for text in page.page_layout.text:
            bbox = text.bbox
            chunk = {
                "markdown": text.text,  # Plain text - Claude will format
                "type": "text",
                "id": f"text-{page_num}-{len(chunks)}",
                "grounding": {
                    "box": {
                        "left": bbox.x,
                        "top": bbox.y,
                        "right": bbox.x + bbox.width,
                        "bottom": bbox.y + bbox.height
                    }
                },
                "page": page_num,
                "needs_formatting": True  # Flag for Claude processing
            }
            chunks.append(chunk)

    return chunks
```

### Visualization Example

```python
# Visualize specific elements
image_with_tables = document.tables.visualize()
image_with_tables.save("tables_highlighted.png")

# Visualize search results
matches = document.search_words("pH")
image_with_matches = matches.visualize()
image_with_matches.save("ph_highlighted.png")

# Visualize all layouts
image_with_layouts = document.pages[0].layouts.visualize()
image_with_layouts.save("all_layouts.png")
```

---

## Summary

### Textractor is GREAT for:

| Feature | Use Case |
|---------|----------|
| **Bounding boxes** | PDF highlighting, visual references |
| **LAYOUT feature** | Correct reading order |
| **Title/header detection** | Document structure |
| **Table structure** | Render as HTML/markdown tables |
| **Built-in visualization** | Debugging, quick previews |
| **Export formats** | Markdown, HTML, CSV, DataFrame |

### Claude Vision is NEEDED for:

| Feature | Use Case |
|---------|----------|
| **Label-value grouping** | "Document Number: PSS-001" |
| **Markdown formatting** | `# Heading`, `**bold**` |
| **Semantic understanding** | What belongs together |
| **Visual relationships** | Items on same line |

---

## Conclusion

**Use BOTH together:**

```
Document Upload
      ↓
Textractor extracts:
  - Tables (with structure + bbox)
  - Titles (with bbox)
  - Text blocks (with bbox)
  - Reading order
      ↓
For TEXT blocks only:
  - Send page image + text to Claude Vision
  - Claude groups and formats
      ↓
Combine all chunks with bounding boxes
      ↓
Ready for Landing AI-style UI!
```

---

*Document Version: 1.0*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
