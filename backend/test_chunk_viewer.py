"""
Test script to view chunks from Weaviate and demonstrate how RAG query would work.
Shows chunk structure with cell_grounding/line_grounding for bounding box lookup.

Uses the actual WeaviateIndexer from Phase 3.
"""
import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.weaviate_indexer import WeaviateIndexer

PROCESS_ID = 'e97f76ec-7372-4db0-ab7d-d5c76c055591'


def get_all_chunks(indexer, process_id):
    """Query all chunks for the given process_id using raw GraphQL"""
    import requests

    query = '''
    {
      Get {
        DocumentChunk(
          where: {
            path: ["process_id"],
            operator: Equal,
            valueText: "%s"
          }
          limit: 100
        ) {
          chunk_id
          page
          chunk_index
          chunk_type
          layout_type
          content
          bbox_left
          bbox_top
          bbox_right
          bbox_bottom
          cell_grounding
          line_grounding
          markdown
        }
      }
    }
    ''' % process_id

    response = requests.post(
        f'{indexer.weaviate_url}/v1/graphql',
        json={'query': query},
        headers={'Content-Type': 'application/json'},
        timeout=30
    )

    if response.status_code == 200:
        data = response.json()
        return data.get('data', {}).get('Get', {}).get('DocumentChunk', [])
    else:
        print(f'Error: {response.status_code}')
        print(response.text)
        return []


def display_chunks(chunks):
    """Display chunks in a readable format"""
    import sys
    # Fix encoding for Windows console
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    print(f'\n{"="*80}')
    print(f'FOUND {len(chunks)} CHUNKS')
    print(f'{"="*80}')

    for i, chunk in enumerate(chunks):
        print(f'\n{"="*80}')
        print(f'CHUNK {i+1}: {chunk.get("chunk_id", "unknown")}')
        print(f'{"="*80}')
        print(f'  Type: {chunk.get("chunk_type")}')
        print(f'  Layout Type: {chunk.get("layout_type")}')
        print(f'  Page: {chunk.get("page")}')
        print(f'  Index: {chunk.get("chunk_index")}')
        print(f'  BBox: L={chunk.get("bbox_left", 0):.4f}, T={chunk.get("bbox_top", 0):.4f}, R={chunk.get("bbox_right", 0):.4f}, B={chunk.get("bbox_bottom", 0):.4f}')

        print(f'\n  --- CONTENT ---')
        content = chunk.get('content', '')
        if len(content) > 600:
            print(f'  {content[:600]}...')
            print(f'  (truncated, total {len(content)} chars)')
        else:
            print(f'  {content}')

        # Show cell grounding for TABLE chunks
        if chunk.get('cell_grounding'):
            try:
                grounding = json.loads(chunk['cell_grounding']) if isinstance(chunk['cell_grounding'], str) else chunk['cell_grounding']
                print(f'\n  --- CELL GROUNDING ({len(grounding)} cells) ---')
                for j, (cell_id, cell_data) in enumerate(grounding.items()):
                    if j < 8:  # Show first 8 cells
                        bbox = cell_data.get('bbox', {})
                        text = cell_data.get('text', '')[:50]
                        row = cell_data.get('row')
                        col = cell_data.get('col')
                        print(f'    [{cell_id}] R{row}:C{col} -> "{text}"')
                        # Use lowercase keys (as stored by TextractParser)
                        print(f'        BBox: L={bbox.get("left", 0):.4f}, T={bbox.get("top", 0):.4f}, W={bbox.get("width", 0):.4f}, H={bbox.get("height", 0):.4f}')
                if len(grounding) > 8:
                    print(f'    ... and {len(grounding) - 8} more cells')
            except Exception as e:
                print(f'  Error parsing cell_grounding: {e}')

        # Show line grounding for TEXT chunks
        if chunk.get('line_grounding'):
            try:
                grounding = json.loads(chunk['line_grounding']) if isinstance(chunk['line_grounding'], str) else chunk['line_grounding']
                print(f'\n  --- LINE GROUNDING ({len(grounding)} lines) ---')
                for j, (line_id, line_data) in enumerate(grounding.items()):
                    if j < 3:  # Show first 3 lines
                        bbox = line_data.get('bbox', {})
                        text = line_data.get('text', '')[:40]
                        print(f'    [{line_id[:12]}...] -> "{text}"')
                        # Use lowercase keys (as stored by TextractParser)
                        print(f'        BBox: L={bbox.get("left", 0):.4f}, T={bbox.get("top", 0):.4f}')
                if len(grounding) > 3:
                    print(f'    ... and {len(grounding) - 3} more lines')
            except Exception as e:
                print(f'  Error parsing line_grounding: {e}')


