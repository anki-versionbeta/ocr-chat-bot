"""
Schema Execution Service — Discovery + Parameter Extraction + Verification via Gemini Vision

Phase 1 (Discovery): Neo4j text search per parameter → find candidate pages
Phase 2 (Extraction + Verification): Group params by page → Gemini Vision (image + OCR) → structured results

Supports mixed schemas with both "extract" and "verify" task types in a single execution pass.
Verification is image-driven — Gemini inspects the page visually, not formula-locked.

Reuses:
- visual_audit_service.extract_page_as_image() for PDF→base64 PNG
- weaviate_indexer.get_all_chunks_for_page() for OCR text + grounding
- neo4j_service.search_document_text() for page discovery
"""

import os
import re
import json
import logging
import requests
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .neo4j_service import get_neo4j_service
from .weaviate_indexer import WeaviateIndexer
from .visual_audit_service import extract_page_as_image
from .database import create_execution, update_execution, get_execution

ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED
GEMINI_MODEL = "gemini-3.1-pro-preview"
# Fallback models for 429 rate-limit or failures (ordered by quality)
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]

logger = logging.getLogger("ocr-chatbot.schema_execution")

MAX_PARALLEL_PAGES = 3
MAX_PARAMS_PER_GEMINI_CALL = 10

# =========================================================================
# VERIFICATION TEMPLATES — Image-driven instructions (NOT formula-locked)
# Gemini Vision reads the page and adapts to whatever format the document uses.
# =========================================================================
VERIFICATION_TEMPLATES = {
    "elapsed_time": (
        "Look at this page image carefully. Find all time-related values and any "
        "calculations involving elapsed time, duration, start time, or end time. "
        "Verify the arithmetic is correct based on how the values and calculations "
        "appear on the page. If a value was corrected (strikethrough + new value), "
        "verify the corrected value is mathematically correct. "
        "Report: what calculation you found, expected result, actual result, "
        "who performed (initials + date from Perform column), "
        "who witnessed (initials + date from Confirm column, or 'No Witness' if empty)."
    ),
    "witness_verification": (
        "Look at this page image carefully. Find all corrections or strikethroughs "
        "on this page. For each correction, check if a witness exists with initials "
        "and date near the correction area (typically in the Confirm/Date column). "
        "Report: what was corrected (old value → new value), who performed the "
        "correction (initials + date), who witnessed it (initials + date), or "
        "'No Witness' if no witness signature/initials found near the correction."
    ),
    "significant_figures": (
        "Look at this page image carefully. Check if the recorded numerical values "
        "match the significant figures required by the specification shown on the page. "
        "If a value was corrected for significant figures (e.g., 37.0 → 37), verify "
        "the correction is appropriate. Report: the original value, corrected value, "
        "specification, who performed, who witnessed."
    ),
    "correction_check": (
        "Look at this page image carefully. Find ALL corrections on this page — "
        "any value that has been struck through and replaced with a new value. "
        "For each correction, report: the original (struck-through) value, the "
        "new corrected value, the reason for correction if noted, who performed "
        "the correction (initials + date), and who witnessed it (initials + date "
        "or 'No Witness' if missing)."
    ),
    "calculation_check": (
        "Look at this page image carefully. Find all mathematical calculations "
        "visible on this page. Verify each calculation is arithmetically correct "
        "based on how the values appear visually. If any calculation was corrected, "
        "verify the corrected value. Report: the calculation found, expected result, "
        "actual result, and whether it passes or fails."
    ),
    "date_sequence": (
        "Look at this page image carefully. Check all dates visible on this page. "
        "Verify they are in correct chronological order (earlier dates should come "
        "before later dates in the workflow sequence). Report any dates that appear "
        "out of sequence."
    ),
    "custom": "",  # User provides instruction directly
}


