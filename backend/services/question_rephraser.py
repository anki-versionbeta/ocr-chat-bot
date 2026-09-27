"""
Question Rephraser for Phase 4 - Multi-Agent RAG Orchestration

This module generates alternative phrasings of user queries to improve
search recall. COA documents use varied terminology, so rephrasing helps
find relevant content that might use different terms.

Example:
  "batch number" → ["lot number", "batch ID", "lot ID", "manufacturing batch"]
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ocr-chatbot.question_rephraser")


# Iliad API configuration
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED


REPHRASER_PROMPT = """You are a search query optimizer for Certificate of Analysis (COA) documents.

Given a user question, generate 3-5 alternative phrasings that might match relevant content in the document.

Use COA-specific terminology and synonyms:
- batch number → lot number, lot ID, batch ID, manufacturing batch
- expiry date → expiration date, exp date, best before, shelf life
- appearance → visual inspection, physical description, color, form
- specifications → specs, requirements, acceptance criteria, limits
- test results → analytical results, testing data, assay results
- pH → acidity, hydrogen ion concentration
- moisture → water content, loss on drying, LOD
- assay → purity, content, potency

Original question: {query}

Generate variations that:
1. Use synonyms (batch number → lot number, lot ID)
2. Use industry terms (specifications → specs, requirements)
3. Rephrase the question structure
4. Include abbreviations and full forms

