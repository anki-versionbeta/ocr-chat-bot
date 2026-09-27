"""
Visual Audit Service - Deep Analysis with Gemini Multimodal

This service provides visual audit capabilities for COA documents:
- Stage 1: Discovery (BM25/Hybrid search to find relevant data)
- Stage 2: Deep Analysis (Gemini multimodal with image + OCR text)

Features:
- Calculation verification (start + duration = end?)
- Strikethrough/correction detection
- Handwriting analysis
- Data entry error detection

Usage:
    from services.visual_audit_service import get_visual_audit_service

    service = get_visual_audit_service()

    # Stage 1: Discovery
    discovery_result = service.discover_audit_targets(
        query="Check elapsed time calculations",
        process_id="uuid-here",
        filename="document.pdf"
    )

    # Stage 2: Deep Analysis (after user picks page)
    audit_result = service.deep_analyze_page(
        query="Check elapsed time calculations",
        process_id="uuid-here",
        pdf_path="/path/to/document.pdf",
        page_number=31,
        chunks=relevant_chunks
    )

Author: OCR Chatbot Team
Updated: February 2026 - Phase 7 Visual Audit
"""

import os
import re
import json
import logging
import base64
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import requests
import fitz  # PyMuPDF

from dotenv import load_dotenv

# Import context building from answer_synthesizer (same pattern as parallel_agent_graph)
from services.answer_synthesizer import build_context_from_chunks, build_cell_grounding_summary

load_dotenv()

logger = logging.getLogger("ocr-chatbot.visual_audit")

# =============================================================================
# CONFIGURATION
# =============================================================================

ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED
GEMINI_MODEL = "gemini-3.1-pro-preview"  # Multimodal model for visual analysis

# Maximum pages for deep analysis at once
MAX_PAGES_FOR_ANALYSIS = 3


# =============================================================================
# LLM-BASED QUERY ANALYSIS
# =============================================================================

