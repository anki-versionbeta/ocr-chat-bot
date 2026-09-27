"""
Prompt templates for extraction and verification tasks.
Designed for pharmaceutical batch records but works with any document type.
"""
import json
from typing import List
from .models import ExtractionTask, VerificationTask


def build_extraction_prompt(tasks: List[ExtractionTask]) -> str:
    """Build the extraction instruction prompt from task definitions."""
    if not tasks:
        return ""

    task_lines = []
    for i, task in enumerate(tasks, 1):
        cols = ", ".join(task.columns)
        line = f'{i}. "{task.name}" — Extract a table with columns: [{cols}]'
        if task.description:
            line += f"\n   Hint: {task.description}"
        if task.pages:
            line += f"\n   Focus on pages: {task.pages}"
        task_lines.append(line)

    tasks_text = "\n\n".join(task_lines)

    # Build the expected JSON format example
    format_examples = []
    for task in tasks:
        row_example = ", ".join(f'"{c}": <value>' for c in task.columns)
        row_example += ', "page": <page_number>'
        format_examples.append(f'  "{task.name}": [{{{row_example}}}, ...]')
    format_text = "{\n" + ",\n".join(format_examples) + "\n}"

    return f"""EXTRACTION TASKS:
Analyze the document pages and extract structured data for each task below.

{tasks_text}

Return a JSON object with this exact structure:
{format_text}

EXTRACTION RULES:
- Extract ALL instances found across ALL pages shown
- Use exact values as they visually appear on the page
- Handwritten values take priority over printed text
- If a value is crossed out (strikethrough) and corrected, use the CORRECTED value
- Include the "page" number where each row was found
- For blank/empty fields, use null
- If a task has no matching data on these pages, return an empty array for it
- Do NOT invent or hallucinate data — only extract what is visually present
- Keep values SHORT — do not include long instruction text, abbreviate if needed
- You MUST return complete, valid JSON. Close all brackets and braces."""


def build_verification_prompt(tasks: List[VerificationTask]) -> str:
    """Build the verification instruction prompt from task definitions."""
    if not tasks:
        return ""

    task_lines = []
    for i, task in enumerate(tasks, 1):
        line = f'{i}. "{task.name}" [{task.check_type}]'
        line += f"\n   Rule: {task.instruction}"
        if task.pages:
            line += f"\n   Check pages: {task.pages}"
        task_lines.append(line)

    tasks_text = "\n\n".join(task_lines)

    return f"""VERIFICATION TASKS:
Analyze the document pages and check the following rules. Report any violations.

{tasks_text}

Return a JSON object with this exact structure:
{{
  "<task_name>": {{
    "status": "pass" | "fail" | "warning",
    "findings": [
      {{"issue": "<description>", "page": <page_number>, "details": "<specifics>"}}
    ]
  }}
}}

VERIFICATION RULES:
- "pass" = rule is fully satisfied, no issues found
- "fail" = clear violation(s) found
- "warning" = potential issue that needs human review
- Report EVERY instance of a violation, not just the first one
- Include the exact page number and specific details for each finding
- If a check passes with no issues, return an empty findings array
- Be thorough — check ALL pages shown
- Keep findings concise — short issue description, brief details
- You MUST return complete, valid JSON. Close all brackets and braces."""


