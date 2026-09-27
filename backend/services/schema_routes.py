"""
Extraction Schema API Routes

Endpoints:
- GET    /api/schemas                              - List user's schemas
- POST   /api/schemas                              - Create schema
- GET    /api/schemas/{schema_id}                  - Get schema
- PATCH  /api/schemas/{schema_id}                  - Update schema
- DELETE /api/schemas/{schema_id}                  - Delete schema
- GET    /api/documents/{process_id}/search         - Document text search (Ctrl+F)
- POST   /api/schemas/{schema_id}/discover          - Discover pages per parameter
- POST   /api/schemas/executions/{execution_id}/run - Run extraction (SSE stream)
- GET    /api/schemas/executions/{execution_id}     - Get execution results
"""

import os
import io
import re
import json
import logging
import queue
import threading
import glob
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict

from .database import (
    get_or_create_user,
    create_extraction_schema,
    get_user_schemas,
    get_schema,
    update_schema,
    delete_schema,
    ensure_extraction_schemas_table,
    ensure_execution_results_table,
    get_execution,
    update_execution,
    get_executions_by_schema,
)
from .neo4j_service import get_neo4j_service
from .schema_execution_service import get_schema_execution_service

logger = logging.getLogger("ocr-chatbot.schema_routes")

router = APIRouter(prefix="/api", tags=["schemas"])

# Ensure tables exist on module load
try:
    ensure_extraction_schemas_table()
    ensure_execution_results_table()
    logger.info("Extraction schemas + execution results tables ready")
except Exception as e:
    logger.warning(f"Could not ensure schema tables: {e}")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ParameterDefinition(BaseModel):
    name: str
    type: str = "string"  # string, number, date, boolean
    hint: Optional[str] = None
    required: bool = True
    unit: Optional[str] = None
    page: Optional[int] = None  # Specific page number (skips discovery if set)
    task_type: str = "extract"  # "extract" | "verify"
    verification_config: Optional[Dict] = None  # {"check_type": "elapsed_time", "instruction": "..."}


class CreateSchemaRequest(BaseModel):
    name: str
    description: Optional[str] = None
    document_type: str = "general"
    parameters: List[ParameterDefinition]
    is_shared: bool = False


class UpdateSchemaRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    parameters: Optional[List[ParameterDefinition]] = None
    is_shared: Optional[bool] = None


# ============================================================================
# HELPER
# ============================================================================

def get_user_id(request: Request) -> str:
    """Extract user_id from request headers or use default."""
    user_id = request.headers.get("x-user-id", "default_user")
    get_or_create_user(user_id)
    return user_id


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/schemas")
async def list_schemas(request: Request):
    """List all schemas for the current user (own + shared)."""
    user_id = get_user_id(request)

    try:
        schemas = get_user_schemas(user_id)
        return {
            "schemas": schemas,
            "count": len(schemas)
        }
    except Exception as e:
        logger.error(f"Error listing schemas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schemas")
async def create_schema(request: Request, body: CreateSchemaRequest):
    """Create a new extraction schema."""
    user_id = get_user_id(request)

    try:
        schema = create_extraction_schema(
            user_id=user_id,
            name=body.name,
            parameters=[p.dict() for p in body.parameters],
            description=body.description,
            document_type=body.document_type,
            is_shared=body.is_shared
        )
        return schema
    except Exception as e:
        logger.error(f"Error creating schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schemas/{schema_id}")
async def get_schema_by_id(schema_id: str):
    """Get a schema by ID."""
    try:
        schema = get_schema(schema_id)
        if not schema:
            raise HTTPException(status_code=404, detail="Schema not found")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/schemas/{schema_id}")
