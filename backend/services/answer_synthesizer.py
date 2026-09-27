"""
Answer Synthesizer for Phase 4 - Multi-Agent RAG Orchestration

This module generates natural language answers from retrieved context chunks.
It uses Claude Sonnet to synthesize answers and includes cell references
for PDF highlighting.

Key Features:
- Synthesizes answers from retrieved chunks
- Includes [cell:X-Y] references for table values
- Supports row/column position queries
- Returns confidence scores
- Handles missing information gracefully
"""

import os
import json
import logging
import re
from typing import Dict, List, Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ocr-chatbot.answer_synthesizer")


# Iliad API configuration
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED


ANSWER_SYNTHESIS_PROMPT = """You are analyzing a Certificate of Analysis (COA) document.

Document: {filename}

Context from the document (retrieved via hybrid search):
{context}

Grounding Data (for referencing specific locations in the PDF):
{cell_grounding}

User Question: {query}
{focus_instruction}
Instructions:
1. Answer using ONLY information from the provided context
2. Determine what the user wants:

   A) VIEW/DISPLAY A SPECIFIC TABLE (e.g., "show me the error detection table", "display the material properties table"):
      - Display ONLY the requested table in clean markdown format
      - Do NOT include [cell:...] references - just show the table
      - Return EMPTY cell_ids: []
      - Return table_chunk_index with the chunk number of the TABLE you are displaying

   B) VIEW ALL TABLES or GENERAL TABLE REQUEST (e.g., "show me tables from page 1", "what tables are present"):
      - Display ALL relevant tables in markdown format
      - Return EMPTY cell_ids: []
      - Return table_chunk_index: null

   C) SPECIFIC VALUE LOOKUP (e.g., "what is the batch number", "what is the value for X"):
      - Include [cell:CHUNK:CELL_ID] or [line:CHUNK:LINE_ID] references for ALL values you mention
      - cell_ids must include EVERY value referenced in your answer
      - Do NOT set table_chunk_index for value lookups

   D) EXPLORATORY/PAGE FINDING QUERIES (e.g., "which pages have signatures", "show pages with X", "where is Y located"):
      - List the pages where the requested content is found
      - INCLUDE [cell:CHUNK:CELL_ID] or [line:CHUNK:LINE_ID] references for EACH piece of evidence
      - For EVERY page you mention, include the cell/line reference that proves it
      - Example: "Page 51 contains signatures [cell:120:51-5], Page 68 has a signature block [line:135:abc123]"
      - cell_ids must contain ALL references you cite

   E) EXTRACT ALL/LIST ALL QUERIES (e.g., "show all step numbers", "list all batch numbers", "what are all the values"):
      - **EXTRACT THE ACTUAL VALUES** from the context - do NOT just say "found on pages X, Y, Z"
      - Example: "show all step numbers" → "Step 1, Step 2, Step 3, Step 4, Step 5, Step 7, Step 8, Step 9, Step 10, Step 11"
      - Include page references WITH each value: "Step 1 (Page 80), Step 2 (Page 80), Step 7 (Page 106)..."
      - Include [cell:...] or [line:...] references for bounding box highlighting

3. Be concise and accurate
4. If the answer is NOT in the context, return EMPTY answer with confidence 0:
   {{"answer": "", "cell_ids": [], "table_chunk_index": null, "confidence": 0.0}}
   Do NOT say "I couldn't find..." - just return empty answer.

Respond with JSON (no markdown code block):
{{
    "answer": "Your answer (or empty string if not found)",
    "cell_ids": [],
    "table_chunk_index": null,
    "confidence": 0.95
}}

KEY RULES:
- Specific table request → table_chunk_index = chunk number of that table
- General/all tables request → table_chunk_index = null
- Value lookup requests → cell_ids = specific IDs, no table_chunk_index
- Exploratory/page finding → cell_ids = references for each page/finding mentioned
- EXTRACT ALL/LIST ALL → Extract ACTUAL VALUES with page refs and cell_ids for highlighting
- ALWAYS include cell/line references when citing specific content from the document
- confidence should be 0.0-1.0 based on how well the context supports the answer

**CRITICAL**: When user asks for "all X" or "list X", your answer must contain the ACTUAL VALUES extracted from the context, not just page locations where they appear."""


