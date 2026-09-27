# Complete Chunking Strategy - TABLE + TEXT Blocks (LAYOUT-Based)

> **Purpose:** Unified strategy for transforming ALL Textract blocks into searchable chunks
> **Covers:** TABLE blocks → table chunks | LAYOUT blocks → text chunks (with LINE children)
> **Implementation:** Uses Textract LAYOUT feature for semantic region detection
> **Created:** January 2026
> **Updated:** January 23, 2026 - Changed to LAYOUT-based chunking approach

---

## Table of Contents

1. [Overview](#overview)
2. [Current Problem](#current-problem)
3. [Solution: Block-Based Chunking](#solution-block-based-chunking)
4. [Comparison: Text vs Table Chunks](#comparison-text-vs-table-chunks)
5. [Complete Implementation Flow](#complete-implementation-flow)
6. [Chunk Type Detection in RAG](#chunk-type-detection-in-rag)
7. [Implementation Checklist](#implementation-checklist)

---

## Overview

### What We're Replacing

```python
# ❌ CURRENT (app.py lines 1270-1520):
# Loses ALL structure!

text = ""
for block in blocks:
    if block["BlockType"] == "LINE":
        text += block["Text"] + "\n"

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
chunks = text_splitter.split_text(text)

# Result: Generic text chunks, no bbox, no structure
```

### What We're Building

```python
# ✅ NEW (LAYOUT-Based):
# Uses AWS ML for semantic region detection!

def chunk_textract_blocks(blocks, document_id, process_id):
    chunks = []

    # TABLE blocks → Table chunks (with cell_grounding)
    for table in find_tables(blocks):
        chunk = build_table_chunk(table, blocks, document_id, process_id)
        chunks.append(chunk)

    # LAYOUT blocks → Text chunks (AWS ML detected regions)
    # LAYOUT feature must be enabled: FeatureTypes=["TABLES", "LAYOUT"]
    layout_regions = extract_regions_from_layout_blocks(blocks, exclude_table_lines=True)
    for region in layout_regions:
        chunk = build_text_chunk(region, document_id, process_id)
        chunks.append(chunk)

    return chunks

# Result: Structured chunks with bbox + layout_type for highlighting
# layout_type examples: "SECTION_HEADER", "TEXT", "FOOTER", "TITLE"
```

---

## Current Problem

### Issue with RecursiveCharacterTextSplitter

```
PROBLEM 1: Loses Structure
═══════════════════════════════════════════════════════════════════════════════

Original Textract Output:
├─ TABLE block (entire table)
│   ├─ CELL blocks (individual cells with row/col/bbox)
│   │   ├─ CELL 1: "pH" (Test Name column)
│   │   ├─ CELL 2: "6.1" (Result column)
│   │   └─ CELL 3: "5.7 to 6.4" (Criteria column)
│   └─ Table structure preserved!
│
└─ LINE blocks (text lines)
    ├─ LINE 1: "Batch #: 1000459079"
    ├─ LINE 2: "Production Date: 17 Sept 2021"
    └─ Spatial info preserved!

After RecursiveCharacterTextSplitter:
├─ chunk_001: "...pH 6.1 5.7 to 6.4..."  ← Mixed up!
├─ chunk_002: "...Batch #: 1000459..."   ← Arbitrary split!
└─ chunk_003: "...079 Production Dat..."  ← Word broken!

❌ Table structure LOST
❌ Cell boundaries LOST
❌ Spatial information LOST
❌ Cannot highlight specific cells
```

```
PROBLEM 2: Cannot Highlight
═══════════════════════════════════════════════════════════════════════════════

User: "What is the pH result value?"

Current System:
1. RAG finds chunk: "...pH 6.1 5.7 to 6.4..."
2. Claude answers: "The pH result is 6.1"
3. ❌ No bbox information!
4. ❌ No cell ID information!
5. ❌ Cannot show [Page 2] button
6. ❌ Cannot highlight specific cell

Desired System:
1. RAG finds TABLE chunk with cell_grounding
2. Claude answers: "The pH result is 6.1"
3. Claude returns: {"cell_ids": ["1-29"]}
4. ✅ Lookup bbox from cell_grounding["1-29"]
5. ✅ Show [Page 2] button
6. ✅ Highlight specific cell when clicked
```

---

## Solution: Block-Based Chunking

### Two Transformation Strategies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  TEXTRACT BLOCKS (1591 total in COA document)                              │
│  ═══════════════════════════════════════════                                │
│                                                                             │
│  ┌──────────────────────────┐         ┌─────────────────────────────────┐  │
│  │   TABLE BLOCKS (6)       │         │   LINE BLOCKS (367)             │  │
│  │   ├─ CELL blocks (222)   │         │   (Text lines from document)    │  │
│  │   ├─ MERGED_CELL (10)    │         │                                 │  │
│  │   └─ TABLE_TITLE (2)     │         │   Exclude lines inside tables!  │  │
│  └──────────────────────────┘         └─────────────────────────────────┘  │
│           │                                         │                       │
│           │ TRANSFORM                               │ TRANSFORM             │
│           ▼                                         ▼                       │
│  ┌──────────────────────────┐         ┌─────────────────────────────────┐  │
│  │   TABLE CHUNKS (6)       │         │   TEXT CHUNKS (20-40)           │  │
│  │                          │         │                                 │  │
│  │   type: "table"          │         │   type: "text"                  │  │
│  │   content: Plain text    │         │   content: Combined lines       │  │
│  │   markdown: HTML         │         │   markdown: null                │  │
│  │   cell_grounding: {...}  │         │   cell_grounding: null          │  │
│  │   bbox_*: Table bbox     │         │   bbox_*: Region bbox           │  │
│  │   embedding: [...]       │         │   embedding: [...]              │  │
│  └──────────────────────────┘         └─────────────────────────────────┘  │
│           │                                         │                       │
│           └─────────────────┬───────────────────────┘                       │
│                             ▼                                               │
│                   ┌─────────────────────┐                                   │
│                   │  ELASTICSEARCH      │                                   │
│                   │  (26-46 chunks)     │                                   │
│                   │                     │                                   │
│                   │  - Searchable       │                                   │
│                   │  - Highlightable    │                                   │
│                   │  - Structured       │                                   │
│                   └─────────────────────┘                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Comparison: Text vs Table Chunks

### Side-by-Side Comparison

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│       TEXT CHUNKS                   │       TABLE CHUNKS                  │
│       (from LINE blocks)            │       (from TABLE blocks)           │
├─────────────────────────────────────┼─────────────────────────────────────┤
│                                     │                                     │
│  SOURCE:                            │  SOURCE:                            │
│  ──────                             │  ──────                             │
│  367 LINE blocks                    │  6 TABLE blocks                     │
│  (individual text lines)            │  (with 222 CELL children)           │
│                                     │                                     │
│  GROUPING:                          │  GROUPING:                          │
│  ────────                           │  ────────                           │
│  Group by LAYOUT blocks:            │  1 chunk per TABLE:                 │
│  - AWS ML semantic detection        │  - No splitting needed              │
│  - LAYOUT_SECTION_HEADER, etc.      │  - Already structured               │
│  Result: 20-40 text chunks          │  Result: 6 table chunks             │
│                                     │                                     │
│  CONTENT:                           │  CONTENT:                           │
│  ───────                            │  ───────                            │
│  "Batch #: 1000459079               │  "Test Name | Result | Criteria     │
│   Production Date: 17 Sept 2021     │   pH | 6.1 | 5.7 to 6.4            │
│   Storage: - 40 °C ± 10 °C"         │   Osmolality | 289 | 260-320"      │
│                                     │                                     │
│  BBOX:                              │  BBOX:                              │
│  ────                               │  ────                               │
│  Region-level (min/max of lines):   │  Table-level (entire table):        │
│  {                                  │  {                                  │
│    left: 0.1234,                    │    left: 0.1316,                    │
│    top: 0.2173,                     │    top: 0.3054,                     │
│    right: 0.7815,                   │    right: 0.8416,                   │
│    bottom: 0.2742                   │    bottom: 0.7046                   │
│  }                                  │  }                                  │
│                                     │                                     │
│  MARKDOWN:                          │  MARKDOWN:                          │
│  ────────                           │  ────────                           │
│  null                               │  "<table id='1-t0'>                 │
│  (not needed)                       │     <tr>                            │
│                                     │       <td id='1-29'>6.1</td>        │
│                                     │     </tr>                           │
│                                     │   </table>"                         │
│                                     │                                     │
│  CELL_GROUNDING:                    │  CELL_GROUNDING:                    │
│  ──────────────                     │  ──────────────                     │
│  null                               │  {                                  │
│  (not needed)                       │    "1-29": {                        │
│                                     │      "box": {                       │
│                                     │        "left": 0.31,                │
│                                     │        "top": 0.45, ...             │
│                                     │      },                             │
│                                     │      "text": "6.1",                 │
│                                     │      "type": "tableCell"            │
│                                     │    }                                │
│                                     │  }                                  │
│                                     │                                     │
│  HIGHLIGHTING:                      │  HIGHLIGHTING:                      │
│  ────────────                       │  ────────────                       │
│  ✅ Direct bbox                     │  ⚠️ Claude finds cells:             │
│  - Use bbox_* fields directly       │  - Send markdown to Claude          │
│  - No extra processing              │  - Claude returns cell_ids          │
│  - Instant (< 1ms)                  │  - Lookup from cell_grounding       │
│  - 100% accurate                    │  - Takes 1-2s                       │
│  - Free                             │  - 99% accurate                     │
│                                     │  - ~$0.01/question                  │
│                                     │                                     │
│  EXAMPLE QUESTION:                  │  EXAMPLE QUESTION:                  │
│  ────────────────                   │  ────────────────                   │
│  "What is the batch number?"        │  "What is the pH result?"           │
│                                     │                                     │
│  USER SEES:                         │  USER SEES:                         │
│  ─────────                          │  ─────────                          │
│  [Bot] Batch is 1000459079          │  [Bot] pH result is 6.1             │
│        📍 [Page 1]                  │        📍 [Page 2]                  │
│                                     │                                     │
│  ON CLICK:                          │  ON CLICK:                          │
│  ───────                            │  ───────                            │
│  Highlights ENTIRE region           │  Highlights SPECIFIC CELL           │
│  (header section)                   │  (only "6.1" cell)                  │
│                                     │                                     │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Chunk Structure Examples

#### Text Chunk (JSON)

```json
{
  "id": "chunk_text_001",
  "document_id": "doc_COA_1000459079",
  "process_id": "uuid-abc-123",
  "type": "text",
  "layout_type": "SECTION_HEADER",
  "page": 1,

  "bbox_left": 0.1359,
  "bbox_top": 0.2173,
  "bbox_right": 0.7815,
  "bbox_bottom": 0.2742,

  "content": "AbbVie Material #: 20029070\nBatch #: 1000459079\nProduction Date: 17 Sept 2021\nStorage: - 40 °C ± 10 °C\nRetest Date: 17 Sept 2023",

  "embedding": [0.023, -0.156, ...],

  "markdown": null,
  "cell_grounding": null,

  "filename": "COA_1000459079_1.pdf",
  "chunk_index": 0,
  "total_chunks": 28
}
```

#### Table Chunk (JSON)

```json
{
  "id": "chunk_table_001",
  "document_id": "doc_COA_1000459079",
  "process_id": "uuid-abc-123",
  "type": "table",
  "page": 2,

  "bbox_left": 0.1316,
  "bbox_top": 0.3054,
  "bbox_right": 0.8416,
  "bbox_bottom": 0.7046,

  "content": "Test Name | Test Method # | Acceptance Criteria | Results\nAppearance and Description | - | - | -\npH | QCG-055 | 5.7 to 6.4 | 6.1\nOsmolality | QCG-068 | 260 to 320 mOsmol/kg | 289 mOsmol/Kg",

  "embedding": [0.023, -0.156, ...],

  "markdown": "<table id=\"1-t0\">\n  <tr><td id=\"1-0\">Test Name</td><td id=\"1-1\">Test Method #</td><td id=\"1-2\">Acceptance Criteria</td><td id=\"1-3\">Results</td></tr>\n  <tr><td id=\"1-28\">pH</td><td id=\"1-29\">QCG-055</td><td id=\"1-30\">5.7 to 6.4</td><td id=\"1-31\">6.1</td></tr>\n</table>",

  "cell_grounding": {
    "1-t0": {
      "box": {"left": 0.1316, "top": 0.3054, "right": 0.8416, "bottom": 0.7046},
      "type": "table"
    },
    "1-29": {
      "box": {"left": 0.3112, "top": 0.4500, "right": 0.4484, "bottom": 0.4750},
      "text": "QCG-055",
      "type": "tableCell",
      "row": 7,
      "col": 1
    },
    "1-31": {
      "box": {"left": 0.7000, "top": 0.4500, "right": 0.8416, "bottom": 0.4750},
      "text": "6.1",
      "type": "tableCell",
      "row": 7,
      "col": 3
    }
  },

  "filename": "COA_1000459079_1.pdf",
  "chunk_index": 5,
  "total_chunks": 28
}
```

---

## Complete Implementation Flow

### Main Chunking Function

```python
def chunk_textract_blocks(
    blocks: list[dict],
    document_id: str,
    process_id: str,
    filename: str
) -> list[dict]:
    """
    Complete transformation: Textract blocks → Elasticsearch chunks

    Returns list of chunks (both table and text types)
    """

    chunks = []
    chunk_index = 0

    # ═══════════════════════════════════════════════════════════════════
    # STEP 1: Transform TABLE blocks → Table chunks
    # ═══════════════════════════════════════════════════════════════════
    print("Processing TABLE blocks...")

    table_blocks = [b for b in blocks if b.get('BlockType') == 'TABLE']
    print(f"Found {len(table_blocks)} TABLE blocks")

    for table_block in table_blocks:
        table_chunk = build_table_chunk(
            table_block,
            blocks,  # Need all blocks to lookup CELL children
            document_id,
            process_id,
            chunk_index
        )
        chunks.append(table_chunk)
        chunk_index += 1

    # ═══════════════════════════════════════════════════════════════════
    # STEP 2: Transform LAYOUT blocks → Text chunks (AWS ML semantic regions)
    # ═══════════════════════════════════════════════════════════════════
    print("Processing LAYOUT blocks...")

    # Extract semantic regions using LAYOUT feature
    # LAYOUT blocks reference child LINE blocks via Relationships
    text_regions = extract_regions_from_layout_blocks(
        blocks,
        exclude_table_lines=True  # Skip lines that are inside TABLE blocks
    )
    print(f"Found {len(text_regions)} LAYOUT semantic regions")

    # Convert each region to a chunk
    for region in text_regions:
        text_chunk = build_text_chunk(
            region,
            document_id,
            process_id,
            chunk_index
        )
        chunks.append(text_chunk)
        chunk_index += 1

    # ═══════════════════════════════════════════════════════════════════
    # STEP 3: Generate embeddings for all chunks
    # ═══════════════════════════════════════════════════════════════════
    print("Generating embeddings...")

    for chunk in chunks:
        chunk['embedding'] = generate_embedding(chunk['content'])

    # ═══════════════════════════════════════════════════════════════════
    # STEP 4: Add global metadata
    # ═══════════════════════════════════════════════════════════════════
    total_chunks = len(chunks)
    for chunk in chunks:
        chunk['total_chunks'] = total_chunks
        chunk['filename'] = filename

    print(f"Created {total_chunks} chunks ({len(table_blocks)} table, {len(text_regions)} LAYOUT-based text)")

    return chunks
```

### Integration with app.py

```python
# app.py lines 1270-1520

# ❌ OLD CODE (REMOVE):
# text = ""
# for block in blocks:
#     if block["BlockType"] == "LINE":
#         text += block["Text"] + "\n"
#
# text_splitter = RecursiveCharacterTextSplitter(
#     chunk_size=1000,
#     chunk_overlap=200
# )
# chunks = text_splitter.split_text(text)

# ✅ NEW CODE (ADD):
from services.textract_parser import parse_textract_blocks
from services.chunk_transformer import chunk_textract_blocks

# Load Textract blocks
blocks_file = f"{temp_dir}/{filename}_blocks.json"
with open(blocks_file, 'r') as f:
    responses = json.load(f)

# Extract all blocks from response array
all_blocks = []
for response in responses:
    if 'Blocks' in response:
        all_blocks.extend(response['Blocks'])

# Transform blocks into typed chunks
chunks = chunk_textract_blocks(
    all_blocks,
    document_id=document_id,
    process_id=process_id,
    filename=os.path.basename(filename)
)

# Upload to Elasticsearch/Iliad
for chunk in chunks:
    iliad_service.upload_chunk(
        source_name=f"coa_{username}",
        chunk=chunk
    )
```

---

## Chunk Type Detection in RAG

### Automatic Detection and Handling

```python
# Backend: app.py RAG endpoint

@app.post("/api/chat/coa-rag/{process_id}")
async def chat_with_coa(process_id: str, request: Request):
    data = await request.json()
    question = data["question"]

    # Step 1: RAG search (returns mixed chunk types)
    chunks = hybrid_search(question, process_id, top_k=5)

    # Step 2: Process each chunk based on type
    references = []

    for chunk in chunks:
        if chunk["type"] == "text":
            # ═══════════════════════════════════════════════════════════
            # TEXT CHUNK: Direct bbox highlighting
            # ═══════════════════════════════════════════════════════════
            references.append({
                "page": chunk["page"],
                "bbox": {
                    "left": chunk["bbox_left"],
                    "top": chunk["bbox_top"],
                    "right": chunk["bbox_right"],
                    "bottom": chunk["bbox_bottom"]
                },
                "type": "text",
                "content": chunk["content"][:100] + "..."
            })

        elif chunk["type"] == "table":
            # ═══════════════════════════════════════════════════════════
            # TABLE CHUNK: Claude finds specific cells
            # ═══════════════════════════════════════════════════════════

            # Call Claude with markdown HTML
            claude_response = call_claude_for_cells(
                markdown=chunk["markdown"],
                question=question
            )

            # Get cell IDs from Claude
            cell_ids = claude_response.get("cell_ids", [])

            # Lookup bbox for each cell
            for cell_id in cell_ids:
                if cell_id in chunk["cell_grounding"]:
                    cell_data = chunk["cell_grounding"][cell_id]
                    references.append({
                        "page": chunk["page"],
                        "bbox": cell_data["box"],
                        "type": "table",
                        "cell_id": cell_id,
                        "text": cell_data.get("text", "")
                    })

    # Step 3: Generate answer with Claude
    context = "\n".join([c["content"] for c in chunks])
    answer = call_claude(question, context)

    return {
        "answer": answer,
        "references": references
    }


def call_claude_for_cells(markdown: str, question: str) -> dict:
    """
    Ask Claude to find cell IDs from markdown HTML.
    """
    prompt = f"""You are analyzing a table from a Certificate of Analysis.

TABLE HTML (with cell IDs):
{markdown}

USER QUESTION: {question}

Return JSON with:
- answer: Your answer text
- cell_ids: Array of cell IDs from <td id="...">

Example: {{"answer": "The pH is 6.1", "cell_ids": ["1-31"]}}
"""

    response = iliad_service.call_claude(prompt)
    return json.loads(response)
```

### Frontend: Single Handler for Both Types

```typescript
// frontend/src/app/chat/page.tsx

function handleReferenceClick(reference: Reference) {
  // Navigate to page
  setCurrentPage(reference.page);

  // Load page if not cached (lazy loading)
  if (!pageCache[reference.page]) {
    loadPageImage(reference.page);
  }

  // Draw highlight based on type
  if (reference.type === "text") {
    // Text chunk: Direct bbox
    drawHighlight(reference.bbox, "yellow");
  } else if (reference.type === "table") {
    // Table cell: Cell-level bbox
    drawHighlight(reference.bbox, "yellow");

    // Optionally show cell info
    if (reference.text) {
      showTooltip(reference.text, reference.cell_id);
    }
  }

  // Scroll into view
  scrollToBbox(reference.bbox);
}
```

---

## Implementation Checklist

### Phase 1: Create Core Modules

```
[ ] Create backend/services/textract_parser.py
    [ ] find_blocks_by_type(blocks, block_type)
    [ ] parse_table_structure(table_block, all_blocks)
    [ ] parse_cell_children(cell_block, all_blocks)
    [ ] extract_word_text(word_ids, blocks_by_id)

[ ] Create backend/services/chunk_transformer.py
    [ ] chunk_textract_blocks(blocks, document_id, process_id, filename)
    [ ] build_table_chunk(table_block, all_blocks, ...)
    [ ] build_text_chunk(region, document_id, process_id, ...)
    [ ] group_lines_into_regions(line_blocks, table_blocks, gap_threshold)
    [ ] is_line_in_table(line_block, table_blocks)
    [ ] generate_embedding(content)
```

### Phase 2: Update app.py

```
[ ] backend/app.py lines 1270-1520 (RAG indexing)
    [ ] Remove RecursiveCharacterTextSplitter code
    [ ] Add import for chunk_textract_blocks
    [ ] Load blocks from blocks.json (handle array structure)
    [ ] Call chunk_textract_blocks()
    [ ] Upload chunks to Iliad with new schema

[ ] backend/app.py lines 2609-2820 (RAG chat endpoint)
    [ ] Add chunk type detection (if type == "text" vs "table")
    [ ] For text chunks: Use direct bbox
    [ ] For table chunks: Call Claude for cell IDs
    [ ] Build references array with both types
```

### Phase 3: Update Elasticsearch Schema

```
[ ] backend/Ruben_AI_Chatbot-main/dependency/services/iliad_service.py
    [ ] Update create_source() custom fields:
        [ ] Add type field (text, table)
        [ ] Add markdown field (not indexed)
        [ ] Add cell_grounding field (object, not indexed)
        [ ] Add bbox_left, bbox_top, bbox_right, bbox_bottom (float)
    [ ] Update upload_chunk() to accept full chunk dict
```

### Phase 4: Test with Real Data

```
[ ] Test TABLE chunking:
    [ ] Process COA_1000459079_1_blocks.json
    [ ] Verify 6 table chunks created
    [ ] Check cell_grounding structure
    [ ] Verify markdown HTML has cell IDs

[ ] Test TEXT chunking:
    [ ] Process same blocks.json
    [ ] Verify 20-40 text chunks created
    [ ] Check region grouping (gap threshold works)
    [ ] Verify lines inside tables are excluded

[ ] Test RAG Q&A:
    [ ] Ask text question: "What is the batch number?"
    [ ] Verify direct bbox highlighting works
    [ ] Ask table question: "What is the pH result?"
    [ ] Verify Claude returns cell IDs
    [ ] Verify cell highlighting works
```

### Phase 5: Update Documentation

```
[ ] Update COMPLETE_RAG_FLOW_WITH_BBOX_furtherhighlight.md
    [ ] Add section on chunk type detection
    [ ] Update examples with both text and table

[ ] Update RAG_QUERY_EXTRACTION_STRATEGY.md
    [ ] Confirm strategy works for both chunk types

[ ] Update ACTUAL_ERD.md
    [ ] Verify chunk schema matches implementation
```

---

## Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  COMPLETE CHUNKING STRATEGY                                                 │
│  ══════════════════════════                                                 │
│                                                                             │
│  GOAL:                                                                      │
│  ────                                                                       │
│  Replace RecursiveCharacterTextSplitter with block-based chunking that      │
│  preserves Textract structure and enables precise highlighting.             │
│                                                                             │
│  APPROACH:                                                                  │
│  ────────                                                                   │
│  • TABLE blocks → Table chunks (6 chunks)                                   │
│    - With cell_grounding for cell-level highlighting                       │
│    - With markdown HTML for Claude parsing                                  │
│    - Claude returns cell IDs for precise highlighting                       │
│                                                                             │
│  • LAYOUT blocks → Text chunks (20-40 chunks)                               │
│    - AWS ML semantic region detection (SECTION_HEADER, TEXT, FOOTER, etc.) │
│    - LAYOUT blocks reference child LINE blocks via Relationships            │
│    - With region-level bbox for direct highlighting                         │
│    - No Claude call needed (instant highlighting)                           │
│                                                                             │
│  RESULT:                                                                    │
│  ──────                                                                     │
│  • 26-46 structured chunks per COA document                                 │
│  • All chunks searchable via RAG (content + embedding)                      │
│  • All chunks highlightable (bbox for text, cell_grounding for tables)     │
│  • Automatic type detection (no user intervention)                          │
│                                                                             │
│  BENEFITS:                                                                  │
│  ────────                                                                   │
│  ✅ Preserves Textract structure                                            │
│  ✅ Enables cell-level highlighting for tables                              │
│  ✅ Enables region-level highlighting for text                              │
│  ✅ Same RAG search (content + embedding)                                   │
│  ✅ Automatic handling based on chunk type                                  │
│  ✅ User-friendly (no special commands needed)                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Document Version: 1.0*
*Created: January 22, 2026*
*Combines: TRANSFORMATION_OF_CELL_GROUNDING.md + TRANSFORMATION_OF_LINE_BLOCKS.md*
*Implementation Ready: Yes*