class SchemaExecutionService:

    def __init__(self):
        self.neo4j = get_neo4j_service()
        self.weaviate = WeaviateIndexer()

    # =========================================================================
    # PHASE 1: DISCOVERY — Find candidate pages per parameter
    # =========================================================================

    def discover_pages(
        self,
        schema_id: str,
        parameters: List[Dict],
        process_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        For each parameter, find which pages contain it.
        Uses Neo4j text search (same as Document Search Ctrl+F).

        Returns execution record with discovery results.
        """
        execution = create_execution(schema_id, process_id, user_id)
        execution_id = execution["execution_id"]

        discovery = []

        for param in parameters:
            name = param.get("name", "")
            hint = param.get("hint", "") or ""
            explicit_page = param.get("page")

            # Check if page field is set directly → auto-confirm
            if explicit_page:
                auto_page = int(explicit_page)
            elif re.search(r'page\s+(\d+)', hint, re.IGNORECASE):
                auto_page = int(re.search(r'page\s+(\d+)', hint, re.IGNORECASE).group(1))
            else:
                auto_page = None

            if auto_page:
                discovery.append({
                    "param_name": name,
                    "hint": hint,
                    "candidate_pages": [{"page": auto_page, "preview": f"From hint: page {auto_page}"}],
                    "confirmed_pages": [auto_page],
                    "auto_confirmed": True,
                    "source": "hint"
                })
                continue

            # Search Neo4j for parameter name
            if self.neo4j.is_connected:
                try:
                    results = self.neo4j.search_document_text(process_id, name, limit=50)
                    candidates = []
                    for row in results:
                        page_num = row.get("page")
                        # Get first preview text from any match type
                        preview = ""
                        for match_type in ["cell_matches", "line_matches", "section_matches"]:
                            for m in (row.get(match_type) or []):
                                if m and m.get("text"):
                                    preview = (m["text"] or "")[:100]
                                    break
                            if preview:
                                break
                        candidates.append({"page": page_num, "preview": preview})

                    # Auto-confirm if only 1 page found
                    auto = len(candidates) == 1
                    discovery.append({
                        "param_name": name,
                        "hint": hint,
                        "candidate_pages": candidates,
                        "confirmed_pages": [candidates[0]["page"]] if auto else [],
                        "auto_confirmed": auto,
                        "source": "neo4j"
                    })
                    continue
                except Exception as e:
                    logger.error(f"Neo4j discovery failed for '{name}': {e}")

            # Fallback: not found
            discovery.append({
                "param_name": name,
                "hint": hint,
                "candidate_pages": [],
                "confirmed_pages": [],
                "auto_confirmed": False,
                "source": "not_found"
            })

        # Save discovery to DB
        update_execution(execution_id, discovery=discovery, status="discovered")

        return {
            "execution_id": execution_id,
            "schema_id": schema_id,
            "process_id": process_id,
            "discovery": discovery,
            "status": "discovered"
        }

    # =========================================================================
    # PHASE 2: EXTRACTION — Group by page → Gemini Vision
    # =========================================================================

    def execute_extraction(
        self,
        execution_id: str,
        process_id: str,
        pdf_path: str,
        confirmed_params: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Execute parameter extraction using Gemini Vision.
        Groups parameters by page, one Gemini call per page.

        Args:
            execution_id: DB record ID
            process_id: Weaviate/Neo4j document ID
            pdf_path: Path to PDF file
            confirmed_params: [{param_name, param_def, pages: [3, 7]}]
            progress_callback: fn(event_type, data) for SSE streaming
        """
        def emit(event_type, data):
            if progress_callback:
                progress_callback(event_type, data)

        update_execution(execution_id, status="running")

        # Step 1: Group parameters by page
        page_groups = {}  # {page_num: [{param_name, param_def}]}
        for cp in confirmed_params:
            param_name = cp["param_name"]
            param_def = cp.get("param_def", {})
            for page in cp.get("pages", []):
                if page not in page_groups:
                    page_groups[page] = []
                page_groups[page].append({
                    "param_name": param_name,
                    "type": param_def.get("type", "string"),
                    "unit": param_def.get("unit"),
                    "hint": param_def.get("hint", ""),
                    "task_type": param_def.get("task_type", "extract"),
                    "verification_config": param_def.get("verification_config"),
                })

        total_pages = len(page_groups)
        total_params = sum(len(params) for params in page_groups.values())

        emit("schema_start", {
            "total_params": total_params,
            "total_pages": total_pages,
            "pages": list(page_groups.keys())
        })

        logger.info(f"Execution {execution_id}: {total_params} params across {total_pages} pages")

        # Step 2: Process each page group (parallel, max 3)
        all_results = []

        def process_page_group(page_num, params):
            """Process one page: render image → get OCR → call Gemini → parse results."""
            emit("page_start", {
                "page": page_num,
                "params": [p["param_name"] for p in params],
                "status": "analyzing"
            })

            try:
                # 2a: Render page as image
                image_base64 = extract_page_as_image(pdf_path, page_num, zoom=2.0)
                if not image_base64:
                    logger.error(f"Failed to render page {page_num}")
                    return [{"param_name": p["param_name"], "found": False,
                             "value": None, "error": "Page render failed"} for p in params]

                # 2b: Get ALL chunks for this page (complete content, no keyword filter)
                page_chunks = self.weaviate.get_all_chunks_for_page(
                    process_id=process_id,
                    page_num=page_num,
                    limit=50
                )

                # Build OCR text
                ocr_parts = []
                for chunk in page_chunks:
                    content = chunk.get("content", "")
                    chunk_type = chunk.get("chunk_type", "text")
                    ocr_parts.append(f"[{chunk_type.upper()}]: {content}")
                ocr_text = "\n\n".join(ocr_parts) or "No OCR text available."

                # Build grounding references (cell + line) AND bbox lookup map
                grounding_lines = []
                bbox_lookup = {}  # ref_key → {left, top, width, height}
                for chunk in page_chunks:
                    chunk_idx = chunk.get("chunk_index", 0)
                    # Cell grounding (tables)
                    cg = chunk.get("cell_grounding")
                    if cg:
                        cg_data = json.loads(cg) if isinstance(cg, str) else cg
                        for cell_id, info in (cg_data or {}).items():
                            ref_key = f"[cell:{chunk_idx}:{cell_id}]"
                            grounding_lines.append(
                                f"{ref_key} row={info.get('row')}, col={info.get('col')}: \"{info.get('text', '')}\""
                            )
                            bbox = info.get("bbox", {})
                            if bbox:
                                bbox_lookup[ref_key] = {
                                    "left": bbox.get("left", 0),
                                    "top": bbox.get("top", 0),
                                    "width": bbox.get("width", 0),
                                    "height": bbox.get("height", 0),
                                }
                    # Line grounding (text blocks)
                    lg = chunk.get("line_grounding")
                    if lg:
                        lg_data = json.loads(lg) if isinstance(lg, str) else lg
                        for line_id, info in (lg_data or {}).items():
                            ref_key = f"[line:{chunk_idx}:{line_id}]"
                            grounding_lines.append(
                                f"{ref_key}: \"{info.get('text', '')}\""
                            )
                            bbox = info.get("bbox", {})
                            if bbox:
                                bbox_lookup[ref_key] = {
                                    "left": bbox.get("left", 0),
                                    "top": bbox.get("top", 0),
                                    "width": bbox.get("width", 0),
                                    "height": bbox.get("height", 0),
                                }
                grounding_text = "\n".join(grounding_lines) if grounding_lines else "No reference data."

                # 2c: Build prompt (handles both extract and verify params)
                has_verify = any(p.get("task_type") == "verify" for p in params)
                if has_verify:
                    user_prompt = self._build_page_prompt(params, grounding_text)
                else:
                    user_prompt = self._build_extraction_prompt(params, grounding_text)

                gemini_result = self._call_gemini_extraction(
                    image_base64=image_base64,
                    ocr_text=ocr_text,
                    user_prompt=user_prompt
                )

                if not gemini_result.get("success"):
                    logger.error(f"Gemini failed for page {page_num}: {gemini_result.get('error')}")
                    return [{"param_name": p["param_name"], "found": False,
                             "value": None, "page": page_num,
                             "error": gemini_result.get("error", "Gemini call failed")} for p in params]

                # 2e: Parse JSON response and resolve refs to bboxes
                analysis = gemini_result.get("analysis", "")
                page_results = self._parse_extraction_response(analysis, params, page_num, bbox_lookup)

                # 2f: Agent 2 — Deep validation for verify results
                verify_results = [r for r in page_results if r.get("task_type") == "verify" and r.get("found")]
                if verify_results:
                    page_results = self._deep_validate_verification(
                        image_base64, page_results
                    )

                # Emit per-parameter results
                for r in page_results:
                    emit("param_result", r)

                emit("page_complete", {
                    "page": page_num,
                    "params_found": sum(1 for r in page_results if r.get("found")),
                    "params_total": len(params)
                })

                return page_results

            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                return [{"param_name": p["param_name"], "found": False,
                         "value": None, "page": page_num, "error": str(e)} for p in params]

        # Run page groups in parallel (max 3)
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_PAGES) as executor:
            futures = {}
            for page_num, params in page_groups.items():
                future = executor.submit(process_page_group, page_num, params)
                futures[future] = page_num

            for future in as_completed(futures):
                page_results = future.result()
                all_results.extend(page_results)

        # Step 3: Build summary and save
        verify_results = [r for r in all_results if r.get("task_type") == "verify"]
        extract_results = [r for r in all_results if r.get("task_type", "extract") == "extract"]
        summary = {
            "total_params": total_params,
            "found": sum(1 for r in all_results if r.get("found")),
            "not_found": sum(1 for r in all_results if not r.get("found")),
            "pages_analyzed": list(page_groups.keys()),
            "gemini_calls": total_pages,
            "extract_count": len(extract_results),
            "verify_count": len(verify_results),
            "verify_pass": sum(1 for r in verify_results if r.get("status") == "pass"),
            "verify_fail": sum(1 for r in verify_results if r.get("status") == "fail"),
            "verify_warning": sum(1 for r in verify_results if r.get("status") == "warning"),
        }

        update_execution(
            execution_id,
            status="completed",
            results=all_results,
            summary=summary,
            completed_at="NOW()"
        )

        emit("complete", {
            "execution_id": execution_id,
            "results": all_results,
            "summary": summary
        })

        return {"execution_id": execution_id, "results": all_results, "summary": summary}

    # =========================================================================
    # GEMINI EXTRACTION CALL (separate from visual audit)
    # =========================================================================

    def _call_gemini_extraction(
        self,
        image_base64: str,
        ocr_text: str,
        user_prompt: str
    ) -> Dict[str, Any]:
        """
        Call Gemini Vision specifically for parameter extraction.
        Uses a dedicated system prompt focused on precise value extraction
        from handwritten/printed documents with strikethrough awareness.
        Retries with fallback models on 429 rate-limit errors.
        """
        system_prompt = f"""You are a precise document data extractor and verifier. You receive a page image and OCR text.

Your job: Extract specific parameter values AND perform verification checks by visually inspecting the page image.

CRITICAL RULES:
- ALWAYS trust the visual image over OCR text. OCR can be inaccurate.
- Extract the current valid value as it visually appears on the page.
- If multiple instances exist, use the Comment/Hint to pick the right one.
- For VERIFICATION tasks, carefully inspect the page image for:
  * Strikethrough text (original values crossed out)
  * Handwritten corrections next to strikethroughs
  * Initials and dates near corrections (Perform/Date and Confirm/Date columns)
  * Mathematical calculations — verify arithmetic based on how values appear visually
  * Significant figures — check against specification shown on page
- The task name is a user-given label — it may not appear literally on the page. Use the page content to understand what it refers to.

OCR TEXT (for reference only — verify against the image):
{ocr_text}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                {"type": "text", "text": user_prompt}
            ]}
        ]

        # Try primary model, then fallbacks on 429/5xx errors
        models_to_try = [GEMINI_MODEL] + GEMINI_FALLBACK_MODELS

        for model in models_to_try:
            try:
                logger.info(f"Calling Gemini extraction with model: {model}")
                response = requests.post(
                    f"{ILIAD_URL}/api/llm/v1/chat/completions",
                    headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 4000,
                        "temperature": 0
                    },
                    timeout=120
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    if model != GEMINI_MODEL:
                        logger.info(f"Extraction succeeded with fallback model: {model} ({len(content)} chars)")
                    else:
                        logger.info(f"Extraction Gemini completed ({len(content)} chars)")
                    return {"success": True, "analysis": content, "model_used": model}

                elif response.status_code in (429, 500, 502, 503):
                    logger.warning(f"Model {model} returned {response.status_code}, trying next fallback...")
                    import time
                    time.sleep(1)  # Brief pause before fallback
                    continue
                else:
                    logger.error(f"Extraction Gemini error: {response.status_code} (model: {model})")
                    return {"success": False, "error": f"API error: {response.status_code}"}

            except requests.exceptions.Timeout:
                logger.warning(f"Model {model} timed out, trying next fallback...")
                continue
            except Exception as e:
                logger.error(f"Extraction Gemini error with {model}: {e}")
                continue

        return {"success": False, "error": "All models failed (rate-limited or unavailable)"}

    # =========================================================================
    # PROMPT BUILDING
    # =========================================================================

    def _build_extraction_prompt(self, params: List[Dict], grounding_text: str) -> str:
        """Build Gemini prompt listing all parameters for one page."""
        param_lines = []
        for i, p in enumerate(params, 1):
            line = f'{i}. "{p["param_name"]}" (type: {p.get("type", "string")}'
            if p.get("unit"):
                line += f', unit: {p["unit"]}'
            line += ")"
            hint = p.get("hint", "")
            if hint:
                line += f"\n   Comment: {hint}"
            param_lines.append(line)

        return f"""Look at the page image carefully and extract these parameters. Return ONLY a JSON array.