VIEW_TABLE_PROMPT = """You are displaying a table from a Certificate of Analysis (COA) document.

Document: {filename}

Context from the document:
{context}

User Request: {query}

Instructions:
1. Display the table in a clean markdown format
2. Include ALL rows and columns from the table
3. Preserve the exact values from the document
4. Do NOT include [cell:...] references - the user wants to VIEW the table, not look up specific values
5. Just show the table layout clearly

Respond with JSON (no markdown code block):
{{
    "answer": "Here is the table from page X:\\n\\n| Header1 | Header2 |...\\n|---|---|...\\n| value | value |...",
    "cell_ids": [],
    "confidence": 0.95
}}

IMPORTANT:
- Return an EMPTY cell_ids array - no references needed for viewing
- Focus on clean table layout presentation
- Include all data from the table"""


ROW_COL_LOOKUP_PROMPT = """You are looking up a specific cell in a table from a COA document.

The user asked for: {query}

Target Position: Row {row}, Column {col}

Available cells from table chunks:
{cell_data}

Instructions:
1. Find the cell at the exact row and column position
2. Return the cell's value and its cell_id
3. If no exact match, find the closest cell or say it doesn't exist

Respond with JSON (no markdown code block):
{{
    "answer": "The value at row {row}, column {col} is: [value] [cell:X-Y]",
    "cell_ids": ["X-Y"],
    "confidence": 0.95,
    "found": true
}}

If not found:
{{
    "answer": "I couldn't find a cell at row {row}, column {col} in the document.",
    "cell_ids": [],
    "confidence": 0.9,
    "found": false
}}"""


def build_context_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    """
    Build context string from retrieved chunks.

    Args:
        chunks: List of chunk dictionaries from Weaviate

    Returns:
        Formatted context string
    """
    context_parts = []

    for i, chunk in enumerate(chunks):
        chunk_type = chunk.get('chunk_type', 'text').upper()
        page = chunk.get('page', '?')
        content = chunk.get('content', '')
        layout_type = chunk.get('layout_type', '')

        # Add chunk header
        header = f"[{chunk_type}"
        if layout_type:
            header += f" - {layout_type}"
        header += f"] Page {page}:"

        context_parts.append(header)
        context_parts.append(content)
        context_parts.append("")  # Empty line separator

    return "\n".join(context_parts)


def build_cell_grounding_summary(chunks: List[Dict[str, Any]]) -> str:
    """
    Build grounding summary for the prompt (both table cells and text lines).

    Includes chunk_index to create globally unique references.
    - Tables: chunk_index:row-col (e.g., "23:2-4")
    - Text: chunk_index:line_id (e.g., "5:abc-123")

    Args:
        chunks: List of chunk dictionaries

    Returns:
        Formatted grounding string
    """
    grounding_lines = []

    for chunk in chunks:
        chunk_index = chunk.get('chunk_index', 0)
        page = chunk.get('page', 1)
        chunk_type = chunk.get('chunk_type', 'text')

        # Handle TABLE chunks with cell_grounding
        if chunk_type == 'table' and chunk.get('cell_grounding'):
            try:
                cell_grounding = json.loads(chunk['cell_grounding'])
                grounding_lines.append(f"  [TABLE Chunk {chunk_index}, Page {page}]:")

                for cell_id, data in cell_grounding.items():
                    row = data.get('row', '?')
                    col = data.get('col', '?')
                    text = data.get('text', '')[:50]
                    composite_id = f"{chunk_index}:{cell_id}"
                    grounding_lines.append(
                        f"    [cell:{composite_id}]: row={row}, col={col}, text=\"{text}\""
                    )
            except json.JSONDecodeError:
                continue

        # Handle TEXT chunks with line_grounding
        elif chunk_type == 'text' and chunk.get('line_grounding'):
            try:
                line_grounding = json.loads(chunk['line_grounding'])
                grounding_lines.append(f"  [TEXT Chunk {chunk_index}, Page {page}]:")

                for line_id, data in line_grounding.items():
                    text = data.get('text', '')[:60]
                    composite_id = f"{chunk_index}:{line_id}"
                    grounding_lines.append(
                        f"    [line:{composite_id}]: text=\"{text}\""
                    )
            except json.JSONDecodeError:
                continue

    if not grounding_lines:
        return "No grounding data available."

    # Increased limit to 200 to ensure complete table data is included
    # Tables can have many cells and truncating loses critical data
    if len(grounding_lines) > 200:
        grounding_lines = grounding_lines[:200]
        grounding_lines.append("  ... (more entries available)")

    return "\n".join(grounding_lines)


