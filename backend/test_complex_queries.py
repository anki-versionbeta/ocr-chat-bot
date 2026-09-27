"""
Complex Query Tester for German Particle Contamination Report

Tests MORE COMPLEX and EDGE CASE queries against:
Process ID: f96d6d53-8257-4d3c-86b1-279f0e3ad069

Document Structure:
- "Ges.-Mittel." is at Row 7, Col 1 on pages 2-9
- Threshold columns at Row 1, Cols 2-8 (2,0 um through 50,0 um)
- Sample numbers at Row 8, Col 2 (SA00040984, SA00041012, etc.)

Test Categories:
1. Multi-page with specific columns
2. Cross-reference with filter
3. Aggregation queries
4. Row comparisons
5. German language queries
6. Special character handling
7. Non-existent data (graceful failure)
8. Wrong column names (error handling)

Usage:
    python test_complex_queries.py              # Run all edge case tests
    python test_complex_queries.py 1            # Run test case 1 only
    python test_complex_queries.py --verbose    # Verbose output

Created: 2026-02-20
Agent: Agent D - Complex Query Tester
"""

import sys
import json
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional

# Import the cypher generation function
from test_multiagent_cypher import run_fewshot_cypher_generation

# Process ID for the German particle contamination report
PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

# =============================================================================
# EDGE CASE TEST QUERIES
# =============================================================================

