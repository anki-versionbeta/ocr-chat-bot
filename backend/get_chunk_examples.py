"""
Fetch actual chunk examples from Weaviate - one table chunk and one text chunk
"""

import requests
import json

WEAVIATE_URL = "http://10.242.190.53:8080"
COLLECTION_NAME = "DocumentChunk"

def get_chunks():
    """Get sample chunks - one table and one text."""

    # Query to get a variety of chunks
    graphql_query = '''
    {
        Get {
            DocumentChunk(
                limit: 50
            ) {
                document_id
                process_id
                chunk_id
                chunk_index
                page
                chunk_type
                layout_type
                content
                cell_grounding
                line_grounding
                markdown
                bbox_left
                bbox_top
                bbox_right
                bbox_bottom
                filename
            }
        }
    }
    '''

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json={"query": graphql_query},
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("Get", {}).get(COLLECTION_NAME, [])
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return []


def main():
    print("Fetching chunks from Weaviate...\n")

    chunks = get_chunks()
    print(f"Total chunks fetched: {len(chunks)}\n")

    if not chunks:
        print("No chunks found!")
        return

    # Find one table chunk with cell_grounding
    table_chunk = None
    for c in chunks:
        if c.get('chunk_type') == 'table' and c.get('cell_grounding'):
            table_chunk = c
            break

    # Find one text chunk with line_grounding
    text_chunk = None
    for c in chunks:
        if c.get('chunk_type') == 'text' and c.get('line_grounding'):
            text_chunk = c
            break

    # ========================================
    # EXAMPLE 1: TABLE CHUNK
    # ========================================
    print("=" * 80)
    print("EXAMPLE 1: TABLE CHUNK")
    print("=" * 80)

    if table_chunk:
        print(f"\n[METADATA]")
        print(f"  process_id:   {table_chunk.get('process_id')}")
        print(f"  chunk_id:     {table_chunk.get('chunk_id')}")
        print(f"  chunk_index:  {table_chunk.get('chunk_index')}")
        print(f"  page:         {table_chunk.get('page')}")
        print(f"  chunk_type:   {table_chunk.get('chunk_type')}")
        print(f"  layout_type:  {table_chunk.get('layout_type')}")
        print(f"  filename:     {table_chunk.get('filename')}")

        print(f"\n[CHUNK-LEVEL BOUNDING BOX] (normalized 0-1)")
        print(f"  bbox_left:    {table_chunk.get('bbox_left', 0):.4f}")
        print(f"  bbox_top:     {table_chunk.get('bbox_top', 0):.4f}")
        print(f"  bbox_right:   {table_chunk.get('bbox_right', 0):.4f}")
        print(f"  bbox_bottom:  {table_chunk.get('bbox_bottom', 0):.4f}")

        print(f"\n[CONTENT] (plain text for search)")
        content = table_chunk.get('content', '') or ''
        print(content[:600] + ('...' if len(content) > 600 else ''))

        print(f"\n[MARKDOWN] (HTML with cell IDs for Claude)")
        markdown = table_chunk.get('markdown', '') or ''
        print(markdown[:800] + ('...' if len(markdown) > 800 else ''))

        print(f"\n[CELL_GROUNDING] (JSON mapping cell IDs to bboxes)")
        cell_grounding_str = table_chunk.get('cell_grounding', '')
        if cell_grounding_str:
            try:
                cg = json.loads(cell_grounding_str)
                print(f"  Total cells: {len(cg)}")
                print(f"\n  First 5 cells:")
                for i, (cell_id, cell_data) in enumerate(list(cg.items())[:5]):
                    bbox = cell_data.get('bbox', {})
                    text = cell_data.get('text', '')[:40]
                    row = cell_data.get('row', '?')
                    col = cell_data.get('col', '?')
                    print(f"\n    Cell ID: '{cell_id}'")
                    print(f"      text: \"{text}\"")
                    print(f"      row: {row}, col: {col}")
                    print(f"      bbox: {{left: {bbox.get('left', 0):.4f}, top: {bbox.get('top', 0):.4f}, width: {bbox.get('width', 0):.4f}, height: {bbox.get('height', 0):.4f}}}")
            except Exception as e:
                print(f"  Parse error: {e}")
    else:
        print("  No table chunk with cell_grounding found")

    # ========================================
    # EXAMPLE 2: TEXT CHUNK
    # ========================================
    print("\n\n" + "=" * 80)
    print("EXAMPLE 2: TEXT CHUNK")
    print("=" * 80)

    if text_chunk:
        print(f"\n[METADATA]")
        print(f"  process_id:   {text_chunk.get('process_id')}")
        print(f"  chunk_id:     {text_chunk.get('chunk_id')}")
        print(f"  chunk_index:  {text_chunk.get('chunk_index')}")
        print(f"  page:         {text_chunk.get('page')}")
        print(f"  chunk_type:   {text_chunk.get('chunk_type')}")
        print(f"  layout_type:  {text_chunk.get('layout_type')}")
        print(f"  filename:     {text_chunk.get('filename')}")

        print(f"\n[CHUNK-LEVEL BOUNDING BOX] (normalized 0-1)")
        print(f"  bbox_left:    {text_chunk.get('bbox_left', 0):.4f}")
        print(f"  bbox_top:     {text_chunk.get('bbox_top', 0):.4f}")
        print(f"  bbox_right:   {text_chunk.get('bbox_right', 0):.4f}")
        print(f"  bbox_bottom:  {text_chunk.get('bbox_bottom', 0):.4f}")

        print(f"\n[CONTENT] (plain text for search)")
        content = text_chunk.get('content', '') or ''
        print(content[:500] + ('...' if len(content) > 500 else ''))

        print(f"\n[MARKDOWN] (HTML with line IDs for Claude)")
        markdown = text_chunk.get('markdown', '') or ''
        print(markdown[:600] + ('...' if len(markdown) > 600 else ''))

        print(f"\n[LINE_GROUNDING] (JSON mapping line IDs to bboxes)")
        line_grounding_str = text_chunk.get('line_grounding', '')
        if line_grounding_str:
            try:
                lg = json.loads(line_grounding_str)
                print(f"  Total lines: {len(lg)}")
                print(f"\n  First 3 lines:")
                for i, (line_id, line_data) in enumerate(list(lg.items())[:3]):
                    bbox = line_data.get('bbox', {})
                    text = line_data.get('text', '')[:50]
                    print(f"\n    Line ID: '{line_id}'")
                    print(f"      text: \"{text}\"")
                    print(f"      bbox: {{left: {bbox.get('left', 0):.4f}, top: {bbox.get('top', 0):.4f}, width: {bbox.get('width', 0):.4f}, height: {bbox.get('height', 0):.4f}}}")
            except Exception as e:
                print(f"  Parse error: {e}")
    else:
        print("  No text chunk with line_grounding found")

    print("\n\n" + "=" * 80)
    print("DONE - These are actual chunks stored in Weaviate")
    print("=" * 80)


if __name__ == '__main__':
    main()