def lookup_cell_by_position(
    chunks: List[Dict[str, Any]],
    target_row: int,
    target_col: int
) -> Optional[Dict[str, Any]]:
    """
    Find a cell by exact row/column position.

    Args:
        chunks: List of chunk dictionaries
        target_row: Target row number
        target_col: Target column number

    Returns:
        Cell data dict if found, None otherwise
    """
    for chunk in chunks:
        if chunk.get('chunk_type') != 'table':
            continue

        cell_grounding_str = chunk.get('cell_grounding', '')
        if not cell_grounding_str:
            continue

        chunk_index = chunk.get('chunk_index', 0)

        try:
            cell_grounding = json.loads(cell_grounding_str)

            for cell_id, data in cell_grounding.items():
                if data.get('row') == target_row and data.get('col') == target_col:
                    # Create composite cell_id with chunk_index for uniqueness
                    composite_cell_id = f"{chunk_index}:{cell_id}"
                    return {
                        'found': True,
                        'cell_id': composite_cell_id,
                        'text': data.get('text', ''),
                        'bbox': data.get('bbox', {}),
                        'page': chunk.get('page', 1),
                        'chunk_index': chunk_index,
                        'row': target_row,
                        'col': target_col
                    }

        except json.JSONDecodeError:
            continue

    return None


