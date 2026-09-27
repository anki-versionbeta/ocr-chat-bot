"""
Test Script for Query Variations on German Particle Contamination Report

Tests various query formulations against the multi-agent cypher system
for process_id: f96d6d53-8257-4d3c-86b1-279f0e3ad069

Document characteristics:
- German particle contamination report
- Row labels like "Ges.-Mittel.", "Testfl. 1 - Mittelwert", etc.
- Column headers: 2,0 um | 5,0 um | 10,0 um | 15,0 um | 25,0 um | 40,0 um | 50,0 um
- Sample ID: pega-prod-SA00040984

Usage:
    python test_query_variations.py              # Run all queries
    python test_query_variations.py 1            # Run query 1 only
    python test_query_variations.py --verbose    # Verbose output
"""

import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Any
from test_multiagent_cypher import run_fewshot_cypher_generation

# Process ID for the German particle contamination report
PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

# Test query variations for Ges.-Mittel. row extraction
TEST_QUERIES = {
    1: {
        "query": "Get all Ges.-Mittel. row values",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_behavior": "Extract entire Ges.-Mittel. row with all threshold values",
        "expected_columns": ["2,0 um", "5,0 um", "10,0 um", "15,0 um", "25,0 um", "40,0 um", "50,0 um"],
        "notes": "Tests exact German term matching with hyphen and period"
    },
    2: {
        "query": "Get Ges.-Mittel. values for columns 2.0 um to 50.0 um",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_behavior": "Extract Ges.-Mittel. row values across all threshold columns",
        "expected_columns": ["2,0 um", "5,0 um", "10,0 um", "15,0 um", "25,0 um", "40,0 um", "50,0 um"],
        "notes": "Tests column range specification (note: user uses . but doc uses ,)"
    },
    3: {
        "query": "Extract the Ges.-Mittel. row with all threshold ranges",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_behavior": "Extract entire row with all particle size thresholds",
        "expected_columns": ["2,0 um", "5,0 um", "10,0 um", "15,0 um", "25,0 um", "40,0 um", "50,0 um"],
        "notes": "Tests semantic understanding of 'threshold ranges'"
    },
    4: {
        "query": "What are the particle counts for Ges.-Mittel.?",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_behavior": "Return particle count values for the Ges.-Mittel. row",
        "expected_columns": ["2,0 um", "5,0 um", "10,0 um", "15,0 um", "25,0 um", "40,0 um", "50,0 um"],
        "notes": "Tests question-style query with domain term 'particle counts'"
    },
    5: {
        "query": "Get all rows containing 'Mittel' with their threshold values",
        "category": "multi_row_extraction",
        "difficulty": "hard",
        "expected_behavior": "Extract all rows with 'Mittel' in name (Ges.-Mittel., Testfl. X - Mittelwert)",
        "expected_rows": ["Ges.-Mittel.", "Testfl. 1 - Mittelwert", "Testfl. 2 - Mittelwert"],
        "notes": "Tests wildcard/partial matching across multiple rows"
    },
    6: {
        "query": "Show sample number SA00040984 with its Ges.-Mittel. data",
        "category": "cross_reference",
        "difficulty": "hard",
        "expected_behavior": "Return Ges.-Mittel. data associated with sample SA00040984",
        "expected_sample": "pega-prod-SA00040984",
        "notes": "Tests cross-referencing sample ID with row data"
    },
    7: {
        "query": "Extract Ges.-Mittel. row from the particle contamination table",
        "category": "table_specific",
        "difficulty": "medium",
        "expected_behavior": "Identify particle contamination table and extract Ges.-Mittel. row",
        "expected_columns": ["2,0 um", "5,0 um", "10,0 um", "15,0 um", "25,0 um", "40,0 um", "50,0 um"],
        "notes": "Tests table identification with German terminology"
    }
}