REFERENCE IDS (cite these when you find values):
{grounding_text}

Parameters:
{chr(10).join(param_lines)}

Rules:
- Trust the image over OCR. Extract the current valid value as it appears on the page.
- Use the Comment to locate the correct instance when multiple exist.
- For each value, include the reference ID from REFERENCE IDS above that contains that value.

Return format:
{{"param": "<name>", "value": "<final correct value>", "confidence": <0-1>, "ref": "<ref ID>", "found": true}}

If not found:
{{"param": "<name>", "value": null, "confidence": 0, "ref": null, "found": false}}

JSON array only, no other text."""

    def _build_page_prompt(self, params: List[Dict], grounding_text: str) -> str:
        """Build combined Gemini prompt for mixed extract + verify params on one page."""
        extract_params = [p for p in params if p.get("task_type", "extract") == "extract"]
        verify_params = [p for p in params if p.get("task_type") == "verify"]

        sections = []
        task_num = 0

        # Extraction section
        if extract_params:
            sections.append("== EXTRACTION TASKS ==")
            for p in extract_params:
                task_num += 1
                line = f'Task {task_num} - EXTRACT "{p["param_name"]}" (type: {p.get("type", "string")}'
                if p.get("unit"):
                    line += f', unit: {p["unit"]}'
                line += ")"
                hint = p.get("hint", "")
                if hint:
                    line += f"\n   Comment: {hint}"
                sections.append(line)

        # Verification section
        if verify_params:
            sections.append("\n== VERIFICATION TASKS ==")
            for p in verify_params:
                task_num += 1
                config = p.get("verification_config") or {}
                check_type = config.get("check_type", "custom")
                instruction = config.get("instruction") or VERIFICATION_TEMPLATES.get(check_type, "")

                line = f'Task {task_num} - VERIFY "{p["param_name"]}"'
                line += f"\n   Check type: {check_type}"
                line += f"\n   Instruction: {instruction}"
                hint = p.get("hint", "")
                if hint:
                    line += f"\n   Additional hint: {hint}"
                sections.append(line)

        tasks_text = "\n\n".join(sections)

        return f"""Look at the page image carefully and complete these tasks. Return ONLY a JSON array.