def synthesize_answer_sync(
    query: str,
    chunks: List[Dict[str, Any]],
    filename: str = "document",
    row_col_position: Optional[Dict[str, int]] = None,
    focus_entities: Optional[List[str]] = None,
    relevance_rule: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synthesize answer from retrieved chunks using Claude Sonnet.

    Args:
        query: User's question
        chunks: Retrieved chunks from Weaviate
        filename: Original document filename
        row_col_position: Optional row/col for position queries
        focus_entities: Optional list of entities that MUST be in the answer (Phase 8)
        relevance_rule: Optional rule for filtering relevant information (Phase 8)

    Returns:
        Dict with answer, cell_ids, and confidence
    """
    # Handle row/column position queries
    if row_col_position:
        target_row = row_col_position.get('row')
        target_col = row_col_position.get('col')

        # Direct lookup first
        cell_result = lookup_cell_by_position(chunks, target_row, target_col)

        if cell_result and cell_result.get('found'):
            return {
                'answer': f"The value at row {target_row}, column {target_col} is: **{cell_result['text']}** [cell:{cell_result['cell_id']}]",
                'cell_ids': [cell_result['cell_id']],
                'confidence': 0.95,
                'found': True
            }
        else:
            return {
                'answer': f"I couldn't find a cell at row {target_row}, column {target_col} in the document tables.",
                'cell_ids': [],
                'confidence': 0.9,
                'found': False
            }

    # Build context for LLM
    context = build_context_from_chunks(chunks)
    cell_grounding = build_cell_grounding_summary(chunks)

    if not context.strip():
        return {
            'answer': "I couldn't find relevant information in the document to answer your question.",
            'cell_ids': [],
            'confidence': 0.0
        }

    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        # Build focus instruction for Phase 8 query-focused synthesis
        focus_instruction = ""
        if focus_entities or relevance_rule:
            focus_parts = []
            if focus_entities:
                entities_str = ", ".join(focus_entities)
                focus_parts.append(f"FOCUS ENTITIES (MUST be in answer): {entities_str}")
            if relevance_rule:
                focus_parts.append(f"RELEVANCE RULE: {relevance_rule}")
            focus_instruction = "\n\n**IMPORTANT FILTER:**\n" + "\n".join(focus_parts) + "\nONLY include information that relates to these focus entities. Exclude unrelated data.\n"

        prompt = ANSWER_SYNTHESIS_PROMPT.format(
            filename=filename,
            context=context,
            cell_grounding=cell_grounding,
            query=query,
            focus_instruction=focus_instruction
        )

        payload = {
            "model": "claude-haiku-4-5-20251001",  # Using Haiku for faster response (~3x faster than Sonnet)
            "max_tokens": 4000,  # Increased from 1000 to handle large tables without truncation
            "temperature": 0,  # Set to 0 for consistent, deterministic responses
            "messages": [{
                "role": "user",
                "content": prompt
            }]
        }

        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            logger.error(f"Answer synthesis API error: {response.status_code} - {response.text}")
            return {
                'answer': "I encountered an error while processing your question. Please try again.",
                'cell_ids': [],
                'confidence': 0.0,
                'error': True
            }

        result = response.json()
        content = result.get("content", [{}])[0].get("text", "").strip()

        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            if "```" in content:
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    content = json_match.group(1)

            answer_data = json.loads(content)

            return {
                'answer': answer_data.get('answer', content),
                'cell_ids': answer_data.get('cell_ids', []),
                'table_chunk_index': answer_data.get('table_chunk_index'),
                'confidence': answer_data.get('confidence', 0.7)
            }

        except json.JSONDecodeError:
            # If JSON parsing fails, return raw content
            logger.warning("Failed to parse answer synthesis response as JSON")

            # Try to extract cell references from raw text
            # New format: [cell:CHUNK:ROW-COL] e.g., [cell:23:2-4]
            cell_ids = re.findall(r'\[cell:(\d+:\d+-\d+)\]', content)

            # Also try old format for backward compatibility
            if not cell_ids:
                cell_ids = re.findall(r'\[cell:(\d+-\d+)\]', content)

            return {
                'answer': content,
                'cell_ids': cell_ids,
                'confidence': 0.6
            }

    except requests.exceptions.Timeout:
        logger.error("Answer synthesis timeout")
        return {
            'answer': "The request timed out. Please try a simpler question.",
            'cell_ids': [],
            'confidence': 0.0,
            'error': True
        }
    except Exception as e:
        logger.error(f"Answer synthesis error: {e}")
        return {
            'answer': f"An error occurred: {str(e)}",
            'cell_ids': [],
            'confidence': 0.0,
            'error': True
        }


async def synthesize_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    filename: str = "document",
    row_col_position: Optional[Dict[str, int]] = None,
    focus_entities: Optional[List[str]] = None,
    relevance_rule: Optional[str] = None
) -> Dict[str, Any]:
    """
    Async wrapper for answer synthesis.

    Args:
        query: User's question
        chunks: Retrieved chunks from Weaviate
        filename: Original document filename
        row_col_position: Optional row/col for position queries
        focus_entities: Optional list of entities that MUST be in the answer (Phase 8)
        relevance_rule: Optional rule for filtering relevant information (Phase 8)

    Returns:
        Dict with answer, cell_ids, and confidence
    """
    # For now, just call sync version
    # Can be made truly async with aiohttp in the future
    return synthesize_answer_sync(query, chunks, filename, row_col_position, focus_entities, relevance_rule)


def add_confidence_disclaimer(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add disclaimer for low-confidence answers.

    Args:
        response: Answer response dict

    Returns:
        Modified response with disclaimer if needed
    """
    confidence = response.get('confidence', 0.5)

    if confidence < 0.7:
        original_answer = response.get('answer', '')
        response['answer'] = (
            "I'm not fully confident in this answer, but based on the document: " +
            original_answer
        )
        response['low_confidence'] = True

    return response