Return ONLY a JSON array of strings, no explanation.
Example: ["variation 1", "variation 2", "variation 3"]"""


# Common COA term synonyms for quick expansion
COA_SYNONYMS = {
    "batch number": ["lot number", "batch ID", "lot ID", "batch no", "lot no"],
    "batch": ["lot", "manufacturing batch"],
    "expiry date": ["expiration date", "exp date", "best before", "use by date"],
    "expiry": ["expiration", "exp"],
    "appearance": ["visual inspection", "physical description", "color and form"],
    "specifications": ["specs", "specification limits", "acceptance criteria", "requirements"],
    "test results": ["analytical results", "testing data", "assay results"],
    "results": ["values", "findings", "data"],
    "ph": ["acidity", "pH value", "hydrogen ion"],
    "moisture": ["water content", "loss on drying", "LOD", "moisture content"],
    "assay": ["purity", "content", "potency", "assay value"],
    "identity": ["identification", "ID test"],
    "sterility": ["sterile", "sterility test"],
    "endotoxin": ["bacterial endotoxins", "LAL test", "pyrogen"],
    "particulate": ["particulate matter", "visible particles", "subvisible particles"],
    "description": ["appearance", "physical form"],
    "method": ["test method", "procedure", "analytical method"],
    "specification": ["spec", "limit", "acceptance criterion"],
    "result": ["value", "finding", "outcome"],
    "material": ["product", "substance", "item"],
    "product name": ["material name", "item name", "substance name"],
    "manufacturer": ["supplier", "vendor", "producer"],
    "coa": ["certificate of analysis", "cert of analysis", "analysis certificate"],
}


def expand_with_synonyms(query: str) -> List[str]:
    """
    Quick expansion of query using COA synonym dictionary.

    Args:
        query: Original query

    Returns:
        List of expanded variations
    """
    variations = []
    query_lower = query.lower()

    for term, synonyms in COA_SYNONYMS.items():
        if term in query_lower:
            for synonym in synonyms:
                # Replace the term with synonym
                variation = re.sub(
                    re.escape(term),
                    synonym,
                    query_lower,
                    flags=re.IGNORECASE
                )
                if variation != query_lower:
                    variations.append(variation)

    return variations[:5]  # Limit to 5 variations


def rephrase_with_llm(query: str) -> List[str]:
    """
    Generate query variations using Claude Haiku.

    Args:
        query: Original query

    Returns:
        List of rephrased queries
    """
    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 300,
            "messages": [{
                "role": "user",
                "content": REPHRASER_PROMPT.format(query=query)
            }]
        }

        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"Rephraser API error: {response.status_code} - {response.text}")
            return []

        result = response.json()
        content = result.get("content", [{}])[0].get("text", "").strip()

        # Parse JSON array
        try:
            # Handle potential markdown code blocks
            if "```" in content:
                # Extract JSON from code block
                json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', content, re.DOTALL)
                if json_match:
                    content = json_match.group(1)

            variations = json.loads(content)

            if isinstance(variations, list):
                # Filter out empty strings and limit
                variations = [v.strip() for v in variations if v.strip()]
                logger.info(f"LLM generated {len(variations)} variations for query")
                return variations[:5]

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse rephraser response as JSON: {e}")
            # Try to extract variations from plain text
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            lines = [re.sub(r'^[\d\.\-\*]+\s*', '', line) for line in lines]
            return lines[:5]

    except requests.exceptions.Timeout:
        logger.warning("Rephraser timeout")
    except Exception as e:
        logger.error(f"Rephraser error: {e}")

    return []


async def rephrase_question(query: str, use_llm: bool = True) -> List[str]:
    """
    Generate query variations for better search recall.

    Combines rule-based synonym expansion with optional LLM rephrasing.
    Always includes the original query as the first variation.

    Args:
        query: Original user query
        use_llm: Whether to use LLM for additional variations

    Returns:
        List of query variations (including original)
    """
    # Always start with original query
    variations = [query]

    # Add synonym-based expansions
    synonym_variations = expand_with_synonyms(query)
    for var in synonym_variations:
        if var not in variations:
            variations.append(var)

    # Add LLM variations if enabled
    if use_llm and len(variations) < 4:
        llm_variations = rephrase_with_llm(query)
        for var in llm_variations:
            if var not in variations and var.lower() != query.lower():
                variations.append(var)

    # Limit total variations
    variations = variations[:6]

    logger.info(f"Generated {len(variations)} query variations: {variations[:3]}...")

    return variations


def rephrase_question_sync(query: str, use_llm: bool = True) -> List[str]:
    """
    Synchronous version of rephrase_question.

    Args:
        query: Original user query
        use_llm: Whether to use LLM for additional variations

    Returns:
        List of query variations (including original)
    """
    # Always start with original query
    variations = [query]

    # Add synonym-based expansions
    synonym_variations = expand_with_synonyms(query)
    for var in synonym_variations:
        if var not in variations:
            variations.append(var)

    # Add LLM variations if enabled
    if use_llm and len(variations) < 4:
        llm_variations = rephrase_with_llm(query)
        for var in llm_variations:
            if var not in variations and var.lower() != query.lower():
                variations.append(var)

    # Limit total variations
    variations = variations[:6]

    logger.info(f"Generated {len(variations)} query variations")

    return variations


def detect_page_filter(query: str) -> Optional[int]:
    """
    Detect if query specifies a page number to filter by.

    Args:
        query: User query

    Returns:
        Page number (int) if detected, None otherwise

    Examples:
        "from page 5" → 5
        "on page 3" → 3
        "in table from page 10" → 10
        "page number 7" → 7
        "p.5" → 5
    """
    query_lower = query.lower()

    # Pattern: "from page X", "on page X", "page X", "page number X"
    # IMPORTANT: Avoid matching "step 8.4" as page 8 - require word boundary or start of string!
    patterns = [
        r'(?:from|on|in|at)\s+page\s*(\d+)',   # from page 5, on page 3
        r'\bpage\s+(?:number\s+)?(\d+)',        # page 5, page number 5
        r'(?:^|\s)p\.?\s*(\d+)(?:\s|$|[,.])',   # p.5 or p5 - must have space/start before and space/end/punct after
        r'\bpg\.?\s*(\d+)',                     # pg.5 or pg5
    ]

    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            page_num = int(match.group(1))
            logger.info(f"Detected page filter: page {page_num} from query")
            return page_num

    return None


def detect_row_col_query(query: str) -> Optional[Dict[str, int]]:
    """
    Detect if query is asking for a specific row/column position.

    Args:
        query: User query

    Returns:
        Dict with 'row' and 'col' if detected, None otherwise

    Examples:
        "value at row 7, column 3" → {'row': 7, 'col': 3}
        "what's in row 5 col 2?" → {'row': 5, 'col': 2}
        "cell 2-5" → {'row': 2, 'col': 5}
    """
    query_lower = query.lower()

    # Pattern: "row X, column Y" or "row X col Y"
    match = re.search(
        r'row\s*(\d+)\s*[,\s]*(?:column|col)\s*(\d+)',
        query_lower
    )
    if match:
        return {'row': int(match.group(1)), 'col': int(match.group(2))}

    # Pattern: "cell X-Y"
    match = re.search(r'cell\s*(\d+)-(\d+)', query_lower)
    if match:
        return {'row': int(match.group(1)), 'col': int(match.group(2))}

    # Pattern: "r5 c3" or "R5 C3"
    match = re.search(r'\br(\d+)\s*c(\d+)', query_lower)
    if match:
        return {'row': int(match.group(1)), 'col': int(match.group(2))}

    return None


def resolve_context_references(
    query: str,
    recent_messages: List[Dict[str, str]]
) -> str:
    """
    Resolve pronouns and context references using recent conversation history.

    Args:
        query: Current user query
        recent_messages: Last 3 messages from conversation

    Returns:
        Resolved query with context

    Examples:
        "What about the expiry?" + context about batch number
        → "What is the expiry date for this document?"
    """
    # Simple pronoun patterns that might need context
    context_patterns = [
        r'^what about (it|that|this|the)(\s|$)',
        r'^and (the|its|their)?\s*',
        r'^(show|get|find) (it|that|this)\s*$',
        r'^(its|their|the same)\s+',
    ]

    query_lower = query.lower().strip()

    # Check if query needs context resolution
    needs_context = any(
        re.search(pattern, query_lower)
        for pattern in context_patterns
    )

    if not needs_context or not recent_messages:
        return query

    # Try to extract subject from recent messages
    # Look for nouns/entities in assistant's last response
    for msg in reversed(recent_messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')

            # Extract potential subjects (batch number, expiry date, etc.)
            subject_patterns = [
                r'(batch\s+number|lot\s+number)',
                r'(expiry\s+date|expiration\s+date)',
                r'(test\s+results?)',
                r'(specifications?)',
                r'(appearance)',
                r'(\w+\s+value)',
            ]

            for pattern in subject_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    subject = match.group(1)
                    # Replace context reference with subject
                    resolved = re.sub(
                        r'\b(it|that|this)\b',
                        subject,
                        query,
                        flags=re.IGNORECASE
                    )
                    if resolved != query:
                        logger.info(f"Resolved context: '{query}' → '{resolved}'")
                        return resolved

    return query
