"""
AI Table Export Service — Gemini Vision-powered table extraction for Export with AI

Uses Gemini 2.5 Pro to re-extract table data from PDF page images,
producing more accurate results than raw Textract OCR (especially for handwritten docs).

Reuses:
- visual_audit_service.extract_page_as_image() for PDF → base64 PNG
- pdf_image_service.PDFImageService.get_pdf_path() for PDF file resolution
- table_export_service.export_all_tables_to_excel() for final Excel generation
"""

import os
import re
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .visual_audit_service import extract_page_as_image
from .table_export_service import export_all_tables_to_excel

ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

GEMINI_PRIMARY_MODEL = "gemini-2.5-pro"
GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash"]

MAX_PARALLEL_PAGES = 11

logger = logging.getLogger("ocr-chatbot.ai_table_export")


# =========================================================================
# MAIN ENTRY POINT
# =========================================================================

def export_tables_with_ai(
    process_id: str,
    tables_meta: List[Dict],
    tables_data_list: List[Dict],
    document_name: str = "",
    user_prompt: str = "",
    extraction_model: str = None
) -> str:
    """
    AI-powered table export: re-extracts table values from PDF images using Gemini Vision,
    then exports to Excel.

    Args:
        process_id: Document process ID
        tables_meta: List of table metadata from Neo4j, each with:
            {table_id, chunk_index, page_num, bbox_top, bbox_left, bbox_right, bbox_bottom}
        tables_data_list: Textract-extracted table data (same format as Export All).
            Used for column headers AND as fallback if AI extraction fails.
        document_name: Original document name for labeling

    Returns:
        Absolute file path of the generated Excel
    """
    # Resolve PDF path (same DB lookup as schema_routes.py)
    pdf_path = _resolve_pdf_path(process_id)
    if not pdf_path:
        logger.warning(f"[AI-Export] PDF not found for {process_id[:8]}, falling back to Textract data")
        return export_all_tables_to_excel(tables_data_list, document_name, process_id, ai_enhanced=True)

    logger.info(f"[AI-Export] Starting AI extraction for {len(tables_meta)} tables from {process_id[:8]}")

    # Group tables by page_num — we only need page number and deduplicated headers
    pages_to_tables: Dict[int, List[Dict]] = {}
    for i, meta in enumerate(tables_meta):
        page_num = meta.get("page_num", 1)
        if page_num not in pages_to_tables:
            pages_to_tables[page_num] = []
        # Deduplicate headers (Neo4j can have duplicates from merged header rows)
        raw_headers = tables_data_list[i]["headers"] if i < len(tables_data_list) else []
        deduped_headers = list(dict.fromkeys(raw_headers))  # preserves order, removes dupes
        pages_to_tables[page_num].append({
            "table_index_global": i,
            "headers": deduped_headers,
        })

    logger.info(f"[AI-Export] {len(pages_to_tables)} unique pages to process")

    # Process pages in parallel (max 3 concurrent)
    ai_results: Dict[int, List[Dict]] = {}  # page_num -> list of AI-extracted table data

    # Use user-selected model or default
    model = extraction_model if extraction_model else GEMINI_PRIMARY_MODEL
    logger.info(f"[AI-Export] Using extraction model: {model}")

    if user_prompt:
        logger.info(f"[AI-Export] User prompt: {user_prompt[:100]}")

    def process_page(page_num: int, tables_on_page: List[Dict]) -> tuple:
        """Process one page: render image, call Gemini, return results."""
        try:
            image_base64 = extract_page_as_image(pdf_path, page_num, zoom=2.0)
            if not image_base64:
                logger.warning(f"[AI-Export] Failed to render page {page_num}")
                return (page_num, None)

            result = _extract_page_tables_with_gemini(page_num, image_base64, tables_on_page, user_prompt, model)
            return (page_num, result)
        except Exception as e:
            logger.error(f"[AI-Export] Error processing page {page_num}: {e}")
            return (page_num, None)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PAGES) as executor:
        futures = {
            executor.submit(process_page, page_num, tables): page_num
            for page_num, tables in pages_to_tables.items()
        }
        for future in as_completed(futures):
            page_num = futures[future]
            try:
                pn, result = future.result()
                if result is not None:
                    ai_results[pn] = result
                    logger.info(f"[AI-Export] Page {pn}: AI extracted {len(result)} tables")
                else:
                    logger.warning(f"[AI-Export] Page {pn}: AI extraction failed, will use Textract fallback")
            except Exception as e:
                logger.error(f"[AI-Export] Page {page_num} future error: {e}")

    # Build the final tables_data_list with AI data where available, Textract fallback otherwise
    ai_tables_data_list = []
    ai_enhanced_count = 0

    for i, original_td in enumerate(tables_data_list):
        page_num = original_td.get("page_num", 1)
        replaced = False

        if page_num in ai_results:
            page_tables_on_this_page = pages_to_tables.get(page_num, [])
            local_idx = None
            for li, pt in enumerate(page_tables_on_this_page):
                if pt["table_index_global"] == i:
                    local_idx = li
                    break

            if local_idx is not None and local_idx < len(ai_results[page_num]):
                ai_table = ai_results[page_num][local_idx]
                if ai_table and ai_table.get("rows"):
                    deduped_headers = page_tables_on_this_page[local_idx]["headers"]
                    ai_td = {
                        "headers": deduped_headers,
                        "rows": _convert_ai_rows_to_export_format(ai_table["rows"], deduped_headers),
                        "page_num": original_td.get("page_num"),
                        "chunk_index": original_td.get("chunk_index"),
                    }
                    ai_tables_data_list.append(ai_td)
                    ai_enhanced_count += 1
                    replaced = True

        if not replaced:
            # Fallback: deduplicate headers for Textract data too
            raw_headers = original_td["headers"]
            deduped = list(dict.fromkeys(raw_headers))
            if len(deduped) < len(raw_headers):
                # Rebuild rows with only unique column positions
                keep_cols = []
                seen = set()
                for ci, h in enumerate(raw_headers):
                    if h not in seen:
                        keep_cols.append(ci)
                        seen.add(h)
                new_rows = []
                for row in original_td.get("rows", []):
                    cells = row.get("cells", [])
                    new_cells = [c for c in cells if c["col_index"] in keep_cols]
                    # Re-index col_index
                    for new_ci, cell in enumerate(new_cells):
                        cell["col_index"] = new_ci
                    new_rows.append({"row_index": row["row_index"], "cells": new_cells})
                ai_tables_data_list.append({
                    "headers": deduped,
                    "rows": new_rows,
                    "page_num": original_td.get("page_num"),
                    "chunk_index": original_td.get("chunk_index"),
                })
            else:
                ai_tables_data_list.append(original_td)

    logger.info(f"[AI-Export] {ai_enhanced_count}/{len(tables_data_list)} tables AI-enhanced, rest are Textract fallback")

    # Fix column shifts: detect and correct when Gemini returns data shifted right
    ai_tables_data_list = _fix_column_shifts(ai_tables_data_list)

    # Validation agent: review and fix extracted data before export
    ai_tables_data_list = _validate_and_fix_extracted_data(ai_tables_data_list)

    # Post-process: expand date/time columns into separate day/month/year/hour/minute columns
    ai_tables_data_list = _expand_date_time_columns(ai_tables_data_list)

    # Export to Excel
    filepath = export_all_tables_to_excel(ai_tables_data_list, document_name, process_id, ai_enhanced=True)
    return filepath


