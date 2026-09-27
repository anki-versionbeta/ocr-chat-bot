"""
Test Script for Multi-Agent GraphRAG System

Tests various query types to validate:
- Phase 1: Topology NEV (path validation)
- Phase 2: Success Bank (dynamic learning)
- Phase 3: Hard Constraints (mandatory node type selection)

Usage:
    python run_test_queries.py [query_number]
    python run_test_queries.py 1        # Run query 1 only
    python run_test_queries.py all      # Run all queries
    python run_test_queries.py easy     # Run easy queries only
    python run_test_queries.py hard     # Run hard queries only
"""

import sys
import json
from datetime import datetime
from test_multiagent_cypher import run_fewshot_cypher_generation

# Process ID for the MFI Stability Samples document
PROCESS_ID = "53e654a3-d0ce-47ed-9d7f-d5d676958d80"

# Test queries organized by category and difficulty
TEST_QUERIES = {
    # Category 1: Simple Value Lookup (Easy)
    1: {
        "query": "What is the Batch Name?",
        "category": "simple_lookup",
        "difficulty": "easy",
        "expected_node": "Line or Cell",
        "description": "Basic value lookup from header area"
    },
    2: {
        "query": "What is the Project Name?",
        "category": "simple_lookup",
        "difficulty": "easy",
        "expected_node": "Cell",
        "description": "Project name from table area"
    },
    3: {
        "query": "What is the Mean ECD value?",
        "category": "simple_lookup",
        "difficulty": "easy",
        "expected_node": "Cell",
        "description": "Mean value from ECD statistics"
    },
    4: {
        "query": "What is the Particle Count?",
        "category": "simple_lookup",
        "difficulty": "easy",
        "expected_node": "Cell",
        "description": "Particle count from summary"
    },

    # Category 2: Row Extraction (Medium)
    6: {
        "query": "Get all Count row values from the first ECD table",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_node": "Cell",
        "description": "Extract entire row by label"
    },
    7: {
        "query": "Get all Concentration values from the ECD table",
        "category": "row_extraction",
        "difficulty": "medium",
        "expected_node": "Cell",
        "description": "Extract Concentration row values"
    },

    # Category 3: Hard Queries (Second row, cross-page)
    8: {
        "query": "Get the second Count row values only, not the first one",
        "category": "second_row",
        "difficulty": "hard",
        "expected_node": "Cell",
        "description": "Must differentiate between two Count rows"
    },
    12: {
        "query": "Get Project Name and Count values from all pages",
        "category": "cross_page",
        "difficulty": "hard",
        "expected_node": "Cell",
        "description": "Cross-page aggregation with multiple fields"
    },
    14: {
        "query": "Get second Count row with Project Name for each page",
        "category": "cross_page_complex",
        "difficulty": "hard",
        "expected_node": "Cell",
        "description": "The hardest query - combines all challenges"
    },

    # Category 4: Line-based queries (Topology test)
    15: {
        "query": "What is the document title?",
        "category": "line_based",
        "difficulty": "easy",
        "expected_node": "Line",
        "description": "Tests Line node path"
    },
    16: {
        "query": "Who is the User that created this analysis?",
        "category": "line_based",
        "difficulty": "easy",
        "expected_node": "Line or Cell",
        "description": "User field lookup"
    },

    # Category 5: Mixed node type queries
    18: {
        "query": "Get Batch Name and all Count values from the table",
        "category": "mixed_nodes",
        "difficulty": "hard",
        "expected_node": "Line + Cell",
        "description": "Requires joining Line and Cell data"
    },

    # Category 6: Structural queries
    20: {
        "query": "What tables exist on page 1?",
        "category": "structural",
        "difficulty": "medium",
        "expected_node": "Table",
        "description": "Table enumeration"
    },
}


