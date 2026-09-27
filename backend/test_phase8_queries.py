"""
Test script for Phase 8 Dynamic Query Routing
Process ID: b5b3648f-1da1-4ab5-bd3d-5f935c0288b5
"""

import os
import sys
import json
import logging

# Setup logging to see detailed flow
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from services.rag_orchestrator import get_rag_orchestrator

# Test configuration
PROCESS_ID = "b5b3648f-1da1-4ab5-bd3d-5f935c0288b5"
FILENAME = "test_document.pdf"

def test_query(query: str, query_num: int, recent_messages: list = None):
    """Test a single query and print detailed results."""
    print("\n" + "="*80)
    print(f"QUERY {query_num}: {query}")
    print("="*80)

    orchestrator = get_rag_orchestrator()

    result = orchestrator.process_query_sync(
        query=query,
        process_id=PROCESS_ID,
        filename=FILENAME,
        recent_messages=recent_messages
    )

    print(f"\n--- RESULT ---")
    print(f"Intent: {result.get('intent', 'N/A')}")
    print(f"Query Type: {result.get('query_type', 'N/A')}")
    print(f"Confidence: {result.get('confidence', 0):.2f}")
    print(f"Focus Entities: {result.get('focus_entities', [])}")
    print(f"Agents Used: {result.get('agents_used', 'N/A')}")
    print(f"Filtered Findings: {result.get('filtered_findings', 0)}")
    print(f"\nAnswer:\n{result.get('answer', 'No answer')[:500]}")

    if result.get('references'):
        print(f"\nReferences: {len(result.get('references', []))} found")
        for i, ref in enumerate(result.get('references', [])[:3]):
            print(f"  - Page {ref.get('page')}: {ref.get('text', '')[:50]}...")

    print("-"*80)
    return result


def main():
    print("="*80)
    print("PHASE 8 DYNAMIC QUERY ROUTING - TEST SUITE")
    print(f"Process ID: {PROCESS_ID}")
    print("="*80)

    # Query 1: Lot number signature check (conditional)
    result1 = test_query(
        "Does the page which has lot number 1000962712 have the signature or not?",
        query_num=1
    )

    # Query 2: General signatures query
    result2 = test_query(
        "Which page contains signatures?",
        query_num=2
    )

    # Query 3: Perform date check on specific page
    result3 = test_query(
        "Check if the perform date in page 31 is written properly, I need proper analysis",
        query_num=3
    )

    # Query 4: Handwritten signatures
    result4 = test_query(
        "Which pages have sign? by handwritten sign?",
        query_num=4
    )

    # Query 5: What is the lot number
    result5 = test_query(
        "What is the lot number?",
        query_num=5
    )

    # Query 6: Follow-up - page and step reference for lot number
    # Simulate conversation context from Query 5
    recent_messages = [
        {"role": "user", "content": "What is the lot number?"},
        {"role": "assistant", "content": result5.get('answer', 'The lot number is 1000962712')}
    ]

    result6 = test_query(
        "Can you check what is the page and step reference for this lot that is present?",
        query_num=6,
        recent_messages=recent_messages
    )

    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    results = [
        ("Lot signature check", result1),
        ("Signatures query", result2),
        ("Perform date analysis", result3),
        ("Handwritten signs", result4),
        ("Lot number", result5),
        ("Page/step reference", result6)
    ]

    for name, res in results:
        conf = res.get('confidence', 0)
        status = "✓" if conf > 0.5 else "✗" if conf == 0 else "?"
        print(f"  {status} Query: {name} - Confidence: {conf:.2f}")


if __name__ == "__main__":
    main()