# =========================================================================
# GEMINI EXTRACTION (per page)
# =========================================================================

def _extract_page_tables_with_gemini(
    page_num: int,
    image_base64: str,
    tables_on_page: List[Dict],
    user_prompt_extra: str = "",
    model: str = GEMINI_PRIMARY_MODEL
) -> Optional[List[Dict]]:
    """
    Send one page image to Gemini and extract table data.

    Args:
        page_num: Page number (for logging)
        image_base64: Base64-encoded PNG of the page
        tables_on_page: List of tables on this page, each with:
            {headers}
        user_prompt_extra: Optional additional instructions from user

    Returns:
        List of dicts, one per table: {headers, rows} where rows is list of lists.
        None on failure.
    """
    user_prompt = _build_table_extraction_prompt(tables_on_page, user_prompt_extra)

    system_prompt = """You are a precise document table reader specialized in pharmaceutical/manufacturing documents.
You receive a page image and must extract table data with extremely high accuracy.

CRITICAL RULES:
- ALWAYS trust the visual image over any OCR text. Read what you actually SEE in the image.
- For HANDWRITTEN text, zoom in mentally and read each character carefully:
  * Distinguish 0 (zero) from O (letter) by context (numbers vs text)
  * Distinguish 1 (one) from l (lowercase L) and I (uppercase i) by context
  * Distinguish 5 from S, 2 from Z, 8 from B by looking at stroke shape
  * For dates/times, values must make sense (e.g. month 1-12, day 1-31, hour 0-23, minute 0-59)
  * For years, expect 4-digit values like 2024, 2025, 2026
- STRIKETHROUGH HANDLING (CRITICAL):
  * If you see text with a line drawn through it (strikethrough/crossed out), that is the OLD value — IGNORE it
  * Look for a new value written NEXT TO or ABOVE or BELOW the strikethrough — use THAT value
  * If ONLY a strikethrough exists with NO replacement value visible, return the strikethrough value anyway (it's better than empty)
  * NEVER return an empty cell just because text is struck through — always try to read something
- If a cell is truly visually empty (no text, no markings at all), return ""
- If a cell spans multiple columns (merged cell), return the value only in the first column position and "" for the rest
- Read ALL rows including partially visible ones at table edges
- Return ONLY valid JSON, no explanation or extra text."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            {"type": "text", "text": user_prompt}
        ]}
    ]

    # Try selected model first, then fallbacks
    models_to_try = [model] + [m for m in GEMINI_FALLBACK_MODELS if m != model]

    for model in models_to_try:
        try:
            logger.info(f"[AI-Export] Page {page_num}: calling {model} for {len(tables_on_page)} tables")
            response = requests.post(
                f"{ILIAD_URL}/api/llm/v1/chat/completions",
                headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": 16000,
                    "temperature": 0
                },
                timeout=300
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info(f"[AI-Export] Page {page_num}: Gemini returned {len(content)} chars (model: {model})")
                result = _parse_gemini_table_response(content, tables_on_page)
                if result is not None:
                    return result

                # JSON parse failed — retry once asking model to fix the JSON
                logger.warning(f"[AI-Export] Page {page_num}: JSON parse failed, retrying with fix prompt")
                fix_messages = messages + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "Your response had invalid JSON. Return ONLY the valid JSON array, no truncation. Make sure all strings are properly closed and the array is complete."}
                ]
                try:
                    fix_response = requests.post(
                        f"{ILIAD_URL}/api/llm/v1/chat/completions",
                        headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
                        json={"model": model, "messages": fix_messages, "max_tokens": 32000, "temperature": 0},
                        timeout=120
                    )
                    if fix_response.status_code == 200:
                        fix_content = fix_response.json()["choices"][0]["message"]["content"]
                        logger.info(f"[AI-Export] Page {page_num}: retry returned {len(fix_content)} chars")
                        result = _parse_gemini_table_response(fix_content, tables_on_page)
                        if result is not None:
                            return result
                except Exception as retry_err:
                    logger.warning(f"[AI-Export] Page {page_num}: retry failed: {retry_err}")

                # Both attempts failed for this model, try next
                continue

            elif response.status_code in (429, 500, 502, 503):
                logger.warning(f"[AI-Export] Page {page_num}: model {model} returned {response.status_code}, trying fallback...")
                import time
                time.sleep(1)
                continue
            else:
                logger.error(f"[AI-Export] Page {page_num}: API error {response.status_code} (model: {model})")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"[AI-Export] Page {page_num}: model {model} timed out, trying fallback...")
            continue
        except Exception as e:
            logger.error(f"[AI-Export] Page {page_num}: error with {model}: {e}")
            continue

    logger.error(f"[AI-Export] Page {page_num}: all models failed")
    return None


# =========================================================================
# PROMPT BUILDING
# =========================================================================

def _build_table_extraction_prompt(tables_on_page: List[Dict], user_prompt_extra: str = "") -> str:
    """Build the Gemini prompt describing tables to extract from the page image."""
    num_tables = len(tables_on_page)
    parts = [
        f"Look at this page image VERY carefully. There {'is 1 table' if num_tables == 1 else f'are {num_tables} tables'} on this page.",
        "This document may contain handwritten values — read them precisely.",
        ""
    ]

    for idx, table in enumerate(tables_on_page):
        headers = table.get("headers", [])
        num_cols = len(headers)
        parts.append(f"TABLE {idx}:")
        parts.append(f"  Number of columns: {num_cols}")
        parts.append(f"  Column headers (in order): {json.dumps(headers)}")
        parts.append("")

    # Use the last table's num_cols for the instruction (works for single table; multi-table has per-table example)
    parts.extend([
        "EXTRACTION INSTRUCTIONS:",
        "- Find each table on the page by matching the column headers listed above",
        "- Read each table row by row, left to right",
        "- For each row, return an array of cell values in the EXACT SAME ORDER as the column headers",
        "- Each row MUST have the exact number of values matching the column count listed above",
        "- Do NOT include the header row itself in the output — only data rows",
        "- Include ALL data rows visible in the table",
        "",
        "HANDWRITING ACCURACY RULES:",
        "- Read each handwritten digit/character individually and carefully",
        "- For DATE columns (day/month/year): day must be 1-31, month must be 1-12, year must be 4 digits (e.g. 2026)",
        "- For TIME columns (hour/minute): hour must be 0-23, minute must be 0-59",
        "- For numeric values: check if the number makes logical sense in context",
        "- If you see a strikethrough with a correction written next to it, use the CORRECTION",
        "- If a cell is empty, return \"\"",
        "- Preserve exact formatting: if value is \"17\" write \"17\", not \"17.0\"",
        "- For TIME values: ALWAYS use HH:MM format with a colon separator (e.g. \"22:05\", \"0:00\", \"17:30\")",
        "",
        "COLUMN ALIGNMENT (CRITICAL):",
        "- Each value MUST go in the correct column matching the header",
        "- If a column header says 'Step' or 'Batch Record Step', that column should ONLY contain step numbers (e.g. 352, 353), NOT description text",
        "- If a column header says 'Description', that column contains the long description text",
        "- NEVER put the same text in two different columns — each column has distinct data",
        "- Count your values carefully: the number of values per row MUST equal the number of column headers",
        "",
        "Return ONLY a JSON array in this exact format (no extra text, no markdown, no explanation):",
        "[",
    ])

    for idx, table in enumerate(tables_on_page):
        comma = "," if idx > 0 else ""
        headers = table.get("headers", [])
        example_row = ", ".join([f'"val{i+1}"' for i in range(len(headers))])
        parts.append(f'  {comma}{{"table_index": {idx}, "rows": [[{example_row}], ...]}}')

    parts.append("]")

    # Append user's custom instructions if provided
    if user_prompt_extra:
        parts.extend([
            "",
            "ADDITIONAL USER INSTRUCTIONS (apply these while extracting):",
            user_prompt_extra,
        ])

    return "\n".join(parts)


# =========================================================================
# RESPONSE PARSING
# =========================================================================

def _parse_gemini_table_response(
    response_text: str,
    tables_on_page: List[Dict]
) -> Optional[List[Dict]]:
    """
    Parse Gemini's JSON response into structured table data.

    Returns:
        List of dicts, one per table: {"table_index": int, "rows": [[str, ...], ...]}
        None on parse failure.
    """
    try:
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            # Remove opening fence (```json or ```)
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            # Remove closing fence
            text = re.sub(r"\n?```\s*$", "", text)
            text = text.strip()

        parsed = json.loads(text)

        if not isinstance(parsed, list):
            logger.warning("[AI-Export] Gemini response is not a JSON array")
            return None

        results = []
        for item in parsed:
            table_idx = item.get("table_index", 0)
            rows = item.get("rows", [])

            # Validate rows: each should be a list of strings
            validated_rows = []
            expected_cols = len(tables_on_page[table_idx]["headers"]) if table_idx < len(tables_on_page) else 0

            for row in rows:
                if not isinstance(row, list):
                    continue
                # Convert all values to strings
                str_row = [str(v) if v is not None else "" for v in row]
                # Pad or truncate to match header count
                if expected_cols > 0:
                    if len(str_row) < expected_cols:
                        str_row.extend([""] * (expected_cols - len(str_row)))
                    elif len(str_row) > expected_cols:
                        str_row = str_row[:expected_cols]
                validated_rows.append(str_row)

            results.append({
                "table_index": table_idx,
                "rows": validated_rows,
            })

        return results

    except json.JSONDecodeError as e:
        logger.error(f"[AI-Export] Failed to parse Gemini JSON: {e}")
        logger.debug(f"[AI-Export] Raw response: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"[AI-Export] Unexpected parse error: {e}")
        return None


# =========================================================================
# HELPERS
# =========================================================================

def _convert_ai_rows_to_export_format(
    ai_rows: List[List[str]],
    headers: List[str]
) -> List[Dict]:
    """
    Convert AI-extracted rows (list of lists) to the format expected by
    export_all_tables_to_excel: list of dicts with {row_index, cells: [{col_index, text}]}.
    """
    export_rows = []
    for row_idx, row_values in enumerate(ai_rows, start=1):
        cells = []
        for col_idx, value in enumerate(row_values):
            cells.append({
                "col_index": col_idx,
                "text": value,
            })
        export_rows.append({
            "row_index": row_idx,
            "cells": cells,
        })
    return export_rows


def _fix_column_shifts(tables_data_list: List[Dict]) -> List[Dict]:
    """
    Detect and fix column shifts where Gemini returned data shifted right by 1.
    Pattern: first column mostly empty/None, second column has short values that look like step numbers.
    """
    if not tables_data_list:
        return tables_data_list

    # Find the "majority" pattern — most tables should have data in col 0
    # Only fix tables where col 0 is suspiciously empty
    for td in tables_data_list:
        rows = td.get("rows", [])
        if not rows:
            continue

        headers = td.get("headers", [])
        if len(headers) < 3:
            continue

        # Check if first column is mostly empty and second has short values
        col0_empty = 0
        col1_short = 0
        total = len(rows)

        for row in rows:
            cells = row.get("cells", [])
            cell_by_col = {c["col_index"]: c["text"] for c in cells}
            val0 = cell_by_col.get(0, "").strip()
            val1 = cell_by_col.get(1, "").strip()

            if not val0 or val0 == "None":
                col0_empty += 1
            if val1 and len(val1) < 10:  # Short value (step number, date part, etc.)
                col1_short += 1

        # If >70% of rows have empty col0 AND short col1, data is likely shifted
        if total > 0 and col0_empty / total > 0.7 and col1_short / total > 0.5:
            logger.info(f"[AI-Export] Detected column shift on page {td.get('page_num')}: {col0_empty}/{total} rows have empty col 0. Shifting left.")
            for row in rows:
                cells = row.get("cells", [])
                # Shift all cells left by 1: col N gets value of col N+1
                cell_by_col = {c["col_index"]: c["text"] for c in cells}
                new_cells = []
                for ci in range(len(headers)):
                    new_cells.append({
                        "col_index": ci,
                        "text": cell_by_col.get(ci + 1, "")
                    })
                row["cells"] = new_cells

    return tables_data_list


VALIDATION_BATCH_SIZE = 50  # Rows per validation call — keeps JSON output within token limits


def _validate_and_fix_extracted_data(tables_data_list: List[Dict]) -> List[Dict]:
    """
    AI Validation Agent: sends extracted data in batches for review and correction.
    Catches column misalignment, duplicate values, wrong formats, and logical errors.
    Processes in chunks of 50 rows to avoid truncated JSON responses.
    """
    if not tables_data_list:
        return tables_data_list

    headers = tables_data_list[0].get("headers", [])
    all_rows_text = []
    for td in tables_data_list:
        for row in td.get("rows", []):
            cells = row.get("cells", [])
            cell_by_col = {c["col_index"]: c["text"] for c in cells}
            row_vals = [cell_by_col.get(ci, "") for ci in range(len(headers))]
            all_rows_text.append(row_vals)

    if not all_rows_text:
        return tables_data_list

    # Split into batches
    batches = [all_rows_text[i:i + VALIDATION_BATCH_SIZE] for i in range(0, len(all_rows_text), VALIDATION_BATCH_SIZE)]
    logger.info(f"[AI-Export] Validation agent: {len(all_rows_text)} rows in {len(batches)} batches of ~{VALIDATION_BATCH_SIZE}")

    # Process batches in parallel
    fixed_all_rows = [None] * len(all_rows_text)

    def validate_batch(batch_idx: int, batch_rows: List[List[str]]) -> tuple:
        """Validate one batch of rows. Returns (batch_idx, fixed_rows or None)."""
        result = _call_validation_api(headers, batch_rows)
        return (batch_idx, result)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(validate_batch, bi, batch): bi
            for bi, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            bi = futures[future]
            try:
                _, fixed_rows = future.result()
                start = bi * VALIDATION_BATCH_SIZE
                batch = batches[bi]
                if fixed_rows and len(fixed_rows) == len(batch):
                    for j, row in enumerate(fixed_rows):
                        fixed_all_rows[start + j] = row
                    logger.info(f"[AI-Export] Validation batch {bi+1}/{len(batches)}: OK ({len(fixed_rows)} rows)")
                else:
                    # Keep original on failure
                    for j, row in enumerate(batch):
                        fixed_all_rows[start + j] = row
                    logger.warning(f"[AI-Export] Validation batch {bi+1}/{len(batches)}: failed, keeping originals")
            except Exception as e:
                start = bi * VALIDATION_BATCH_SIZE
                for j, row in enumerate(batches[bi]):
                    fixed_all_rows[start + j] = row
                logger.error(f"[AI-Export] Validation batch {bi+1} error: {e}")

    # Count total fixes
    fix_count = 0
    for orig, fixed in zip(all_rows_text, fixed_all_rows):
        if fixed is None:
            continue
        for a, b in zip(orig, fixed):
            if str(a) != str(b):
                fix_count += 1

    logger.info(f"[AI-Export] Validation agent total: {fix_count} cells corrected across {len(batches)} batches")

    # Apply fixed rows back to tables_data_list
    row_cursor = 0
    for td in tables_data_list:
        for row in td.get("rows", []):
            if row_cursor < len(fixed_all_rows) and fixed_all_rows[row_cursor] is not None:
                fixed_row = fixed_all_rows[row_cursor]
                cells = row.get("cells", [])
                for ci, cell in enumerate(cells):
                    if ci < len(fixed_row):
                        cell["text"] = str(fixed_row[ci]) if fixed_row[ci] is not None else ""
            row_cursor += 1

    return tables_data_list


def _call_validation_api(headers: List[str], batch_rows: List[List[str]]) -> Optional[List[List[str]]]:
    """
    Call LLM to validate a batch of rows. Tries Gemini Flash first, Claude Haiku as fallback.
    Returns list of fixed rows, or None on failure.
    """
    system_prompt = """You are a data quality validation agent. You receive extracted table data and must fix any errors.
