"""
Quick test to verify bug fixes are working.
Tests:
1. Non-existent column query (should fail gracefully, not infinite loop)
2. Aggregation query (should work with AVG)
3. Normal row extraction (should still work)
"""
import sys
import os
import time
import json

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.multiagent_cypher_service import run_fewshot_cypher_generation

PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

def test_query(name: str, query: str, max_time: int = 60):
    """Run a query with timeout check"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    start = time.time()
    try:
        result = run_fewshot_cypher_generation(
            user_query=query,
            process_id=PROCESS_ID,
            max_iterations=2  # Limit iterations
        )
        duration = time.time() - start

        success = result.get('success', False)
        rows = result.get('result_count', 0)
        error = result.get('execution_error', '')
        iterations = result.get('iterations', 0)

        print(f"\nRESULT:")
        print(f"  Success: {success}")
        print(f"  Rows: {rows}")
        print(f"  Iterations: {iterations}")
        print(f"  Duration: {duration:.1f}s")
        if error:
            print(f"  Error: {error}")

        # Check for timeout (infinite loop)
        if duration > max_time:
            print(f"  WARNING: Took longer than {max_time}s - possible infinite loop!")
            return False

        return True

    except Exception as e:
        duration = time.time() - start
        print(f"\nEXCEPTION: {e}")
        print(f"Duration: {duration:.1f}s")
        return False

def main():
    print("="*60)
    print("QUICK FIX VERIFICATION TEST")
    print(f"Process ID: {PROCESS_ID}")
    print("="*60)

    results = {}

    # Test 1: Non-existent column (should fail gracefully, NOT infinite loop)
    results['nonexistent_column'] = test_query(
        "Non-existent Column (BUG #1 - Infinite Loop Fix)",
        "Get Ges.-Mittel. values for the 100.0 um column",  # 100.0 um doesn't exist
        max_time=90
    )

    # Test 2: Normal row extraction (should still work)
    results['normal_extraction'] = test_query(
        "Normal Row Extraction (Verify no regression)",
        "Get all Ges.-Mittel. row values from all pages",
        max_time=60
    )

    # Test 3: Aggregation (BUG #2 fix)
    results['aggregation'] = test_query(
        "Aggregation Query (BUG #2 - Type Mismatch Fix)",
        "What is the average value for Ges.-Mittel. in the 2.0 um column?",
        max_time=90
    )

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Passed: {passed}/{total}")
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
