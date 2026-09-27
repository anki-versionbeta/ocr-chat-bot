"""
Query Analyzer Module - Phase 8 Enhancement

Extracts focus entities and analyzes query structure for targeted agent processing.
This enables agents to focus on relevant information only.
"""

import os
import re
import json
import logging
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# API Configuration
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED


class QueryType(Enum):
    """Types of queries based on structure."""
    SIMPLE = "simple"              # "What is the batch number?"
    CONDITIONAL = "conditional"    # "What is X for this Y?" (Y is anchor)
    MULTI_PART = "multi_part"      # "Find X and Y and Z"
    VERIFICATION = "verification"  # "Is X correct?" "Does page have Y?"
    EXHAUSTIVE = "exhaustive"      # "List ALL X" "Show every Y"


@dataclass
class QueryAnalysis:
    """Result of query analysis with focus entities and structure."""
    query_type: QueryType
    focus_entities: List[str] = field(default_factory=list)  # Must be in results
    anchor_term: Optional[str] = None      # Fixed reference (e.g., "lot number 1000962712")
    target_terms: List[str] = field(default_factory=list)    # What to find
    relevance_rule: str = ""               # Rule for filtering results
    expanded_keywords: List[str] = field(default_factory=list)  # Synonyms/variations
    confidence: float = 0.8


# =============================================================================
# LLM-BASED QUERY ANALYZER
# =============================================================================

QUERY_ANALYZER_PROMPT = """You are a query analyzer for a document Q&A system. Analyze the user's query to extract key information for targeted search.

## YOUR TASK
Analyze the query and identify:
1. **Query Type**: simple, conditional, multi_part, verification, or exhaustive
2. **Focus Entities**: Specific values that MUST be present in the answer (lot numbers, dates, specific names)
3. **Anchor Term**: If conditional query, the fixed reference point (e.g., "lot number 1000962712")
4. **Target Terms**: What the user wants to find (e.g., "step reference", "page number")
5. **Expanded Keywords**: Include singular/plural forms and synonyms

## QUERY TYPES
- **simple**: Direct question with no conditions ("What is the batch number?")
- **conditional**: Find X for specific Y ("What is the page for lot 1000962712?")
- **multi_part**: Multiple things to find ("Find page, date, and signature")
- **verification**: Yes/no question ("Does page 31 have signatures?")
- **exhaustive**: Find ALL instances ("List all batch numbers")

## IMPORTANT RULES
1. Extract EXACT values mentioned (lot numbers, dates, specific terms)
2. Include both singular AND plural forms in expanded_keywords
3. If user references previous answer (e.g., "this lot number"), note it needs context
4. For verification queries, the anchor_term is what's being verified

## CONVERSATION CONTEXT
{conversation_context}

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
    "query_type": "<type>",
    "focus_entities": ["entity1", "entity2"],
    "anchor_term": "<anchor or null>",
    "target_terms": ["target1", "target2"],
    "relevance_rule": "<rule for filtering results>",
    "expanded_keywords": ["keyword1", "keyword2", "keyword1s"],
    "confidence": 0.9
}}

## EXAMPLES

Query: "What is the step reference for lot number 1000962712?"
{{
    "query_type": "conditional",
    "focus_entities": ["1000962712", "lot number"],
    "anchor_term": "lot number 1000962712",
    "target_terms": ["step reference", "page"],
    "relevance_rule": "Only include results containing lot 1000962712",
    "expanded_keywords": ["lot number", "lot", "1000962712", "step reference", "step references"],
    "confidence": 0.95
}}

Query: "Which pages have signatures?"
{{
    "query_type": "simple",
    "focus_entities": [],
    "anchor_term": null,
    "target_terms": ["signature", "page"],
    "relevance_rule": "Include all pages with signature information",
    "expanded_keywords": ["signature", "signatures", "signed", "sign"],
    "confidence": 0.9
}}

Query: "Does the page with lot 1000962712 have a signature?"
{{
    "query_type": "verification",
    "focus_entities": ["1000962712"],
    "anchor_term": "lot number 1000962712",
    "target_terms": ["signature"],
    "relevance_rule": "Only check pages containing lot 1000962712 for signature presence",
    "expanded_keywords": ["signature", "signatures", "signed", "lot", "1000962712"],
    "confidence": 0.9
}}

Query: "List all batch numbers in the document"
{{
    "query_type": "exhaustive",
    "focus_entities": [],
    "anchor_term": null,
    "target_terms": ["batch number"],
    "relevance_rule": "Find ALL batch numbers across all pages",
    "expanded_keywords": ["batch number", "batch numbers", "batch id", "batch", "lot number"],
    "confidence": 0.9
}}

Query: {query}
"""


