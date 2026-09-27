"""
Test Intent Classifier for VIEW vs EXTRACT distinction
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from services.intent_classifier import classify_intent_sync, QueryIntent

def test_intent_classification():
    """Test that view table queries are classified as vector_only"""

    test_cases = [
        # VIEW TABLE queries - should be vector_only
        ("give me the table from page 5 entire table", QueryIntent.VECTOR_ONLY),
        ("show me the table from page 5", QueryIntent.VECTOR_ONLY),
        ("display table on page 3", QueryIntent.VECTOR_ONLY),
        ("give me the entire table from page 5", QueryIntent.VECTOR_ONLY),
        ("show table from page 2", QueryIntent.VECTOR_ONLY),

        # EXTRACT queries - should be hybrid_semantic_structural
        ("get all concentration values from all pages", QueryIntent.HYBRID_SEMANTIC_STRUCTURAL),
        ("extract all data and export to excel", QueryIntent.HYBRID_SEMANTIC_STRUCTURAL),
        ("get ECD concentration from all pages and export to csv", QueryIntent.HYBRID_SEMANTIC_STRUCTURAL),

        # Simple Q&A - should be vector_only
        ("what is the batch number", QueryIntent.VECTOR_ONLY),
        ("what is the value for 10,0 um", QueryIntent.VECTOR_ONLY),
    ]

    print("\n" + "="*70)
    print("INTENT CLASSIFIER TEST - VIEW vs EXTRACT")
    print("="*70)

    passed = 0
    failed = 0

    for query, expected in test_cases:
        actual = classify_intent_sync(query)
        status = "PASS" if actual == expected else "FAIL"

        if actual == expected:
            passed += 1
        else:
            failed += 1

        print(f"\n{status}")
        print(f"  Query: '{query}'")
        print(f"  Expected: {expected.value}")
        print(f"  Got: {actual.value}")

    print("\n" + "="*70)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*70)

if __name__ == "__main__":
    test_intent_classification()
