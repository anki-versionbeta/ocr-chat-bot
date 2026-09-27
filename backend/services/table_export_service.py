"""
Table Export Service

Exports table data from Neo4j to Excel, Word, and PDF formats.
Consumes structured table data from neo4j_service.get_full_table_data_by_chunk_index().

Input format:
{
    "table_key": "...",
    "chunk_index": 5,
    "page_num": 1,
    "headers": ["Col1", "Col2", ...],
    "rows": [{"row_index": 1, "cells": [{"col_index": 0, "text": "..."}]}],
    "bbox": {"left": ..., "top": ..., "right": ..., "bottom": ...}
}
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

import json
import glob

logger = logging.getLogger(__name__)

EXPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'exports')
TEMP_DIR = os.path.join(os.path.dirname(__file__), '..', 'temp')
os.makedirs(EXPORTS_DIR, exist_ok=True)


def get_merged_cells_from_blocks(process_id: str, page_num: int) -> Dict[tuple, Dict]:
    """
    Read MERGED_CELL blocks from the Textract blocks JSON file.
    Textract stores merges as separate BlockType='MERGED_CELL' with RowSpan/ColumnSpan.

    Returns: {(row_index, col_index): {"row_span": N, "col_span": M}}
    """
    merged = {}
    try:
        # Find blocks JSON file — try matching by process_id in Neo4j first
        blocks_files = glob.glob(os.path.join(TEMP_DIR, '*_blocks.json'))
        blocks_path = None

        # The blocks file is named {original_filename}_blocks.json
        # We need to find which one belongs to this process_id
        # Try to match via Neo4j document filename
        try:
            from services.neo4j_service import get_neo4j_service
            neo4j = get_neo4j_service()
            if neo4j and neo4j.is_connected:
                doc = neo4j.query_single("""
                    MATCH (d:Document {process_id: $pid})
                    RETURN d.filename AS filename
                """, {"pid": process_id})
                if doc and doc.get("filename"):
                    fname = doc["filename"].replace('.pdf', '').replace('.PDF', '')
                    # Sanitize same as backend does
                    fname = fname.replace(' ', '_').replace('(', '').replace(')', '')
                    candidate = os.path.join(TEMP_DIR, f"{fname}_blocks.json")
                    if os.path.exists(candidate):
                        blocks_path = candidate
                    else:
                        # Try fuzzy match
                        for bf in blocks_files:
                            if fname.lower() in os.path.basename(bf).lower():
                                blocks_path = bf
                                break
        except Exception:
            pass

        if not blocks_path:
            return merged

        with open(blocks_path, 'r') as f:
            data = json.load(f)

        # Parse paginated Textract responses
        pages_data = data if isinstance(data, list) else [data]
        for page_resp in pages_data:
            for block in page_resp.get('Blocks', []):
                if (block.get('BlockType') == 'MERGED_CELL' and
                        block.get('Page') == page_num):
                    ri = block.get('RowIndex')
                    ci = block.get('ColumnIndex')
                    rs = block.get('RowSpan', 1)
                    cs = block.get('ColumnSpan', 1)
                    if ri and ci and (rs > 1 or cs > 1):
                        merged[(ri, ci)] = {'row_span': rs, 'col_span': cs}

        if merged:
            logger.info(f"Found {len(merged)} MERGED_CELL blocks for page {page_num}")

    except Exception as e:
        logger.warning(f"Could not read merged cells from blocks JSON: {e}")

    return merged


def _build_2d_grid(table_data: Dict, textract_merges: Optional[Dict[tuple, Dict]] = None) -> tuple:
    """
    Convert Neo4j table data into a 2D grid (list of lists).
    Handles sparse columns from merged cells by filling gaps with empty strings.

    Args:
        table_data: Table data from Neo4j (headers + rows)
        textract_merges: {(row_index, col_index): {"row_span": N, "col_span": M}}
                         from Textract MERGED_CELL blocks (1-based row/col indices)

    Returns: (headers: List[str], rows: List[List[str]], merges: List[tuple])
        merges: list of (start_row, start_col, end_row, end_col) — 0-indexed data rows (not header)
    """
    headers = table_data.get("headers", [])
    raw_rows = table_data.get("rows", [])

    # Find the minimum col_index across all cells (Neo4j often uses 1-based)
    min_col = None
    for row in raw_rows:
        for cell in row.get("cells", []):
            ci = cell.get("col_index", 0)
            if min_col is None or ci < min_col:
                min_col = ci
    col_offset = min_col if min_col and min_col > 0 else 0

    # Determine column count from headers or max col_index (adjusted)
    col_count = len(headers)
    for row in raw_rows:
        for cell in row.get("cells", []):
            adjusted = cell.get("col_index", 0) - col_offset
            col_count = max(col_count, adjusted + 1)

    # If headers are empty but rows exist, use first row as headers
    if not headers and raw_rows:
        first_row = raw_rows[0]
        first_cells = sorted(first_row.get("cells", []), key=lambda x: x.get("col_index", 0))
        headers = [c.get("text", "") for c in first_cells]
        raw_rows = raw_rows[1:]

    # Ensure col_count matches headers
    col_count = max(col_count, len(headers))

    # Pad headers if fewer than col_count
    while len(headers) < col_count:
        headers.append("")

    # Trim trailing empty headers
    while headers and headers[-1] == "":
        headers.pop()
    col_count = len(headers)

    # Build rows as ordered lists (normalize col_index to 0-based)
    grid_rows = []
    for row in raw_rows:
        grid_row = [""] * col_count
        for cell in row.get("cells", []):
            col_idx = cell.get("col_index", 0) - col_offset
            if 0 <= col_idx < col_count:
                grid_row[col_idx] = cell.get("text", "")
        grid_rows.append(grid_row)

    # Detect merged cells from TWO sources:
    # 1. Explicit row_span/col_span on cell data (from Neo4j)
    # 2. Textract MERGED_CELL blocks (separate BlockType with real span info)

    merges = []

    # Source 1: Cell-level span data
    for data_row_idx, row in enumerate(raw_rows):
        for cell in row.get("cells", []):
            rs = cell.get("row_span", 1) or 1
            cs = cell.get("col_span", 1) or 1
            if rs > 1 or cs > 1:
                col_idx = cell.get("col_index", 0) - col_offset
                if 0 <= col_idx < col_count:
                    merges.append((
                        data_row_idx, col_idx,
                        data_row_idx + rs - 1, col_idx + cs - 1
                    ))

    # Source 2: Textract MERGED_CELL blocks (keyed by 1-based row/col)
    # The header row is the first row (min_row_index), data starts after it.
    # We need to convert Textract's 1-based row index to 0-based data row index.
    if textract_merges and not merges:
        # Determine which row is the header (min row index in original data)
        all_row_indices = set()
        for row in raw_rows:
            for cell in row.get("cells", []):
                pass
        # raw_rows have row_index from Neo4j. The header was already stripped.
        # The first data row's original row_index tells us the offset.
        if raw_rows and raw_rows[0].get("cells"):
            first_data_row_orig = raw_rows[0].get("row_index", 2)
            # header_row_orig is one less (it was stripped)
            header_row_orig = first_data_row_orig - 1

            for (mc_row, mc_col), span_info in textract_merges.items():
                rs = span_info.get("row_span", 1)
                cs = span_info.get("col_span", 1)
                # Convert to 0-based data row index
                data_row_start = mc_row - first_data_row_orig
                # Convert 1-based Textract col to 0-based grid col
                data_col = mc_col - col_offset if col_offset > 0 else mc_col - 1

                if data_row_start >= 0 and data_col >= 0 and data_col < col_count:
                    data_row_end = data_row_start + rs - 1
                    data_col_end = data_col + cs - 1
                    # Clamp to grid bounds
                    data_row_end = min(data_row_end, len(grid_rows) - 1)
                    data_col_end = min(data_col_end, col_count - 1)
                    if data_row_end > data_row_start or data_col_end > data_col:
                        merges.append((data_row_start, data_col, data_row_end, data_col_end))

    return headers, grid_rows, merges


def _generate_filename(process_id: str, chunk_index: int, ext: str) -> str:
    """Generate a unique filename for the export."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid_short = (process_id or "unknown")[:8]
    return f"table_{pid_short}_chunk{chunk_index}_{timestamp}.{ext}"