EDGE_CASE_QUERIES = {
    1: {
        "name": "Multi-page with specific columns",
        "query": "Get Ges.-Mittel. values for 2.0 um and 10.0 um columns only from all pages",
        "category": "multi_page_specific_columns",
        "difficulty": "hard",
        "expected_behavior": "Extract Ges.-Mittel. row values for ONLY 2.0 um and 10.0 um columns across pages 2-9",
        "expected_columns": ["2,0 um", "10,0 um"],
        "expected_pages": [2, 3, 4, 5, 6, 7, 8, 9],
        "validation": {
            "min_results": 8,  # At least 8 pages worth of data
            "must_contain_columns": ["2", "10"],  # Must contain these column references
            "must_not_contain": ["5,0", "15,0", "25,0", "40,0", "50,0"]  # Should NOT include other columns
        },
        "notes": "Tests ability to filter specific columns while extracting from multiple pages"
    },

    2: {
        "name": "Cross-reference with filter",
        "query": "Show Ges.-Mittel. data only for samples starting with SA00040",
        "category": "cross_reference_filter",
        "difficulty": "hard",
        "expected_behavior": "Filter results to only show data for samples with IDs starting with SA00040",
        "expected_samples": ["SA00040984"],
        "validation": {
            "min_results": 1,
            "must_contain": ["SA00040", "Ges.-Mittel", "Mittel"],
            "must_not_contain": ["SA00041"]  # Should filter out SA00041xxx samples
        },
        "notes": "Tests cross-referencing sample IDs with row data and applying prefix filter"
    },

    3: {
        "name": "Aggregation query",
        "query": "What is the average Ges.-Mittel. value for the 2.0 um column across all pages?",
        "category": "aggregation",
        "difficulty": "hard",
        "expected_behavior": "Calculate average of numeric values in 2.0 um column for Ges.-Mittel. row across all pages",
        "validation": {
            "min_results": 1,
            "must_contain": ["average", "avg", "mean", "2"],  # Should mention average calculation
            "result_type": "numeric"  # Result should be a number
        },
        "notes": "Tests aggregation (AVG) across multiple pages - requires numeric extraction"
    },

    4: {
        "name": "Row comparison",
        "query": "Compare Testfl. 1 - Mittelwert with Ges.-Mittel. for the 2.0 um column",
        "category": "row_comparison",
        "difficulty": "hard",
        "expected_behavior": "Extract and compare values from two different rows for the same column",
        "expected_rows": ["Testfl. 1 - Mittelwert", "Ges.-Mittel."],
        "validation": {
            "min_results": 2,  # Need at least 2 rows worth of data
            "must_contain": ["Testfl", "Mittel", "2"],  # Should have both row types
        },
        "notes": "Tests comparison between multiple named rows for a specific column"
    },

    5: {
        "name": "German with exact punctuation",
        "query": "Extrahiere alle Ges.-Mittel. Werte",
        "category": "german_language",
        "difficulty": "medium",
        "expected_behavior": "Understand German query and extract Ges.-Mittel. values",
        "validation": {
            "min_results": 1,
            "must_contain": ["Ges", "Mittel"],  # Should find the German row
        },
        "notes": "Tests German language understanding - 'Extrahiere alle X Werte' = 'Extract all X values'"
    },

    6: {
        "name": "Column header with special chars",
        "query": "Get all values under the '>=2,0 um' column header",
        "category": "special_characters",
        "difficulty": "hard",
        "expected_behavior": "Handle special characters (>=) in column header search",
        "validation": {
            "min_results": 1,
            "must_contain": ["2"],  # Should find 2,0 um column data
        },
        "notes": "Tests handling of special characters like >= in column headers"
    },

    7: {
        "name": "Non-existent row (graceful failure)",
        "query": "Get the 'Durchschnitt' row values",
        "category": "error_handling_nonexistent",
        "difficulty": "easy",
        "expected_behavior": "Return empty results or helpful message - 'Durchschnitt' does not exist",
        "should_fail_gracefully": True,
        "validation": {
            "max_results": 0,  # Should return no results
            "accept_empty": True,
            "error_should_be_helpful": True
        },
        "notes": "'Durchschnitt' (German for 'average') is NOT a row label in this document - should fail gracefully"
    },

    8: {
        "name": "Wrong column name (error handling)",
        "query": "Get Ges.-Mittel. for the '100.0 um' column",
        "category": "error_handling_wrong_column",
        "difficulty": "easy",
        "expected_behavior": "Return empty results or helpful message - 100.0 um column does not exist",
        "should_fail_gracefully": True,
        "validation": {
            "max_results": 0,  # Should return no results
            "accept_empty": True,
            "error_should_be_helpful": True
        },
        "notes": "100.0 um column does NOT exist (only goes up to 50.0 um) - should fail gracefully"
    }
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def validate_results(results: List[Any], validation: Dict[str, Any], natural_answer: str = "") -> Dict[str, Any]:
    """
    Validate query results against expected criteria.
    Returns validation report with pass/fail status and details.
    """
    validation_report = {
        "passed": True,
        "checks": [],
        "issues": []
    }

    # Check minimum results
    if "min_results" in validation:
        min_req = validation["min_results"]
        actual = len(results)
        passed = actual >= min_req
        validation_report["checks"].append({
            "name": "min_results",
            "expected": f">= {min_req}",
            "actual": actual,
            "passed": passed
        })
        if not passed:
            validation_report["passed"] = False
            validation_report["issues"].append(f"Expected at least {min_req} results, got {actual}")

    # Check maximum results (for expected failures)
    if "max_results" in validation:
        max_req = validation["max_results"]
        actual = len(results)
        passed = actual <= max_req
        validation_report["checks"].append({
            "name": "max_results",
            "expected": f"<= {max_req}",
            "actual": actual,
            "passed": passed
        })
        if not passed and not validation.get("accept_empty", False):
            validation_report["passed"] = False
            validation_report["issues"].append(f"Expected at most {max_req} results, got {actual}")

    # Check must_contain patterns
    if "must_contain" in validation:
        results_str = json.dumps(results, default=str).lower() + " " + natural_answer.lower()
        for pattern in validation["must_contain"]:
            found = pattern.lower() in results_str
            validation_report["checks"].append({
                "name": f"must_contain_{pattern}",
                "expected": f"Contains '{pattern}'",
                "actual": "Found" if found else "Not found",
                "passed": found
            })
            if not found:
                validation_report["passed"] = False
                validation_report["issues"].append(f"Results should contain '{pattern}' but don't")

    # Check must_not_contain patterns
    if "must_not_contain" in validation:
        results_str = json.dumps(results, default=str).lower()
        for pattern in validation["must_not_contain"]:
            found = pattern.lower() in results_str
            validation_report["checks"].append({
                "name": f"must_not_contain_{pattern}",
                "expected": f"Does NOT contain '{pattern}'",
                "actual": "Found (BAD)" if found else "Not found (GOOD)",
                "passed": not found
            })
            if found:
                validation_report["passed"] = False
                validation_report["issues"].append(f"Results should NOT contain '{pattern}' but do")

    # Check must_contain_columns
    if "must_contain_columns" in validation:
        results_str = json.dumps(results, default=str)
        for col in validation["must_contain_columns"]:
            found = col in results_str
            validation_report["checks"].append({
                "name": f"must_contain_column_{col}",
                "expected": f"Contains column reference '{col}'",
                "actual": "Found" if found else "Not found",
                "passed": found
            })
            if not found:
                validation_report["passed"] = False
                validation_report["issues"].append(f"Results should contain column '{col}' data")

    return validation_report


def analyze_query_result(result: Dict[str, Any], test_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a query result and produce detailed report.
    """
    analysis = {
        "success": result.get("success", False),
        "result_count": result.get("result_count", 0),
        "iterations": result.get("iterations", 0),
        "has_natural_answer": bool(result.get("natural_answer", "")),
        "cypher_generated": bool(result.get("cypher", result.get("generated_cypher", ""))),
        "errors": []
    }

    # Check for errors
    if result.get("error"):
        analysis["errors"].append(result["error"])

    # Check for expected failure scenarios
    if test_info.get("should_fail_gracefully", False):
        if analysis["result_count"] == 0:
            analysis["graceful_failure"] = True
            analysis["success"] = True  # This is expected behavior
        else:
            analysis["graceful_failure"] = False
            analysis["notes"] = "Query returned results when it should have failed gracefully"

    # Validate results if validation criteria provided
    if "validation" in test_info:
        results_data = result.get("results", [])
        natural_answer = result.get("natural_answer", "")
        validation_report = validate_results(results_data, test_info["validation"], natural_answer)
        analysis["validation"] = validation_report

        # Override success based on validation
        if not validation_report["passed"]:
            analysis["success"] = False

    return analysis


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_single_test(test_num: int, verbose: bool = False) -> Dict[str, Any]:
    """
    Run a single edge case test and return detailed results.
    """
    if test_num not in EDGE_CASE_QUERIES:
        print(f"ERROR: Test case {test_num} not found. Available: {list(EDGE_CASE_QUERIES.keys())}")
        return {"error": "Test case not found", "test_num": test_num, "success": False}

    test_info = EDGE_CASE_QUERIES[test_num]

    print("\n" + "=" * 100)
    print(f"EDGE CASE TEST #{test_num}: {test_info['name']}")
    print("=" * 100)
    print(f"Query: {test_info['query']}")
    print(f"Category: {test_info['category']}")
    print(f"Difficulty: {test_info['difficulty']}")
    print(f"Expected Behavior: {test_info['expected_behavior']}")
    print(f"Notes: {test_info['notes']}")
    if test_info.get("should_fail_gracefully"):
        print(">>> EXPECTED TO FAIL GRACEFULLY (no results expected)")
    print("=" * 100)

    start_time = time.time()

    try:
        result = run_fewshot_cypher_generation(
            user_query=test_info['query'],
            process_id=PROCESS_ID,
            max_iterations=2  # Reduced from 3 to avoid long-running retries
        )
    except Exception as e:
        print(f"\nEXCEPTION during query execution:")
        traceback.print_exc()
        result = {
            "success": False,
            "error": str(e),
            "result_count": 0,
            "iterations": 0,
            "results": [],
            "exception": True
        }

    end_time = time.time()
    duration = end_time - start_time

    # Analyze the result
    analysis = analyze_query_result(result, test_info)

    # Extract key data
    cypher = result.get('cypher', result.get('generated_cypher', ''))
    natural_answer = result.get('natural_answer', '')
    results_data = result.get('results', [])

    # Print results
    print("\n" + "-" * 100)
    print("RESULTS")
    print("-" * 100)
    print(f"Overall Success: {'PASS' if analysis['success'] else 'FAIL'}")
    print(f"Result Count: {analysis['result_count']}")
    print(f"Iterations: {analysis['iterations']}")
    print(f"Duration: {duration:.2f}s")

    if analysis.get("graceful_failure"):
        print(f"Graceful Failure: YES (expected behavior)")

    if analysis.get("errors"):
        print(f"\nErrors:")
        for err in analysis["errors"]:
            print(f"  - {err[:200]}..." if len(str(err)) > 200 else f"  - {err}")

    # Print validation results
    if "validation" in analysis:
        print("\nValidation Checks:")
        for check in analysis["validation"]["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            print(f"  [{status}] {check['name']}: expected {check['expected']}, got {check['actual']}")

        if analysis["validation"]["issues"]:
            print("\nValidation Issues:")
            for issue in analysis["validation"]["issues"]:
                print(f"  - {issue}")

    if verbose:
        if cypher:
            print("\nGenerated Cypher:")
            print("-" * 50)
            print(cypher[:1500] + "..." if len(cypher) > 1500 else cypher)
            print("-" * 50)

        if natural_answer:
            print("\nNatural Language Answer:")
            print("-" * 50)
            try:
                print(natural_answer[:800] + "..." if len(natural_answer) > 800 else natural_answer)
            except UnicodeEncodeError:
                print(natural_answer.encode('ascii', 'replace').decode('ascii')[:800])
            print("-" * 50)

        if results_data:
            print(f"\nSample Results (first 5):")
            for i, row in enumerate(results_data[:5], 1):
                try:
                    row_str = json.dumps(row, indent=2, default=str, ensure_ascii=False)
                except:
                    row_str = str(row)
                print(f"  Result {i}:")
                try:
                    lines = row_str.split('\n')[:10]
                    for line in lines:
                        print(f"    {line}")
                    if len(row_str.split('\n')) > 10:
                        print("    ...")
                except UnicodeEncodeError:
                    print(f"    {row_str.encode('ascii', 'replace').decode('ascii')[:300]}...")

    print("=" * 100 + "\n")

    # Return full test report
    return {
        "test_num": test_num,
        "name": test_info["name"],
        "query": test_info["query"],
        "category": test_info["category"],
        "difficulty": test_info["difficulty"],
        "expected_behavior": test_info["expected_behavior"],
        "should_fail_gracefully": test_info.get("should_fail_gracefully", False),
        "success": analysis["success"],
        "result_count": analysis["result_count"],
        "iterations": analysis["iterations"],
        "duration": duration,
        "graceful_failure": analysis.get("graceful_failure", False),
        "validation": analysis.get("validation", {}),
        "errors": analysis.get("errors", []),
        "cypher": cypher,
        "natural_answer": natural_answer,
        "raw_results": results_data[:10]  # Keep first 10 for debugging
    }


def run_all_tests(verbose: bool = False) -> List[Dict[str, Any]]:
    """
    Run all edge case tests and return results.
    """
    results = []

    print("\n" + "#" * 100)
    print("# COMPLEX QUERY EDGE CASE TESTING")
    print("# Process ID: " + PROCESS_ID)
    print("# Total Test Cases: " + str(len(EDGE_CASE_QUERIES)))
    print("#" * 100 + "\n")

    for num in sorted(EDGE_CASE_QUERIES.keys()):
        result = run_single_test(num, verbose)
        results.append(result)
        # Small delay between tests
        time.sleep(2)

    return results


def print_summary(results: List[Dict[str, Any]]):
    """
    Print comprehensive summary of all test results.
    """
    print("\n" + "#" * 100)
    print("#" * 100)
    print("## EDGE CASE TEST SUMMARY")
    print("#" * 100)
    print(f"Process ID: {PROCESS_ID}")
    print(f"Document: German Particle Contamination Report (Ges.-Mittel.)")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Tests: {len(results)}")
    print("#" * 100)

    # Calculate statistics
    total = len(results)
    passed = sum(1 for r in results if r.get("success"))
    failed = total - passed

    graceful_failures = sum(1 for r in results if r.get("graceful_failure"))
    expected_failures = sum(1 for r in results if r.get("should_fail_gracefully"))

    total_duration = sum(r.get("duration", 0) for r in results)
    avg_duration = total_duration / total if total > 0 else 0

    # Overall stats
    print("\n" + "=" * 80)
    print("OVERALL STATISTICS")
    print("=" * 80)
    print(f"  Tests Passed: {passed}/{total} ({100*passed/total:.1f}%)")
    print(f"  Tests Failed: {failed}/{total} ({100*failed/total:.1f}%)")
    print(f"  Graceful Failures (expected): {graceful_failures}/{expected_failures}")
    print(f"  Total Duration: {total_duration:.1f}s")
    print(f"  Avg Duration: {avg_duration:.1f}s per test")

    # By category
    print("\n" + "-" * 80)
    print("RESULTS BY CATEGORY")
    print("-" * 80)
    categories = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"passed": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.get("success"):
            categories[cat]["passed"] += 1

    for cat, stats in sorted(categories.items()):
        pct = 100 * stats["passed"] / stats["total"] if stats["total"] > 0 else 0
        status = "OK" if pct == 100 else "ISSUES"
        print(f"  {cat:<40} {stats['passed']}/{stats['total']} ({pct:.0f}%) [{status}]")

    # By difficulty
    print("\n" + "-" * 80)
    print("RESULTS BY DIFFICULTY")
    print("-" * 80)
    difficulties = {}
    for r in results:
        diff = r.get("difficulty", "unknown")
        if diff not in difficulties:
            difficulties[diff] = {"passed": 0, "total": 0}
        difficulties[diff]["total"] += 1
        if r.get("success"):
            difficulties[diff]["passed"] += 1

    for diff in ["easy", "medium", "hard"]:
        if diff in difficulties:
            stats = difficulties[diff]
            pct = 100 * stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {diff.upper():<10} {stats['passed']}/{stats['total']} ({pct:.0f}%)")

    # Detailed results table
    print("\n" + "=" * 120)
    print("DETAILED RESULTS")
    print("=" * 120)
    print(f"{'#':<4} {'Name':<40} {'Category':<30} {'Status':<8} {'Results':<10} {'Time':<8}")
    print("-" * 120)

    for r in results:
        name = r["name"][:37] + "..." if len(r["name"]) > 40 else r["name"]
        cat = r["category"][:27] + "..." if len(r["category"]) > 30 else r["category"]
        status = "PASS" if r.get("success") else "FAIL"
        if r.get("graceful_failure"):
            status = "GRACEFUL"
        result_count = r.get("result_count", 0)
        duration = r.get("duration", 0)

        print(f"{r['test_num']:<4} {name:<40} {cat:<30} {status:<8} {result_count:<10} {duration:.1f}s")

    print("=" * 120)

    # Issues and bugs found
    print("\n" + "#" * 80)
    print("## ISSUES, BUGS, AND FAILURES FOUND")
    print("#" * 80)

    issues_found = []
    bugs_found = []

    for r in results:
        if not r.get("success") and not r.get("should_fail_gracefully"):
            # This is a real failure
            issue = {
                "test_num": r["test_num"],
                "name": r["name"],
                "category": r["category"],
                "query": r["query"],
                "errors": r.get("errors", []),
                "validation_issues": r.get("validation", {}).get("issues", [])
            }
            issues_found.append(issue)

            # Check for specific bug patterns
            if r.get("result_count", 0) == 0 and not r.get("should_fail_gracefully"):
                bugs_found.append({
                    "type": "NO_RESULTS",
                    "test": r["test_num"],
                    "description": f"Query '{r['query'][:50]}...' returned no results when data should exist"
                })

            if r.get("validation", {}).get("issues"):
                for val_issue in r["validation"]["issues"]:
                    if "should NOT contain" in val_issue:
                        bugs_found.append({
                            "type": "WRONG_DATA",
                            "test": r["test_num"],
                            "description": val_issue
                        })
                    elif "should contain" in val_issue:
                        bugs_found.append({
                            "type": "MISSING_DATA",
                            "test": r["test_num"],
                            "description": val_issue
                        })

        # Check for expected graceful failures that didn't fail gracefully
        if r.get("should_fail_gracefully") and not r.get("graceful_failure"):
            bugs_found.append({
                "type": "SHOULD_FAIL_BUT_DIDNT",
                "test": r["test_num"],
                "description": f"Test #{r['test_num']} should have returned no results for non-existent data but returned {r.get('result_count', 0)} results"
            })

    if issues_found:
        print("\n--- FAILED TESTS ---")
        for issue in issues_found:
            print(f"\nTest #{issue['test_num']}: {issue['name']}")
            print(f"  Category: {issue['category']}")
            print(f"  Query: {issue['query'][:80]}...")
            if issue["errors"]:
                print(f"  Errors:")
                for err in issue["errors"]:
                    print(f"    - {str(err)[:100]}...")
            if issue["validation_issues"]:
                print(f"  Validation Issues:")
                for vi in issue["validation_issues"]:
                    print(f"    - {vi}")
    else:
        print("\nNo failed tests found!")

    if bugs_found:
        print("\n--- BUGS/ISSUES IDENTIFIED ---")
        bug_types = {}
        for bug in bugs_found:
            bt = bug["type"]
            if bt not in bug_types:
                bug_types[bt] = []
            bug_types[bt].append(bug)

        for bt, bugs in bug_types.items():
            print(f"\n[{bt}] - {len(bugs)} occurrence(s):")
            for bug in bugs:
                print(f"  - Test #{bug['test']}: {bug['description'][:100]}...")
    else:
        print("\nNo bugs identified!")

    # Recommendations
    print("\n" + "#" * 80)
    print("## RECOMMENDATIONS")
    print("#" * 80)

    recommendations = []

    if any(r.get("category") == "aggregation" and not r.get("success") for r in results):
        recommendations.append("1. AGGREGATION: System may not support AVG/SUM/COUNT functions well. Consider adding aggregation examples to few-shot bank.")

    if any(r.get("category") == "multi_page_specific_columns" and not r.get("success") for r in results):
        recommendations.append("2. COLUMN FILTERING: Multi-column filtering across pages needs improvement. Ensure Cypher correctly selects specific columns.")

    if any(r.get("category") == "cross_reference_filter" and not r.get("success") for r in results):
        recommendations.append("3. CROSS-REFERENCE: Sample ID cross-referencing with row data may need better pattern matching in Cypher generation.")

    if any(r.get("category") == "german_language" and not r.get("success") for r in results):
        recommendations.append("4. GERMAN SUPPORT: German language queries may need additional NLP handling or translation preprocessing.")

    if any(r.get("category") == "special_characters" and not r.get("success") for r in results):
        recommendations.append("5. SPECIAL CHARS: Special characters (>=, <=, etc.) in column headers need proper escaping in Cypher queries.")

    if any(r.get("should_fail_gracefully") and not r.get("graceful_failure") for r in results):
        recommendations.append("6. ERROR HANDLING: Queries for non-existent data should return empty results with helpful messages, not incorrect data.")

    if not recommendations:
        recommendations.append("All test categories passed! System handles edge cases well.")

    for rec in recommendations:
        print(f"  {rec}")

    print("\n" + "#" * 100)
    print("## END OF REPORT")
    print("#" * 100 + "\n")

    # Return summary dict for programmatic use
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": 100 * passed / total if total > 0 else 0,
        "issues_found": len(issues_found),
        "bugs_found": len(bugs_found),
        "recommendations": recommendations
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point."""
    verbose = '--verbose' in sys.argv or '-v' in sys.argv

    # Filter out flags
    args = [a for a in sys.argv[1:] if a not in ['--verbose', '-v']]

    if len(args) == 0:
        # Run all tests
        print("Running ALL edge case tests...")
        print("This will test complex queries including:")
        print("  - Multi-page column filtering")
        print("  - Cross-reference with filters")
        print("  - Aggregation queries")
        print("  - Row comparisons")
        print("  - German language queries")
        print("  - Special character handling")
        print("  - Non-existent data (graceful failure)")
        print("  - Wrong column names (error handling)")
        print()

        results = run_all_tests(verbose)
        summary = print_summary(results)

        # Exit with appropriate code
        sys.exit(0 if summary["failed"] == 0 else 1)
    else:
        try:
            test_num = int(args[0])
            result = run_single_test(test_num, verbose)

            # Print single test verdict
            if result.get("success"):
                print(f"\n>>> TEST #{test_num} PASSED <<<\n")
                sys.exit(0)
            else:
                print(f"\n>>> TEST #{test_num} FAILED <<<\n")
                sys.exit(1)

        except ValueError:
            print(f"Error: Unknown argument '{args[0]}'")
            print("\nUsage:")
            print("  python test_complex_queries.py              # Run all edge case tests")
            print("  python test_complex_queries.py 1            # Run test case 1 only")
            print("  python test_complex_queries.py --verbose    # Verbose output")
            print("\nAvailable edge case tests:")
            for num, info in sorted(EDGE_CASE_QUERIES.items()):
                fail_note = " [EXPECTED FAILURE]" if info.get("should_fail_gracefully") else ""
                print(f"  {num}: [{info['difficulty']}] {info['name']}{fail_note}")
                print(f"      Query: {info['query'][:60]}...")
            sys.exit(1)


if __name__ == "__main__":
    main()