async def update_schema_endpoint(schema_id: str, request: Request, body: UpdateSchemaRequest):
    """Update a schema (owner only)."""
    user_id = get_user_id(request)

    try:
        updates = body.dict(exclude_none=True)
        if 'parameters' in updates:
            updates['parameters'] = [p.dict() if hasattr(p, 'dict') else p for p in updates['parameters']]

        schema = update_schema(schema_id, user_id, **updates)
        if not schema:
            raise HTTPException(status_code=403, detail="Not authorized to update this schema")
        return schema
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/schemas/{schema_id}")
async def delete_schema_endpoint(schema_id: str, request: Request):
    """Delete a schema (owner only)."""
    user_id = get_user_id(request)

    try:
        success = delete_schema(schema_id, user_id)
        if not success:
            raise HTTPException(status_code=403, detail="Not authorized to delete this schema")
        return {"success": True, "deleted": schema_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DOCUMENT SEARCH (Ctrl+F via Neo4j)
# ============================================================================

@router.get("/documents/{process_id}/search")
async def search_document_text(process_id: str, q: str = "", limit: int = 200):
    """
    Search document text across all cells, lines, and sections using Neo4j.
    Returns every match with bounding boxes, grouped by page.

    This is an exact text search (CONTAINS), not semantic/vector search.
    100% recall, <10ms, zero cost — ideal for Ctrl+F style lookup.
    """
    if not q or len(q.strip()) < 1:
        return {"query": q, "total_matches": 0, "total_pages": 0, "pages": []}

    neo4j = get_neo4j_service()
    if not neo4j.is_connected:
        raise HTTPException(status_code=503, detail="Neo4j not connected")

    try:
        raw_results = neo4j.search_document_text(process_id, q.strip(), limit=limit)

        # Format results for frontend
        total_matches = 0
        pages = []

        def format_match(m, match_type):
            """Format a single match from any node type (cell, line, section)."""
            if not m or not m.get("key"):
                return None
            # Neo4j stores bbox as left/top/width/height (normalized 0-1)
            left = m.get("bbox_left", 0) or 0
            top = m.get("bbox_top", 0) or 0
            width = m.get("bbox_width", 0) or 0
            height = m.get("bbox_height", 0) or 0
            return {
                "type": match_type,
                "key": m["key"],
                "text": (m.get("text", "") or "")[:200],
                "bbox": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                },
                "row": m.get("row"),
                "col": m.get("col"),
                "chunk_index": m.get("chunk_index"),
            }

        for row in raw_results:
            page_num = row.get("page")
            cell_matches = row.get("cell_matches", [])
            line_matches = row.get("line_matches", [])
            section_matches = row.get("section_matches", [])

            # Collect cell matches first (most precise — table cells)
            matches = []
            for m in cell_matches:
                fmt = format_match(m, "cell")
                if fmt:
                    matches.append(fmt)

            # For lines and sections: only add if bbox doesn't overlap with an existing cell match
            # This prevents duplicate highlights when the same text exists as both Cell and Line
            def overlaps_existing(bbox):
                for existing in matches:
                    eb = existing["bbox"]
                    # Check if bboxes overlap (within 5% tolerance)
                    h_overlap = (bbox["left"] < eb["left"] + eb["width"] + 0.05 and
                                 bbox["left"] + bbox["width"] > eb["left"] - 0.05)
                    v_overlap = (bbox["top"] < eb["top"] + eb["height"] + 0.02 and
                                 bbox["top"] + bbox["height"] > eb["top"] - 0.02)
                    if h_overlap and v_overlap:
                        return True
                return False

            for m in line_matches:
                fmt = format_match(m, "line")
                if fmt and not overlaps_existing(fmt["bbox"]):
                    matches.append(fmt)
            for m in section_matches:
                fmt = format_match(m, "section")
                if fmt and not overlaps_existing(fmt["bbox"]):
                    matches.append(fmt)

            if matches:
                total_matches += len(matches)
                pages.append({
                    "page": page_num,
                    "match_count": len(matches),
                    "matches": matches,
                    "preview": matches[0].get("text", "")[:100] if matches else ""
                })

        return {
            "query": q,
            "total_matches": total_matches,
            "total_pages": len(pages),
            "pages": pages
        }

    except Exception as e:
        logger.error(f"Document search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCHEMA EXECUTION — Discovery + Extraction
# ============================================================================

class DiscoverRequest(BaseModel):
    process_id: str


class ConfirmedParam(BaseModel):
    param_name: str
    pages: List[int]
    param_def: Optional[Dict] = None


class RunExtractionRequest(BaseModel):
    confirmed_params: List[ConfirmedParam]
    process_id: str
    pdf_path: Optional[str] = None


@router.post("/schemas/{schema_id}/discover")
async def discover_pages(schema_id: str, request: Request, body: DiscoverRequest):
    """
    Phase 1: Discover candidate pages for each parameter in a schema.
    Uses Neo4j text search. Returns pages per parameter for user confirmation.
    """
    user_id = get_user_id(request)

    schema = get_schema(schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    try:
        service = get_schema_execution_service()
        result = service.discover_pages(
            schema_id=schema_id,
            parameters=schema.get("parameters", []),
            process_id=body.process_id,
            user_id=user_id
        )
        return result
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schemas/executions/{execution_id}/run")
async def run_extraction(execution_id: str, request: Request, body: RunExtractionRequest):
    """
    Phase 2: Run parameter extraction with Gemini Vision.
    Groups parameters by page, one Gemini call per page.
    Returns SSE stream with progress events.
    """
    execution = get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Find PDF path — look up from DB using process_id (same as extract-parameters)
    pdf_path = body.pdf_path
    if not pdf_path:
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
        try:
            from .database import get_db_cursor
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("""
                    SELECT document_name, file_path
                    FROM chat_documents
                    WHERE process_id = %s
                    LIMIT 1
                """, [body.process_id])
                row = cursor.fetchone()
                if row:
                    fp = row.get('file_path')
                    if fp and os.path.exists(fp):
                        pdf_path = fp
                    if not pdf_path:
                        doc_name = row.get('document_name', '')
                        if doc_name:
                            base = doc_name[:-4] if doc_name.lower().endswith('.pdf') else doc_name
                            sanitized = base.replace(' ', '_')
                            for name in [base, sanitized]:
                                candidate = os.path.join(temp_dir, f"{name}.pdf")
                                if os.path.exists(candidate):
                                    pdf_path = candidate
                                    break
        except Exception as e:
            logger.error(f"PDF lookup failed for run_extraction: {e}")

        logger.info(f"[run-extraction] process_id={body.process_id}, pdf_path={pdf_path}")

    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")

    # Save confirmed params
    update_execution(
        execution_id,
        confirmed_params=[cp.dict() for cp in body.confirmed_params],
        status="running"
    )

    # SSE streaming
    progress_queue = queue.Queue()

    def progress_callback(event_type, data):
        progress_queue.put({"type": event_type, "data": data})

    def run_in_background():
        try:
            service = get_schema_execution_service()
            service.execute_extraction(
                execution_id=execution_id,
                process_id=body.process_id,
                pdf_path=pdf_path,
                confirmed_params=[cp.dict() for cp in body.confirmed_params],
                progress_callback=progress_callback
            )
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            progress_queue.put({"type": "error", "data": {"error": str(e)}})

    # Start background thread
    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()

    async def generate_stream():
        while True:
            try:
                event = progress_queue.get(timeout=180)
                yield f"data: {json.dumps(event)}\n\n"
                if event["type"] in ("complete", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")


@router.get("/schemas/executions/{execution_id}")
async def get_execution_result(execution_id: str):
    """Get execution results."""
    execution = get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/schemas/{schema_id}/executions")
async def list_schema_executions(schema_id: str, limit: int = 10):
    """List recent executions for a schema."""
    try:
        executions = get_executions_by_schema(schema_id, limit=limit)
        return {"executions": executions, "count": len(executions)}
    except Exception as e:
        logger.error(f"Error listing executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schemas/executions/{execution_id}/download")
async def download_execution_excel(execution_id: str):
    """Download extraction results as Excel file."""
    import io
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed")

    execution = get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    results = execution.get("results", [])
    if not results:
        raise HTTPException(status_code=404, detail="No results to download")

    # Build Excel
    wb = openpyxl.Workbook()
    ws = wb.active

    extract_results = [r for r in results if r.get("task_type", "extract") == "extract"]
    verify_results = [r for r in results if r.get("task_type") == "verify"]
    has_verify = len(verify_results) > 0

    # Color fills for status
    green_fill = openpyxl.styles.PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")
    red_fill = openpyxl.styles.PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid")
    amber_fill = openpyxl.styles.PatternFill(start_color="FFF8E1", end_color="FFF8E1", fill_type="solid")
    header_fill = openpyxl.styles.PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")
    bold = openpyxl.styles.Font(bold=True)

    def auto_width(sheet):
        for col in sheet.columns:
            max_len = max(len(str(c.value or "")) for c in col)
            sheet.column_dimensions[col[0].column_letter].width = min(max_len + 3, 50)

    if has_verify:
        # --- Verification Results (single sheet) ---
        ws.title = "Verification Results"
        ver_headers = ["Parameter", "Status", "Finding", "Correction",
                       "Performed By", "Witnessed By", "Page"]
        for c, h in enumerate(ver_headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = bold
            cell.fill = header_fill
        for i, r in enumerate(verify_results, 2):
            ws.cell(row=i, column=1, value=r.get("param_name", ""))
            status = r.get("status", "")
            status_cell = ws.cell(row=i, column=2, value=status.upper() if status else "")
            if status == "pass":
                status_cell.fill = green_fill
                status_cell.font = openpyxl.styles.Font(color="2E7D32", bold=True)
            elif status == "fail":
                status_cell.fill = red_fill
                status_cell.font = openpyxl.styles.Font(color="C62828", bold=True)
            elif status == "warning":
                status_cell.fill = amber_fill
                status_cell.font = openpyxl.styles.Font(color="F57F17", bold=True)
            ws.cell(row=i, column=3, value=r.get("finding", ""))
            ws.cell(row=i, column=4, value=r.get("correction", ""))
            ws.cell(row=i, column=5, value=r.get("performed_by", ""))
            witnessed = r.get("witnessed_by", "")
            witness_cell = ws.cell(row=i, column=6, value=witnessed)
            if witnessed == "No Witness":
                witness_cell.font = openpyxl.styles.Font(color="C62828", bold=True)
            ws.cell(row=i, column=7, value=r.get("page", ""))
        auto_width(ws)
    else:
        # --- Extraction Results (single sheet) ---
        ws.title = "Extraction Results"
        ext_headers = ["Parameter", "Value", "Page", "Confidence"]
        for c, h in enumerate(ext_headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font = bold
            cell.fill = header_fill
        for i, r in enumerate(extract_results, 2):
            ws.cell(row=i, column=1, value=r.get("param_name", ""))
            ws.cell(row=i, column=2, value=r.get("value", ""))
            ws.cell(row=i, column=3, value=r.get("page", ""))
            ws.cell(row=i, column=4, value=r.get("confidence", 0))
        auto_width(ws)

    # Save to bytes
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"extraction_{execution_id}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================================
# PARAMETER EXTRACTION FROM EXCEL — Chat-driven flow
# ============================================================================

@router.post("/extract-parameters/{process_id}")
async def extract_parameters_from_excel(
    process_id: str,
    request: Request,
    file: UploadFile = File(...)
):
    """
    Accept an Excel file with parameters (Parameter, Search_Pages, Comments),
    run Gemini Vision extraction using schema execution logic,
    return results as SSE stream + generate output Excel.
    """
    try:
        import openpyxl
        import pandas as pd
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl/pandas not installed")

    # 1. Read and validate Excel
    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read Excel file: {e}")

    # Normalize column names (case-insensitive)
    col_map = {}
    for col in df.columns:
        lower = str(col).strip().lower().replace(" ", "_")
        if "param" in lower:
            col_map["parameter"] = col
        elif "page" in lower or "search" in lower:
            col_map["search_pages"] = col
        elif "comment" in lower or "hint" in lower:
            col_map["comments"] = col

    if "parameter" not in col_map:
        raise HTTPException(status_code=400, detail="Excel must have a 'Parameter' column")

    # 2. Build parameter list
    params = []
    for _, row in df.iterrows():
        name = str(row.get(col_map["parameter"], "")).strip()
        if not name or name == "nan":
            continue

        # Parse pages
        pages_raw = str(row.get(col_map.get("search_pages", ""), "")).strip()
        pages = []
        if pages_raw and pages_raw != "nan":
            for p in re.split(r'[,;\s]+', pages_raw):
                try:
                    pages.append(int(p))
                except ValueError:
                    pass

        comment = str(row.get(col_map.get("comments", ""), "")).strip()
        if comment == "nan":
            comment = ""

        params.append({
            "name": name,
            "type": "string",
            "hint": comment,
            "pages": pages,
            "task_type": "extract",
        })

    if not params:
        raise HTTPException(status_code=400, detail="No valid parameters found in Excel")

    # 3. Find PDF path — same DB lookup as pdf_image_service.get_pdf_path()
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
    pdf_path = None

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
            logger.info(f"[extract-params] DB lookup for {process_id}: {row}")

            if row:
                # Try file_path first
                fp = row.get('file_path')
                if fp and os.path.exists(fp):
                    pdf_path = fp
                # Try temp/{document_name} with various name formats
                if not pdf_path:
                    doc_name = row.get('document_name', '')
                    if doc_name:
                        # Get base name (without .pdf if present)
                        base = doc_name[:-4] if doc_name.lower().endswith('.pdf') else doc_name
                        # Try original name and sanitized name (spaces → underscores)
                        sanitized = base.replace(' ', '_')
                        for name in [base, sanitized]:
                            candidate = os.path.join(temp_dir, f"{name}.pdf")
                            if os.path.exists(candidate):
                                pdf_path = candidate
                                break
    except Exception as e:
        logger.error(f"[extract-params] DB lookup failed: {e}", exc_info=True)

    logger.info(f"[extract-params] process_id={process_id}, resolved pdf_path={pdf_path}")

    if not pdf_path:
        raise HTTPException(status_code=404, detail="PDF file not found for this document")

    # 4. Build confirmed_params (with discovery for missing pages)
    service = get_schema_execution_service()
    confirmed_params = []

    for param in params:
        if param["pages"]:
            # Pages provided in Excel → use directly
            confirmed_params.append({
                "param_name": param["name"],
                "pages": param["pages"],
                "param_def": param,
            })
        else:
            # No pages → run discovery
            if service.neo4j.is_connected:
                try:
                    results = service.neo4j.search_document_text(process_id, param["name"], limit=20)
                    discovered_pages = [r.get("page") for r in results if r.get("page")]
                    if discovered_pages:
                        confirmed_params.append({
                            "param_name": param["name"],
                            "pages": discovered_pages[:5],
                            "param_def": param,
                        })
                    else:
                        confirmed_params.append({
                            "param_name": param["name"],
                            "pages": [1],  # fallback to page 1
                            "param_def": param,
                        })
                except Exception:
                    confirmed_params.append({
                        "param_name": param["name"],
                        "pages": [1],
                        "param_def": param,
                    })

    if not confirmed_params:
        raise HTTPException(status_code=400, detail="No parameters could be mapped to pages")

    # 5. Execute with SSE streaming
    result_queue = queue.Queue()

    def progress_callback(event_type, data):
        # Suppress the "complete" event from schema_execution_service —
        # we'll emit our own with download_filename after generating Excel
        if event_type == "complete":
            return
        result_queue.put({"type": event_type, "data": data})

    def run_extraction():
        try:
            from .database import create_execution, update_execution
            execution = create_execution("excel_upload", process_id, "chat_user")
            execution_id = execution["execution_id"]

            result = service.execute_extraction(
                execution_id=execution_id,
                process_id=process_id,
                pdf_path=pdf_path,
                confirmed_params=confirmed_params,
                progress_callback=progress_callback
            )

            # Generate output Excel
            all_results = result.get("results", [])
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Extraction Results"
            bold = openpyxl.styles.Font(bold=True)
            headers = ["Parameter", "Value", "Page", "Confidence"]
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=1, column=c, value=h)
                cell.font = bold
            for i, r in enumerate(all_results, 2):
                ws.cell(row=i, column=1, value=r.get("param_name", ""))
                ws.cell(row=i, column=2, value=r.get("value", ""))
                ws.cell(row=i, column=3, value=r.get("page", ""))
                ws.cell(row=i, column=4, value=r.get("confidence", 0))
            for col in ws.columns:
                max_len = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 50)

            output_filename = f"parameter_extraction_{execution_id}.xlsx"
            output_path = os.path.join(temp_dir, output_filename)
            wb.save(output_path)
            logger.info(f"[extract-params] Excel saved: {output_path}")

            # Emit the single "complete" with download_filename
            result_queue.put({
                "type": "complete",
                "data": {
                    "execution_id": execution_id,
                    "results": all_results,
                    "summary": result.get("summary", {}),
                    "download_filename": output_filename
                }
            })
        except Exception as e:
            logger.error(f"Excel parameter extraction failed: {e}")
            result_queue.put({"type": "error", "data": {"error": str(e)}})

    thread = threading.Thread(target=run_extraction, daemon=True)
    thread.start()

    def event_stream():
        while True:
            try:
                event = result_queue.get(timeout=180)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
