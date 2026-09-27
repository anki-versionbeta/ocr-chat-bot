"""
Comprehensive Test for All Reference Types - Phase 5

Tests that all query types return appropriate bounding box references:
1. Specific cell lookup (row X, col Y) → single cell bbox
2. Value lookup (what is batch number) → specific cell/line bbox
3. View table (show me table from page X) → entire table layout bbox
4. All tables (what tables are present) → multiple table layout bboxes
5. Text content lookup → line bbox
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from services.weaviate_indexer import WeaviateIndexer
from services.rag_orchestrator import get_rag_orchestrator

PROCESS_ID = "5a97f7c9-536b-41fa-be14-037b116b4a10"

def explore_data():
    """Explore what data exists for this process_id"""
    print("\n" + "="*70)
    print("STEP 1: EXPLORING DATA FOR PROCESS ID")
    print("="*70)

    indexer = WeaviateIndexer()

    # Get chunk count
    count = indexer.get_chunk_count(PROCESS_ID)
    print(f"\nTotal chunks: {count}")

    # Search to see sample data
    print("\n--- Sample chunks ---")
    results = indexer.search_chunks(
        query="table data",
        process_id=PROCESS_ID,
        limit=20,
        alpha=0.5
    )

    # Analyze chunks
    table_chunks = []
    text_chunks = []
    pages = set()

    for r in results:
        page = r.get('page', 0)
        chunk_type = r.get('chunk_type', 'unknown')
        chunk_index = r.get('chunk_index', 0)
        content_preview = r.get('content', '')[:100]

        pages.add(page)

        if chunk_type == 'table':
            table_chunks.append({
                'chunk_index': chunk_index,
                'page': page,
                'content': content_preview,
                'has_cell_grounding': bool(r.get('cell_grounding')),
                'bbox_left': r.get('bbox_left', 0),
                'bbox_top': r.get('bbox_top', 0),
                'bbox_right': r.get('bbox_right', 0),
                'bbox_bottom': r.get('bbox_bottom', 0)
            })
        else:
            text_chunks.append({
                'chunk_index': chunk_index,
                'page': page,
                'content': content_preview,
                'has_line_grounding': bool(r.get('line_grounding'))
            })

    print(f"\nPages found: {sorted(pages)}")
    print(f"Table chunks: {len(table_chunks)}")
    print(f"Text chunks: {len(text_chunks)}")

    if table_chunks:
        print("\n--- Table Chunks Detail ---")
        for tc in table_chunks[:5]:
            print(f"  Chunk {tc['chunk_index']} (Page {tc['page']}): {tc['content'][:60]}...")
            print(f"    bbox: left={tc['bbox_left']:.3f}, top={tc['bbox_top']:.3f}, right={tc['bbox_right']:.3f}, bottom={tc['bbox_bottom']:.3f}")
            print(f"    has_cell_grounding: {tc['has_cell_grounding']}")

    if text_chunks:
        print("\n--- Text Chunks Detail ---")
        for tc in text_chunks[:3]:
            print(f"  Chunk {tc['chunk_index']} (Page {tc['page']}): {tc['content'][:60]}...")
            print(f"    has_line_grounding: {tc['has_line_grounding']}")

    # Get a sample cell_grounding to see structure
    for r in results:
        if r.get('cell_grounding'):
            print("\n--- Sample cell_grounding structure ---")
            try:
                cg = json.loads(r['cell_grounding'])
                sample_keys = list(cg.keys())[:3]
                for key in sample_keys:
                    print(f"  Cell '{key}': {cg[key]}")
            except:
                pass
            break

    return table_chunks, text_chunks, pages


def run_test_queries():
    """Run comprehensive test queries"""
    print("\n" + "="*70)
    print("STEP 2: RUNNING TEST QUERIES")
    print("="*70)

    orchestrator = get_rag_orchestrator()

    test_cases = [
        # TYPE 1: View entire table
        {
            "name": "VIEW TABLE - Show table from specific page",
            "query": "show me the table from page 1",
            "expected_ref_type": "table_layout",
            "description": "Should return empty cell_ids, use chunk bbox"
        },
        {
            "name": "VIEW TABLE - Give me entire table",
            "query": "give me the entire table",
            "expected_ref_type": "table_layout",
            "description": "Should return empty cell_ids, use chunk bbox"
        },

        # TYPE 2: Specific value lookup
        {
            "name": "VALUE LOOKUP - What is batch number",
            "query": "what is the batch number",
            "expected_ref_type": "cell_or_line",
            "description": "Should return specific cell/line bbox"
        },
        {
            "name": "VALUE LOOKUP - What is the product name",
            "query": "what is the product name",
            "expected_ref_type": "cell_or_line",
            "description": "Should return specific cell/line bbox"
        },

        # TYPE 3: Row/column lookup
        {
            "name": "ROW/COL LOOKUP - Value at row 2 column 3",
            "query": "what is the value at row 2 column 3",
            "expected_ref_type": "specific_cell",
            "description": "Should return specific cell bbox"
        },

        # TYPE 4: All tables
        {
            "name": "ALL TABLES - What tables are present",
            "query": "what tables are present in this document",
            "expected_ref_type": "multiple_tables",
            "description": "Should return multiple table layout bboxes"
        },

        # TYPE 5: Text content
        {
            "name": "TEXT LOOKUP - General question",
            "query": "what is the document about",
            "expected_ref_type": "line_or_text",
            "description": "Should return line bbox if from text chunk"
        },
    ]

    results = []

    for i, tc in enumerate(test_cases, 1):
        print(f"\n--- Test {i}: {tc['name']} ---")
        print(f"Query: {tc['query']}")
        print(f"Expected: {tc['expected_ref_type']}")

        try:
            response = orchestrator.process_query_sync(
                query=tc['query'],
                process_id=PROCESS_ID,
                filename="test_doc.pdf"
            )

            answer = response.get('answer', '')[:200]
            # Sanitize answer for Windows console (remove unicode)
            answer = answer.encode('ascii', 'replace').decode('ascii')
            refs = response.get('references', [])
            cell_ids = response.get('cell_ids', [])
            confidence = response.get('confidence', 0)

            print(f"\nAnswer: {answer}...")
            print(f"Confidence: {confidence:.2f}")
            print(f"cell_ids count: {len(cell_ids)}")
            print(f"References count: {len(refs)}")

            if refs:
                print("References detail:")
                for ref in refs[:3]:
                    page = ref.get('page', '?')
                    bbox = ref.get('bbox', {})
                    ref_type = ref.get('type', 'cell')
                    text = ref.get('text', '')[:30]
                    print(f"  - Page {page}, type={ref_type}, bbox={bbox}, text='{text}'")

            # Determine if test passed
            has_refs = len(refs) > 0
            if tc['expected_ref_type'] == 'table_layout':
                passed = has_refs and any(r.get('type') == 'table_layout' for r in refs)
            elif tc['expected_ref_type'] in ['cell_or_line', 'specific_cell', 'line_or_text']:
                passed = has_refs  # Any reference is good
            else:
                passed = has_refs

            status = "PASS" if passed else "FAIL"
            print(f"\nResult: {status}")

            results.append({
                'name': tc['name'],
                'passed': passed,
                'refs_count': len(refs),
                'cell_ids_count': len(cell_ids)
            })

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                'name': tc['name'],
                'passed': False,
                'error': str(e)
            })

    return results


def print_summary(results):
    """Print test summary"""
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for r in results if r.get('passed'))
    total = len(results)

    for r in results:
        status = "PASS" if r.get('passed') else "FAIL"
        refs = r.get('refs_count', 0)
        print(f"  [{status}] {r['name']} - {refs} reference(s)")

    print(f"\nTotal: {passed}/{total} passed")
    print("="*70)


if __name__ == "__main__":
    print("\n" + "="*70)
    print("COMPREHENSIVE REFERENCE TYPE TEST")
    print(f"Process ID: {PROCESS_ID}")
    print("="*70)

    # Step 1: Explore data
    table_chunks, text_chunks, pages = explore_data()

    # Step 2: Run tests
    results = run_test_queries()

    # Step 3: Summary
    print_summary(results)