REFERENCE IDS (cite these when you find values):
{grounding_text}

{tasks_text}

Return format — For each task, return ONE JSON object using the EXACT "param" name as written above:

For EXTRACT tasks:
{{"task_type": "extract", "param": "<exact name from above>", "value": "<final correct value>", "confidence": <0-1>, "ref": "<ref ID>", "found": true}}

For VERIFY tasks:
{{"task_type": "verify", "param": "<exact name from above>", "status": "pass|fail|warning", "finding": "<detailed description>", "correction": "<old_value -> new_value or null>", "expected": "<expected value or null>", "actual": "<actual value or null>", "performed_by": "<initials date or null>", "witnessed_by": "<initials date or No Witness>", "refs": ["<ref1>", "<ref2>"], "found": true}}

Rules:
- The "param" name is a user label. Use the page image + OCR to understand what it refers to.
- ALWAYS copy the param name exactly as given above in your response.
- Trust the image over OCR. Inspect visually for strikethroughs, corrections, initials, dates.
- Use reference IDs from REFERENCE IDS above to cite specific cells.

JSON array only, no other text."""

    # =========================================================================
    # RESPONSE PARSING
    # =========================================================================

    def _parse_extraction_response(
        self,
        analysis: str,
        params: List[Dict],
        page_num: int,
        bbox_lookup: Dict = None
    ) -> List[Dict]:
        """Parse Gemini's JSON array response into structured results with bboxes."""
        bbox_lookup = bbox_lookup or {}

        def resolve_bbox(ref_str):
            """Look up bbox from grounding map using the ref string."""
            if not ref_str:
                return None
            # Normalize: ensure brackets
            key = ref_str.strip()
            if not key.startswith("["):
                key = f"[{key}]"
            # Direct match
            if key in bbox_lookup:
                return bbox_lookup[key]
            # Try partial match (Gemini may return slightly different format)
            for k, v in bbox_lookup.items():
                if ref_str in k or k in ref_str:
                    return v
            return None

        try:
            # Handle markdown code blocks
            text = analysis.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            parsed = json.loads(text.strip())

            if not isinstance(parsed, list):
                parsed = [parsed]

            # Map results back to parameters (case-insensitive matching)
            results = []
            parsed_map = {}
            for r in parsed:
                key = (r.get("param") or "").strip()
                parsed_map[key] = r
                parsed_map[key.lower()] = r  # also store lowercase for fallback

            for p in params:
                name = p["param_name"]
                task_type = p.get("task_type", "extract")

                # Try exact match first, then case-insensitive
                matched = parsed_map.get(name) or parsed_map.get(name.lower())

                if matched:
                    r = matched

                    if task_type == "verify":
                        # Resolve multiple refs to multiple bboxes
                        refs = r.get("refs") or []
                        if not refs and r.get("ref"):
                            refs = [r.get("ref")]
                        bboxes = [b for b in (resolve_bbox(ref) for ref in refs) if b]
                        single_ref = refs[0] if refs else None

                        results.append({
                            "param_name": name,
                            "task_type": "verify",
                            "status": r.get("status"),
                            "finding": r.get("finding"),
                            "correction": r.get("correction"),
                            "expected": r.get("expected"),
                            "actual": r.get("actual"),
                            "performed_by": r.get("performed_by"),
                            "witnessed_by": r.get("witnessed_by"),
                            "ref": single_ref,
                            "refs": refs,
                            "bbox": bboxes[0] if bboxes else None,
                            "bboxes": bboxes if bboxes else None,
                            "found": r.get("found", True),
                            "page": page_num,
                            "confidence": r.get("confidence", 0),
                            "value": None,
                        })
                    else:
                        # Extraction result (unchanged)
                        ref = r.get("ref")
                        bbox = resolve_bbox(ref)
                        results.append({
                            "param_name": name,
                            "task_type": "extract",
                            "value": r.get("value"),
                            "confidence": r.get("confidence", 0),
                            "ref": ref,
                            "bbox": bbox,
                            "found": r.get("found", r.get("value") is not None),
                            "page": page_num
                        })
                else:
                    results.append({
                        "param_name": name,
                        "task_type": task_type,
                        "value": None,
                        "confidence": 0,
                        "ref": None,
                        "bbox": None,
                        "found": False,
                        "page": page_num,
                        **({"status": "warning", "finding": "Not found in Gemini response"} if task_type == "verify" else {})
                    })

            return results

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse Gemini response for page {page_num}: {e}")
            logger.debug(f"Raw response: {analysis[:500]}")
            return [{
                "param_name": p["param_name"],
                "value": None,
                "confidence": 0,
                "ref": None,
                "bbox": None,
                "found": False,
                "page": page_num,
                "error": f"Parse error: {str(e)}"
            } for p in params]


    # =========================================================================
    # AGENT 2: DEEP VALIDATION — Re-inspect image to verify structured fields
    # =========================================================================

    def _deep_validate_verification(
        self,
        image_base64: str,
        results: List[Dict]
    ) -> List[Dict]:
        """
        Agent 2: Deep validation pass using Gemini Pro Vision.

        Takes the findings from Agent 1 and the SAME page image.
        Looks at the image again with focused attention to verify and extract:
        - correction: exact old → new value
        - performed_by: exact initials + date from Perform/Date column
        - witnessed_by: exact initials + date from Confirm/Date column, or "No Witness"

        Uses the same vision model because it needs to read handwritten initials.
        """
        verify_items = []
        for i, r in enumerate(results):
            if r.get("task_type") == "verify" and r.get("found") and r.get("finding"):
                verify_items.append((i, r))

        if not verify_items:
            return results

        # Build validation prompt with findings from Agent 1
        items_text = []
        for idx, (_, r) in enumerate(verify_items):
            items_text.append(f"""Item {idx + 1}: "{r['param_name']}"
Agent 1 Finding: {r.get('finding', '')}
Agent 1 correction: {r.get('correction', 'null')}
Agent 1 performed_by: {r.get('performed_by', 'null')}
Agent 1 witnessed_by: {r.get('witnessed_by', 'null')}""")

        system_prompt = """You are a document verification validator. Another agent analyzed this page and wrote findings.
Your job: Look at the page image and extract the EXACT structured fields by reading the image carefully.
You MUST extract values from the image. NEVER return null — always give your best reading."""

        user_prompt = f"""An agent analyzed this page and produced these findings. Now YOU look at the page image and verify the structured fields.

{chr(10).join(items_text)}

For each item, look at the image — find the area described in the finding, then extract:

1. CORRECTION: The old value (struck through) and new value. Format: "old -> new"
2. PERFORMED BY: Who performed it — initials + date visible near the relevant area
3. WITNESSED BY: Who witnessed/confirmed it — initials + date, or "No Witness" if no witness is visible

Return a JSON object for each item:
{{"item": <number>, "correction": "<old -> new>", "performed_by": "<initials date>", "witnessed_by": "<initials date, or 'No Witness'>"}}

RULES:
- NEVER return null. Always read the image and give your best answer.
- Look at the area described in the finding AND any related notes/footnotes on the page.
- performed_by and witnessed_by are usually DIFFERENT people.
- If the finding mentions names/initials, verify them against what you see in the image.

JSON array only, no other text."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    {"type": "text", "text": user_prompt}
                ]}
            ]

            # Try primary model, then fallbacks on 429/5xx
            content = None
            for model in [GEMINI_MODEL] + GEMINI_FALLBACK_MODELS:
                response = requests.post(
                    f"{ILIAD_URL}/api/llm/v1/chat/completions",
                    headers={"X-API-Key": ILIAD_API_KEY, "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": 2000,
                        "temperature": 0
                    },
                    timeout=120
                )
                if response.status_code == 200:
                    content = response.json()["choices"][0]["message"]["content"]
                    if model != GEMINI_MODEL:
                        logger.info(f"Agent 2 succeeded with fallback: {model}")
                    break
                elif response.status_code in (429, 500, 502, 503):
                    logger.warning(f"Agent 2 model {model} returned {response.status_code}, trying fallback...")
                    import time
                    time.sleep(1)
                    continue
                else:
                    logger.warning(f"Agent 2 validation call failed: {response.status_code}")
                    return results

            if not content:
                logger.warning("Agent 2: All models failed")
                return results

            # Parse JSON
            text = content.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            validated = json.loads(text.strip())
            if not isinstance(validated, list):
                validated = [validated]

            # Apply validated fields back to results
            val_map = {v.get("item"): v for v in validated}
            for idx, (result_idx, _) in enumerate(verify_items):
                v = val_map.get(idx + 1)
                if not v:
                    continue
                r = results[result_idx]
                # Overwrite with Agent 2's verified values (only if non-null)
                if v.get("correction") and v["correction"] != "null":
                    r["correction"] = v["correction"]
                if v.get("performed_by") and v["performed_by"] != "null":
                    r["performed_by"] = v["performed_by"]
                if v.get("witnessed_by") and v["witnessed_by"] != "null":
                    r["witnessed_by"] = v["witnessed_by"]

            logger.info(f"Agent 2 validated {len(verify_items)} verification results")
            return results

        except Exception as e:
            logger.warning(f"Agent 2 validation failed: {e}")
            return results  # Return Agent 1 results if validation fails


# Singleton
_service_instance = None

def get_schema_execution_service() -> SchemaExecutionService:
    global _service_instance
    if _service_instance is None:
        _service_instance = SchemaExecutionService()
    return _service_instance