def run_single_query(query_num: int, verbose: bool = False) -> Dict[str, Any]:
    """Run a single test query and return results."""
    if query_num not in TEST_QUERIES:
        print(f"Error: Query {query_num} not found. Available: {list(TEST_QUERIES.keys())}")
        return {"error": "Query not found", "success": False}

    query_info = TEST_QUERIES[query_num]

    print("\n" + "=" * 80)
    print(f"TEST QUERY #{query_num}")
    print("=" * 80)
    print(f"Query: {query_info['query']}")
    print(f"Category: {query_info['category']}")
    print(f"Difficulty: {query_info['difficulty']}")
    print(f"Expected Behavior: {query_info['expected_behavior']}")
    print(f"Notes: {query_info['notes']}")
    print("=" * 80 + "\n")

    start_time = time.time()

    try:
        result = run_fewshot_cypher_generation(
            user_query=query_info['query'],
            process_id=PROCESS_ID,
            max_iterations=3
        )
    except Exception as e:
        print(f"ERROR executing query: {e}")
        import traceback
        traceback.print_exc()
        result = {
            "success": False,
            "error": str(e),
            "result_count": 0,
            "iterations": 0
        }

    end_time = time.time()
    duration = end_time - start_time

    # Analyze results
    success = result.get('success', False)
    result_count = result.get('result_count', 0)
    results_data = result.get('results', [])
    cypher = result.get('cypher', result.get('generated_cypher', ''))
    natural_answer = result.get('natural_answer', '')

    # Check if results contain expected data patterns
    data_quality = "UNKNOWN"
    found_columns = []
    found_values = []

    if results_data:
        # Extract column/value information from results
        for row in results_data[:5]:  # Check first 5 results
            if isinstance(row, dict):
                for key, value in row.items():
                    if key not in found_columns:
                        found_columns.append(key)
                    if 'um' in str(key).lower() or 'mittel' in str(key).lower():
                        found_values.append({key: value})

        # Simple quality assessment
        if result_count > 0 and found_columns:
            data_quality = "GOOD" if any('mittel' in str(c).lower() for c in found_columns + [str(v) for v in results_data]) else "PARTIAL"
        else:
            data_quality = "POOR"
    else:
        data_quality = "NO_DATA"

    # Print results summary
    print("\n" + "=" * 80)
    print(f"QUERY #{query_num} RESULTS")
    print("=" * 80)
    print(f"Success: {success}")
    print(f"Result Count: {result_count}")
    print(f"Data Quality: {data_quality}")
    print(f"Iterations: {result.get('iterations', 'N/A')}")
    print(f"Duration: {duration:.2f}s")

    if verbose and cypher:
        print(f"\nGenerated Cypher:")
        print("-" * 40)
        print(cypher[:1000] + "..." if len(cypher) > 1000 else cypher)
        print("-" * 40)

    if natural_answer:
        print(f"\nNatural Language Answer:")
        print("-" * 40)
        # Handle encoding for Windows console
        try:
            print(natural_answer[:500] + "..." if len(natural_answer) > 500 else natural_answer)
        except UnicodeEncodeError:
            print(natural_answer.encode('ascii', 'replace').decode('ascii')[:500])
        print("-" * 40)

    if results_data:
        print(f"\nSample Results (first 3):")
        for i, row in enumerate(results_data[:3], 1):
            try:
                row_str = json.dumps(row, indent=2, default=str, ensure_ascii=False)
            except:
                row_str = str(row)
            print(f"  Result {i}:")
            # Handle encoding for Windows console
            try:
                print(f"    {row_str[:300]}...")
            except UnicodeEncodeError:
                print(f"    {row_str.encode('ascii', 'replace').decode('ascii')[:300]}...")

    print("=" * 80 + "\n")

    return {
        "query_num": query_num,
        "query": query_info['query'],
        "category": query_info['category'],
        "difficulty": query_info['difficulty'],
        "success": success,
        "result_count": result_count,
        "data_quality": data_quality,
        "iterations": result.get('iterations', 0),
        "duration": duration,
        "found_columns": found_columns,
        "error": result.get('error', ''),
        "cypher": cypher,
        "natural_answer": natural_answer
    }


def run_all_queries(verbose: bool = False) -> List[Dict[str, Any]]:
    """Run all test queries and return results."""
    results = []
    for num in sorted(TEST_QUERIES.keys()):
        results.append(run_single_query(num, verbose))
        # Small delay between queries to avoid overwhelming the system
        time.sleep(1)
    return results


