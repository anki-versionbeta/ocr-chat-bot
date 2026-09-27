"""
Test the parallel agents merge fix - filtering out "not found" type answers.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.parallel_agent_graph import run_parallel_agents_sync, detect_query_type
from services.weaviate_indexer import WeaviateIndexer

def test_parallel_merge():
    """Test parallel agents with the elapsed mix time query."""

    query = "what is the elapsed mix time?"
    process_id = "b5b3648f-1da1-4ab5-bd3d-5f935c0288b5"
    filename = "BR-1003 1000962712.pdf"

    print("=" * 80)
    print("TESTING PARALLEL AGENTS MERGE FIX")
    print("=" * 80)
    print(f"\nQuery: {query}")
    print(f"Process ID: {process_id}")
    print(f"Filename: {filename}")

    # Step 1: Get chunks from Weaviate
    print("\n" + "-" * 40)
    print("Step 1: Fetching chunks from Weaviate...")

    weaviate = WeaviateIndexer()
    chunks = weaviate.search_chunks(
        query=query,
        process_id=process_id,
        limit=25,
        alpha=0.0  # BM25 for exploratory
    )

    print(f"Retrieved {len(chunks)} chunks")

    # Show chunk pages
    pages = set(c.get('page', 0) for c in chunks)
    print(f"Pages covered: {sorted(pages)}")

    # Step 2: Run parallel agents
    print("\n" + "-" * 40)
    print("Step 2: Running parallel agents...")

    result = run_parallel_agents_sync(
        query=query,
        chunks=chunks,
        filename=filename
    )

    # Step 3: Check results
    print("\n" + "-" * 40)
    print("Step 3: Results")
    print("-" * 40)

    answer = result.get('answer', '')
    confidence = result.get('confidence', 0)
    agents_used = result.get('agents_used', 0)
    cell_ids = result.get('cell_ids', [])

    print(f"\nAgents used: {agents_used}")
    print(f"Confidence: {confidence:.2f}")
    print(f"Cell IDs: {len(cell_ids)}")

    print(f"\n--- FINAL ANSWER ---")
    print(answer)
    print("--- END ANSWER ---")

    # Check if "not found" phrases are filtered
    NOT_FOUND_PHRASES = [
        "cannot be determined",
        "not provided",
        "not found",
        "not available",
        "no information",
        "not explicitly",
        "not mentioned",
    ]

    print("\n" + "-" * 40)
    print("Step 4: Checking for 'not found' phrases in answer...")

    answer_lower = answer.lower()
    found_phrases = []
    for phrase in NOT_FOUND_PHRASES:
        if phrase in answer_lower:
            found_phrases.append(phrase)

    if found_phrases:
        print(f"WARNING: Found these 'not found' phrases still in answer:")
        for p in found_phrases:
            print(f"  - '{p}'")
        print("\n⚠️  FIX MAY NOT BE WORKING CORRECTLY")
    else:
        print("✓ No 'not found' phrases found in answer!")
        print("✓ FIX IS WORKING - Invalid answers are being filtered out")

    # Show references
    refs = result.get('references', [])
    print(f"\n--- REFERENCES ({len(refs)}) ---")
    for ref in refs[:5]:
        print(f"  Page {ref.get('page')}: {ref.get('text', '')[:50]}...")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    return result

if __name__ == "__main__":
    test_parallel_merge()
