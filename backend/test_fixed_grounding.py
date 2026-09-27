"""
Test Fixed Grounding - Re-index with correct bbox (left, top, right, bottom)
"""

import sys
import os
import json
import uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from textract_parser import TextractParser
from chunk_transformer import chunk_textract_blocks
from weaviate_indexer import WeaviateIndexer

def main():
    # Use the blocks.json from the PDF we processed
    blocks_path = r"C:\Users\BAPATAR\Downloads\ocr-chatbot\backend\temp\CoA_-_CoC_-_lot_0001903354_1_blocks.json"

    if not os.path.exists(blocks_path):
        print(f"File not found: {blocks_path}")
        return

    print("=" * 80)
    print("RE-PROCESSING WITH FIXED BBOX (left, top, right, bottom)")
    print("=" * 80)

    # Parse blocks
    print("\n[1] Parsing Textract blocks...")
    parser = TextractParser(blocks_json_path=blocks_path)
    tables = parser.get_all_tables()
    layouts = parser.get_all_layouts()
    print(f"    Tables: {len(tables)}, Layouts: {len(layouts)}")

    # Show sample cell bbox from parser (should now have right/bottom)
    if tables:
        sample_table = tables[0]
        sample_cells = list(sample_table['cells'].items())[:2]
        print("\n[2] Sample cell bbox from parser:")
        for cell_id, cell_data in sample_cells:
            bbox = cell_data['bbox']
            print(f"    Cell {cell_id}: {cell_data['text'][:30]}")
            print(f"      left={bbox['left']:.4f}, top={bbox['top']:.4f}")
            print(f"      right={bbox.get('right', 'MISSING')}, bottom={bbox.get('bottom', 'MISSING')}")

    # Create chunks
    print("\n[3] Creating chunks...")
    document_id = str(uuid.uuid4())[:8]
    process_id = f"fixed-bbox-test-{document_id}"

    chunks = chunk_textract_blocks(
        tables=tables,
        layouts=layouts,
        document_id=document_id,
        process_id=process_id,
        filename="CoA_-_CoC_-_lot_0001903354_1.pdf"
    )
    print(f"    Created {len(chunks)} chunks")

    # Show sample cell_grounding from chunk
    table_chunks = [c for c in chunks if c['chunk_type'] == 'table']
    if table_chunks:
        sample_chunk = table_chunks[0]
        cell_grounding = json.loads(sample_chunk['cell_grounding'])
        sample_cells = list(cell_grounding.items())[:3]

        print("\n[4] Sample cell_grounding from chunk (for Phase 5):")
        print("-" * 60)
        for cell_id, cell_data in sample_cells:
            bbox = cell_data['bbox']
            print(f"\n    Cell ID: {cell_id}")
            print(f"    Text: \"{cell_data['text'][:40]}\"")
            print(f"    Row: {cell_data['row']}, Col: {cell_data['col']}")
            print(f"    BBox:")
            print(f"      left:   {bbox['left']:.4f}")
            print(f"      top:    {bbox['top']:.4f}")
            print(f"      right:  {bbox.get('right', 'MISSING')}")
            print(f"      bottom: {bbox.get('bottom', 'MISSING')}")

    # Index to Weaviate with new process_id
    print("\n[5] Indexing to Weaviate...")
    indexer = WeaviateIndexer()

    # Delete old test chunks first
    old_count = indexer.get_chunk_count('layout-full-test-c2d0b134')
    if old_count > 0:
        print(f"    Deleting {old_count} old chunks...")
        indexer.delete_by_process_id('layout-full-test-c2d0b134')

    # Index new chunks
    result = indexer.index_chunks_batch(chunks)
    print(f"    Indexed: {result['success']} success, {result['failed']} failed")

    # Verify search returns correct bbox
    print("\n[6] Verifying search returns correct bbox...")
    results = indexer.search_chunks(
        query="batch number",
        process_id=process_id,
        limit=2
    )

    for r in results:
        if r.get('chunk_type') == 'table' and r.get('cell_grounding'):
            cell_grounding = json.loads(r['cell_grounding'])
            print(f"\n    Retrieved table chunk (Page {r.get('page')}):")
            sample = list(cell_grounding.items())[0]
            cell_id, cell_data = sample
            bbox = cell_data['bbox']
            print(f"    Cell '{cell_id}': \"{cell_data['text'][:30]}\"")
            print(f"    BBox: left={bbox['left']:.4f}, top={bbox['top']:.4f}, "
                  f"right={bbox.get('right', 'N/A')}, bottom={bbox.get('bottom', 'N/A')}")
            break

    print("\n" + "=" * 80)
    print("PHASE 5 HIGHLIGHTING FLOW:")
    print("=" * 80)
    print("""
    1. Claude answers: "The batch number is 0001903356" [references cell 1-5]

    2. Frontend extracts cell_id "1-5" from response

    3. Frontend looks up cell_grounding:
       cell_grounding["1-5"].bbox = {
         left: 0.5,
         top: 0.2,
         right: 0.75,   <-- NOW INCLUDED!
         bottom: 0.25   <-- NOW INCLUDED!
       }

    4. Frontend draws highlight on PDF canvas:
       ctx.fillRect(
         left * pageWidth,    // x
         top * pageHeight,    // y
         (right - left) * pageWidth,   // width
         (bottom - top) * pageHeight   // height
       )
    """)

    print(f"\nProcess ID for testing: {process_id}")

if __name__ == '__main__':
    main()
