"""
Test script for Extract & Verify Engine.
Tests both extraction (post-review) and verification (pre-review) against the 99-page executed batch record.
"""
import json
import sys
import time
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.extract_verify.engine import ExtractVerifyEngine
from services.extract_verify.models import (
    ExtractVerifyRequest,
    ExtractionTask,
    VerificationTask,
)
from services.extract_verify.utils import get_pdf_page_count, pdf_to_jpeg_pages

PDF_PATH = r"C:\Users\BAPATAR\Downloads\OneDrive_2026-03-27\Document Parser Info\executed batch record.pdf"


def progress_handler(event_type, data):
    """Print progress events in real-time."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"  [{timestamp}] {event_type}: {json.dumps(data, default=str)[:200]}")


def test_stage_1_pdf_info():
    """Stage 1: Check PDF basics."""
    print("\n" + "=" * 70)
    print("STAGE 1: PDF Info")
    print("=" * 70)

    count = get_pdf_page_count(PDF_PATH)
    print(f"  PDF: {PDF_PATH}")
    print(f"  Total pages: {count}")
    file_size = os.path.getsize(PDF_PATH)
    print(f"  File size: {file_size / (1024*1024):.1f} MB")
    return count


def test_stage_2_render_pages():
    """Stage 2: Test JPEG rendering for a few pages."""
    print("\n" + "=" * 70)
    print("STAGE 2: Page Rendering (first 3 pages)")
    print("=" * 70)

    start = time.time()
    images = pdf_to_jpeg_pages(PDF_PATH, pages=[1, 2, 3], zoom=1.5, quality=85)
    elapsed = time.time() - start

    for page_num, img_b64 in images.items():
        size_kb = len(img_b64) * 3 / 4 / 1024  # base64 to bytes approx
        print(f"  Page {page_num}: {size_kb:.0f} KB (base64 len: {len(img_b64)})")

    print(f"  Render time: {elapsed:.1f}s")
    return images


def test_stage_3_single_page_extraction():
    """Stage 3: Test extraction on a small page range (pages 1-5)."""
    print("\n" + "=" * 70)
    print("STAGE 3: Small Extraction Test (pages 1-5)")
    print("=" * 70)

    engine = ExtractVerifyEngine()
    request = ExtractVerifyRequest(
        pdf_path=PDF_PATH,
        extraction_tasks=[
            ExtractionTask(
                name="Charges",
                columns=["Step Number", "Material Name", "Material Number", "Batch Number", "Target Charge", "Actual Charge", "Units"],
                description="Extract all charge/addition steps with materials and amounts",
                pages=[1, 2, 3, 4, 5],
            ),
        ],
        verification_tasks=[],
        page_range=[1, 2, 3, 4, 5],
    )

    start = time.time()
    response = engine.run(request, progress_callback=progress_handler)
    elapsed = time.time() - start

    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  Model used: {response.model_used}")
    print(f"  Pages analyzed: {response.pages_analyzed}")
    print(f"  Errors: {response.errors}")

    for result in response.extraction_results:
        print(f"\n  Task: {result.task_name}")
        print(f"  Rows found: {result.row_count}")
        for row in result.rows[:5]:
            print(f"    Page {row.page}: {json.dumps(row.data, default=str)[:150]}")
        if result.row_count > 5:
            print(f"    ... and {result.row_count - 5} more rows")

    return response


def test_stage_4_verification():
    """Stage 4: Test verification (pre-review) on a page range."""
    print("\n" + "=" * 70)
    print("STAGE 4: Verification Test (pages 1-10)")
    print("=" * 70)

    engine = ExtractVerifyEngine()
    request = ExtractVerifyRequest(
        pdf_path=PDF_PATH,
        extraction_tasks=[],
        verification_tasks=[
            VerificationTask(
                name="Batch Number Consistency",
                check_type="consistency",
                instruction="Check that every batch number referenced throughout these pages is identical. Report any discrepancies with page numbers.",
                pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            ),
            VerificationTask(
                name="Material Number Cross-Reference",
                check_type="cross_reference",
                instruction="Check if any 8-digit material numbers appear in step instructions. If so, verify the same numbers appear in the Materials Needed table. Report any missing cross-references.",
                pages=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            ),
        ],
        page_range=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    )

    start = time.time()
    response = engine.run(request, progress_callback=progress_handler)
    elapsed = time.time() - start

    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  Model used: {response.model_used}")
    print(f"  Errors: {response.errors}")

    for result in response.verification_results:
        print(f"\n  Task: {result.task_name}")
        print(f"  Status: {result.status}")
        print(f"  Findings: {len(result.findings)}")
        for f in result.findings[:5]:
            print(f"    Page {f.page}: {f.issue} — {f.details[:100]}")

    return response


def test_stage_5_full_extraction():
    """Stage 5: Full extraction test — all 5 extraction types on 30 pages."""
    print("\n" + "=" * 70)
    print("STAGE 5: Full Extraction (30 pages, all task types)")
    print("=" * 70)

    engine = ExtractVerifyEngine()
    request = ExtractVerifyRequest(
        pdf_path=PDF_PATH,
        extraction_tasks=[
            ExtractionTask(
                name="Charges",
                columns=["Step Number", "Material Name", "Material Number", "Batch Number", "Target Charge", "Actual Charge", "Units"],
                description="Extract all charge/addition steps with materials and amounts",
            ),
            ExtractionTask(
                name="Samples",
                columns=["Step Number", "Sample Number", "B&P"],
                description="Extract all sample recordings with sample numbers and B&P identifiers",
            ),
            ExtractionTask(
                name="Timed Steps",
                columns=["Step Number", "Instruction", "Start Time", "Stop Time"],
                description="Extract all timed steps with start and stop times including mixes, additions, temperature adjustments",
            ),
            ExtractionTask(
                name="Weights",
                columns=["Step Number", "Gross", "Tare", "Net", "Units"],
                description="Extract all weight recordings (gross, tare, net) excluding charge weights",
            ),
        ],
        verification_tasks=[],
        page_range=list(range(1, 31)),  # First 30 pages
    )

    start = time.time()
    response = engine.run(request, progress_callback=progress_handler)
    elapsed = time.time() - start

    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  Model used: {response.model_used}")
    print(f"  Pages analyzed: {response.pages_analyzed}")
    print(f"  Errors: {response.errors}")

    for result in response.extraction_results:
        print(f"\n  === {result.task_name} ===")
        print(f"  Rows found: {result.row_count}")
        for row in result.rows[:3]:
            print(f"    Page {row.page}: {json.dumps(row.data, default=str)[:150]}")
        if result.row_count > 3:
            print(f"    ... and {result.row_count - 3} more rows")

    return response


def test_stage_6_combined():
    """Stage 6: Combined extraction + verification on 20 pages."""
    print("\n" + "=" * 70)
    print("STAGE 6: Combined Extract + Verify (20 pages)")
    print("=" * 70)

    engine = ExtractVerifyEngine()
    request = ExtractVerifyRequest(
        pdf_path=PDF_PATH,
        extraction_tasks=[
            ExtractionTask(
                name="Charges",
                columns=["Step Number", "Material Name", "Material Number", "Batch Number", "Target Charge", "Actual Charge", "Units"],
                description="Extract all charge/addition steps",
            ),
        ],
        verification_tasks=[
            VerificationTask(
                name="Batch Number Consistency",
                check_type="consistency",
                instruction="Every batch number called out throughout must be identical. Report any batch number that differs.",
            ),
            VerificationTask(
                name="Column Completeness",
                check_type="completeness",
                instruction="For rows with 'weigh' instruction in the second column, the third column must contain 'Scale'. Record step numbers where this is missing.",
            ),
            VerificationTask(
                name="Start Stop Format",
                check_type="format",
                instruction="Start/Stop time entries must appear as 'Start___Hrs Date___' and 'Stop___Hrs Date___'. Report any that don't match this format.",
            ),
        ],
        page_range=list(range(1, 21)),  # First 20 pages
    )

    start = time.time()
    response = engine.run(request, progress_callback=progress_handler)
    elapsed = time.time() - start

    print(f"\n  Completed in {elapsed:.1f}s")
    print(f"  Model used: {response.model_used}")
    print(f"  Errors: {response.errors}")

    print(f"\n  --- EXTRACTION RESULTS ---")
    for result in response.extraction_results:
        print(f"  {result.task_name}: {result.row_count} rows")
        for row in result.rows[:3]:
            print(f"    Page {row.page}: {json.dumps(row.data, default=str)[:120]}")

    print(f"\n  --- VERIFICATION RESULTS ---")
    for result in response.verification_results:
        print(f"  {result.task_name}: {result.status.upper()}")
        for f in result.findings[:3]:
            print(f"    Page {f.page}: {f.issue[:100]}")

    return response


if __name__ == "__main__":
    print("=" * 70)
    print("EXTRACT & VERIFY ENGINE — FULL TEST SUITE")
    print(f"PDF: executed batch record (99 pages, 47MB)")
    print("=" * 70)

    # Run stages sequentially
    try:
        test_stage_1_pdf_info()
        test_stage_2_render_pages()
        test_stage_3_single_page_extraction()
        test_stage_4_verification()
        test_stage_5_full_extraction()
        test_stage_6_combined()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("TEST SUITE COMPLETE")
    print("=" * 70)