def print_summary(results: List[Dict[str, Any]]):
    """Print summary of all test results."""
    print("\n" + "=" * 80)
    print("QUERY VARIATIONS TEST SUMMARY")
    print("=" * 80)
    print(f"Process ID: {PROCESS_ID}")
    print(f"Document: German Particle Contamination Report")
    print(f"Target Row: Ges.-Mittel.")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    total = len(results)
    passed = sum(1 for r in results if r.get('success') and r.get('result_count', 0) > 0)
    good_quality = sum(1 for r in results if r.get('data_quality') == 'GOOD')

    print(f"\nOverall Results:")
    print(f"  Total Queries: {total}")
    print(f"  Passed (success + results): {passed}/{total} ({100*passed/total:.1f}%)")
    print(f"  Good Data Quality: {good_quality}/{total} ({100*good_quality/total:.1f}%)")

    total_duration = sum(r.get('duration', 0) for r in results)
    avg_duration = total_duration / total if total > 0 else 0
    print(f"  Total Duration: {total_duration:.1f}s")
    print(f"  Avg Duration: {avg_duration:.1f}s per query")

    # By difficulty
    print("\nResults by Difficulty:")
    for diff in ['medium', 'hard']:
        diff_results = [r for r in results if r.get('difficulty') == diff]
        if diff_results:
            diff_passed = sum(1 for r in diff_results if r.get('success') and r.get('result_count', 0) > 0)
            print(f"  {diff.upper()}: {diff_passed}/{len(diff_results)} passed")

    # By category
    print("\nResults by Category:")
    categories = set(r.get('category') for r in results)
    for cat in sorted(categories):
        cat_results = [r for r in results if r.get('category') == cat]
        if cat_results:
            cat_passed = sum(1 for r in cat_results if r.get('success') and r.get('result_count', 0) > 0)
            print(f"  {cat}: {cat_passed}/{len(cat_results)} passed")

    # Detailed results table
    print("\n" + "-" * 100)
    print(f"{'#':<4} {'Query':<50} {'Status':<8} {'Results':<8} {'Quality':<10} {'Time':<8}")
    print("-" * 100)

    for r in results:
        query_short = r['query'][:47] + "..." if len(r['query']) > 50 else r['query']
        status = "PASS" if r.get('success') and r.get('result_count', 0) > 0 else "FAIL"
        result_count = r.get('result_count', 0)
        quality = r.get('data_quality', 'N/A')
        duration = r.get('duration', 0)
        print(f"{r['query_num']:<4} {query_short:<50} {status:<8} {result_count:<8} {quality:<10} {duration:.1f}s")

    print("-" * 100)

    # Issues found
    print("\nISSUES IDENTIFIED:")
    issues = []
    for r in results:
        if not r.get('success'):
            issues.append(f"  Query {r['query_num']}: FAILED - {r.get('error', 'Unknown error')[:100]}")
        elif r.get('result_count', 0) == 0:
            issues.append(f"  Query {r['query_num']}: No results returned")
        elif r.get('data_quality') == 'POOR':
            issues.append(f"  Query {r['query_num']}: Poor data quality - results don't match expected pattern")
        elif r.get('data_quality') == 'PARTIAL':
            issues.append(f"  Query {r['query_num']}: Partial match - some expected data missing")

    if issues:
        for issue in issues:
            print(issue)
    else:
        print("  No issues found - all queries passed with good data quality")

    print("=" * 80 + "\n")


def main():
    """Main entry point."""
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    # Filter out verbose flag from args
    args = [a for a in sys.argv[1:] if a not in ['--verbose', '-v']]

    if len(args) == 0:
        print("Running ALL query variations...")
        results = run_all_queries(verbose)
        print_summary(results)
    else:
        try:
            query_num = int(args[0])
            run_single_query(query_num, verbose)
        except ValueError:
            print(f"Error: Unknown argument '{args[0]}'")
            print("\nUsage:")
            print("  python test_query_variations.py              # Run all queries")
            print("  python test_query_variations.py 1            # Run query 1 only")
            print("  python test_query_variations.py --verbose    # Verbose output")
            print("\nAvailable queries:")
            for num, info in sorted(TEST_QUERIES.items()):
                print(f"  {num}: [{info['difficulty']}] {info['query']}")


if __name__ == "__main__":
    main()