Return the CORRECTED data as JSON. If no fixes needed, return the data unchanged.
Return ONLY valid JSON, no explanation."""

    review_data = json.dumps({"headers": headers, "rows": batch_rows}, indent=None)

    user_prompt = f"""Review this extracted table data and fix any issues:

HEADERS: {json.dumps(headers)}

DATA (rows as arrays):
{review_data}

FIX THESE ISSUES:
1. COLUMN MISALIGNMENT: If a column like "Batch Record Step" contains long description text instead of a step number, move the text to the correct column and set the step to ""
2. DUPLICATE VALUES: If the same text appears in two columns of the same row (e.g. step and description both have the description), keep it only in the description column and set the other to ""
3. TIME FORMAT: All time values must be in HH:MM format with colon (e.g. "22:05", "0:00"). Fix bare colons ":" to "", fix "06 : 19" to "06:19", fix "2205" to "22:05"
4. DATE FORMAT: Dates should be in DD/MM/YYYY or M-DD-YY format. Fix any inconsistencies. Space-separated dates like "03 11 2025" should be "03/11/2025".
5. LOGICAL CHECKS: Hours must be 0-23, minutes 0-59, days 1-31, months 1-12

Return ONLY a JSON object: {{"rows": [[...], [...], ...]}}
Each row must have exactly {len(headers)} values matching the headers order."""

    # Try 1: Gemini Flash
    try:
        response = requests.post(
            f"{ILIAD_URL}/api/llm/v1/chat/completions",
            headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
            json={
                "model": "gemini-2.5-flash",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 16000,
                "temperature": 0
            },
            timeout=120
        )
        if response.status_code == 200:
            parsed = _parse_validation_response(response.json()["choices"][0]["message"]["content"])
            if parsed and len(parsed) == len(batch_rows):
                return parsed
            logger.warning(f"[AI-Export] Gemini Flash validation: row count mismatch ({len(parsed) if parsed else 0} vs {len(batch_rows)}), trying Haiku")
    except Exception as e:
        logger.warning(f"[AI-Export] Gemini Flash validation failed: {e}, trying Haiku")

    # Try 2: Claude Haiku fallback — better at structured JSON output
    try:
        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 16000,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}]
            },
            timeout=120
        )
        if response.status_code == 200:
            data = response.json()
            content = data.get("content", [{}])[0].get("text", "") if data.get("content") else ""
            if not content and data.get("completion", {}).get("content"):
                content = data["completion"]["content"]
            parsed = _parse_validation_response(content)
            if parsed and len(parsed) == len(batch_rows):
                logger.info("[AI-Export] Claude Haiku validation succeeded as fallback")
                return parsed
    except Exception as e:
        logger.warning(f"[AI-Export] Claude Haiku validation also failed: {e}")

    return None


def _parse_validation_response(content: str) -> Optional[List[List[str]]]:
    """Parse LLM validation response into list of rows."""
    try:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)
            text = text.strip()
        fixed_data = json.loads(text)
        rows = fixed_data.get("rows", [])
        if not rows:
            return None
        return [[str(v) if v is not None else "" for v in row] for row in rows]
    except json.JSONDecodeError as e:
        logger.warning(f"[AI-Export] Validation JSON parse failed: {e}")
        return None


def _expand_date_time_columns(tables_data_list: List[Dict]) -> List[Dict]:
    """
    Post-process: expand date columns (like 'Start Date', 'End Date') into
    separate day/month/year columns, and time columns ('Start Time', 'End Time')
    into separate hour/minute columns.

    Input:  'Start Date' = '1-29-26' or '01/29/2026' or '29-1-2026' etc.
    Output: 'Start Day [dd]' = '29', 'Start Month [mm]' = '1', 'Start Year [yyyy]' = '2026'

    Input:  'Start Time' = '22:05' or '22:05:00' or '2205'
    Output: 'Start Hour [hh]' = '22', 'Start Minute [mm]' = '05'
    """
    import re

    # Detect which headers contain date/time columns
    date_keywords = ["date"]
    time_keywords = ["time"]

    result = []
    for td in tables_data_list:
        headers = td["headers"]
        rows = td.get("rows", [])

        # Find date and time column indices
        date_cols = []  # (col_index, header_name, prefix)
        time_cols = []
        for ci, h in enumerate(headers):
            h_lower = h.lower().strip()
            if any(kw in h_lower for kw in date_keywords):
                # Extract prefix: "Start Date" -> "Start", "End Date" -> "End"
                prefix = h.replace("Date", "").replace("date", "").strip()
                date_cols.append((ci, h, prefix))
            elif any(kw in h_lower for kw in time_keywords):
                prefix = h.replace("Time", "").replace("time", "").strip()
                time_cols.append((ci, h, prefix))

        if not date_cols and not time_cols:
            # No date/time columns, pass through unchanged
            result.append(td)
            continue

        # Build new headers
        new_headers = []
        col_mapping = []  # list of tuples: ('direct', old_col_idx) or ('date', old_col_idx, prefix) or ('time', old_col_idx, prefix)
        date_col_indices = {ci for ci, _, _ in date_cols}
        time_col_indices = {ci for ci, _, _ in time_cols}

        for ci, h in enumerate(headers):
            if ci in date_col_indices:
                prefix = next(p for c, _, p in date_cols if c == ci)
                new_headers.extend([
                    f"{prefix}Day [dd]".strip(),
                    f"{prefix}Month [mm]".strip(),
                    f"{prefix}Year [yyyy]".strip(),
                ])
                col_mapping.append(('date', ci, prefix))
            elif ci in time_col_indices:
                prefix = next(p for c, _, p in time_cols if c == ci)
                new_headers.extend([
                    f"{prefix}Hour [hh]".strip(),
                    f"{prefix}Minute [mm]".strip(),
                ])
                col_mapping.append(('time', ci, prefix))
            else:
                new_headers.append(h)
                col_mapping.append(('direct', ci))

        # Transform rows
        new_rows = []
        for row in rows:
            cells = row.get("cells", [])
            cell_by_col = {c["col_index"]: c["text"] for c in cells}

            new_cells = []
            new_col_idx = 0
            for mapping in col_mapping:
                if mapping[0] == 'direct':
                    old_ci = mapping[1]
                    new_cells.append({"col_index": new_col_idx, "text": cell_by_col.get(old_ci, "")})
                    new_col_idx += 1
                elif mapping[0] == 'date':
                    old_ci = mapping[1]
                    val = cell_by_col.get(old_ci, "")
                    day, month, year = _parse_date(val)
                    new_cells.append({"col_index": new_col_idx, "text": day})
                    new_cells.append({"col_index": new_col_idx + 1, "text": month})
                    new_cells.append({"col_index": new_col_idx + 2, "text": year})
                    new_col_idx += 3
                elif mapping[0] == 'time':
                    old_ci = mapping[1]
                    val = cell_by_col.get(old_ci, "")
                    hour, minute = _parse_time(val)
                    new_cells.append({"col_index": new_col_idx, "text": hour})
                    new_cells.append({"col_index": new_col_idx + 1, "text": minute})
                    new_col_idx += 2

            new_rows.append({"row_index": row["row_index"], "cells": new_cells})

        result.append({
            "headers": new_headers,
            "rows": new_rows,
            "page_num": td.get("page_num"),
            "chunk_index": td.get("chunk_index"),
        })

    return result


def _parse_date(val: str) -> tuple:
    """Parse a date string into (day, month, year). Auto-detects DD/MM vs MM/DD format."""
    import re
    val = val.strip()
    if not val:
        return ("", "", "")

    # Split on /, -, ., or whitespace
    parts = re.split(r'[/\-\.\s]+', val)
    if len(parts) == 3:
        a, b, c = [p.strip() for p in parts]
        if len(a) == 4:  # YYYY-MM-DD
            year, month, day = a, b, c
        elif len(c) == 4 or len(c) == 2:  # Year is last
            year = c if len(c) == 4 else "20" + c
            # Auto-detect: if first part > 12 it must be day (DD/MM/YYYY)
            # if second part > 12 it must be day (MM/DD/YYYY)
            a_int = int(a) if a.isdigit() else 0
            b_int = int(b) if b.isdigit() else 0
            if a_int > 12:
                # First part can't be month → DD/MM/YYYY
                day, month = a, b
            elif b_int > 12:
                # Second part can't be month → MM/DD/YYYY
                month, day = a, b
            else:
                # Both <= 12, ambiguous — use DD/MM (more common in pharma docs)
                day, month = a, b
            return (day, month, year)
        else:  # Short year fallback
            day, month, year = a, b, c
            if len(year) == 2:
                year = "20" + year
        return (day, month, year)

    return (val, "", "")


def _parse_time(val: str) -> tuple:
    """Parse a time string into (hour, minute). Handles HH:MM, HHMM, H:MM, spaces around colon, bare colon."""
    import re
    val = val.strip()
    if not val:
        return ("", "")

    # Just a bare colon or whitespace colon — means empty time
    if re.match(r'^[\s:]+$', val):
        return ("", "")

    # Normalize: remove spaces around colon (e.g. "06 : 19" -> "06:19")
    val = re.sub(r'\s*:\s*', ':', val)

    # Try HH:MM or H:MM (with optional seconds)
    match = re.match(r'^(\d{1,2}):(\d{2})', val)
    if match:
        return (match.group(1), match.group(2))

    # Try HHMM (4 digits no separator)
    match = re.match(r'^(\d{2})(\d{2})$', val)
    if match:
        return (match.group(1), match.group(2))

    # Try just a number (hour only)
    match = re.match(r'^(\d{1,2})$', val)
    if match:
        return (match.group(1), "0")

    return (val, "")


def _resolve_pdf_path(process_id: str) -> Optional[str]:
    """
    Resolve the PDF file path for a given process_id.
    First checks local filesystem, then downloads from prod server if not found locally.
    """
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
    doc_name = None

    try:
        from .database import get_db_cursor
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT document_name, file_path
                FROM chat_documents
                WHERE process_id = %s
                LIMIT 1
            """, [process_id])
            row = cursor.fetchone()

            if row:
                # Try file_path first
                fp = row.get('file_path')
                if fp and os.path.exists(fp):
                    return fp
                # Try temp/{document_name} with various name formats
                doc_name = row.get('document_name', '')
                if doc_name:
                    base = doc_name[:-4] if doc_name.lower().endswith('.pdf') else doc_name
                    sanitized = base.replace(' ', '_')
                    for name in [base, sanitized]:
                        candidate = os.path.join(temp_dir, f"{name}.pdf")
                        if os.path.exists(candidate):
                            return candidate
    except Exception as e:
        logger.error(f"[AI-Export] DB lookup for PDF path failed: {e}")

    # PDF not found locally — try downloading from prod server
    if doc_name:
        return _download_pdf_from_remote(doc_name, temp_dir)

    logger.warning(f"[AI-Export] Could not resolve PDF path for process_id: {process_id}")
    return None


