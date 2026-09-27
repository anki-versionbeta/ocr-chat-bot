"""
Show the actual grounding structure for Phase 5 highlighting
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from weaviate_indexer import WeaviateIndexer

def main():
    indexer = WeaviateIndexer()
    process_id = 'layout-full-test-c2d0b134'

    print("=" * 70)
    print("GROUNDING STRUCTURE FOR PHASE 5 HIGHLIGHTING")
    print("=" * 70)

    # Search for a table chunk
    results = indexer.search_chunks(
        query="test results specifications",
        process_id=process_id,
        limit=3
    )

    # Find a table chunk
    table_chunk = None
    for r in results:
        if r.get('chunk_type') == 'table' and r.get('cell_grounding'):
            table_chunk = r
            break

    if not table_chunk:
        print("No table chunk found")
        return

    print(f"\n[TABLE CHUNK - Page {table_chunk.get('page')}]")
    print("-" * 70)

    # Parse cell_grounding
    cell_grounding = json.loads(table_chunk['cell_grounding'])

    print(f"\nTotal cells in this table: {len(cell_grounding)}")
    print("\nSample cells with bbox (first 5):\n")

    for i, (cell_id, cell_data) in enumerate(list(cell_grounding.items())[:5]):
        bbox = cell_data['bbox']
        print(f"  Cell ID: '{cell_id}'")
        print(f"  Text:    \"{cell_data['text'][:50].encode('ascii', 'replace').decode()}\"")
        print(f"  Row/Col: row={cell_data['row']}, col={cell_data['col']}")
        print(f"  BBox:    left={bbox['left']:.4f}, top={bbox['top']:.4f}")
        print(f"           width={bbox['width']:.4f}, height={bbox['height']:.4f}")
        print()

    print("=" * 70)
    print("HOW PHASE 5 WILL USE THIS:")
    print("=" * 70)
    print("""
    1. User asks: "What is the pH result?"

    2. RAG retrieves this table chunk with cell_grounding

    3. Claude reads markdown and answers:
       "The pH result is 6.1 [ref: cell 2-8]"

    4. Frontend extracts cell_id "2-8" from response

    5. Frontend looks up in cell_grounding:
       cell_grounding["2-8"] = {
         bbox: {left: 0.78, top: 0.24, width: 0.17, height: 0.02},
         text: "6.1",
         row: 2, col: 4
       }

    6. Frontend highlights on PDF canvas:
       const { left, top, width, height } = cell_grounding["2-8"].bbox;
       const page = chunk.page;  // e.g., 2

       // Convert normalized coords to pixels
       ctx.fillStyle = "rgba(255, 255, 0, 0.3)";  // Yellow highlight
       ctx.fillRect(
         left * pageWidth,      // X position
         top * pageHeight,      // Y position
         width * pageWidth,     // Width
         height * pageHeight    // Height
       );

    That's it! Simple and direct.
    """)

if __name__ == '__main__':
    main()
