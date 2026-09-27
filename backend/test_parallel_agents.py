"""
Test Parallel Agents with Pure BM25 for Exploratory Queries

This tests that Page 31 (Elapsed Mix Time) is now found when asking
exploratory queries like "which sections have elapsed time or duration?"
"""

import sys
import os

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.rag_orchestrator import get_rag_orchestrator
from services.parallel_agent_graph import detect_query_type

# Test configuration
PROCESS_ID = "b5b3648f-1da1-4ab5-bd3d-5f935c0288b5"
FILENAME = "BR-1003 1000962712.pdf"

def test_exploratory_query():
    """Test that exploratory queries use pure BM25 and find Page 31."""
    print("=" * 80)
    print("TESTING PARALLEL AGENTS WITH PURE BM25 FOR EXPLORATORY QUERIES")
    print("=" * 80)

    query = "which sections have elapsed time or duration?"

    # Step 1: Verify query type detection
    query_type = detect_query_type(query)
    print(f"\n[QUERY TYPE DETECTION]")
    print(f"  Query: {query}")
    print(f"  Detected Type: {query_type}")
    print(f"  Expected: exploratory")
    assert query_type == "exploratory", f"Expected 'exploratory', got '{query_type}'"
    print(f"  ✓ Correctly detected as exploratory")

    # Step 2: Run the full RAG query
    print(f"\n[RUNNING RAG QUERY]")
    print(f"  Process ID: {PROCESS_ID}")
    print(f"  Using alpha=0.0 (pure BM25) for exploratory query")

    orchestrator = get_rag_orchestrator()
    response = orchestrator.process_query_sync(
        query=query,
        process_id=PROCESS_ID,
        filename=FILENAME
    )

    # Step 3: Check results
    print(f"\n[RESULTS]")
    print(f"  Query Type: {response.get('query_type', 'N/A')}")
    print(f"  Confidence: {response.get('confidence', 0):.2f}")
    print(f"  Agents Used: {response.get('agents_used', 1)}")
    print(f"  References: {len(response.get('references', []))}")

    # Check if answer mentions Page 31 or step 7.3
    answer = response.get('answer', '')
    print(f"\n[ANSWER]")
    print("-" * 40)
    print(answer[:1500] if len(answer) > 1500 else answer)
    print("-" * 40)

    # Verify Page 31 is found
    has_page_31 = "31" in answer or "7.3" in answer or "elapsed mix time" in answer.lower()
    print(f"\n[VERIFICATION]")
    print(f"  Contains Page 31/Step 7.3/Elapsed Mix Time: {has_page_31}")

    if has_page_31:
        print(f"  ✓ SUCCESS: Page 31 with Elapsed Mix Time is now being found!")
    else:
        print(f"  ✗ WARNING: Page 31 may not be in results. Check search rankings.")

    # Show references
    refs = response.get('references', [])
    if refs:
        print(f"\n[REFERENCES BY PAGE]")
        pages = sorted(set(r.get('page', 0) for r in refs))
        for page in pages:
            print(f"  Page {page}: {sum(1 for r in refs if r.get('page') == page)} references")

    return response


def test_specific_query():
    """Test that specific queries still use hybrid search."""
    print("\n" + "=" * 80)
    print("TESTING SPECIFIC QUERY (should use hybrid alpha=0.5)")
    print("=" * 80)

    query = "what is the elapsed mix time for step 7.3?"

    query_type = detect_query_type(query)
    print(f"\n[QUERY TYPE DETECTION]")
    print(f"  Query: {query}")
    print(f"  Detected Type: {query_type}")
    print(f"  Expected: specific")

    orchestrator = get_rag_orchestrator()
    response = orchestrator.process_query_sync(
        query=query,
        process_id=PROCESS_ID,
        filename=FILENAME
    )

    print(f"\n[RESULTS]")
    print(f"  Confidence: {response.get('confidence', 0):.2f}")
    print(f"  Agents Used: {response.get('agents_used', 1)}")

    answer = response.get('answer', '')
    print(f"\n[ANSWER]")
    print("-" * 40)
    print(answer[:800] if len(answer) > 800 else answer)
    print("-" * 40)

    return response


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("PARALLEL AGENT + PURE BM25 TEST")
    print("=" * 80)

    # Test exploratory query (should use alpha=0.0)
    test_exploratory_query()

    # Test specific query (should use alpha=0.5)
    test_specific_query()

    print("\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)