def export_table_to_excel(table_data: Dict, document_name: str = "", process_id: str = "", textract_merges: Optional[Dict] = None) -> str:
    """
    Export table to Excel (.xlsx) with styling and merged cells.
    Returns the absolute file path.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    headers, rows, merges = _build_2d_grid(table_data, textract_merges)
    chunk_index = table_data.get("chunk_index", 0)
    page_num = table_data.get("page_num", "?")

    filename = _generate_filename(process_id, chunk_index, "xlsx")
    filepath = os.path.join(EXPORTS_DIR, filename)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Page {page_num} Table"

    # Styles
    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_alignment = Alignment(vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    # Row offset: row 1 = headers, data starts at row 2
    data_start_row = 1

    # Add metadata row at top (optional info)
    if document_name:
        info_cell = ws.cell(row=1, column=1, value=f"Source: {document_name} — Page {page_num}")
        info_cell.font = Font(italic=True, size=9, color="6B7280")
        if len(headers) > 1:
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        data_start_row = 2

    header_row = data_start_row

    # Write headers
    for col_idx, header_text in enumerate(headers, 1):
        cell = ws.cell(row=header_row, column=col_idx, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Write data rows
    for row_idx, row_data in enumerate(rows):
        excel_row = header_row + 1 + row_idx
        for col_idx, cell_text in enumerate(row_data, 1):
            cell = ws.cell(row=excel_row, column=col_idx, value=cell_text)
            cell.alignment = cell_alignment
            cell.border = thin_border

    # Apply merged cells
    for (start_r, start_c, end_r, end_c) in merges:
        excel_start_row = header_row + 1 + start_r
        excel_end_row = header_row + 1 + end_r
        excel_start_col = start_c + 1
        excel_end_col = end_c + 1
        try:
            ws.merge_cells(
                start_row=excel_start_row, start_column=excel_start_col,
                end_row=excel_end_row, end_column=excel_end_col
            )
            # Style the merged cell
            merged_cell = ws.cell(row=excel_start_row, column=excel_start_col)
            merged_cell.alignment = Alignment(vertical="center", wrap_text=True)
            merged_cell.border = thin_border
        except Exception as e:
            logger.warning(f"Could not merge cells ({start_r},{start_c})->({end_r},{end_c}): {e}")

    # Apply borders to all merged area cells (openpyxl doesn't auto-border merged cells)
    for (start_r, start_c, end_r, end_c) in merges:
        for r in range(header_row + 1 + start_r, header_row + 1 + end_r + 1):
            for c in range(start_c + 1, end_c + 2):
                ws.cell(row=r, column=c).border = thin_border

    # Auto-fit column widths
    for col_idx in range(1, len(headers) + 1):
        max_len = len(str(headers[col_idx - 1]))
        for row_data in rows:
            val = str(row_data[col_idx - 1]) if col_idx - 1 < len(row_data) else ""
            max_len = max(max_len, len(val))
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 4, 50)

    wb.save(filepath)
    logger.info(f"Excel export saved: {filepath}")
    return filepath


def export_table_to_docx(table_data: Dict, document_name: str = "", process_id: str = "", textract_merges: Optional[Dict] = None) -> str:
    """
    Export table to Word (.docx).
    Returns the absolute file path.
    """
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.table import WD_TABLE_ALIGNMENT

    headers, rows, merges = _build_2d_grid(table_data, textract_merges)
    chunk_index = table_data.get("chunk_index", 0)
    page_num = table_data.get("page_num", "?")

    filename = _generate_filename(process_id, chunk_index, "docx")
    filepath = os.path.join(EXPORTS_DIR, filename)

    doc = Document()

    # Title
    title = doc.add_paragraph()
    run = title.add_run(f"Table from {document_name or 'Document'} — Page {page_num}")
    run.bold = True
    run.font.size = Pt(14)
    run.font.color.rgb = RGBColor(0x25, 0x63, 0xEB)

    # Create table
    total_rows = len(rows) + 1  # +1 for header
    total_cols = len(headers)
    table = doc.add_table(rows=total_rows, cols=total_cols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Write headers
    for col_idx, header_text in enumerate(headers):
        cell = table.rows[0].cells[col_idx]
        cell.text = header_text
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.bold = True
                run.font.size = Pt(10)

    # Write data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_text in enumerate(row_data):
            if col_idx < total_cols:
                cell = table.rows[row_idx + 1].cells[col_idx]
                cell.text = cell_text
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.size = Pt(9)

    # Apply vertical merges
    for (start_r, start_c, end_r, end_c) in merges:
        try:
            # +1 offset because row 0 in docx table is the header row
            top_cell = table.cell(start_r + 1, start_c)
            bottom_cell = table.cell(end_r + 1, end_c)
            top_cell.merge(bottom_cell)
        except Exception as e:
            logger.warning(f"Could not merge docx cells ({start_r},{start_c})->({end_r},{end_c}): {e}")

    doc.save(filepath)
    logger.info(f"Word export saved: {filepath}")
    return filepath


def export_table_to_pdf(table_data: Dict, document_name: str = "", process_id: str = "", textract_merges: Optional[Dict] = None) -> str:
    """
    Export table to PDF by first generating a Word doc (which handles merges
    and formatting well), then converting it to PDF using docx2pdf.
    Returns the absolute file path.
    """
    chunk_index = table_data.get("chunk_index", 0)

    # Step 1: Generate Word doc (reuses the full docx export with merges)
    docx_path = export_table_to_docx(table_data, document_name, process_id, textract_merges)

    # Step 2: Convert Word to PDF
    pdf_filename = _generate_filename(process_id, chunk_index, "pdf")
    pdf_filepath = os.path.join(EXPORTS_DIR, pdf_filename)

    try:
        from docx2pdf import convert
        convert(docx_path, pdf_filepath)
        logger.info(f"PDF export saved (via docx2pdf): {pdf_filepath}")

        # Clean up the intermediate docx file
        try:
            os.remove(docx_path)
        except Exception:
            pass

        return pdf_filepath

    except Exception as e:
        logger.warning(f"docx2pdf conversion failed: {e}. Returning docx file instead.")
        # If conversion fails (e.g., MS Word not installed), return the docx
        # Rename it to .pdf extension so the download works
        return docx_path


def export_all_tables_to_excel(tables_data_list: List[Dict], document_name: str = "", process_id: str = "", ai_enhanced: bool = False) -> str:
    """
    Export ALL tables from a document into a single Excel file.
    Tables with matching headers are merged into one sheet with a single header row.
    Tables with different headers go to separate sheets.

    Args:
        tables_data_list: List of table_data dicts, each with {headers, rows, page_num, chunk_index}
        document_name: Original document name for labeling
        process_id: For filename generation
        ai_enhanced: If True, label the export as AI-enhanced and use ai_ filename prefix

    Returns:
        Absolute file path of the generated Excel
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    if not tables_data_list:
        raise ValueError("No tables to export")

    # Group tables by normalized header signature (fuzzy: same column count + similar headers)
    groups: Dict[str, List[Dict]] = {}
    for td in tables_data_list:
        headers = td.get("headers", [])
        # Normalize: lowercase, strip whitespace, join with pipe
        sig = "|".join(h.strip().lower() for h in headers)
        # Try to find an existing group with same column count and similar headers
        matched_sig = None
        for existing_sig in groups:
            existing_headers = existing_sig.split("|")
            if len(existing_headers) == len(headers):
                # Count matching headers (case-insensitive, allow substring match)
                matches = 0
                for eh, nh in zip(existing_headers, [h.strip().lower() for h in headers]):
                    if eh == nh or eh in nh or nh in eh:
                        matches += 1
                # If >80% of headers match, consider it the same group
                if matches >= len(headers) * 0.8:
                    matched_sig = existing_sig
                    break
        target_sig = matched_sig if matched_sig else sig
        if target_sig not in groups:
            groups[target_sig] = []
        groups[target_sig].append(td)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pid_short = (process_id or "unknown")[:8]
    prefix = "ai_tables_" if ai_enhanced else "all_tables_"
    filename = f"{prefix}{pid_short}_{timestamp}.xlsx"
    filepath = os.path.join(EXPORTS_DIR, filename)

    wb = openpyxl.Workbook()
    # Remove default sheet — we'll create our own
    wb.remove(wb.active)

    # Styles (same as export_table_to_excel)
    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_alignment = Alignment(vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    for group_idx, (sig, group_tables) in enumerate(groups.items()):
        # Sheet name
        if len(groups) == 1:
            sheet_name = "All Tables"
        else:
            # Use first header as sheet name, truncated to 31 chars (Excel limit)
            first_header = group_tables[0]["headers"][0] if group_tables[0]["headers"] else f"Group {group_idx + 1}"
            sheet_name = first_header[:31]

        ws = wb.create_sheet(title=sheet_name)
        headers = group_tables[0]["headers"]

        # Row 1: metadata
        data_start_row = 1
        if document_name:
            table_count = len(group_tables)
            suffix = " (AI-enhanced extraction)" if ai_enhanced else ""
            info_cell = ws.cell(row=1, column=1, value=f"Source: {document_name} — {table_count} tables merged{suffix}")
            info_cell.font = Font(italic=True, size=9, color="6B7280")
            if len(headers) > 1:
                ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
            data_start_row = 2

        header_row = data_start_row

        # Write headers once
        for col_idx, header_text in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=col_idx, value=header_text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

        # Append all data rows from all tables in this group
        current_row = header_row + 1
        for td in group_tables:
            _, row_grid, _ = _build_2d_grid(td, None)
            for row_data in row_grid:
                for col_idx, cell_text in enumerate(row_data, 1):
                    cell = ws.cell(row=current_row, column=col_idx, value=cell_text)
                    cell.alignment = cell_alignment
                    cell.border = thin_border
                current_row += 1

        # Auto-fit column widths
        for col_idx in range(1, len(headers) + 1):
            max_len = len(str(headers[col_idx - 1]))
            for r in range(header_row + 1, current_row):
                val = str(ws.cell(row=r, column=col_idx).value or "")
                max_len = max(max_len, len(val))
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 4, 50)

    wb.save(filepath)
    logger.info(f"Export All Tables saved: {filepath} ({len(tables_data_list)} tables)")
    return filepath


def export_table(table_data: Dict, format: str, document_name: str = "", process_id: str = "") -> str:
    """
    Main entry point. Export table data to the specified format.
    Automatically reads MERGED_CELL data from Textract blocks JSON if available.

    Args:
        table_data: Output from neo4j_service.get_full_table_data_by_chunk_index()
        format: "excel", "docx", or "pdf"
        document_name: Original document name for labeling
        process_id: For filename generation

    Returns:
        Absolute file path of the generated export
    """
    # Try to get merge data from Textract blocks JSON
    page_num = table_data.get("page_num")
    textract_merges = None
    if process_id and page_num:
        textract_merges = get_merged_cells_from_blocks(process_id, page_num)

    if format == "excel":
        return export_table_to_excel(table_data, document_name, process_id, textract_merges)
    elif format == "docx":
        return export_table_to_docx(table_data, document_name, process_id, textract_merges)
    elif format == "pdf":
        return export_table_to_pdf(table_data, document_name, process_id, textract_merges)
    else:
        raise ValueError(f"Unsupported export format: {format}. Use 'excel', 'docx', or 'pdf'.")
