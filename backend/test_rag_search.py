"""
Test RAG Search on Indexed Chunks
Tests the full search pipeline including hybrid search with process_id filtering.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from weaviate_indexer import WeaviateIndexer

def main():
    # Initialize indexer
    indexer = WeaviateIndexer()

    # Check connection
    print("=" * 60)
    print("WEAVIATE CONNECTION TEST")
    print("=" * 60)
    connected = indexer.check_connection()
    print(f"Connection: {'OK' if connected else 'FAILED'}")

    if not connected:
        print("Cannot proceed - Weaviate not connected")
        return

    # Get chunk count for our process
    process_id = 'layout-full-test-c2d0b134'
    count = indexer.get_chunk_count(process_id)
    print(f"Chunks for process '{process_id}': {count}")

    # Also get total chunks
    total = indexer.get_chunk_count()
    print(f"Total chunks in collection: {total}")

    if count == 0:
        print("\nNo chunks found for this process_id.")
        print("Testing with total chunks instead...")
        process_id = None  # Remove filter

    # Test search queries
    test_queries = [
        'batch number',
        'pH test result',
        'Manufacturing date',
        'appearance',
        'certificate of analysis'
    ]

    print("\n" + "=" * 60)
    print("SEARCH VERIFICATION TESTS")
    print("=" * 60)

    for query in test_queries:
        print(f'\n--- Query: "{query}" ---')
        results = indexer.search_chunks(
            query=query,
            process_id=process_id,
            limit=3,
            alpha=0.7  # 70% semantic, 30% keyword
        )

        if results:
            print(f"Found {len(results)} results:")
            for i, r in enumerate(results, 1):
                score = r.get('_additional', {}).get('score', 'N/A')
                chunk_type = r.get('chunk_type', 'unknown')
                page = r.get('page', '?')
                layout_type = r.get('layout_type', '')
                content = r.get('content', '')
                # Clean content for console output (remove special chars)
                content_preview = content[:150].replace('\n', ' ').encode('ascii', 'replace').decode('ascii') if content else '[no content]'

                print(f"  {i}. [Score: {score}] Type: {chunk_type} | Page: {page} | Layout: {layout_type}")
                print(f"     Content: {content_preview}...")

                # Show grounding info if available
                if chunk_type == 'table' and r.get('cell_grounding'):
                    print("     Has cell_grounding: Yes")
                if chunk_type == 'text' and r.get('line_grounding'):
                    print("     Has line_grounding: Yes")
        else:
            print("  No results found")

    print("\n" + "=" * 60)
    print("SEARCH VERIFICATION COMPLETE")
    print("=" * 60)

if __name__ == '__main__':
    main()