def build_verify_gather_prompt(tasks: List[VerificationTask]) -> str:
    """Phase 1: GATHER — collect inventory from pages (no judgments yet)."""
    if not tasks:
        return ""

    # Build checklist of what to look for based on task types
    gather_items = []
    for task in tasks:
        ct = task.check_type
        if ct == "consistency":
            if "batch" in task.name.lower():
                gather_items.append("batch_numbers: List every batch number you see with its page number and context (is it a process batch or material batch?)")
            elif "process" in task.name.lower() or "order" in task.name.lower():
                gather_items.append("process_orders: List every process order number with its page number")
            else:
                gather_items.append(f"consistency_{task.name}: List all instances of the checked value with page numbers")
        elif ct == "cross_reference":
            if "material" in task.name.lower():
                gather_items.append("material_numbers: List every 8-digit material number with page number and context (in table? in step instruction?)")
            elif "equipment" in task.name.lower():
                gather_items.append("equipment: List every equipment name/ID with page number and context (in table? in step instruction?)")
            else:
                gather_items.append(f"cross_ref_{task.name}: List all items and where they appear with page numbers")
        elif ct == "completeness":
            gather_items.append("column_issues: List any rows where 4th column is missing entry line, or weigh rows missing Scale. Include step number and page.")
        elif ct == "format":
            gather_items.append("time_entries: List every Start/Stop time entry with page, step number, and exact format used. Flag any NLT/NMT steps missing start or stop lines.")

    items_text = "\n".join(f"- {item}" for item in gather_items)

    return f"""INVENTORY SCAN: Look at these pages and collect the following data. Do NOT make judgments — just report what you see.

Collect:
{items_text}

Return a JSON object:
{{
  "batch_numbers": [{{"value": "<number>", "page": <N>, "context": "<process batch | material batch for X>"}}],
  "process_orders": [{{"value": "<number>", "page": <N>}}],
  "material_numbers": [{{"value": "<8-digit>", "page": <N>, "location": "<materials_table | step_instruction | other>"}}],
  "equipment": [{{"name": "<equipment>", "page": <N>, "location": "<equipment_table | step_instruction | other>"}}],
  "column_issues": [{{"step": "<N>", "page": <N>, "issue": "<description>"}}],
  "time_entries": [{{"step": "<N>", "page": <N>, "format": "<exact format>", "has_start": true/false, "has_stop": true/false, "has_nlt_nmt": true/false}}]
}}

RULES:
- Report EVERYTHING you see, not just problems
- Include page numbers for every item
- Be exhaustive — scan every row, every table, every step
- You MUST return complete, valid JSON"""


def build_verify_judge_prompt(tasks: List[VerificationTask], merged_inventory: dict) -> str:
    """Phase 2: JUDGE — evaluate rules using the complete inventory (no images needed)."""
    if not tasks:
        return ""

    task_lines = []
    for i, task in enumerate(tasks, 1):
        line = f'{i}. "{task.name}" [{task.check_type}]'
        line += f"\n   Rule: {task.instruction}"
        task_lines.append(line)

    tasks_text = "\n\n".join(task_lines)
    inventory_json = json.dumps(merged_inventory, indent=2, default=str)

    return f"""You have a COMPLETE INVENTORY of data collected from ALL pages of a document.
Using this inventory, evaluate each verification rule below.

COMPLETE DOCUMENT INVENTORY:
{inventory_json}

VERIFICATION RULES TO CHECK:
{tasks_text}

Return a JSON object:
{{
  "<task_name>": {{
    "status": "pass" | "fail",
    "findings": [
      {{"issue": "<description>", "page": <page_number>, "details": "<specifics>"}}
    ]
  }}
}}

JUDGMENT RULES:
- "pass" = rule is fully satisfied based on the inventory
- "fail" = clear violation found in the inventory
- Do NOT use "warning" — you have the COMPLETE inventory, so make a definitive judgment
- For cross-reference checks: an item passes if it appears in BOTH the table AND at least one other location
- For consistency checks: all values must be identical
- Empty findings array for passing checks
- Return ONLY valid JSON"""


def build_combined_prompt(
    extraction_tasks: List[ExtractionTask],
    verification_tasks: List[VerificationTask],
) -> str:
    """Build a combined prompt for both extraction and verification."""
    parts = [
        "You are analyzing a document. Complete ALL tasks below and return a single JSON response.",
        "",
    ]

    extract_prompt = build_extraction_prompt(extraction_tasks)
    verify_prompt = build_verification_prompt(verification_tasks)

    if extract_prompt:
        parts.append(extract_prompt)
    if verify_prompt:
        if extract_prompt:
            parts.append("\n---\n")
        parts.append(verify_prompt)

    parts.append("\n\nReturn ONLY valid JSON. No markdown, no explanations, no code blocks.")

    return "\n".join(parts)