def simulate_rag_query(indexer, process_id, query_text):
    """
    Simulate how Phase 4 RAG query would work:
    1. Search Weaviate with hybrid search
    2. Get matching chunks with cell_grounding
    3. Show how Claude would identify cells and return bbox
    """
    print(f'\n\n{"#"*80}')
    print(f'SIMULATING RAG QUERY: "{query_text}"')
    print(f'{"#"*80}')

    # Use the indexer's search method
    print('\n1. HYBRID SEARCH (70% semantic, 30% BM25)...')
    results = indexer.search_chunks(
        query=query_text,
        process_id=process_id,
        limit=5,
        alpha=0.7
    )

    print(f'   Found {len(results)} matching chunks\n')

    for i, result in enumerate(results):
        score = result.get('_additional', {}).get('score', 0)
        # Convert score to float if it's a string
        try:
            score = float(score) if score else 0.0
        except (ValueError, TypeError):
            score = 0.0
        chunk_type = result.get('chunk_type')
        layout_type = result.get('layout_type')
        page = result.get('page')

        print(f'\n2. MATCHING CHUNK {i+1} (score: {score:.4f})')
        print(f'   Type: {chunk_type} | Layout: {layout_type} | Page: {page}')

        content = result.get('content', '')[:400]
        print(f'\n   Content preview:')
        print(f'   {content}...\n')

        # For table chunks, show how to find specific cells
        if result.get('cell_grounding'):
            grounding = json.loads(result['cell_grounding']) if isinstance(result['cell_grounding'], str) else result['cell_grounding']

            print(f'3. CELL GROUNDING LOOKUP:')
            print(f'   This chunk has {len(grounding)} cells with bounding boxes')

            # Find cells that might contain "minor defect" or related terms
            search_terms = query_text.lower().split()
            found_cells = []

            for cell_id, cell_data in grounding.items():
                cell_text = cell_data.get('text', '').lower()
                if any(term in cell_text for term in search_terms):
                    found_cells.append((cell_id, cell_data))

            if found_cells:
                print(f'\n   Found {len(found_cells)} cells matching query terms:')
                for cell_id, cell_data in found_cells[:5]:
                    bbox = cell_data.get('bbox', {})
                    row = cell_data.get('row')
                    col = cell_data.get('col')
                    text = cell_data.get('text', '')

                    print(f'\n   CELL: {cell_id}')
                    print(f'     Row: {row}, Col: {col}')
                    print(f'     Text: "{text}"')
                    print(f'     BBox for highlighting (normalized 0-1):')
                    # Use lowercase keys (as stored by TextractParser)
                    print(f'       Left:   {bbox.get("left", 0):.4f}')
                    print(f'       Top:    {bbox.get("top", 0):.4f}')
                    print(f'       Width:  {bbox.get("width", 0):.4f}')
                    print(f'       Height: {bbox.get("height", 0):.4f}')

                    # Show all cells in same row
                    print(f'\n     All cells in Row {row}:')
                    for cid, cdata in grounding.items():
                        if cdata.get('row') == row:
                            print(f'       Col {cdata.get("col")}: "{cdata.get("text", "")}"')


def main():
    print('='*80)
    print('PHASE 4 RAG QUERY SIMULATION')
    print('='*80)
    print(f'\nProcess ID: {PROCESS_ID}')

    # Initialize indexer
    indexer = WeaviateIndexer()
    print(f'Weaviate URL: {indexer.weaviate_url}')
    print(f'Connection OK: {indexer.check_connection()}')

    # Get chunk count
    count = indexer.get_chunk_count(PROCESS_ID)
    print(f'Chunks for this process: {count}')

    if count == 0:
        print('\nNo chunks found! Make sure the document was indexed.')
        return

    # Get all chunks and display
    print('\n\n' + '='*80)
    print('VIEWING ALL INDEXED CHUNKS')
    print('='*80)

    chunks = get_all_chunks(indexer, PROCESS_ID)
    display_chunks(chunks)

    # Simulate RAG query
    simulate_rag_query(indexer, PROCESS_ID, "minor defect acceptance")


if __name__ == '__main__':
    main()
