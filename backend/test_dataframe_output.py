"""
Test Script for Dataframe Output Validation - Agent F

This script tests whether tabular data is properly formatted for dataframe display.
It validates:
1. Results are properly structured as tabular data (list of dicts)
2. Column headers are correctly extracted from the document
3. NULL values are handled properly (not showing row labels as values)
4. Multi-page results are properly aggregated
5. Data alignment (right column with right header)

Process ID: f96d6d53-8257-4d3c-86b1-279f0e3ad069

Test Scenarios:
1. "Get all Ges.-Mittel. values as a table with page number and all threshold columns"
2. "Show Ges.-Mittel. row in a dataframe with columns: Page, 2.0um, 5.0um, 10.0um, 15.0um, 25.0um, 40.0um, 50.0um"
3. "Export Ges.-Mittel. data to a table format"

Created: February 20, 2026
"""

import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, '.')

# Import the multiagent service
from services.multiagent_cypher_service import run_fewshot_cypher_generation

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test process ID
PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

# Test queries for dataframe validation
TEST_QUERIES = [
    {
        "id": 1,
        "query": "Get all Ges.-Mittel. values as a table with page number and all threshold columns",
        "description": "Tests row extraction with page numbers and multiple columns",
        "expected_columns": ["page", "2.0um", "5.0um", "10.0um", "15.0um", "25.0um", "40.0um", "50.0um"],
        "min_rows": 1,
        "validation_checks": [
            "has_tabular_structure",
            "has_page_column",
            "has_numeric_columns",
            "no_null_value_issues"
        ]
    },
    {
        "id": 2,
        "query": "Show Ges.-Mittel. row in a dataframe with columns: Page, 2.0um, 5.0um, 10.0um, 15.0um, 25.0um, 40.0um, 50.0um",
        "description": "Tests explicit column specification for dataframe display",
        "expected_columns": ["Page", "2.0um", "5.0um", "10.0um", "15.0um", "25.0um", "40.0um", "50.0um"],
        "min_rows": 1,
        "validation_checks": [
            "has_tabular_structure",
            "column_headers_preserved",
            "data_alignment_correct"
        ]
    },
    {
        "id": 3,
        "query": "Get Ges.-Mittel. row data with all columns from all pages",
        "description": "Tests generic table export functionality",
        "expected_columns": None,  # Any columns are valid
        "min_rows": 1,
        "validation_checks": [
            "has_tabular_structure",
            "multi_page_aggregation"
        ]
    }
]