def run_single_query(query_num: int) -> dict:
    """Run a single test query and return results."""
    if query_num not in TEST_QUERIES:
        print(f"Error: Query {query_num} not found. Available: {list(TEST_QUERIES.keys())}")
        return {"error": "Query not found"}

    query_info = TEST_QUERIES[query_num]

    print("\n" + "=" * 80)
    print(f"TEST QUERY #{query_num}")
    print("=" * 80)
    print(f"Query: {query_info['query']}")
    print(f"Category: {query_info['category']}")
    print(f"Difficulty: {query_info['difficulty']}")
    print(f"Expected Node Type: {query_info['expected_node']}")
    print(f"Description: {query_info['description']}")
    print("=" * 80 + "\n")

    start_time = datetime.now()

    result = run_fewshot_cypher_generation(
        user_query=query_info['query'],
        process_id=PROCESS_ID,
        max_iterations=3
    )

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Print summary
    print("\n" + "=" * 80)
    print(f"QUERY #{query_num} RESULTS")
    print("=" * 80)
    print(f"Success: {result.get('success', False)}")
    print(f"Result Count: {result.get('result_count', 0)}")
    print(f"Iterations: {result.get('iterations', 0)}")
    print(f"Duration: {duration:.2f}s")

    if result.get('success') and result.get('results'):
        print(f"\nSample Result:")
        sample = result['results'][0] if result['results'] else {}
        print(f"  {json.dumps(sample, indent=2, default=str)[:500]}")

    print("=" * 80 + "\n")

    return {
        "query_num": query_num,
        "query": query_info['query'],
        "category": query_info['category'],
        "difficulty": query_info['difficulty'],
        "success": result.get('success', False),
        "result_count": result.get('result_count', 0),
        "iterations": result.get('iterations', 0),
        "duration": duration
    }


def run_queries_by_difficulty(difficulty: str) -> list:
    """Run all queries of a specific difficulty."""
    results = []
    for num, info in TEST_QUERIES.items():
        if info['difficulty'] == difficulty:
            results.append(run_single_query(num))
    return results


def run_all_queries() -> list:
    """Run all test queries."""
    results = []
    for num in sorted(TEST_QUERIES.keys()):
        results.append(run_single_query(num))
    return results


def print_summary(results: list):
    """Print summary of all test results."""
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total = len(results)
    passed = sum(1 for r in results if r.get('success'))

    print(f"\nOverall: {passed}/{total} queries passed ({100*passed/total:.1f}%)")

    # By difficulty
    for diff in ['easy', 'medium', 'hard']:
        diff_results = [r for r in results if TEST_QUERIES.get(r['query_num'], {}).get('difficulty') == diff]
        if diff_results:
            diff_passed = sum(1 for r in diff_results if r.get('success'))
            print(f"  {diff.upper()}: {diff_passed}/{len(diff_results)} passed")

    print("\nDetailed Results:")
    print("-" * 80)
    print(f"{'#':<4} {'Query':<45} {'Success':<8} {'Iters':<6} {'Time':<8}")
    print("-" * 80)

    for r in results:
        query_short = r['query'][:42] + "..." if len(r['query']) > 45 else r['query']
        status = "PASS" if r.get('success') else "FAIL"
        print(f"{r['query_num']:<4} {query_short:<45} {status:<8} {r.get('iterations', '-'):<6} {r.get('duration', 0):.1f}s")

    print("=" * 80)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run_test_queries.py [query_number|all|easy|medium|hard]")
        print("\nExamples:")
        print("  python run_test_queries.py 1      # Run query 1")
        print("  python run_test_queries.py 8      # Run query 8 (second Count row)")
        print("  python run_test_queries.py easy   # Run all easy queries")
        print("  python run_test_queries.py hard   # Run all hard queries")
        print("  python run_test_queries.py all    # Run all queries")
        print("\nAvailable queries:")
        for num, info in sorted(TEST_QUERIES.items()):
            print(f"  {num}: [{info['difficulty']}] {info['query'][:60]}")
        return

    arg = sys.argv[1].lower()

    if arg == "all":
        results = run_all_queries()
        print_summary(results)
    elif arg in ["easy", "medium", "hard"]:
        results = run_queries_by_difficulty(arg)
        print_summary(results)
    else:
        try:
            query_num = int(arg)
            run_single_query(query_num)
        except ValueError:
            print(f"Error: Unknown argument '{arg}'")
            print("Use: query number, 'all', 'easy', 'medium', or 'hard'")


if __name__ == "__main__":
    main()