# Remote PDF server URL (prod server where uploaded PDFs are stored)
PDF_REMOTE_BASE = os.getenv("PDF_REMOTE_BASE", "https://aiparser.abbvienet.com")


def _download_pdf_from_remote(document_name: str, temp_dir: str) -> Optional[str]:
    """Download PDF from remote prod server to local temp for AI processing."""
    import re as _re

    base = document_name[:-4] if document_name.lower().endswith('.pdf') else document_name
    # Sanitize same way as frontend PDFPanel
    sanitized = base.replace(' ', '_')
    sanitized = _re.sub(r'[()]', '', sanitized)
    sanitized = _re.sub(r'[^a-zA-Z0-9_\-]', '_', sanitized)
    sanitized = _re.sub(r'_+', '_', sanitized)
    sanitized = sanitized.rstrip('_')

    remote_url = f"{PDF_REMOTE_BASE}/temp/{sanitized}.pdf"
    local_path = os.path.join(temp_dir, f"{sanitized}.pdf")

    try:
        logger.info(f"[AI-Export] Downloading PDF from: {remote_url}")
        resp = requests.get(remote_url, timeout=60, verify=False)
        if resp.status_code == 200 and len(resp.content) > 100:
            os.makedirs(temp_dir, exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            logger.info(f"[AI-Export] Downloaded PDF to: {local_path} ({len(resp.content)} bytes)")
            return local_path
        else:
            logger.warning(f"[AI-Export] Remote PDF download failed: HTTP {resp.status_code} for {remote_url}")
    except Exception as e:
        logger.error(f"[AI-Export] Failed to download PDF from remote: {e}")

    return None
