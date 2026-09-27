"""
Test Page Filtering for Phase 5

Tests that page filtering in RAG queries works correctly.
When user specifies "from page 5", only chunks from page 5 should be searched.
"""

import os
import sys
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from services.question_rephraser import detect_page_filter
from services.rag_orchestrator import get_rag_orchestrator

def test_page_detection():
    """Test page number detection from queries"""
    print("\n" + "="*60)
    print("TEST 1: Page Detection")
    print("="*60)

    test_cases = [
        ("what is value for 10,0 um for the row Testfl. 1- Mes. 3 in table from page 5", 5),
        ("show me the table on page 3", 3),
        ("what is in page 10", 10),
        ("get data from p.7", 7),
        ("what is the batch number", None),  # No page mentioned
        ("show page 1 results", 1),
    ]

    for query, expected in test_cases:
        detected = detect_page_filter(query)
        status = "✓" if detected == expected else "✗"
        print(f"  {status} Query: '{query[:50]}...' → Expected: {expected}, Got: {detected}")

    print()

def test_weaviate_page_filter():
    """Test that Weaviate search respects page filter"""
    print("\n" + "="*60)
    print("TEST 2: Weaviate Page Filter")
    print("="*60)

    from services.weaviate_indexer import WeaviateIndexer

    # Use your test process_id
    process_id = "88177f13-ef6b-45ec-a787-1ad3e39bc8f7"
    query = "Testfl measurement value"

    indexer = WeaviateIndexer()

    # Test without page filter
    print(f"\n  Searching WITHOUT page filter...")
    results_no_filter = indexer.search_chunks(
        query=query,
        process_id=process_id,
        limit=50,
        alpha=0.5
    )

    pages_found = set(r.get('page', 0) for r in results_no_filter)
    chunk_indices = [r.get('chunk_index', 0) for r in results_no_filter]
    print(f"  → Found {len(results_no_filter)} chunks across pages: {sorted(pages_found)}")
    print(f"  → Chunk indices: {sorted(chunk_indices)[:15]}...")

    # Test WITH page filter = 5
    print(f"\n  Searching WITH page_filter=5...")
    results_with_filter = indexer.search_chunks(
        query=query,
        process_id=process_id,
        limit=50,
        alpha=0.5,
        page_filter=5
    )

    pages_found_filtered = set(r.get('page', 0) for r in results_with_filter)
    chunk_indices_filtered = [r.get('chunk_index', 0) for r in results_with_filter]
    print(f"  → Found {len(results_with_filter)} chunks, pages: {sorted(pages_found_filtered)}")
    print(f"  → Chunk indices: {sorted(chunk_indices_filtered)}")

    # Verify only page 5
    if pages_found_filtered == {5}:
        print(f"\n  ✓ SUCCESS: Page filter correctly restricted results to page 5!")
    else:
        print(f"\n  ✗ FAIL: Expected only page 5, got pages: {pages_found_filtered}")

    print()

def test_full_rag_with_page_filter():
    """Test full RAG pipeline with page-filtered query"""
    print("\n" + "="*60)
    print("TEST 3: Full RAG Pipeline with Page Filter")
    print("="*60)

    process_id = "88177f13-ef6b-45ec-a787-1ad3e39bc8f7"
    query = "what is value for 10,0 um for the row Testfl. 1- Mes. 3 in table from page 5"

    print(f"\n  Query: {query}")
    print(f"  Process ID: {process_id}")

    orchestrator = get_rag_orchestrator()
    response = orchestrator.process_query_sync(
        query=query,
        process_id=process_id,
        filename="test_document.pdf"
    )

    print(f"\n  Response:")
    print(f"  - Answer: {response.get('answer', 'N/A')[:200]}...")
    print(f"  - Confidence: {response.get('confidence', 0):.2f}")
    print(f"  - References: {len(response.get('references', []))} found")

    if response.get('references'):
        print(f"\n  References detail:")
        for ref in response.get('references', [])[:5]:
            print(f"    - Page {ref.get('page')}, cell_id: {ref.get('cell_id')}, text: '{ref.get('text', '')[:30]}'")

    # Check if we got references
    if response.get('references'):
        print(f"\n  ✓ SUCCESS: Got {len(response['references'])} references with bbox data!")
    else:
        print(f"\n  ⚠ WARNING: No references returned (check if chunk 69 is now retrieved)")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  PHASE 5 PAGE FILTERING TEST")
    print("="*60)

    # Run tests
    test_page_detection()
    test_weaviate_page_filter()
    test_full_rag_with_page_filter()

    print("\n" + "="*60)
    print("  TESTS COMPLETE")
    print("="*60)
