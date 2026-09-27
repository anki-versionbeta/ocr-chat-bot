"""
Extract & Verify Engine v4 — Production-grade with full failure handling.

Architecture:
- Extraction: Independent parallel batches → merge → deduplicate
- Verification: Two-phase (gather inventory → judge with complete picture)
- All edge cases handled: retries, fallbacks, dedup, corrupt pages, token limits
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import requests as http_requests

from .gemini_client import GeminiClient
from .models import (
    ExtractVerifyRequest,
    ExtractVerifyResponse,
    ExtractionResult,
    ExtractionRow,
    VerificationFinding,
    VerificationResult,
)
from .prompts import (
    build_extraction_prompt,
    build_verify_gather_prompt,
    build_verify_judge_prompt,
)
from .utils import get_pdf_page_count, pdf_to_jpeg_pages

logger = logging.getLogger("extract_verify.engine")

_global_semaphore = threading.Semaphore(6)

EXTRACT_PAGES_PER_BATCH = 25
VERIFY_PAGES_PER_BATCH = 25  # Same as extract — 50 pages produced too much inventory
MAX_PARALLEL = 4
MAX_JUDGE_INVENTORY_CHARS = 60000  # If inventory exceeds this, summarize before judge


class ExtractVerifyEngine:
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.client = gemini_client or GeminiClient()

    def run(
        self,
        request: ExtractVerifyRequest,
        progress_callback: Optional[Callable] = None,
    ) -> ExtractVerifyResponse:
        errors: List[str] = []
        start_time = time.time()

        def emit(event_type: str, data: Optional[Dict] = None):
            if progress_callback:
                progress_callback(event_type, data or {})

        if not request.extraction_tasks and not request.verification_tasks:
            return ExtractVerifyResponse(errors=["No tasks provided"])

        # ── 1. PDF validation + render ──────────────────────────────────
        try:
            total_pages = get_pdf_page_count(request.pdf_path)
        except Exception as e:
            return ExtractVerifyResponse(errors=[f"Cannot open PDF: {e}"])

        if total_pages == 0:
            return ExtractVerifyResponse(errors=["PDF has 0 pages"])

        emit("start", {
            "total_pages": total_pages,
            "extraction_tasks": len(request.extraction_tasks),
            "verification_tasks": len(request.verification_tasks),
        })

        pages_to_render = self._resolve_pages(request, total_pages)
        emit("rendering", {"pages": len(pages_to_render)})

        t0 = time.time()
        images = pdf_to_jpeg_pages(request.pdf_path, pages=pages_to_render)
        render_time = time.time() - t0

        # Check for failed pages
        failed_pages = [p for p in pages_to_render if p not in images]
        if failed_pages:
            errors.append(f"Failed to render {len(failed_pages)} pages: {failed_pages[:10]}")

        emit("images_ready", {
            "count": len(images),
            "failed_pages": len(failed_pages),
            "render_time_s": round(render_time, 1),
        })

        if not images:
            return ExtractVerifyResponse(errors=["All page renders failed"])

        sorted_pages = sorted(images.keys())
        has_extract = bool(request.extraction_tasks)
        has_verify = bool(request.verification_tasks)

        # ── 2. Batch planning ───────────────────────────────────────────
        extract_batches = self._make_batches(sorted_pages, EXTRACT_PAGES_PER_BATCH) if has_extract else []
        verify_batches = self._make_batches(sorted_pages, VERIFY_PAGES_PER_BATCH) if has_verify else []

        total_calls = len(extract_batches) + len(verify_batches) + (1 if has_verify else 0)
        emit("processing", {
            "mode": "two_phase_parallel",
            "extract_batches": len(extract_batches),
            "gather_batches": len(verify_batches),
            "judge_call": 1 if has_verify else 0,
            "total_api_calls": total_calls,
        })

        # ── 3. PHASE 1: Parallel extraction + gather ────────────────────
        extract_prompt = build_extraction_prompt(request.extraction_tasks) if has_extract else ""
        gather_prompt = build_verify_gather_prompt(request.verification_tasks) if has_verify else ""

        extract_parsed = []
        gather_parsed = []
        lock = threading.Lock()

        def run_batch(job_type, batch_idx, batch_pages, prompt, max_tokens):
            with _global_semaphore:
                batch_images = {p: images[p] for p in batch_pages if p in images}
                page_range = f"{batch_pages[0]}-{batch_pages[-1]}"
                batch_prompt = f"These are pages {page_range} of the document.\n\n{prompt}"

                parsed = self._call_with_retry(batch_images, batch_prompt, max_tokens)

                with lock:
                    emit(f"{job_type}_batch_complete", {
                        "batch": batch_idx + 1,
                        "pages": page_range,
                    })

                return job_type, batch_idx, parsed

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
            futures = []
            if extract_prompt:
                for idx, batch in enumerate(extract_batches):
                    futures.append(executor.submit(
                        run_batch, "extract", idx, batch, extract_prompt, 32000
                    ))
            if gather_prompt:
                for idx, batch in enumerate(verify_batches):
                    futures.append(executor.submit(
                        run_batch, "gather", idx, batch, gather_prompt, 32000
                    ))

            for future in as_completed(futures):
                try:
                    job_type, batch_idx, parsed = future.result()
                    if job_type == "extract":
                        extract_parsed.append(parsed)
                    else:
                        gather_parsed.append(parsed)
                except Exception as e:
                    errors.append(f"Batch failed: {e}")

        # ── 4. Merge extraction + deduplicate ───────────────────────────
        extraction_results = []
        if has_extract:
            extraction_results = self._merge_extraction(extract_parsed, request.extraction_tasks)
            extraction_results = self._deduplicate_extraction(extraction_results)

        # ── 5. PHASE 2: Verify judge ────────────────────────────────────
        verification_results = []
        if has_verify:
            emit("verify_judge_start", {})
            verification_results = self._run_judge(
                gather_parsed, request.verification_tasks, errors
            )
            emit("verify_judge_complete", {})

        # ── 6. Response ─────────────────────────────────────────────────
        total_time = time.time() - start_time
        total_rows = sum(r.row_count for r in extraction_results)

        emit("complete", {
            "total_extraction_rows": total_rows,
            "total_time_s": round(total_time, 1),
            "api_calls": total_calls,
            "errors": len(errors),
        })

        return ExtractVerifyResponse(
            extraction_results=extraction_results,
            verification_results=verification_results,
            pages_analyzed=len(images),
            total_pages=total_pages,
            model_used=self.client.last_model_used,
            batches_used=total_calls,
            errors=errors,
        )

    # ─── API CALL WITH RETRY ───────────────────────────────────────────

    def _call_with_retry(self, images, prompt, max_tokens, retries=2) -> Dict:
        """Call Gemini with retry on JSON parse failure."""
        for attempt in range(retries):
            try:
                raw = self.client.call_with_images(images, prompt, max_tokens=max_tokens)
                parsed = self._parse_json_response(raw)
                if parsed:
                    return parsed

                # Empty parse — retry with JSON reminder
                if attempt < retries - 1:
                    logger.warning(f"Empty JSON parse, retrying with reminder (attempt {attempt+1})")
                    prompt = prompt + "\n\nIMPORTANT: You MUST return valid JSON. No markdown, no explanations."
                    continue
            except RuntimeError as e:
                logger.error(f"API call failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                break

        return {}

    # ─── JUDGE WITH FALLBACK ───────────────────────────────────────────

    def _run_judge(self, gather_parsed, tasks, errors) -> List[VerificationResult]:
        """Phase 2: Judge with FULL inventory. No summarization — accuracy is critical."""
        merged_inventory = self._merge_inventories(gather_parsed)
        inv_size = len(json.dumps(merged_inventory, default=str))
        logger.info(f"Full inventory: {inv_size} chars")

        # Strategy 1: Single judge call with full inventory
        result = self._judge_call(tasks, merged_inventory)
        if result:
            return result

        # Strategy 2: Split verification into 2 judge calls (fewer tasks per call)
        logger.warning("Single judge failed, splitting into 2 calls")
        mid = len(tasks) // 2
        tasks_a, tasks_b = tasks[:mid] or tasks, tasks[mid:] or []

        results = []
        for task_group in [tasks_a, tasks_b]:
            if not task_group:
                continue
            r = self._judge_call(task_group, merged_inventory)
            if r:
                results.extend(r)
            else:
                # Final fallback per task group
                for t in task_group:
                    results.append(VerificationResult(
                        task_name=t.name, status="warning",
                        findings=[VerificationFinding(
                            issue="Judge unavailable — manual review needed",
                            page=None, details="",
                        )],
                    ))
                errors.append(f"Judge failed for: {[t.name for t in task_group]}")

        return results

    def _judge_call(self, tasks, inventory, max_retries=2) -> Optional[List[VerificationResult]]:
        """Execute judge call with retries. Returns None on complete failure."""
        judge_prompt = build_verify_judge_prompt(tasks, inventory)

        for attempt in range(max_retries):
            for model in ["gemini-2.5-pro", "gemini-2.5-flash"]:
                try:
                    logger.info(f"Judge call: model={model}, attempt={attempt+1}")
                    resp = http_requests.post(
                        f"{self.client.api_url}/api/llm/v1/chat/completions",
                        headers={"X-API-Key": self.client.api_key, "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "user", "content": judge_prompt}],
                            "max_tokens": 16000,
                            "temperature": 0,
                        },
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        raw = resp.json()["choices"][0]["message"]["content"]
                        parsed = self._parse_json_response(raw)
                        if parsed:
                            logger.info(f"Judge succeeded: model={model}")
                            return self._build_verification_results(parsed, tasks)
                        logger.warning(f"Judge returned empty JSON, retrying")
                    elif resp.status_code in (429, 500, 502, 503):
                        logger.warning(f"Judge {resp.status_code} on {model}, trying next")
                        time.sleep(2)
                    else:
                        logger.warning(f"Judge error {resp.status_code} on {model}")
                except http_requests.exceptions.Timeout:
                    logger.warning(f"Judge timeout on {model}, trying next")
                except Exception as e:
                    logger.warning(f"Judge error on {model}: {e}")

        return None

    def _fallback_batch_verify(self, gather_parsed, tasks) -> List[VerificationResult]:
        """Fallback: derive verification from raw inventory data."""
        results = []
        for task in tasks:
            results.append(VerificationResult(
                task_name=task.name,
                status="warning",
                findings=[VerificationFinding(
                    issue="Verification judge unavailable — manual review recommended",
                    page=None,
                    details="The AI judge could not process the inventory. Raw data was collected but not evaluated.",
                )],
            ))
        return results

    # ─── DEDUPLICATION ─────────────────────────────────────────────────

    def _deduplicate_extraction(self, results: List[ExtractionResult]) -> List[ExtractionResult]:
        """Remove duplicate rows within each extraction task."""
        deduped = []
        for result in results:
            seen: Set[str] = set()
            unique_rows = []
            for row in result.rows:
                # Create a fingerprint from page + core data values
                key_parts = [str(row.page)]
                for v in row.data.values():
                    key_parts.append(str(v).strip() if v else "")
                key = "|".join(key_parts)

                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)

            deduped.append(ExtractionResult(
                task_name=result.task_name,
                columns=result.columns,
                rows=unique_rows,
                row_count=len(unique_rows),
            ))
        return deduped

    # ─── INVENTORY HELPERS ─────────────────────────────────────────────

    def _merge_inventories(self, gather_results: List[Dict]) -> Dict:
        merged = {
            "batch_numbers": [],
            "process_orders": [],
            "material_numbers": [],
            "equipment": [],
            "column_issues": [],
            "time_entries": [],
        }
        for inv in gather_results:
            for key in merged:
                items = inv.get(key, [])
                if isinstance(items, list):
                    merged[key].extend(items)
        return merged

    def _summarize_inventory(self, inventory: Dict) -> Dict:
        """Reduce inventory size by deduplicating and summarizing."""
        summarized = {}
        for key, items in inventory.items():
            if not isinstance(items, list):
                summarized[key] = items
                continue

            # Deduplicate by value, collect all pages
            by_value = {}
            for item in items:
                if isinstance(item, dict):
                    val = item.get("value") or item.get("name") or item.get("step") or str(item)
                    if val not in by_value:
                        by_value[val] = {"item": item, "pages": []}
                    page = item.get("page")
                    if page:
                        by_value[val]["pages"].append(page)

            summarized[key] = []
            for val, data in by_value.items():
                entry = dict(data["item"])
                entry["found_on_pages"] = sorted(set(data["pages"]))
                summarized[key].append(entry)

        return summarized

    def _build_verification_results(self, parsed: Dict, tasks) -> List[VerificationResult]:
        results = []
        for task in tasks:
            raw = parsed.get(task.name, {})
            if not isinstance(raw, dict):
                raw = {}
            findings = [
                VerificationFinding(
                    issue=f.get("issue", ""),
                    page=f.get("page"),
                    details=f.get("details", ""),
                ) for f in raw.get("findings", []) if isinstance(f, dict)
            ]
            results.append(VerificationResult(
                task_name=task.name,
                status=raw.get("status", "pass"),
                findings=findings,
            ))
        return results

    # ─── MERGE / BATCH HELPERS ─────────────────────────────────────────

    def _make_batches(self, pages: List[int], size: int) -> List[List[int]]:
        return [pages[i:i + size] for i in range(0, len(pages), size)]

    def _merge_extraction(self, parsed_list, tasks):
        merged = {}
        for task in tasks:
            merged[task.name] = ExtractionResult(
                task_name=task.name, columns=task.columns, rows=[], row_count=0
            )
        for parsed in parsed_list:
            for task in tasks:
                raw_rows = parsed.get(task.name, [])
                if not isinstance(raw_rows, list):
                    continue
                for raw in raw_rows:
                    if isinstance(raw, dict):
                        page = raw.pop("page", 0)
                        merged[task.name].rows.append(ExtractionRow(data=raw, page=page))
                        merged[task.name].row_count += 1
        return list(merged.values())

    def _resolve_pages(self, request, total_pages):
        if request.page_range:
            return sorted(set(request.page_range))
        specific = set()
        has_all = False
        for task in request.extraction_tasks + request.verification_tasks:
            if task.pages:
                specific.update(task.pages)
            else:
                has_all = True
        if has_all or not specific:
            return list(range(1, total_pages + 1))
        return sorted(specific)

    # ─── JSON PARSING ──────────────────────────────────────────────────

    def _parse_json_response(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        for old, new in [
            ("\ufffd", "?"), ("\u00b0", "deg"), ("\u00b1", "+-"),
            ("\u2013", "-"), ("\u2014", "-"),
            ("\u2018", "'"), ("\u2019", "'"),
        ]:
            text = text.replace(old, new)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        if start < 0:
            logger.error(f"No JSON in response: {text[:200]}")
            return {}

        end = text.rfind("}") + 1
        if end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        fragment = text[start:]
        repaired = self._repair_truncated_json(fragment)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass

        logger.error(f"JSON parse failed: {text[:300]}")
        return {}

    def _repair_truncated_json(self, text: str) -> Optional[str]:
        ob, ol = 0, 0
        in_s, esc = False, False
        for ch in text:
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if ch == '"' and not esc:
                in_s = not in_s
                continue
            if in_s:
                continue
            if ch == '{': ob += 1
            elif ch == '}': ob -= 1
            elif ch == '[': ol += 1
            elif ch == ']': ol -= 1

        if ob <= 0 and ol <= 0:
            return None

        s = text.rstrip()
        while s and s[-1] in (',', ':', '"', "'", " ", "\n"):
            s = s[:-1].rstrip()
        return s + ']' * max(0, ol) + '}' * max(0, ob)
