"""
Show EXACTLY how markdown cell IDs match with cell_grounding
This is what the agent sees and how it references cells for highlighting
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from weaviate_indexer import WeaviateIndexer

def main():
    indexer = WeaviateIndexer()
    process_id = 'layout-full-test-c2d0b134'

    # Get a table chunk with more data (the test results table)
    results = indexer.search_chunks(
        query="Appearance Identification Assay test results",
        process_id=process_id,
        limit=5
    )

    # Find the bigger table (page 2 has the full test results)
    table_chunk = None
    for r in results:
        if r.get('chunk_type') == 'table' and r.get('page') == 2:
            table_chunk = r
            break

    if not table_chunk:
        # Try any table
        for r in results:
            if r.get('chunk_type') == 'table':
                table_chunk = r
                break

    if not table_chunk:
        print("No table chunk found")
        return

    print("=" * 80)
    print(f"TABLE CHUNK FROM PAGE {table_chunk.get('page')}")
    print("=" * 80)

    # Get markdown and cell_grounding
    markdown = table_chunk.get('markdown', '')
    cell_grounding = json.loads(table_chunk.get('cell_grounding', '{}'))

    print("\n" + "=" * 80)
    print("1. MARKDOWN (what Claude/Agent sees)")
    print("=" * 80)
    # Clean for console output
    markdown_clean = markdown[:1500].encode('ascii', 'replace').decode()
    print(markdown_clean)
    if len(markdown) > 1500:
        print("\n... (truncated)")

    print("\n" + "=" * 80)
    print("2. CELL_GROUNDING (bbox lookup map)")
    print("=" * 80)
    print(f"\nTotal cells: {len(cell_grounding)}")

    # Show a few cells from different rows
    print("\nShowing cells from rows 1, 2, 3, 4:")
    shown_rows = set()
    for cell_id, cell_data in cell_grounding.items():
        row = cell_data['row']
        if row <= 4 and row not in shown_rows:
            shown_rows.add(row)
            bbox = cell_data['bbox']
            text = cell_data['text'][:50].encode('ascii', 'replace').decode()
            print(f"\n  '{cell_id}': {{")
            print(f"    text: \"{text}\",")
            print(f"    row: {row}, col: {cell_data['col']},")
            print(f"    bbox: {{left: {bbox['left']:.4f}, top: {bbox['top']:.4f}, width: {bbox['width']:.4f}, height: {bbox['height']:.4f}}}")
            print(f"  }}")

    print("\n" + "=" * 80)
    print("3. HOW THEY MATCH - THE KEY INSIGHT")
    print("=" * 80)

    # Find a specific cell to demonstrate
    # Look for a result value like "Complies" or a percentage
    example_cell_id = None
    example_cell = None
    for cell_id, cell_data in cell_grounding.items():
        text = cell_data['text'].lower()
        if 'complies' in text or '%' in cell_data['text']:
            example_cell_id = cell_id
            example_cell = cell_data
            break

    if not example_cell:
        # Just use any cell from row 2+
        for cell_id, cell_data in cell_grounding.items():
            if cell_data['row'] >= 2:
                example_cell_id = cell_id
                example_cell = cell_data
                break

    if example_cell:
        print(f"""
    EXAMPLE: Cell '{example_cell_id}'

    IN MARKDOWN (Agent sees this):
    ─────────────────────────────────────────────────────────────
    <td id='{example_cell_id}'>{example_cell['text']}</td>
    ─────────────────────────────────────────────────────────────

    IN CELL_GROUNDING (For highlighting):
    ─────────────────────────────────────────────────────────────
    "{example_cell_id}": {{
        "text": "{example_cell['text']}",
        "row": {example_cell['row']},
        "col": {example_cell['col']},
        "bbox": {{
            "left": {example_cell['bbox']['left']:.4f},
            "top": {example_cell['bbox']['top']:.4f},
            "width": {example_cell['bbox']['width']:.4f},
            "height": {example_cell['bbox']['height']:.4f}
        }}
    }}
    ─────────────────────────────────────────────────────────────
    """)

    print("\n" + "=" * 80)
    print("4. AGENT WORKFLOW EXAMPLE")
    print("=" * 80)
    print(f"""
    USER QUESTION: "What is the Appearance test result?"

    AGENT RECEIVES FROM WEAVIATE:
    ├── content: "TESTS | SPECIFICATIONS | METHOD | RESULTS..."
    ├── markdown: "<table>...<td id='2-5'>Appearance</td>...<td id='2-8'>Complies</td>...</table>"
    └── cell_grounding: {{"2-5": {{...}}, "2-8": {{...}}, ...}}

    AGENT READS MARKDOWN AND FINDS:
    ├── Test name in <td id='2-5'>Appearance</td>
    └── Result in <td id='2-8'>Complies</td>

    AGENT RESPONDS:
    "The Appearance test result is **Complies**. [source: cell 2-8, page 2]"

    FRONTEND EXTRACTS: cell_id = "2-8", page = 2

    FRONTEND LOOKS UP: cell_grounding["2-8"].bbox

    FRONTEND HIGHLIGHTS: Draw yellow box at that bbox on page 2!
    """)

    print("\n" + "=" * 80)
    print("5. WHAT'S STORED IN WEAVIATE (Vector DB)")
    print("=" * 80)
    print(f"""
    DocumentChunk {{
        chunk_id: "{table_chunk.get('chunk_id', 'N/A')[:50]}..."
        chunk_type: "table"
        page: {table_chunk.get('page')}

        content: "{table_chunk.get('content', '')[:100].encode('ascii','replace').decode()}..."

        markdown: "<table id='2-t26'>
                     <tr>
                       <td id='2-1'>TESTS</td>
                       <td id='2-2'>SPECIFICATIONS</td>
                       ...
                     </tr>
                     <tr>
                       <td id='2-5'>Appearance</td>
                       <td id='2-6'>White to tan solid</td>
                       <td id='2-7'>Visual</td>
                       <td id='2-8'>Complies</td>    <-- Agent finds answer here
                     </tr>
                     ...
                   </table>"

        cell_grounding: {{
            "2-1": {{"bbox": {{...}}, "text": "TESTS", "row": 1, "col": 1}},
            "2-5": {{"bbox": {{...}}, "text": "Appearance", "row": 2, "col": 1}},
            "2-8": {{"bbox": {{left: 0.78, top: 0.24, width: 0.17, height: 0.02}},
                    "text": "Complies", "row": 2, "col": 4}},   <-- Bbox for highlighting
            ...
        }}

        vector: [0.123, -0.456, 0.789, ...]  (3072 dimensions for search)
    }}
    """)

if __name__ == '__main__':
    main()