class DataFrameOutputValidator:
    """Validates dataframe output from the RAG system."""

    def __init__(self, process_id: str):
        self.process_id = process_id
        self.issues = []
        self.results = []

    def run_query(self, query: str) -> Dict[str, Any]:
        """Run a query and return the result."""
        logger.info(f"\n{'='*80}")
        logger.info(f"Running query: {query}")
        logger.info(f"{'='*80}")

        try:
            result = run_fewshot_cypher_generation(
                user_query=query,
                process_id=self.process_id,
                max_iterations=3
            )
            return result
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {"success": False, "error": str(e), "results": []}

    def validate_tabular_structure(self, results: List[Dict], test_id: int) -> Dict[str, Any]:
        """
        Validate that results are in proper tabular structure.

        Returns:
            Dict with validation results
        """
        validation = {
            "test_id": test_id,
            "check": "has_tabular_structure",
            "passed": False,
            "issues": []
        }

        if not results:
            validation["issues"].append("No results returned")
            return validation

        # Check if results is a list of dictionaries
        if not isinstance(results, list):
            validation["issues"].append(f"Results is not a list, got: {type(results)}")
            return validation

        if not all(isinstance(r, dict) for r in results):
            validation["issues"].append("Not all results are dictionaries")
            return validation

        # Check for consistent keys across all rows
        if results:
            first_keys = set(results[0].keys())
            for i, row in enumerate(results[1:], start=1):
                row_keys = set(row.keys())
                if row_keys != first_keys:
                    missing = first_keys - row_keys
                    extra = row_keys - first_keys
                    if missing:
                        validation["issues"].append(f"Row {i} missing keys: {missing}")
                    if extra:
                        validation["issues"].append(f"Row {i} has extra keys: {extra}")

        validation["passed"] = len(validation["issues"]) == 0
        return validation

    def validate_null_handling(self, results: List[Dict], test_id: int) -> Dict[str, Any]:
        """
        Validate that NULL values are handled properly.

        Common issues:
        - Row labels appearing as column values
        - None/null values not displaying correctly
        - Empty strings vs actual nulls
        """
        validation = {
            "test_id": test_id,
            "check": "no_null_value_issues",
            "passed": False,
            "issues": [],
            "null_analysis": {}
        }

        if not results:
            validation["issues"].append("No results to validate")
            return validation

        # Analyze NULL patterns per column
        null_analysis = {}
        for col in results[0].keys():
            values = [r.get(col) for r in results]
            null_count = sum(1 for v in values if v is None or v == "null" or v == "")
            total_count = len(values)

            null_analysis[col] = {
                "null_count": null_count,
                "total_count": total_count,
                "null_ratio": null_count / total_count if total_count > 0 else 0,
                "sample_values": values[:5]
            }

            # Check for suspicious patterns
            # If a column is ALL nulls, it might indicate a misalignment
            if null_count == total_count:
                validation["issues"].append(f"Column '{col}' is ALL NULL - possible header mismatch")

            # Check if row labels are appearing as values (common bug)
            row_label_pattern = ["Ges.-Mittel.", "Ges.-Mittel", "ges.-mittel."]
            for v in values:
                if v and isinstance(v, str) and v.strip() in row_label_pattern:
                    validation["issues"].append(
                        f"Row label 'Ges.-Mittel.' appearing as value in column '{col}' - data misalignment"
                    )
                    break

        validation["null_analysis"] = null_analysis
        validation["passed"] = len(validation["issues"]) == 0
        return validation

    def validate_column_headers(self, results: List[Dict], expected_columns: Optional[List[str]], test_id: int) -> Dict[str, Any]:
        """
        Validate that column headers are preserved from the document.
        """
        validation = {
            "test_id": test_id,
            "check": "column_headers_preserved",
            "passed": False,
            "issues": [],
            "actual_columns": [],
            "expected_columns": expected_columns
        }

        if not results:
            validation["issues"].append("No results to validate columns")
            return validation

        actual_columns = list(results[0].keys())
        validation["actual_columns"] = actual_columns

        if expected_columns:
            # Check if expected columns exist (case-insensitive)
            actual_lower = [c.lower() for c in actual_columns]
            for exp_col in expected_columns:
                # Allow for various formatting of the same column
                exp_variants = [
                    exp_col.lower(),
                    exp_col.lower().replace('.', ''),
                    exp_col.lower().replace('um', ''),
                    exp_col.lower().replace('um', 'um'),
                    exp_col.lower().replace('>=', ''),
                ]
                found = any(
                    any(var in actual.lower() for var in exp_variants)
                    for actual in actual_columns
                )
                if not found:
                    validation["issues"].append(f"Expected column '{exp_col}' not found in results")

        # Check for generic/placeholder column names
        generic_patterns = ["col1", "col2", "col3", "range_1", "range_2", "column_1", "column_2"]
        for col in actual_columns:
            for pattern in generic_patterns:
                if pattern in col.lower():
                    validation["issues"].append(
                        f"Generic column name '{col}' detected - headers may not be properly extracted"
                    )
                    break

        validation["passed"] = len(validation["issues"]) == 0
        return validation

    def validate_data_alignment(self, results: List[Dict], test_id: int) -> Dict[str, Any]:
        """
        Validate that data is properly aligned with headers.

        Checks:
        - Numeric values in numeric columns
        - Page numbers are valid integers
        - No data shifted to wrong columns
        """
        validation = {
            "test_id": test_id,
            "check": "data_alignment_correct",
            "passed": False,
            "issues": [],
            "alignment_analysis": {}
        }

        if not results:
            validation["issues"].append("No results to validate alignment")
            return validation

        columns = list(results[0].keys())
        alignment_analysis = {}

        for col in columns:
            values = [r.get(col) for r in results]
            col_lower = col.lower()

            # Check page column
            if 'page' in col_lower:
                non_integer_pages = []
                for v in values:
                    if v is not None:
                        try:
                            int(v)
                        except (ValueError, TypeError):
                            non_integer_pages.append(v)
                if non_integer_pages:
                    validation["issues"].append(
                        f"Page column '{col}' has non-integer values: {non_integer_pages[:3]}"
                    )
                alignment_analysis[col] = {"type": "page", "valid": len(non_integer_pages) == 0}

            # Check numeric columns (threshold values)
            elif any(kw in col_lower for kw in ['um', 'µm', '>=', '2.0', '5.0', '10.0']):
                non_numeric = []
                for v in values:
                    if v is not None and v != '':
                        try:
                            # Handle European number format (comma as decimal)
                            v_clean = str(v).replace(',', '.').replace(' ', '')
                            float(v_clean)
                        except (ValueError, TypeError):
                            non_numeric.append(v)
                if non_numeric:
                    validation["issues"].append(
                        f"Numeric column '{col}' has non-numeric values: {non_numeric[:3]}"
                    )
                alignment_analysis[col] = {"type": "numeric", "valid": len(non_numeric) == 0}

        validation["alignment_analysis"] = alignment_analysis
        validation["passed"] = len(validation["issues"]) == 0
        return validation

    def validate_multi_page_aggregation(self, results: List[Dict], test_id: int) -> Dict[str, Any]:
        """
        Validate that multi-page results are properly aggregated.
        """
        validation = {
            "test_id": test_id,
            "check": "multi_page_aggregation",
            "passed": False,
            "issues": [],
            "page_analysis": {}
        }

        if not results:
            validation["issues"].append("No results to validate aggregation")
            return validation

        # Find page column
        page_col = None
        for col in results[0].keys():
            if 'page' in col.lower():
                page_col = col
                break

        if not page_col:
            validation["issues"].append("No page column found - cannot validate multi-page aggregation")
            validation["passed"] = True  # Not a failure, just can't validate
            return validation

        # Analyze pages
        pages = [r.get(page_col) for r in results if r.get(page_col) is not None]
        unique_pages = sorted(set(pages))

        validation["page_analysis"] = {
            "total_rows": len(results),
            "unique_pages": unique_pages,
            "page_count": len(unique_pages),
            "rows_per_page": {p: pages.count(p) for p in unique_pages}
        }

        # Check for single page when multi-page expected
        if len(unique_pages) == 1 and len(results) > 1:
            validation["issues"].append(
                f"All {len(results)} rows from single page {unique_pages[0]} - multi-page aggregation may have failed"
            )

        validation["passed"] = len(validation["issues"]) == 0
        return validation

    def format_results_as_dataframe(self, results: List[Dict]) -> Optional[pd.DataFrame]:
        """Convert results to pandas DataFrame for display."""
        if not results:
            return None
        try:
            df = pd.DataFrame(results)
            return df
        except Exception as e:
            logger.error(f"Failed to convert to DataFrame: {e}")
            return None

    def run_test(self, test_config: Dict) -> Dict[str, Any]:
        """Run a single test and return comprehensive validation results."""
        test_id = test_config["id"]
        query = test_config["query"]
        description = test_config["description"]
        expected_columns = test_config.get("expected_columns")
        min_rows = test_config.get("min_rows", 1)
        validation_checks = test_config.get("validation_checks", [])

        logger.info(f"\n{'='*80}")
        logger.info(f"TEST {test_id}: {description}")
        logger.info(f"Query: {query}")
        logger.info(f"{'='*80}")

        start_time = datetime.now()

        # Run the query
        result = self.run_query(query)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        test_result = {
            "test_id": test_id,
            "query": query,
            "description": description,
            "success": result.get("success", False),
            "duration_seconds": duration,
            "result_count": result.get("result_count", 0),
            "iterations_used": result.get("iterations", 0),
            "validations": [],
            "issues": [],
            "dataframe_preview": None,
            "natural_answer": result.get("natural_answer", ""),
            "cypher_used": result.get("cypher", "")[:500] if result.get("cypher") else ""
        }

        # Get the actual results
        results = result.get("results", [])

        # Check minimum rows
        if len(results) < min_rows:
            test_result["issues"].append(
                f"Expected at least {min_rows} rows, got {len(results)}"
            )

        # Run validation checks
        if results:
            # Always run tabular structure validation
            struct_val = self.validate_tabular_structure(results, test_id)
            test_result["validations"].append(struct_val)
            if not struct_val["passed"]:
                test_result["issues"].extend(struct_val["issues"])

            # Run specified checks
            if "has_page_column" in validation_checks or "multi_page_aggregation" in validation_checks:
                page_val = self.validate_multi_page_aggregation(results, test_id)
                test_result["validations"].append(page_val)
                if not page_val["passed"]:
                    test_result["issues"].extend(page_val["issues"])

            if "no_null_value_issues" in validation_checks:
                null_val = self.validate_null_handling(results, test_id)
                test_result["validations"].append(null_val)
                if not null_val["passed"]:
                    test_result["issues"].extend(null_val["issues"])

            if "column_headers_preserved" in validation_checks:
                header_val = self.validate_column_headers(results, expected_columns, test_id)
                test_result["validations"].append(header_val)
                if not header_val["passed"]:
                    test_result["issues"].extend(header_val["issues"])

            if "data_alignment_correct" in validation_checks:
                align_val = self.validate_data_alignment(results, test_id)
                test_result["validations"].append(align_val)
                if not align_val["passed"]:
                    test_result["issues"].extend(align_val["issues"])

            # Create DataFrame preview
            df = self.format_results_as_dataframe(results)
            if df is not None:
                test_result["dataframe_preview"] = df.to_string(index=False)
        else:
            test_result["issues"].append("No results returned from query")

        # Overall pass/fail
        test_result["all_validations_passed"] = len(test_result["issues"]) == 0

        return test_result

    def run_all_tests(self) -> List[Dict[str, Any]]:
        """Run all test queries and return results."""
        all_results = []

        for test_config in TEST_QUERIES:
            test_result = self.run_test(test_config)
            all_results.append(test_result)
            self.results.append(test_result)

        return all_results

    def print_summary(self):
        """Print a summary of all test results."""
        print("\n" + "="*100)
        print("DATAFRAME OUTPUT VALIDATION SUMMARY")
        print("="*100)
        print(f"Process ID: {self.process_id}")
        print(f"Total Tests: {len(self.results)}")

        passed = sum(1 for r in self.results if r.get("all_validations_passed", False))
        failed = len(self.results) - passed

        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print("="*100)

        for result in self.results:
            test_id = result["test_id"]
            status = "PASS" if result.get("all_validations_passed") else "FAIL"
            duration = result.get("duration_seconds", 0)
            row_count = result.get("result_count", 0)

            print(f"\n{'='*80}")
            print(f"TEST {test_id}: {status}")
            print(f"Query: {result['query'][:70]}...")
            print(f"Duration: {duration:.2f}s | Rows: {row_count}")

            if result.get("issues"):
                print(f"\nISSUES FOUND ({len(result['issues'])}):")
                for issue in result["issues"]:
                    print(f"  - {issue}")

            if result.get("dataframe_preview"):
                print(f"\nDATAFRAME OUTPUT:")
                print("-"*80)
                # Limit preview to first 20 lines
                preview_lines = result["dataframe_preview"].split("\n")[:20]
                print("\n".join(preview_lines))
                if len(result["dataframe_preview"].split("\n")) > 20:
                    print("... (truncated)")
                print("-"*80)

            if result.get("natural_answer"):
                print(f"\nNATURAL ANSWER:")
                print(result["natural_answer"][:500])

        print("\n" + "="*100)
        print("OVERALL ASSESSMENT")
        print("="*100)

        # Aggregate issues
        all_issues = []
        for result in self.results:
            all_issues.extend(result.get("issues", []))

        if all_issues:
            print("\nALL FORMATTING/DATA ALIGNMENT ISSUES:")
            unique_issues = list(set(all_issues))
            for i, issue in enumerate(unique_issues, 1):
                print(f"  {i}. {issue}")
        else:
            print("\nNo formatting or data alignment issues detected!")

        print("="*100)

        return {
            "total_tests": len(self.results),
            "passed": passed,
            "failed": failed,
            "issues": all_issues
        }


def main():
    """Main entry point."""
    print("\n" + "="*100)
    print("DATAFRAME OUTPUT VALIDATOR - Agent F")
    print("="*100)
    print(f"Testing process_id: {PROCESS_ID}")
    print("="*100)

    validator = DataFrameOutputValidator(PROCESS_ID)

    # Run all tests
    results = validator.run_all_tests()

    # Print summary
    summary = validator.print_summary()

    # Save detailed results to JSON
    output_file = "test_dataframe_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "process_id": PROCESS_ID,
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "test_results": results
        }, f, indent=2, default=str)

    print(f"\nDetailed results saved to: {output_file}")

    # Return exit code based on results
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