def analyze_audit_query_with_llm(query: str) -> Dict[str, Any]:
    """
    Use LLM to analyze the audit query and extract specific identifiers.

    This replaces regex-based detection with intelligent LLM analysis.
    The LLM determines:
    1. Is the query general or specific?
    2. What specific identifier is mentioned (step number, page, batch, etc.)?
    3. What keywords to search for in chunks?

    Args:
        query: User's audit query

    Returns:
        Dict with query_type, identifier, and search_keywords
    """
    prompt = f"""Analyze this document audit query and extract key information.

USER QUERY: "{query}"

Determine:
1. Is this a GENERAL query (no specific item mentioned) or SPECIFIC query (mentions a specific step, page, batch, section, etc.)?
2. If SPECIFIC, what is the identifier? (e.g., "step 7.3", "page 31", "batch 12345")
3. What are the key search terms to find the relevant data?

Respond in this EXACT JSON format only (no markdown, no explanation):
{{
    "query_type": "general" or "specific",
    "identifier": "the specific identifier if any, or null",
    "identifier_type": "step" or "page" or "batch" or "section" or "row" or null,
    "search_keywords": ["keyword1", "keyword2", ...]
}}

Examples:
- "Check for errors" -> {{"query_type": "general", "identifier": null, "identifier_type": null, "search_keywords": ["error", "calculation", "correction"]}}
- "Verify step 7.3 elapsed time" -> {{"query_type": "specific", "identifier": "7.3", "identifier_type": "step", "search_keywords": ["step 7.3", "7.3", "elapsed time"]}}
- "Audit page 31 calculations" -> {{"query_type": "specific", "identifier": "31", "identifier_type": "page", "search_keywords": ["calculation", "time"]}}
- "Check batch 12345 data" -> {{"query_type": "specific", "identifier": "12345", "identifier_type": "batch", "search_keywords": ["batch 12345", "12345"]}}"""

    try:
        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers={
                "x-api-key": ILIAD_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("content", [{}])[0].get("text", "").strip()

            # Parse JSON response - handle markdown code blocks
            try:
                # Remove markdown code block if present
                if content.startswith("```"):
                    # Remove ```json and closing ```
                    content = re.sub(r'^```(?:json)?\s*', '', content)
                    content = re.sub(r'\s*```$', '', content)
                    content = content.strip()

                parsed = json.loads(content)
                logger.info(f"LLM query analysis: {parsed}")
                return parsed
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM response as JSON: {content}")
                return {
                    "query_type": "general",
                    "identifier": None,
                    "identifier_type": None,
                    "search_keywords": []
                }
        else:
            logger.error(f"LLM query analysis API error: {response.status_code}")
            return {
                "query_type": "general",
                "identifier": None,
                "identifier_type": None,
                "search_keywords": []
            }

    except Exception as e:
        logger.error(f"LLM query analysis error: {e}")
        return {
            "query_type": "general",
            "identifier": None,
            "identifier_type": None,
            "search_keywords": []
        }


def find_pages_with_identifier_llm(
    identifier: str,
    identifier_type: str,
    chunks: List[Dict],
    pages_data: Dict[int, Dict]
) -> List[int]:
    """
    Use LLM to find which pages contain the specific identifier.

    Instead of regex matching, this sends chunk summaries to an LLM
    to intelligently determine which pages contain the identifier.

    Args:
        identifier: The specific identifier (e.g., "7.3", "31")
        identifier_type: Type of identifier (step, page, batch, etc.)
        chunks: All discovered chunks
        pages_data: Dict mapping page number to page info and chunk summaries

    Returns:
        List of page numbers that contain the identifier
    """
    # Build page summaries for LLM
    page_summaries = []
    for page_num in sorted(pages_data.keys()):
        data = pages_data[page_num]
        # Get first 3 chunk summaries for each page
        summaries = data.get('summary', [])[:3]
        summary_text = " | ".join(summaries)[:500]  # Limit length
        page_summaries.append(f"Page {page_num}: {summary_text}")

    pages_text = "\n".join(page_summaries)

    prompt = f"""I need to find which pages contain a specific {identifier_type}.

LOOKING FOR: {identifier_type} "{identifier}"

PAGE SUMMARIES:
{pages_text}

Which pages contain {identifier_type} "{identifier}"?

Rules:
- Only return pages that CLEARLY contain the exact {identifier_type} "{identifier}"
- For step numbers, look for "step {identifier}" or "Step {identifier}" or just "{identifier}" as a step reference
- Be strict - if unsure, don't include the page

Respond with ONLY a JSON array of page numbers (no explanation):
Example: [31, 45] or [] if none found"""

    try:
        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers={
                "x-api-key": ILIAD_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("content", [{}])[0].get("text", "").strip()

            # Parse JSON array response - handle markdown code blocks
            try:
                # Remove markdown code block if present
                if content.startswith("```"):
                    content = re.sub(r'^```(?:json)?\s*', '', content)
                    content = re.sub(r'\s*```$', '', content)
                    content = content.strip()

                pages = json.loads(content)
                if isinstance(pages, list):
                    # Filter to only valid pages that exist in our data
                    valid_pages = [p for p in pages if p in pages_data]
                    logger.info(f"LLM found {identifier_type} '{identifier}' on pages: {valid_pages}")
                    return valid_pages
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM page list: {content}")
                return []
        else:
            logger.error(f"LLM page finder API error: {response.status_code}")
            return []

    except Exception as e:
        logger.error(f"LLM page finder error: {e}")
        return []


def detect_audit_query_type(query: str) -> str:
    """
    Detect if visual audit query is GENERAL or SPECIFIC using LLM.

    This is a backward-compatible wrapper that uses the new LLM-based analysis.

    Args:
        query: User's audit query

    Returns:
        "specific" if has page/step/parameter, "general" otherwise
    """
    analysis = analyze_audit_query_with_llm(query)
    query_type = analysis.get("query_type", "general")
    logger.info(f"Audit query type (LLM): {query_type}")
    return query_type


def analyze_conversation_context(
    query: str,
    recent_messages: List[Dict[str, str]]
) -> Dict[str, Any]:
    """
    Analyze chat history to determine if current message is a follow-up action.

    Uses LLM to understand context and detect:
    - Page selection for visual audit Stage 2
    - Follow-up questions about previous results
    - New queries

    Args:
        query: Current user message
        recent_messages: Last 6 messages from conversation

    Returns:
        Dict with:
        - is_page_selection: bool - True if user is selecting pages for deep analysis
        - pages: List[int] - Page numbers if is_page_selection
        - original_query: str - The original audit query if is_page_selection
        - action_type: str - "page_selection" | "follow_up" | "new_query"
    """
    if not recent_messages:
        return {"is_page_selection": False, "action_type": "new_query"}

    # Build conversation context
    conversation_parts = []
    for msg in recent_messages[-6:]:
        role = msg.get('role', 'user').upper()
        content = msg.get('content', '')[:600]
        conversation_parts.append(f"{role}: {content}")

    conversation_text = "\n\n".join(conversation_parts)

    prompt = f"""Analyze this conversation to understand what the user wants NOW.

RECENT CONVERSATION:
{conversation_text}

CURRENT USER MESSAGE: "{query}"

TASK: Determine if the current message is:
1. PAGE_SELECTION - User selecting page(s) after assistant asked "which page to deep analyze?"
2. FOLLOW_UP_VERIFICATION - User EXPLICITLY asking to verify/deep check on a SPECIFIC page
3. NEW_QUERY - A new question (even if it's a clarification like "no i mean X")

**CRITICAL RULES:**

PAGE_SELECTION only when:
- Previous assistant message explicitly asked "which page to deep analyze?" or similar
- User responds with page number(s)

FOLLOW_UP_VERIFICATION only when ALL of these are true:
- User EXPLICITLY says "verify", "check", "audit", "deep check", "same page", "that page"
- User is asking to RE-VERIFY something on a specific page
- NOT just clarifying their question with "no i mean" or "i meant"

NEW_QUERY for:
- Any new question even if related to previous topic
- Clarifications like "no i mean X", "i meant Y", "what about Z"
- Questions that don't explicitly ask for verification

**EXAMPLES:**
- "no i mean what is the elapsed mix time" → NEW_QUERY (user clarifying question, not asking for verification)
- "check the elapsed time on page 31 again" → FOLLOW_UP_VERIFICATION (explicit check request)
- "page 31" (after "which page?") → PAGE_SELECTION
- "what is the batch number" → NEW_QUERY

Respond in JSON only (no markdown):
{{
    "action_type": "page_selection" or "follow_up_verification" or "new_query",
    "is_page_selection": true or false,
    "pages": [page numbers ONLY for page_selection/follow_up_verification, else empty],
    "original_query": "resolved query or null for new_query"
}}"""

    # Retry logic for robustness
    max_retries = 2
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{ILIAD_URL}/anthropic/v1/messages",
                headers={
                    "x-api-key": ILIAD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get("content", [{}])[0].get("text", "").strip()

                # Remove markdown code block if present
                if content.startswith("```"):
                    content = re.sub(r'^```(?:json)?\s*', '', content)
                    content = re.sub(r'\s*```$', '', content)
                    content = content.strip()

                parsed = json.loads(content)
                logger.info(f"Conversation context analysis (attempt {attempt+1}): {parsed}")
                return parsed

            else:
                last_error = f"API error: {response.status_code}"
                logger.warning(f"Context analysis API error (attempt {attempt+1}): {response.status_code}")

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
            logger.warning(f"Context analysis JSON parse error (attempt {attempt+1}): {e}")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Context analysis error (attempt {attempt+1}): {e}")

    logger.error(f"Context analysis failed after {max_retries} attempts: {last_error}")
    return {"is_page_selection": False, "action_type": "new_query"}


# =============================================================================
# PARALLEL AGENTS FOR VISUAL AUDIT DISCOVERY
# =============================================================================

CHUNKS_PER_AGENT = 5  # Each agent processes 5 chunks


def run_discovery_agent(
    query: str,
    chunks: List[Dict],
    agent_idx: int
) -> Dict[str, Any]:
    """
    Single discovery agent that analyzes a batch of chunks for audit targets.

    Uses Claude Haiku with FULL CONTEXT (same pattern as parallel_agent_graph)
    to properly filter and find relevant audit targets.

    Args:
        query: User's audit query
        chunks: Batch of chunks to analyze (max 5)
        agent_idx: Agent index for logging

    Returns:
        Dict with findings, pages, chunk_indices, and relevance scores
    """
    # Build chunk_index_map for reference tracking
    chunk_index_map = {}
    for i, chunk in enumerate(chunks):
        chunk_index_map[i] = {
            'chunk_index': chunk.get('chunk_index', i),
            'page': chunk.get('page', 0),
            'chunk': chunk
        }

    # Use FULL CONTEXT building (same as parallel_agent_graph) for proper filtering
    # This ensures LLM sees complete cell data and can filter semantically
    context = build_context_from_chunks(chunks)
    cell_grounding = build_cell_grounding_summary(chunks)

    prompt = f"""You are an audit discovery agent analyzing document content for potential audit targets.

USER AUDIT REQUEST: "{query}"

DOCUMENT CONTEXT:
{context}

CELL GROUNDING (for reference):
{cell_grounding}

Your task: Find content that is DIRECTLY RELEVANT to the audit request.

IMPORTANT: Only include findings that ACTUALLY match the user's request.
- If user asks about "elapsed time", only include chunks with elapsed time calculations
- Do NOT include unrelated time mentions or generic data

For each RELEVANT finding, identify:
1. The chunk number (0-4) from the context above
2. What audit-worthy content it contains
3. What page it's on
4. A relevance score (0.0 to 1.0) - use 0.9+ only for direct matches

Respond in this EXACT JSON format (no markdown):
{{
    "findings": [
        {{
            "chunk_num": <chunk number 0-4>,
            "page": <page_number>,
            "summary": "<specific finding - include actual values>",
            "audit_type": "calculation" or "correction" or "data_entry" or "time_value" or "general",
            "relevance": <0.0 to 1.0>
        }}
    ],
    "pages_with_audit_targets": [<list of page numbers with relevant content>],
    "agent_summary": "<one sentence summary>"
}}

If no DIRECTLY RELEVANT content found, return empty findings array."""

    try:
        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers={
                "x-api-key": ILIAD_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )

        if response.status_code == 200:
            result = response.json()
            content = result.get("content", [{}])[0].get("text", "").strip()

            # Remove markdown code block if present
            if content.startswith("```"):
                content = re.sub(r'^```(?:json)?\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                content = content.strip()

            parsed = json.loads(content)
            parsed["agent_idx"] = agent_idx
            parsed["chunks_processed"] = len(chunks)

            # Enrich findings with chunk data for reference building
            enriched_findings = []
            for finding in parsed.get("findings", []):
                chunk_num = finding.get("chunk_num", 0)
                if chunk_num in chunk_index_map:
                    chunk_data = chunk_index_map[chunk_num]
                    original_chunk = chunk_data['chunk']
                    # Add bbox data from chunk for PDF highlighting
                    finding["chunk_index"] = chunk_data['chunk_index']
                    finding["bbox"] = {
                        "left": original_chunk.get('bbox_left', 0),
                        "top": original_chunk.get('bbox_top', 0),
                        "right": original_chunk.get('bbox_right', 0),
                        "bottom": original_chunk.get('bbox_bottom', 0),
                    }
                enriched_findings.append(finding)

            parsed["findings"] = enriched_findings

            logger.info(f"Discovery Agent {agent_idx}: Found {len(parsed.get('findings', []))} findings")
            return parsed

        else:
            logger.error(f"Discovery Agent {agent_idx} API error: {response.status_code}")
            return {"findings": [], "pages_with_audit_targets": [], "agent_idx": agent_idx, "error": True}

    except json.JSONDecodeError as e:
        logger.warning(f"Discovery Agent {agent_idx} JSON parse error: {e}")
        return {"findings": [], "pages_with_audit_targets": [], "agent_idx": agent_idx, "error": True}
    except Exception as e:
        logger.error(f"Discovery Agent {agent_idx} error: {e}")
        return {"findings": [], "pages_with_audit_targets": [], "agent_idx": agent_idx, "error": True}


def run_parallel_discovery_agents(
    query: str,
    chunks: List[Dict],
    max_agents: int = 6
) -> Dict[str, Any]:
    """
    Run multiple parallel discovery agents to analyze many chunks.

    Splits chunks into batches of 5 and processes them in parallel.
    Merges findings from all agents into a comprehensive discovery result.

    Args:
        query: User's audit query
        chunks: All retrieved chunks
        max_agents: Maximum number of parallel agents (default 6 = 30 chunks)

    Returns:
        Dict with merged findings, pages, and summary
    """
    if not chunks:
        return {
            "success": False,
            "findings": [],
            "pages_with_audit_targets": [],
            "summary": "No chunks to analyze"
        }

    # Split chunks into batches
    chunk_batches = []
    for i in range(0, len(chunks), CHUNKS_PER_AGENT):
        batch = chunks[i:i + CHUNKS_PER_AGENT]
        if batch:
            chunk_batches.append(batch)

    # Limit number of agents
    if len(chunk_batches) > max_agents:
        logger.info(f"Limiting from {len(chunk_batches)} batches to {max_agents} agents")
        chunk_batches = chunk_batches[:max_agents]

    logger.info(f"Running {len(chunk_batches)} parallel discovery agents for {len(chunks)} chunks")

    # Run agents in parallel
    all_results = []
    with ThreadPoolExecutor(max_workers=min(len(chunk_batches), 6)) as executor:
        futures = {
            executor.submit(run_discovery_agent, query, batch, idx): idx
            for idx, batch in enumerate(chunk_batches)
        }

        for future in futures:
            agent_idx = futures[future]
            try:
                result = future.result(timeout=25)
                all_results.append(result)
            except Exception as e:
                logger.error(f"Discovery Agent {agent_idx} future error: {e}")
                all_results.append({"findings": [], "pages_with_audit_targets": [], "agent_idx": agent_idx, "error": True})

    # Merge results from all agents
    all_findings = []
    all_pages = set()
    agent_summaries = []

    for result in all_results:
        if result.get("error"):
            continue

        findings = result.get("findings", [])
        all_findings.extend(findings)

        pages = result.get("pages_with_audit_targets", [])
        all_pages.update(pages)

        summary = result.get("agent_summary", "")
        if summary:
            agent_summaries.append(summary)

    # Sort findings by relevance
    all_findings.sort(key=lambda x: x.get("relevance", 0), reverse=True)

    # Deduplicate pages
    sorted_pages = sorted(all_pages)

    # Build combined summary
    if agent_summaries:
        combined_summary = " | ".join(agent_summaries[:5])  # Top 5 agent summaries
    else:
        combined_summary = "Parallel agents completed but found no specific audit targets."

    logger.info(f"Parallel discovery complete: {len(all_findings)} findings, {len(sorted_pages)} pages")

    return {
        "success": True,
        "findings": all_findings,
        "pages_with_audit_targets": sorted_pages,
        "agents_used": len(chunk_batches),
        "total_chunks_processed": sum(r.get("chunks_processed", 0) for r in all_results if not r.get("error")),
        "summary": combined_summary
    }


# =============================================================================
# PDF IMAGE EXTRACTION
# =============================================================================

def extract_page_as_image(pdf_path: str, page_number: int, zoom: float = 2.0) -> Optional[str]:
    """
    Extract a specific page from PDF as base64 image.

    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        zoom: Zoom factor for resolution (2.0 = 2x quality)

    Returns:
        Base64 encoded PNG image string, or None if error
    """
    try:
        doc = fitz.open(pdf_path)

        # Page number is 1-indexed, fitz uses 0-indexed
        page_idx = page_number - 1

        if page_idx < 0 or page_idx >= len(doc):
            logger.error(f"Page {page_number} not found. PDF has {len(doc)} pages.")
            doc.close()
            return None

        page = doc[page_idx]

        # Render page at high resolution
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to base64
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        doc.close()

        logger.info(f"Extracted page {page_number} as image ({len(img_base64)} bytes base64)")
        return img_base64

    except Exception as e:
        logger.error(f"Error extracting page {page_number} as image: {e}")
        return None


def extract_multiple_pages(pdf_path: str, page_numbers: List[int], zoom: float = 2.0) -> Dict[int, str]:
    """
    Extract multiple pages as images in parallel.

    Args:
        pdf_path: Path to PDF file
        page_numbers: List of page numbers (1-indexed)
        zoom: Zoom factor for resolution

    Returns:
        Dict mapping page_number -> base64 image
    """
    results = {}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(extract_page_as_image, pdf_path, page_num, zoom): page_num
            for page_num in page_numbers
        }

        for future in futures:
            page_num = futures[future]
            try:
                img_base64 = future.result(timeout=30)
                if img_base64:
                    results[page_num] = img_base64
            except Exception as e:
                logger.error(f"Error extracting page {page_num}: {e}")

    return results


# =============================================================================
# GEMINI MULTIMODAL CLIENT
# =============================================================================

def call_gemini_with_image(
    image_base64: str,
    ocr_text: str,
    user_prompt: str,
    audit_type: str = "general"
) -> Dict[str, Any]:
    """
    Call Gemini with both image and text context for visual audit.

    Args:
        image_base64: Base64 encoded page image
        ocr_text: OCR extracted text for the page
        user_prompt: User's audit request
        audit_type: Type of audit ("calculation", "correction", "handwriting", "general")

    Returns:
        Dict with success status and analysis result
    """

    # Build system prompt based on audit type
    system_content = f"""You are a document auditor analyzing a Certificate of Analysis (COA) page.

You have TWO sources of information:

1. **OCR-EXTRACTED TEXT** (from AWS Textract):
{ocr_text}

2. **VISUAL IMAGE** of the same page (attached)

Your task: Use BOTH sources to perform deep analysis and find issues.

AUDIT CAPABILITIES:
- **Calculation Verification**: Check if math is correct (start_time + duration = end_time?)
- **Correction Detection**: Find strikethroughs, crossed-out text, and corrections
- **Handwriting Analysis**: Read handwritten entries that OCR might miss
- **Data Entry Errors**: Find inconsistencies, typos, missing data

IMPORTANT RULES:
- Compare visual image with OCR text to find discrepancies
- Look for handwritten corrections near printed values
- Check if calculations make sense mathematically
- Report findings with specific locations and values
- Use **bold** for important values (expected vs actual)
- Do NOT include confidence scores or technical metadata
- Keep response focused on findings only"""

    messages = [
        {"role": "system", "content": system_content}
    ]

    # User message with image
    user_content = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{image_base64}"
            }
        },
        {
            "type": "text",
            "text": user_prompt
        }
    ]

    messages.append({"role": "user", "content": user_content})

    try:
        response = requests.post(
            f"{ILIAD_URL}/api/llm/v1/chat/completions",
            headers={
                "X-API-Key": ILIAD_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": GEMINI_MODEL,
                "messages": messages,
                "max_tokens": 4000,
                "temperature": 0  # Deterministic for audit accuracy
            },
            timeout=120  # Longer timeout for vision model
        )

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            logger.info(f"Gemini analysis completed ({len(content)} chars)")

            return {
                "success": True,
                "analysis": content,
                "usage": data.get("usage", {})
            }
        else:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            return {
                "success": False,
                "error": f"API error: {response.status_code}",
                "details": response.text
            }

    except requests.exceptions.Timeout:
        logger.error("Gemini API timeout")
        return {
            "success": False,
            "error": "Request timeout - visual analysis took too long"
        }
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# =============================================================================
# VISUAL AUDIT SERVICE
# =============================================================================