def analyze_query_llm(query: str, conversation_context: str = "") -> QueryAnalysis:
    """
    Use LLM to analyze query structure and extract focus entities.

    Args:
        query: User's query
        conversation_context: Recent conversation for context (e.g., previous lot number mentioned)

    Returns:
        QueryAnalysis with extracted information
    """
    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        prompt = QUERY_ANALYZER_PROMPT.format(
            query=query,
            conversation_context=conversation_context or "No previous context"
        )

        payload = {
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.0
        }

        response = requests.post(
            f"{ILIAD_URL}/api/llm/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"Query analyzer API error: {response.status_code}")
            return _fallback_analysis(query)

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from response
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        analysis = QueryAnalysis(
            query_type=QueryType(data.get("query_type", "simple")),
            focus_entities=data.get("focus_entities", []),
            anchor_term=data.get("anchor_term"),
            target_terms=data.get("target_terms", []),
            relevance_rule=data.get("relevance_rule", ""),
            expanded_keywords=data.get("expanded_keywords", []),
            confidence=data.get("confidence", 0.8)
        )

        logger.info(f"Query analysis: type={analysis.query_type.value}, "
                   f"focus={analysis.focus_entities}, anchor={analysis.anchor_term}")

        return analysis

    except json.JSONDecodeError as e:
        logger.error(f"Query analyzer JSON error: {e}")
        return _fallback_analysis(query)
    except Exception as e:
        logger.error(f"Query analyzer error: {e}")
        return _fallback_analysis(query)


def _fallback_analysis(query: str) -> QueryAnalysis:
    """Fallback rule-based analysis when LLM fails."""
    query_lower = query.lower()

    # Detect query type
    query_type = QueryType.SIMPLE

    if any(w in query_lower for w in ["all ", "every ", "list all", "show all"]):
        query_type = QueryType.EXHAUSTIVE
    elif any(w in query_lower for w in ["does ", "is ", "are ", "can you check", "verify"]):
        query_type = QueryType.VERIFICATION
    elif " for " in query_lower or " of " in query_lower:
        query_type = QueryType.CONDITIONAL

    # Extract numbers (potential lot numbers, dates)
    numbers = re.findall(r'\b\d{7,}\b', query)  # 7+ digit numbers

    # Extract keywords
    keywords = []
    important_terms = ["signature", "lot", "batch", "step", "page", "date", "reference"]
    for term in important_terms:
        if term in query_lower:
            keywords.append(term)
            # Add plural form
            if not term.endswith('s'):
                keywords.append(term + 's')

    return QueryAnalysis(
        query_type=query_type,
        focus_entities=numbers,
        anchor_term=numbers[0] if numbers else None,
        target_terms=keywords[:3],
        relevance_rule="Include results matching query terms",
        expanded_keywords=keywords,
        confidence=0.6
    )


def analyze_query(query: str, conversation_context: str = "", use_llm: bool = True) -> QueryAnalysis:
    """
    Main entry point for query analysis.

    Args:
        query: User's query
        conversation_context: Recent conversation for context
        use_llm: Whether to use LLM (True) or rule-based (False)

    Returns:
        QueryAnalysis object
    """
    if use_llm:
        return analyze_query_llm(query, conversation_context)
    return _fallback_analysis(query)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def extract_conversation_context(messages: List[Dict], max_messages: int = 3) -> str:
    """
    Extract recent conversation context for query analysis.

    This helps when user references previous answers (e.g., "this lot number").
    """
    if not messages:
        return ""

    recent = messages[-max_messages:]
    context_parts = []

    for msg in recent:
        role = msg.get("role", "")
        content = msg.get("content", "")[:200]  # Truncate
        context_parts.append(f"{role}: {content}")

    return "\n".join(context_parts)


def build_focus_filter(analysis: QueryAnalysis) -> callable:
    """
    Build a filter function based on query analysis.

    Returns a function that checks if content is relevant.
    """
    focus_entities = [e.lower() for e in analysis.focus_entities]

    def is_relevant(content: str) -> bool:
        if not focus_entities:
            return True  # No focus entities = everything relevant

        content_lower = content.lower()
        # Check if ANY focus entity is in content
        return any(entity in content_lower for entity in focus_entities)

    return is_relevant
