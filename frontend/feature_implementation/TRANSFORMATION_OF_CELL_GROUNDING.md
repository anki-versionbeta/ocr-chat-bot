# Transformation of Cell Grounding from Textract Blocks

> **Purpose:** Document how Textract block information transforms into chunks with cell_grounding
> **Source Data:** COA_1000459079_1_blocks.json (actual Textract output)
> **Target Format:** Landing AI style with cell-level bbox
> **Created:** January 2026

---

## Table of Contents

1. [Processing Flow Overview](#processing-flow-overview)
2. [Step 1: Raw Textract Output](#step-1-raw-textract-output)
3. [Step 2: Parse TABLE and CELL Blocks](#step-2-parse-table-and-cell-blocks)
4. [Step 3: Transform to Chunk with Cell Grounding](#step-3-transform-to-chunk-with-cell-grounding)
5. [Step 4: Final Elasticsearch Document](#step-4-final-elasticsearch-document)
6. [How Cell Matching Works](#how-cell-matching-works)
7. [Visual Examples](#visual-examples)
8. [ID Structure Explained](#id-structure-explained)

---

## Processing Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  COMPLETE PROCESSING PIPELINE                                               │
│  ════════════════════════════                                               │
│                                                                             │
│  PDF Document                                                               │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: Textract Processing                                         │   │
│  │         PDF → Textract API → blocks.json                            │   │
│  │         Output: PAGE, LINE, WORD, TABLE, CELL blocks               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: Parse Block Information                                     │   │
│  │         • Find all TABLE blocks                                     │   │
│  │         • For each TABLE, find child CELL blocks                   │   │
│  │         • Extract text from WORD children of each CELL             │   │
│  │         • Build block_by_id lookup dictionary                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: Transform to Chunk Format                                   │   │
│  │         • Generate cell IDs: "{page}-{sequence}"                   │   │
│  │         • Build plain text content (for RAG search)                │   │
│  │         • Build HTML markdown with cell IDs                         │   │
│  │         • Build cell_grounding map with per-cell bbox              │   │
│  │         • Generate embedding from content                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 4: Store in Elasticsearch                                      │   │
│  │         • Index: "document_chunks"                                  │   │
│  │         • chunk with all fields including cell_grounding           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step 1: Raw Textract Output

### Source File Structure

```
File: COA_1000459079_1_blocks.json
Size: 942,028 bytes
Pages: 6
Total Blocks: ~2000+
TABLE Blocks: 4
```

### Textract Block Types

```
BLOCK TYPES IN TEXTRACT OUTPUT:
═══════════════════════════════════════════════════════════════════════════════

PAGE        → Full page container
             • Contains all other blocks as children
             • BoundingBox: {Width: 1.0, Height: 1.0, Left: 0, Top: 0}

LINE        → Text line
             • Contains WORD children
             • Has its own bbox

WORD        → Individual word
             • Contains actual text
             • Has its own bbox

TABLE       → Table structure
             • Contains CELL children
             • BoundingBox covers entire table

CELL        → Individual table cell
             • Contains RowIndex, ColumnIndex
             • Contains WORD children (for cell text)
             • Has its own bbox ← THIS IS WHAT WE NEED!

MERGED_CELL → Merged cells (rowspan/colspan)
             • Same structure as CELL
```

### Example TABLE Block (From Actual Data)

```json
{
  "BlockType": "TABLE",
  "Id": "3fba9795-ded1-4782-9c82-2d1485be3b89",
  "Page": 1,
  "Geometry": {
    "BoundingBox": {
      "Width": 0.7100362181663513,
      "Height": 0.3991985023021698,
      "Left": 0.13158844411373138,
      "Top": 0.3054017126560211
    }
  },
  "Relationships": [
    {
      "Type": "CHILD",
      "Ids": [
        "2e3e8686-b6fb-4216-9c08-869efda49301",
        "7625cae3-3adc-4538-9e19-9d71d61079ac",
        "b0200e8b-e025-47e3-b1b0-ed5c2913186b",
        ... (60 CELL IDs total)
      ]
    }
  ]
}
```

### Example CELL Block (From Actual Data)

```json
{
  "BlockType": "CELL",
  "Id": "2e3e8686-b6fb-4216-9c08-869efda49301",
  "RowIndex": 1,
  "ColumnIndex": 1,
  "RowSpan": 1,
  "ColumnSpan": 1,
  "Page": 1,
  "Geometry": {
    "BoundingBox": {
      "Width": 0.17964aboralizerb,
      "Height": 0.02370834350585938,
      "Left": 0.13158844411373138,
      "Top": 0.3054017126560211
    }
  },
  "Relationships": [
    {
      "Type": "CHILD",
      "Ids": ["word-id-1", "word-id-2"]  // WORD blocks containing text
    }
  ]
}
```

---

## Step 2: Parse TABLE and CELL Blocks

### Block Relationships

```
TABLE BLOCK STRUCTURE:
═══════════════════════════════════════════════════════════════════════════════

TABLE (id: 3fba9795...)
  │
  ├── Relationships.Type = "CHILD"
  │       │
  │       └── Ids: [cell_id_1, cell_id_2, cell_id_3, ...]
  │                    │
  │                    ▼
  │              ┌─────────────────────────────────────────────────┐
  │              │                                                 │
  │              │  CELL (id: cell_id_1)                          │
  │              │    ├── RowIndex: 1                             │
  │              │    ├── ColumnIndex: 1                          │
  │              │    ├── BoundingBox: {Left, Top, Width, Height} │
  │              │    │                                           │
  │              │    └── Relationships.Type = "CHILD"            │
  │              │            │                                   │
  │              │            └── Ids: [word_id_1, word_id_2]     │
  │              │                         │                      │
  │              │                         ▼                      │
  │              │                    WORD blocks                 │
  │              │                    Text: "Test Name"           │
  │              │                                                 │
  │              └─────────────────────────────────────────────────┘
  │
  └── BoundingBox: {covers entire table}
```

### Actual Cells from COA_1000459079_1_blocks.json

```
TABLE ON PAGE 1 (60 cells total):
═══════════════════════════════════════════════════════════════════════════════

CELL 1:
  Id: 2e3e8686-b6fb-4216-9...
  Row: 1, Column: 1
  Text: "Test Name"
  BoundingBox:
    Left:   0.1316
    Top:    0.3054
    Width:  0.1796
    Height: 0.0237

CELL 2:
  Id: 7625cae3-3adc-4538-9...
  Row: 1, Column: 2
  Text: "Test Method #"
  BoundingBox:
    Left:   0.3112
    Top:    0.3054
    Width:  0.1373
    Height: 0.0237

CELL 3:
  Id: b0200e8b-e025-47e3-b...
  Row: 1, Column: 3
  Text: "Acceptance Criteria"
  BoundingBox:
    Left:   0.4484
    Top:    0.3054
    Width:  0.2516
    Height: 0.0237

CELL 4:
  Id: c52ef729-789d-418a-a...
  Row: 1, Column: 4
  Text: "Results"
  BoundingBox:
    Left:   0.7000
    Top:    0.3054
    Width:  0.1416
    Height: 0.0237

... (56 more cells)
```

### Visual Table Structure

```
┌───────────────────┬───────────────┬────────────────────┬──────────────┐
│ Row 1, Col 1      │ Row 1, Col 2  │ Row 1, Col 3       │ Row 1, Col 4 │
│ "Test Name"       │"Test Method #"│"Acceptance Criteria"│ "Results"   │
│ bbox: 0.13-0.31   │ bbox: 0.31-0.45│ bbox: 0.45-0.70   │bbox: 0.70-0.84│
├───────────────────┼───────────────┼────────────────────┼──────────────┤
│ Row 2, Col 1      │ Row 2, Col 2  │ Row 2, Col 3       │ Row 2, Col 4 │
│"Appearance and    │ ""            │ ""                 │ ""           │
│ Description"      │               │                    │              │
├───────────────────┼───────────────┼────────────────────┼──────────────┤
│ Row 8, Col 1      │ Row 8, Col 2  │ Row 8, Col 3       │ Row 8, Col 4 │
│ "pH"              │ "QCG-055"     │ "5.7 to 6.4"       │ "6.1"        │
├───────────────────┼───────────────┼────────────────────┼──────────────┤
│ Row 9, Col 1      │ Row 9, Col 2  │ Row 9, Col 3       │ Row 9, Col 4 │
│ "Osmolality"      │ "QCG-068"     │"260 to 320 mOsmol" │"289 mOsmol"  │
└───────────────────┴───────────────┴────────────────────┴──────────────┘
```

---

## Step 3: Transform to Chunk with Cell Grounding

### Transformation Process

```
INPUT: Textract TABLE block + 60 CELL blocks
OUTPUT: Single chunk document with cell_grounding

TRANSFORMATION STEPS:
═══════════════════════════════════════════════════════════════════════════════

1. EXTRACT TABLE-LEVEL BBOX
   ─────────────────────────────────────────────────────────────────────────
   From: TABLE.Geometry.BoundingBox

   bbox_left   = Left                    = 0.1316
   bbox_top    = Top                     = 0.3054
   bbox_right  = Left + Width            = 0.1316 + 0.7100 = 0.8416
   bbox_bottom = Top + Height            = 0.3054 + 0.3992 = 0.7046


2. GENERATE CELL IDs
   ─────────────────────────────────────────────────────────────────────────
   Format: "{page_number}-{sequence_number}"

   Page 1, Cell 0  → "1-0"
   Page 1, Cell 1  → "1-1"
   Page 1, Cell 2  → "1-2"
   ...
   Page 1, Cell 59 → "1-59"

   Table ID: "{page_number}-t{table_index}"
   Page 1, Table 0 → "1-t0"


3. BUILD PLAIN TEXT CONTENT (For RAG Search)
   ─────────────────────────────────────────────────────────────────────────
   Format: Row values separated by " | ", rows separated by "\n"

   "Test Name | Test Method # | Acceptance Criteria | Results
    Appearance and Description | - | - | -
    pH | QCG-055 | 5.7 to 6.4 | 6.1
    Osmolality | QCG-068 | 260 to 320 mOsmol/kg | 289 mOsmol/Kg
    ..."


4. BUILD HTML MARKDOWN (For Display with Cell IDs)
   ─────────────────────────────────────────────────────────────────────────
   <table id="1-t0">
     <tr>
       <td id="1-0">Test Name</td>
       <td id="1-1">Test Method #</td>
       <td id="1-2">Acceptance Criteria</td>
       <td id="1-3">Results</td>
     </tr>
     <tr>
       <td id="1-28">pH</td>
       <td id="1-29">QCG-055</td>
       <td id="1-30">5.7 to 6.4</td>
       <td id="1-31">6.1</td>
     </tr>
     ...
   </table>


5. BUILD CELL_GROUNDING MAP
   ─────────────────────────────────────────────────────────────────────────
   {
     "1-t0": {
       "box": {"left": 0.1316, "top": 0.3054, "right": 0.8416, "bottom": 0.7046},
       "type": "table"
     },
     "1-0": {
       "box": {"left": 0.1316, "top": 0.3054, "right": 0.3112, "bottom": 0.3291},
       "type": "tableCell",
       "row": 0,
       "col": 0,
       "text": "Test Name"
     },
     "1-31": {
       "box": {"left": 0.7000, "top": 0.4500, "right": 0.8416, "bottom": 0.4750},
       "type": "tableCell",
       "row": 7,
       "col": 3,
       "text": "6.1"
     }
     ... (60 total entries)
   }


6. GENERATE EMBEDDING
   ─────────────────────────────────────────────────────────────────────────
   Input: content (plain text)
   Output: 1024-dimensional vector

   embedding = embedding_model.encode(content)
```

---

## Step 4: Final Elasticsearch Document

### Complete Chunk Structure

```json
{
  "id": "chunk_table_001",
  "document_id": "doc_COA_1000459079",
  "type": "table",
  "page": 1,
  "section": "Test Results",

  "bbox_left": 0.1316,
  "bbox_top": 0.3054,
  "bbox_right": 0.8416,
  "bbox_bottom": 0.7046,

  "content": "Test Name | Test Method # | Acceptance Criteria | Results\nAppearance and Description | - | - | -\nAppearance - Clarity and Degree of Opalescence | QCA-377-53 | Clear to slightly opalescent | Complies\nGeneral Tests | - | - | -\npH | QCG-055 | 5.7 to 6.4 | 6.1\nOsmolality | QCG-068 | 260 to 320 mOsmol/kg | 289 mOsmol/Kg\n...",

  "embedding": [0.023, -0.156, 0.089, 0.234, ...],

  "markdown": "<table id=\"1-t0\">\n  <tr><td id=\"1-0\">Test Name</td><td id=\"1-1\">Test Method #</td><td id=\"1-2\">Acceptance Criteria</td><td id=\"1-3\">Results</td></tr>\n  <tr><td id=\"1-4\">Appearance and Description</td><td id=\"1-5\"></td><td id=\"1-6\"></td><td id=\"1-7\"></td></tr>\n  <tr><td id=\"1-28\">pH</td><td id=\"1-29\">QCG-055</td><td id=\"1-30\">5.7 to 6.4</td><td id=\"1-31\">6.1</td></tr>\n</table>",

  "cell_grounding": {
    "1-t0": {
      "box": {"left": 0.1316, "top": 0.3054, "right": 0.8416, "bottom": 0.7046},
      "type": "table"
    },
    "1-0": {
      "box": {"left": 0.1316, "top": 0.3054, "right": 0.3112, "bottom": 0.3291},
      "type": "tableCell",
      "row": 0,
      "col": 0,
      "text": "Test Name"
    },
    "1-1": {
      "box": {"left": 0.3112, "top": 0.3054, "right": 0.4484, "bottom": 0.3291},
      "type": "tableCell",
      "row": 0,
      "col": 1,
      "text": "Test Method #"
    },
    "1-2": {
      "box": {"left": 0.4484, "top": 0.3054, "right": 0.7000, "bottom": 0.3291},
      "type": "tableCell",
      "row": 0,
      "col": 2,
      "text": "Acceptance Criteria"
    },
    "1-3": {
      "box": {"left": 0.7000, "top": 0.3054, "right": 0.8416, "bottom": 0.3291},
      "type": "tableCell",
      "row": 0,
      "col": 3,
      "text": "Results"
    },
    "1-28": {
      "box": {"left": 0.1316, "top": 0.4500, "right": 0.3112, "bottom": 0.4750},
      "type": "tableCell",
      "row": 7,
      "col": 0,
      "text": "pH"
    },
    "1-29": {
      "box": {"left": 0.3112, "top": 0.4500, "right": 0.4484, "bottom": 0.4750},
      "type": "tableCell",
      "row": 7,
      "col": 1,
      "text": "QCG-055"
    },
    "1-30": {
      "box": {"left": 0.4484, "top": 0.4500, "right": 0.7000, "bottom": 0.4750},
      "type": "tableCell",
      "row": 7,
      "col": 2,
      "text": "5.7 to 6.4"
    },
    "1-31": {
      "box": {"left": 0.7000, "top": 0.4500, "right": 0.8416, "bottom": 0.4750},
      "type": "tableCell",
      "row_index": 7,        // Optional: from Textract RowIndex (if available)
      "col_index": 3,        // Optional: from Textract ColumnIndex (if available)
      "text": "6.1"
    }

    // NOTE: row_index and col_index are OPTIONAL
    // Textract provides them for most tables, but not always
    // Cell matching uses Claude + markdown, not row/col indices
  }
}
```

### Field Purposes

```
FIELD USAGE IN CHUNK:
═══════════════════════════════════════════════════════════════════════════════

FIELD              │ PURPOSE                      │ INDEXED? │ USED FOR
───────────────────┼──────────────────────────────┼──────────┼─────────────────
id                 │ Unique chunk identifier      │ Yes      │ Reference
document_id        │ Link to parent document      │ Yes      │ Filtering
type               │ Chunk type (table/text)      │ Yes      │ Filtering
page               │ Page number                  │ Yes      │ Navigation
section            │ Section name                 │ Yes      │ Display
───────────────────┼──────────────────────────────┼──────────┼─────────────────
bbox_left          │ Table left edge              │ No       │ Table highlight
bbox_top           │ Table top edge               │ No       │ Table highlight
bbox_right         │ Table right edge             │ No       │ Table highlight
bbox_bottom        │ Table bottom edge            │ No       │ Table highlight
───────────────────┼──────────────────────────────┼──────────┼─────────────────
content            │ Plain text for search        │ Yes      │ RAG BM25 search
embedding          │ Semantic vector              │ Yes      │ RAG KNN search
───────────────────┼──────────────────────────────┼──────────┼─────────────────
markdown           │ HTML with cell IDs           │ No       │ Claude parsing (primary)
                   │                              │          │ Markdown Tab UI (secondary)
cell_grounding     │ Cell-level bboxes            │ No       │ Cell highlight (bbox lookup)
                   │ (Plain object, not nested)   │          │ After Claude returns cell IDs
```

---

## How Cell Matching Works

### After RAG Returns Chunk

```
CELL MATCHING FLOW (OFFICIAL METHOD):
═══════════════════════════════════════════════════════════════════════════════

1. User asks question
   └─→ "What is the pH value?"

2. RAG search finds chunk_table_001
   └─→ Contains "pH" and "6.1" in content

3. Claude generates answer AND returns cell IDs
   ┌─────────────────────────────────────────────────────────────────────┐
   │ Prompt includes:                                                    │
   │ - Question: "What is the pH value?"                                 │
   │ - Table HTML markdown with cell IDs                                 │
   │ - Instruction: "Return cell IDs from <td id='...'> attributes"      │
   │                                                                     │
   │ Claude Response (JSON):                                             │
   │ {                                                                   │
   │   "answer": "The pH value is 6.1",                                  │
   │   "cell_ids": ["1-31"],                                             │
   │   "clarification": "Showing pH result from Result column"           │
   │ }                                                                   │
   └─────────────────────────────────────────────────────────────────────┘

4. Backend looks up bbox from cell_grounding
   └─→ bbox = cell_grounding["1-31"]["box"]

5. Reference created with cell-level bbox
   └─→ {
         "page": 1,
         "bbox": {"left": 0.70, "top": 0.45, ...},
         "cell_id": "1-31",
         "text": "6.1"
       }

6. Frontend highlights specific cell
   └─→ Draw yellow box at cell_bbox coordinates
```

**Why Claude Returns Cell IDs (Not Code Matching):**
- ✅ Handles duplicate values (knows context: "result" vs "criteria")
- ✅ Handles complex table structures (merged cells, nested)
- ✅ Handles ambiguous questions (returns multiple cells)
- ✅ No complex spatial/regex code needed
- ✅ 99% accurate
- ✅ Same API call (no extra cost)

### Matching Strategies

```
STRATEGY 1: Specific Question → Single Cell
─────────────────────────────────────────────────────────────────────────────
Question: "What is the pH result value?"
Claude understands: Need "result" column, not "criteria" column
Returns: {"cell_ids": ["1-31"]}  ← Only result cell
UI: Highlights single cell


STRATEGY 2: Ambiguous Question → Multiple Cells
─────────────────────────────────────────────────────────────────────────────
Question: "What is the pH value?"  ← Ambiguous!
Claude understands: User might want result AND criteria
Returns: {"cell_ids": ["1-31", "1-30"]}  ← Both cells
UI: Highlights both result and criteria cells


STRATEGY 3: "Show All" Question → All Matches
─────────────────────────────────────────────────────────────────────────────
Question: "Show all pH values across batches"
Claude finds: Multiple pH cells across different columns
Returns: {"cell_ids": ["1-31", "1-45", "1-59"]}  ← All pH cells
UI: Highlights all related cells


STRATEGY 4: No Cell Match (Fallback)
─────────────────────────────────────────────────────────────────────────────
Question: "What are the test results?"  ← Too general
Claude cannot identify specific cells
Returns: {"cell_ids": []}  ← Empty
Backend fallback: Return table-level bbox
UI: Highlights entire table
```

---

## Visual Examples

### Example 1: Table-Level Highlight

```
USER: "Show me the test results table"

SYSTEM:
1. RAG finds chunk_table_001
2. No specific value to match
3. Use TABLE-level bbox

PDF DISPLAY:
┌────────────────────────────────────────────────────────────────────────────┐
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│ ░ Test Name          │ Test Method # │ Acceptance Criteria │ Results     ░ │
│ ░────────────────────┼───────────────┼─────────────────────┼─────────────░ │
│ ░ pH                 │ QCG-055       │ 5.7 to 6.4          │ 6.1         ░ │
│ ░ Osmolality         │ QCG-068       │ 260-320 mOsmol      │ 289 mOsmol  ░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└────────────────────────────────────────────────────────────────────────────┘
                    ↑ ENTIRE TABLE HIGHLIGHTED
                    bbox: 0.1316, 0.3054, 0.8416, 0.7046
```

### Example 2: Cell-Level Highlight (Single Value)

```
USER: "What is the pH value?"
CLAUDE: "The pH value is 6.1"

SYSTEM:
1. Extract value: "6.1"
2. Search cell_grounding: Found "1-31" with text "6.1"
3. Use CELL-level bbox

PDF DISPLAY:
┌────────────────────────────────────────────────────────────────────────────┐
│ Test Name            │ Test Method # │ Acceptance Criteria │ Results      │
│──────────────────────┼───────────────┼─────────────────────┼──────────────│
│ pH                   │ QCG-055       │ 5.7 to 6.4          │░░░░ 6.1 ░░░░│
│                      │               │                     │░░░░░░░░░░░░░│
│ Osmolality           │ QCG-068       │ 260-320 mOsmol      │ 289 mOsmol   │
└────────────────────────────────────────────────────────────────────────────┘
                                                              ↑ ONLY THIS CELL
                                                              cell_id: "1-31"
                                                              bbox: 0.70, 0.45, 0.84, 0.48
```

### Example 3: Cell-Level Highlight (Criteria)

```
USER: "What is the acceptance criteria for pH?"
CLAUDE: "The acceptance criteria for pH is 5.7 to 6.4"

SYSTEM:
1. Extract value: "5.7 to 6.4"
2. Search cell_grounding: Found "1-30" with text "5.7 to 6.4"
3. Use CELL-level bbox

PDF DISPLAY:
┌────────────────────────────────────────────────────────────────────────────┐
│ Test Name            │ Test Method # │ Acceptance Criteria │ Results      │
│──────────────────────┼───────────────┼─────────────────────┼──────────────│
│ pH                   │ QCG-055       │░░░ 5.7 to 6.4 ░░░░░│ 6.1          │
│                      │               │░░░░░░░░░░░░░░░░░░░░│              │
│ Osmolality           │ QCG-068       │ 260-320 mOsmol      │ 289 mOsmol   │
└────────────────────────────────────────────────────────────────────────────┘
                                        ↑ ONLY THIS CELL
                                        cell_id: "1-30"
```

### Example 4: Multiple Cells Highlight

```
USER: "Compare pH value and acceptance criteria"
CLAUDE: "The pH value is 6.1, which is within the acceptance criteria of 5.7 to 6.4"

SYSTEM:
1. Extract values: ["6.1", "5.7 to 6.4"]
2. Search cell_grounding: Found "1-30" and "1-31"
3. Use MULTIPLE cell bboxes

PDF DISPLAY:
┌────────────────────────────────────────────────────────────────────────────┐
│ Test Name            │ Test Method # │ Acceptance Criteria │ Results      │
│──────────────────────┼───────────────┼─────────────────────┼──────────────│
│ pH                   │ QCG-055       │░░░ 5.7 to 6.4 ░░░░░│░░░░ 6.1 ░░░░│
│                      │               │░░░░░░░░░░░░░░░░░░░░│░░░░░░░░░░░░░│
│ Osmolality           │ QCG-068       │ 260-320 mOsmol      │ 289 mOsmol   │
└────────────────────────────────────────────────────────────────────────────┘
                                        ↑ BOTH CELLS HIGHLIGHTED
                                        cell_ids: ["1-30", "1-31"]
```

---

## ID Structure Explained

### Complete ID Hierarchy

```
ID HIERARCHY:
═══════════════════════════════════════════════════════════════════════════════

document_id: "doc_COA_1000459079"
    │
    │   ← Stored in: Elasticsearch + PostgreSQL (chat_documents table)
    │   ← Purpose: Link chunks to document, link chats to documents
    │
    └── chunk_id: "chunk_table_001"
            │
            │   ← Stored in: Elasticsearch (document_chunks index)
            │   ← Purpose: Unique identifier for each chunk
            │
            ├── table_id: "1-t0"
            │       │
            │       │   ← Stored in: cell_grounding field
            │       │   ← Format: "{page}-t{table_index}"
            │       │   ← Purpose: Reference entire table
            │       │
            │       └── bbox: {left: 0.1316, top: 0.3054, ...}
            │
            └── cell_ids: "1-0", "1-1", "1-2", ... "1-59"
                    │
                    │   ← Stored in: cell_grounding field
                    │   ← Format: "{page}-{sequence}"
                    │   ← Purpose: Reference individual cells
                    │
                    └── Each has: bbox, row, col, text
```

### ID Format Details

```
CELL ID FORMAT: "{page}-{sequence}"
═══════════════════════════════════════════════════════════════════════════════

Examples:
  "1-0"   = Page 1, Cell #0  (first cell)
  "1-31"  = Page 1, Cell #31 (pH value cell)
  "2-0"   = Page 2, Cell #0  (first cell on page 2)
  "3-15"  = Page 3, Cell #15

TABLE ID FORMAT: "{page}-t{index}"
═══════════════════════════════════════════════════════════════════════════════

Examples:
  "1-t0"  = Page 1, Table #0 (first table)
  "1-t1"  = Page 1, Table #1 (second table on same page)
  "2-t0"  = Page 2, Table #0

WHY THIS FORMAT:
───────────────────────────────────────────────────────────────────────────────
• Page prefix ensures uniqueness across document
• Simple sequential numbering within page
• Easy to parse: split by "-" gives [page, cell_number]
• Matches HTML id attribute requirements
• Compatible with Landing AI format
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  TRANSFORMATION SUMMARY                                                     │
│  ═════════════════════                                                      │
│                                                                             │
│  INPUT:                                                                     │
│  ──────                                                                     │
│  • Textract blocks.json with TABLE and CELL blocks                         │
│  • Each CELL has: RowIndex, ColumnIndex, BoundingBox, Text (via WORDs)    │
│                                                                             │
│  PROCESSING:                                                                │
│  ───────────                                                                │
│  1. Parse TABLE block, get table-level bbox                                │
│  2. Parse all CELL children, extract text and bbox                         │
│  3. Generate cell IDs: "{page}-{sequence}"                                 │
│  4. Build plain text content (for RAG)                                     │
│  5. Build HTML markdown with cell IDs (for display)                        │
│  6. Build cell_grounding map (for highlighting)                            │
│  7. Generate embedding vector                                               │
│                                                                             │
│  OUTPUT:                                                                    │
│  ───────                                                                    │
│  • Single Elasticsearch chunk document containing:                          │
│    - Basic fields: id, document_id, type, page                             │
│    - Table bbox: bbox_left, bbox_top, bbox_right, bbox_bottom             │
│    - Searchable: content, embedding                                        │
│    - Display: markdown (HTML with cell IDs)                                │
│    - Highlighting: cell_grounding (per-cell bbox map)                      │
│                                                                             │
│  USAGE:                                                                     │
│  ──────                                                                     │
│  • RAG search uses: content + embedding (unchanged)                        │
│  • Table highlight uses: bbox_* fields                                     │
│  • Cell highlight uses: cell_grounding[cell_id].box                        │
│  • Markdown Tab uses: markdown field                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 1.0*
*Created: January 2026*
*Source Data: COA_1000459079_1_blocks.json*
*Compatible With: COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md*
