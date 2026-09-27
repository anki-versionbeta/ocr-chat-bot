"""
Inspect Table Chunks - See exactly how cell_grounding works
This shows how an agent can easily extract bbox for highlighting in Phase 5
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from weaviate_indexer import WeaviateIndexer

def main():
    indexer = WeaviateIndexer()
    process_id = 'layout-full-test-c2d0b134'

    print("=" * 80)
    print("INSPECTING TABLE CHUNKS WITH CELL_GROUNDING")
    print("=" * 80)

    # Search for table-related content
    results = indexer.search_chunks(
        query="test results specifications",
        process_id=process_id,
        limit=5,
        alpha=0.7
    )

    # Find table chunks
    table_chunks = [r for r in results if r.get('chunk_type') == 'table']

    if not table_chunks:
        print("No table chunks found, searching again...")
        results = indexer.search_chunks(
            query="batch number product name",
            process_id=process_id,
            limit=10,
            alpha=0.5
        )
        table_chunks = [r for r in results if r.get('chunk_type') == 'table']

    print(f"\nFound {len(table_chunks)} table chunks\n")

    for idx, chunk in enumerate(table_chunks[:2], 1):  # Show first 2 table chunks
        print("=" * 80)
        print(f"TABLE CHUNK #{idx}")
        print("=" * 80)

        # Basic info
        print(f"\n[BASIC INFO]")
        print(f"  Page: {chunk.get('page')}")
        print(f"  Chunk Type: {chunk.get('chunk_type')}")
        print(f"  Layout Type: {chunk.get('layout_type')}")
        print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")

        # Table-level bounding box
        print(f"\n[TABLE BOUNDING BOX] (normalized 0-1)")
        print(f"  Left:   {chunk.get('bbox_left', 0):.4f}")
        print(f"  Top:    {chunk.get('bbox_top', 0):.4f}")
        print(f"  Right:  {chunk.get('bbox_right', 0):.4f}")
        print(f"  Bottom: {chunk.get('bbox_bottom', 0):.4f}")

        # Content (plain text for search)
        print(f"\n[CONTENT] (searchable text)")
        content = chunk.get('content', '')
        # Show first 500 chars
        print(f"  {content[:500].encode('ascii', 'replace').decode('ascii')}...")

        # Markdown (structured with cell IDs)
        print(f"\n[MARKDOWN] (HTML with cell IDs for Claude)")
        markdown = chunk.get('markdown', '')
        if markdown:
            # Show first 800 chars of markdown
            print(f"  {markdown[:800].encode('ascii', 'replace').decode('ascii')}...")
        else:
            print("  (no markdown)")

        # Cell Grounding - THE KEY FOR PHASE 5 HIGHLIGHTING!
        print(f"\n[CELL_GROUNDING] (cell ID -> bbox mapping for highlighting)")
        cell_grounding_str = chunk.get('cell_grounding', '')

        if cell_grounding_str:
            try:
                cell_grounding = json.loads(cell_grounding_str)
                print(f"  Total cells with grounding: {len(cell_grounding)}")

                print(f"\n  Example cells (first 5):")
                print(f"  " + "-" * 70)

                for i, (cell_id, cell_data) in enumerate(list(cell_grounding.items())[:5]):
                    bbox = cell_data.get('bbox', {})
                    text = cell_data.get('text', '')[:40]
                    row = cell_data.get('row', '?')
                    col = cell_data.get('col', '?')

                    print(f"\n  Cell ID: {cell_id}")
                    print(f"    Text: \"{text.encode('ascii', 'replace').decode('ascii')}\"")
                    print(f"    Row: {row}, Col: {col}")
                    print(f"    BBox: left={bbox.get('left', 0):.4f}, top={bbox.get('top', 0):.4f}, "
                          f"right={bbox.get('right', 0):.4f}, bottom={bbox.get('bottom', 0):.4f}")

                # Show how an agent would use this
                print(f"\n  " + "=" * 70)
                print(f"  HOW PHASE 5 AGENT WOULD USE THIS:")
                print(f"  " + "=" * 70)
                print(f"""
  1. Claude receives question: "What is the batch number?"

  2. Claude finds answer in markdown:
     <td id='1-5'>0001903356</td>

  3. Claude responds: "The batch number is 0001903356 [cell:1-5]"

  4. Frontend extracts cell ID "1-5" from response

  5. Frontend looks up in cell_grounding:
     cell_grounding["1-5"] = {{"bbox": {{"left": 0.5, "top": 0.2, ...}}, ...}}

  6. Frontend draws highlight rectangle on PDF at those coordinates!
""")

            except json.JSONDecodeError as e:
                print(f"  Error parsing cell_grounding: {e}")
        else:
            print("  (no cell_grounding)")

        print("\n")

    # Also show a text chunk for comparison
    print("=" * 80)
    print("COMPARISON: TEXT CHUNK WITH LINE_GROUNDING")
    print("=" * 80)

    text_chunks = [r for r in results if r.get('chunk_type') == 'text' and r.get('line_grounding')]

    if text_chunks:
        chunk = text_chunks[0]
        print(f"\n[BASIC INFO]")
        print(f"  Page: {chunk.get('page')}")
        print(f"  Layout Type: {chunk.get('layout_type')}")

        print(f"\n[CONTENT]")
        print(f"  {chunk.get('content', '')[:300].encode('ascii', 'replace').decode('ascii')}...")

        print(f"\n[LINE_GROUNDING]")
        line_grounding_str = chunk.get('line_grounding', '')
        if line_grounding_str:
            try:
                line_grounding = json.loads(line_grounding_str)
                print(f"  Total lines: {len(line_grounding)}")

                for i, (line_id, line_data) in enumerate(list(line_grounding.items())[:3]):
                    bbox = line_data.get('bbox', {})
                    text = line_data.get('text', '')[:50]
                    print(f"\n  Line ID: {line_id[:20]}...")
                    print(f"    Text: \"{text.encode('ascii', 'replace').decode('ascii')}\"")
                    print(f"    BBox: left={bbox.get('left', 0):.4f}, top={bbox.get('top', 0):.4f}")
            except:
                pass

if __name__ == '__main__':
    main()