class VisualAuditService:
    """
    Main service for visual audit capabilities.

    Two-stage process:
    - Stage 1: Discovery (find relevant data with BM25/Hybrid search)
    - Stage 2: Deep Analysis (Gemini multimodal on selected pages)
    """

    def __init__(self):
        """Initialize the visual audit service."""
        # Import here to avoid circular imports
        from services.weaviate_indexer import WeaviateIndexer
        from services.flashrank_reranker import get_reranker

        self.weaviate = WeaviateIndexer()
        self.reranker = get_reranker()
        self.executor = ThreadPoolExecutor(max_workers=3)

        logger.info("VisualAuditService initialized")

    def discover_audit_targets(
        self,
        query: str,
        process_id: str,
        filename: str = "document"
    ) -> Dict[str, Any]:
        """
        Stage 1: Discovery - Find relevant data for audit.

        Uses LLM-based query analysis to:
        1. Determine if query is general or specific
        2. Extract specific identifiers (step 7.3, page 31, etc.)
        3. Use BM25 (general) or BM25+FlashRank (specific) to find chunks
        4. For SPECIFIC queries: Use LLM to find pages with the identifier
           - If found on 1 page → return with auto_analyze=True
           - If found on multiple pages → show only those pages for user selection

        Args:
            query: User's audit query
            process_id: Document UUID
            filename: Document filename

        Returns:
            Dict with found chunks, pages, and prompt for user
        """
        logger.info(f"Visual Audit Discovery: '{query[:50]}...'")

        # Use LLM to analyze query and extract specific identifiers
        query_analysis = analyze_audit_query_with_llm(query)
        query_type = query_analysis.get("query_type", "general")
        identifier = query_analysis.get("identifier")
        identifier_type = query_analysis.get("identifier_type")
        search_keywords = query_analysis.get("search_keywords", [])

        logger.info(f"Query analysis: type={query_type}, identifier={identifier}, type={identifier_type}")

        # For VISUAL AUDIT: Always use hybrid search + reranking
        # Pure BM25 (alpha=0.0) is too broad - matches ANY chunk with "time" keyword
        # Hybrid (alpha=0.5) + FlashRank ensures semantically relevant chunks
        # e.g., "elapsed time" not just any "time" mention
        alpha = 0.5  # Hybrid search for semantic relevance
        use_reranking = True  # FlashRank to filter out irrelevant chunks
        logger.info(f"Visual audit using hybrid search (alpha={alpha}) + FlashRank reranking")

        # Search for relevant chunks
        try:
            chunks = self.weaviate.search_chunks(
                query=query,
                process_id=process_id,
                limit=30,  # Get more for discovery
                alpha=alpha
            )

            if not chunks:
                return {
                    "success": False,
                    "stage": "discovery",
                    "message": "No relevant data found for audit.",
                    "chunks": [],
                    "pages": []
                }

            # Apply reranking if specific query
            if use_reranking and self.reranker.is_available:
                chunks = self.reranker.rerank(
                    query=query,
                    results=chunks,
                    top_k=20
                )

            # Group chunks by page
            pages_data = {}
            for chunk in chunks:
                page = chunk.get('page', 0)
                if page not in pages_data:
                    pages_data[page] = {
                        'page': page,
                        'chunks': [],
                        'summary': []
                    }
                pages_data[page]['chunks'].append(chunk)

                # Extract key info for summary
                content = chunk.get('content', '')[:150]
                if content:
                    pages_data[page]['summary'].append(content)

            # Sort by page number
            sorted_pages = sorted(pages_data.keys())

            # =================================================================
            # SPECIFIC QUERY: Use LLM to find pages with the identifier
            # =================================================================
            if query_type == "specific" and identifier and identifier_type:
                logger.info(f"Looking for {identifier_type} '{identifier}' using LLM...")

                # Use LLM to find which pages contain the specific identifier
                matching_pages = find_pages_with_identifier_llm(
                    identifier=identifier,
                    identifier_type=identifier_type,
                    chunks=chunks,
                    pages_data=pages_data
                )

                if matching_pages:
                    logger.info(f"LLM found {identifier_type} '{identifier}' on pages: {matching_pages}")

                    # SPECIAL CASE: If user explicitly asked about a specific PAGE number,
                    # and that page is in matching_pages, auto-analyze it directly
                    # (Don't ask for selection when user said "page 31" and page 31 exists)
                    if identifier_type == 'page' and identifier.isdigit():
                        target_page = int(identifier)
                        if target_page in matching_pages:
                            logger.info(f"User explicitly requested page {target_page} - auto-analyzing")
                            return {
                                "success": True,
                                "stage": "discovery",
                                "query_type": query_type,
                                "identifier": identifier,
                                "identifier_type": identifier_type,
                                "message": f"Found data on **Page {target_page}**. Proceeding to deep analysis...",
                                "chunks": chunks,
                                "pages": [{'page': target_page, 'chunk_count': len(pages_data.get(target_page, {}).get('chunks', [])), 'preview': pages_data.get(target_page, {}).get('summary', [''])[0] if pages_data.get(target_page, {}).get('summary') else ''}],
                                "pages_found": [target_page],
                                "auto_analyze": True,
                                "auto_analyze_page": target_page,
                                "needs_page_selection": False
                            }

                    # If found on exactly 1 page → auto-analyze
                    if len(matching_pages) == 1:
                        logger.info(f"Single page match - setting auto_analyze=True for page {matching_pages[0]}")
                        return {
                            "success": True,
                            "stage": "discovery",
                            "query_type": query_type,
                            "identifier": identifier,
                            "identifier_type": identifier_type,
                            "message": f"Found **{identifier_type} {identifier}** on **Page {matching_pages[0]}**. Proceeding to deep analysis...",
                            "chunks": chunks,
                            "pages": [{'page': matching_pages[0], 'chunk_count': len(pages_data[matching_pages[0]]['chunks']), 'preview': pages_data[matching_pages[0]]['summary'][0] if pages_data[matching_pages[0]]['summary'] else ''}],
                            "pages_found": matching_pages,
                            "auto_analyze": True,
                            "auto_analyze_page": matching_pages[0],
                            "needs_page_selection": False
                        }

                    # If found on multiple pages → show only those pages for selection
                    else:
                        pages_info = []
                        for page in matching_pages[:10]:
                            data = pages_data[page]
                            pages_info.append({
                                'page': page,
                                'chunk_count': len(data['chunks']),
                                'preview': data['summary'][0] if data['summary'] else ''
                            })

                        message_parts = [f"Found **{identifier_type} {identifier}** on multiple pages:\n"]
                        for info in pages_info:
                            preview = info['preview'][:80] + "..." if len(info['preview']) > 80 else info['preview']
                            message_parts.append(f"**Page {info['page']}**: {preview}")
                        message_parts.append(f"\nWhich page do you want me to **deep analyze**? (Max {MAX_PAGES_FOR_ANALYSIS} pages)")

                        return {
                            "success": True,
                            "stage": "discovery",
                            "query_type": query_type,
                            "identifier": identifier,
                            "identifier_type": identifier_type,
                            "message": "\n".join(message_parts),
                            "chunks": chunks,
                            "pages": pages_info,
                            "pages_found": matching_pages,
                            "needs_page_selection": True
                        }
                else:
                    logger.info(f"LLM couldn't find {identifier_type} '{identifier}' in any page, showing all pages")

            # =================================================================
            # GENERAL QUERY: Use parallel agents to analyze many chunks
            # =================================================================
            # For general queries with many chunks, use parallel discovery agents
            if len(chunks) > CHUNKS_PER_AGENT:
                logger.info(f"General query with {len(chunks)} chunks - using parallel discovery agents")

                # Run parallel agents to analyze chunks
                parallel_result = run_parallel_discovery_agents(
                    query=query,
                    chunks=chunks,
                    max_agents=6  # Max 6 agents = 30 chunks
                )

                if parallel_result.get("success") and parallel_result.get("findings"):
                    findings = parallel_result["findings"]
                    audit_pages = parallel_result.get("pages_with_audit_targets", [])

                    # Build rich message with findings from parallel agents
                    message_parts = [
                        f"**Parallel Discovery Complete** ({parallel_result.get('agents_used', 1)} agents analyzed {parallel_result.get('total_chunks_processed', 0)} chunks)\n"
                    ]

                    # Group findings by audit type
                    findings_by_type = {}
                    for finding in findings:
                        audit_type = finding.get("audit_type", "general")
                        if audit_type not in findings_by_type:
                            findings_by_type[audit_type] = []
                        findings_by_type[audit_type].append(finding)

                    # Show findings grouped by type
                    type_labels = {
                        "calculation": "Calculations to Verify",
                        "correction": "Potential Corrections",
                        "time_value": "Time Values",
                        "data_entry": "Data Entries",
                        "general": "Other Findings"
                    }

                    for audit_type, type_findings in findings_by_type.items():
                        label = type_labels.get(audit_type, audit_type.title())
                        message_parts.append(f"\n**{label}:**")
                        for f in type_findings[:5]:  # Top 5 per type
                            page = f.get("page", "?")
                            summary = f.get("summary", "")[:80]
                            relevance = f.get("relevance", 0)
                            message_parts.append(f"  - Page {page}: {summary} (relevance: {relevance:.1f})")

                    # Show pages with audit targets
                    if audit_pages:
                        message_parts.append(f"\n**Pages with audit targets:** {', '.join(map(str, audit_pages[:15]))}")

                    message_parts.append(f"\nWhich page(s) do you want me to **deep analyze**? (Max {MAX_PAGES_FOR_ANALYSIS} pages)")

                    # Build pages_info for these specific pages
                    pages_info = []
                    for page in audit_pages[:10]:
                        if page in pages_data:
                            data = pages_data[page]
                            pages_info.append({
                                'page': page,
                                'chunk_count': len(data['chunks']),
                                'preview': data['summary'][0] if data['summary'] else ''
                            })

                    return {
                        "success": True,
                        "stage": "discovery",
                        "query_type": query_type,
                        "message": "\n".join(message_parts),
                        "chunks": chunks,
                        "pages": pages_info,
                        "pages_found": audit_pages,
                        "findings": findings,
                        "agents_used": parallel_result.get("agents_used", 1),
                        "needs_page_selection": True
                    }

            # Fallback: Simple page listing (for few chunks)
            pages_info = []
            for page in sorted_pages[:10]:  # Limit to top 10 pages
                data = pages_data[page]
                pages_info.append({
                    'page': page,
                    'chunk_count': len(data['chunks']),
                    'preview': data['summary'][0] if data['summary'] else ''
                })

            # Build user-friendly message
            message_parts = ["I found relevant data for audit on these pages:\n"]
            for info in pages_info:
                preview = info['preview'][:80] + "..." if len(info['preview']) > 80 else info['preview']
                message_parts.append(f"**Page {info['page']}**: {preview}")

            message_parts.append(f"\nWhich page do you want me to **deep analyze**? (Max {MAX_PAGES_FOR_ANALYSIS} pages at a time)")

            return {
                "success": True,
                "stage": "discovery",
                "query_type": query_type,
                "message": "\n".join(message_parts),
                "chunks": chunks,
                "pages": pages_info,
                "pages_found": sorted_pages,
                "needs_page_selection": True
            }

        except Exception as e:
            logger.error(f"Discovery error: {e}")
            return {
                "success": False,
                "stage": "discovery",
                "error": str(e),
                "chunks": [],
                "pages": []
            }

    def deep_analyze_page(
        self,
        query: str,
        process_id: str,
        pdf_path: str,
        page_number: int,
        chunks: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Stage 2: Deep Analysis - Gemini multimodal on specific page.

        Args:
            query: User's audit query
            process_id: Document UUID
            pdf_path: Path to PDF file
            page_number: Page to analyze (1-indexed)
            chunks: Pre-fetched chunks for the page (optional)

        Returns:
            Dict with detailed audit analysis
        """
        logger.info(f"Visual Audit Deep Analysis: Page {page_number}")

        # Validate PDF path
        if not os.path.exists(pdf_path):
            return {
                "success": False,
                "stage": "deep_analysis",
                "error": f"PDF file not found: {pdf_path}"
            }

        # Extract page as image
        image_base64 = extract_page_as_image(pdf_path, page_number)
        if not image_base64:
            return {
                "success": False,
                "stage": "deep_analysis",
                "error": f"Failed to extract page {page_number} as image"
            }

        # Get OCR text for the page
        if chunks:
            # Filter chunks for this page
            page_chunks = [c for c in chunks if c.get('page') == page_number]
        else:
            # Fetch chunks for this page from Weaviate
            page_chunks = self.weaviate.search_chunks(
                query=query,
                process_id=process_id,
                limit=20,
                alpha=0.0,
                page_filter=page_number
            )

        # Build OCR text from chunks
        ocr_text_parts = []
        for chunk in page_chunks:
            content = chunk.get('content', '')
            chunk_type = chunk.get('chunk_type', 'text')
            ocr_text_parts.append(f"[{chunk_type.upper()}]: {content}")

        ocr_text = "\n\n".join(ocr_text_parts) if ocr_text_parts else "No OCR text available for this page."

        # Build cell grounding info for the prompt
        cell_grounding_info = ""
        for chunk in page_chunks:
            if chunk.get('cell_grounding'):
                try:
                    cg = json.loads(chunk['cell_grounding'])
                    cell_grounding_info += f"\n[Chunk {chunk.get('chunk_index')} cells]:\n"
                    for cell_id, data in cg.items():
                        text = data.get('text', '')[:50]
                        row = data.get('row', '?')
                        col = data.get('col', '?')
                        cell_grounding_info += f"  [cell:{chunk.get('chunk_index')}:{cell_id}] row={row}, col={col}: \"{text}\"\n"
                except:
                    pass

        # Build audit prompt - ask Gemini to return cell references
        audit_prompt = f"""Analyze this page for the following audit request:

**User Request:** {query}

**CELL REFERENCE DATA** (use these IDs to reference specific cells):
{cell_grounding_info}

Please check:
1. **Calculation Errors**: Verify any time calculations (start + duration = end)
2. **Corrections/Strikethroughs**: Find any crossed-out text and what replaced it
3. **Handwriting**: Read any handwritten entries
4. **Data Entry Issues**: Find inconsistencies or errors

IMPORTANT - For each finding:
- Include [cell:CHUNK:CELL_ID|TYPE] references where TYPE is 'error' for errors/corrections or 'info' for normal values
- Example error: "Found incorrect value: 22 [cell:339:31-10|error]"
- Example info: "Mix Start Time: 1643 [cell:339:31-8|info]"

Report your findings clearly with:
- Location of each issue with cell references
- **Expected** vs **Actual** values (in bold) with [cell:...] references
- Any corrections detected (original ~~struck out~~ → new value) with cell references"""

        # Call Gemini for analysis
        result = call_gemini_with_image(
            image_base64=image_base64,
            ocr_text=ocr_text,
            user_prompt=audit_prompt
        )

        if result.get("success"):
            return {
                "success": True,
                "stage": "deep_analysis",
                "page": page_number,
                "analysis": result["analysis"],
                "chunks_used": len(page_chunks),
                "page_chunks": page_chunks  # Return chunks for reference extraction
            }
        else:
            return {
                "success": False,
                "stage": "deep_analysis",
                "page": page_number,
                "error": result.get("error", "Unknown error")
            }

    def deep_analyze_multiple_pages(
        self,
        query: str,
        process_id: str,
        pdf_path: str,
        page_numbers: List[int],
        chunks: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Stage 2: Deep Analysis on multiple pages (parallel).

        Args:
            query: User's audit query
            process_id: Document UUID
            pdf_path: Path to PDF file
            page_numbers: List of pages to analyze (max 3)
            chunks: Pre-fetched chunks (optional)

        Returns:
            Dict with combined audit analysis
        """
        # Limit pages
        if len(page_numbers) > MAX_PAGES_FOR_ANALYSIS:
            page_numbers = page_numbers[:MAX_PAGES_FOR_ANALYSIS]
            logger.warning(f"Limited to {MAX_PAGES_FOR_ANALYSIS} pages")

        logger.info(f"Visual Audit Multi-Page Analysis: {page_numbers}")

        # Run analysis in parallel
        results = {}

        with ThreadPoolExecutor(max_workers=MAX_PAGES_FOR_ANALYSIS) as executor:
            futures = {
                executor.submit(
                    self.deep_analyze_page,
                    query,
                    process_id,
                    pdf_path,
                    page_num,
                    chunks
                ): page_num
                for page_num in page_numbers
            }

            for future in futures:
                page_num = futures[future]
                try:
                    result = future.result(timeout=120)
                    results[page_num] = result
                except Exception as e:
                    logger.error(f"Error analyzing page {page_num}: {e}")
                    results[page_num] = {
                        "success": False,
                        "page": page_num,
                        "error": str(e)
                    }

        # Combine results and aggregate page_chunks for reference extraction
        combined_analysis = []
        successful_pages = []
        failed_pages = []
        all_page_chunks = []  # Aggregate page_chunks from all pages

        for page_num in sorted(results.keys()):
            result = results[page_num]
            if result.get("success"):
                successful_pages.append(page_num)
                combined_analysis.append(f"## Page {page_num}\n\n{result['analysis']}")
                # Collect page_chunks from each successful page analysis
                page_chunks = result.get("page_chunks", [])
                if page_chunks:
                    all_page_chunks.extend(page_chunks)
                    logger.debug(f"Collected {len(page_chunks)} chunks from page {page_num}")
            else:
                failed_pages.append(page_num)
                combined_analysis.append(f"## Page {page_num}\n\nError: {result.get('error', 'Unknown error')}")

        logger.info(f"Multi-page analysis: {len(successful_pages)} pages, {len(all_page_chunks)} total chunks for reference extraction")

        return {
            "success": len(successful_pages) > 0,
            "stage": "deep_analysis",
            "pages_analyzed": successful_pages,
            "pages_failed": failed_pages,
            "analysis": "\n\n---\n\n".join(combined_analysis),
            "page_chunks": all_page_chunks  # Return aggregated chunks for cell reference extraction
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_page_selection(user_input: str, available_pages: List[int]) -> List[int]:
    """
    Parse user's page selection input.

    Args:
        user_input: User's input (e.g., "31", "31, 45", "31 and 45")
        available_pages: List of available pages

    Returns:
        List of selected page numbers
    """
    # Extract all numbers from input
    numbers = re.findall(r'\d+', user_input)
    selected = [int(n) for n in numbers]

    # Filter to only available pages
    valid_pages = [p for p in selected if p in available_pages]

    # Limit to max
    if len(valid_pages) > MAX_PAGES_FOR_ANALYSIS:
        valid_pages = valid_pages[:MAX_PAGES_FOR_ANALYSIS]

    return valid_pages


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_visual_audit_instance: Optional[VisualAuditService] = None


def get_visual_audit_service() -> VisualAuditService:
    """Get or create the global VisualAuditService instance."""
    global _visual_audit_instance
    if _visual_audit_instance is None:
        _visual_audit_instance = VisualAuditService()
    return _visual_audit_instance


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print("=" * 80)
    print("VISUAL AUDIT SERVICE TEST - LLM-BASED QUERY ANALYSIS")
    print("=" * 80)

    # Test LLM-based query analysis
    test_queries = [
        "Check for errors",
        "Verify elapsed time on page 31",
        "Audit step 7.3 calculations",
        "Find all corrections",
        "Check batch 12345 data",
        "Is the elapsed mix time correct for step 7.3?",
        "Verify calculations in section 5",
    ]

    print("\nLLM Query Analysis:")
    print("-" * 60)
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        result = analyze_audit_query_with_llm(query)
        print(f"  Type: {result.get('query_type')}")
        print(f"  Identifier: {result.get('identifier')}")
        print(f"  Identifier Type: {result.get('identifier_type')}")
        print(f"  Keywords: {result.get('search_keywords')}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
