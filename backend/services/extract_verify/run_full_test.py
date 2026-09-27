"""
FULL TEST v3: Optimized — parallel batches, combined extract+verify.
"""
import json
import sys
import time

sys.path.insert(0, "C:/Users/BAPATAR/Downloads/ocr-chatbot/backend")

from services.extract_verify.engine import ExtractVerifyEngine
from services.extract_verify.models import (
    ExtractVerifyRequest, ExtractionTask, VerificationTask,
)

PDF = r"C:\Users\BAPATAR\Downloads\OneDrive_2026-03-27\Document Parser Info\executed batch record.pdf"


def progress(event_type, data):
    ts = time.strftime("%H:%M:%S")
    tag = ""
    if "batch" in event_type:
        done = data.get("pages_done", "?")
        total = data.get("total_pages", "?")
        tag = f" [{done}/{total} pages]"
    elif event_type == "processing":
        tag = f" [mode={data.get('mode')}, batches={data.get('batches')}, parallel={data.get('max_parallel')}]"
    elif event_type == "complete":
        tag = f" [{data.get('total_extraction_rows')} rows, {data.get('total_time_s')}s]"
    print(f"  [{ts}] {event_type}{tag}")
    sys.stdout.flush()


def main():
    engine = ExtractVerifyEngine()

    request = ExtractVerifyRequest(
        pdf_path=PDF,
        extraction_tasks=[
            ExtractionTask(
                name="Charges",
                columns=["Step Number", "Material Name", "Material Number",
                          "Batch Number", "Target Charge", "Actual Charge", "Units"],
                description="Extract ALL charge/addition steps with materials and amounts. "
                            "Include commodity/equipment steps where a material and batch number "
                            "are recorded even if charge values are blank.",
            ),
            ExtractionTask(
                name="Samples",
                columns=["Step Number", "Sample Number", "B_and_P"],
                description="Extract ALL sample recordings with sample numbers and B&P identifiers.",
            ),
            ExtractionTask(
                name="Timed Steps",
                columns=["Step Number", "Instruction", "Start Time", "Stop Time"],
                description="Extract ALL timed steps. Keep Instruction under 50 words.",
            ),
            ExtractionTask(
                name="Weights",
                columns=["Step Number", "Gross", "Tare", "Net", "Units"],
                description="Extract ALL weight recordings (gross, tare, net) EXCLUDING charge weights.",
            ),
            ExtractionTask(
                name="Blank Entries",
                columns=["Step Number", "Description"],
                description="Step numbers with blank entry lines. Keep Description under 15 words.",
            ),
        ],
        verification_tasks=[
            VerificationTask(
                name="Batch Number Consistency",
                check_type="consistency",
                instruction="Main process batch number must be consistent throughout. "
                            "Only flag process batch discrepancies, not material batch numbers.",
            ),
            VerificationTask(
                name="Process Order Consistency",
                check_type="consistency",
                instruction="Process order number must be consistent throughout.",
            ),
            VerificationTask(
                name="Column Completeness",
                check_type="completeness",
                instruction="Fourth column must have entry line. Weigh rows need Scale in third column.",
            ),
            VerificationTask(
                name="Material Number Cross-Reference",
                check_type="cross_reference",
                instruction="8-digit material numbers in steps must appear in Materials Needed table.",
            ),
            VerificationTask(
                name="Materials Table Cross-Reference",
                check_type="cross_reference",
                instruction="Material numbers in Materials table must appear elsewhere in record.",
            ),
            VerificationTask(
                name="Equipment Cross-Reference",
                check_type="cross_reference",
                instruction="Equipment in Equipment table must appear elsewhere in record.",
            ),
            VerificationTask(
                name="Start Stop Time Format",
                check_type="format",
                instruction="Start/Stop must be: Start___Hrs Date___ / Stop___Hrs Date___. "
                            "NLT/NMT steps must have both start and stop lines.",
            ),
        ],
        page_range=None,
    )

    print("=" * 70)
    print("OPTIMIZED TEST: 99 PAGES | PARALLEL COMBINED BATCHES")
    print("=" * 70)
    sys.stdout.flush()

    start = time.time()
    response = engine.run(request, progress_callback=progress)
    elapsed = time.time() - start

    print()
    print("=" * 70)
    print(f"COMPLETED in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Model: {response.model_used} | Batches: {response.batches_used}")
    print(f"Pages: {response.pages_analyzed}/{response.total_pages}")
    if response.errors:
        print(f"ERRORS: {response.errors}")
    print("=" * 70)

    # EXTRACTION
    print()
    print("POST-REVIEW: EXTRACTION")
    print("-" * 40)
    total_rows = 0
    for result in response.extraction_results:
        total_rows += result.row_count
        print(f"  {result.task_name}: {result.row_count} rows")
        for i, row in enumerate(result.rows[:5], 1):
            vals = " | ".join(f"{k}={v}" for k, v in row.data.items() if v is not None and str(v).strip())
            print(f"    [{i}] Pg {row.page}: {vals[:130]}")
        if result.row_count > 5:
            print(f"    ... +{result.row_count - 5} more")
    print(f"  TOTAL: {total_rows} rows")

    # VERIFICATION
    print()
    print("PRE-REVIEW: VERIFICATION")
    print("-" * 40)
    for result in response.verification_results:
        icon = {"pass": "PASS", "fail": "FAIL", "warning": "WARN"}.get(result.status, "???")
        findings_text = f", {len(result.findings)} findings" if result.findings else ""
        print(f"  {result.task_name}: [{icon}]{findings_text}")
        for f in result.findings[:3]:
            pg = f"Pg {f.page}" if f.page else "   "
            print(f"    {pg}: {f.issue[:100]}")
        if len(result.findings) > 3:
            print(f"    ... +{len(result.findings) - 3} more")

    # Save
    out = r"C:\Users\BAPATAR\Downloads\ocr-chatbot\backend\services\extract_verify\full_test_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(response.model_dump(), f, indent=2, default=str, ensure_ascii=False)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
