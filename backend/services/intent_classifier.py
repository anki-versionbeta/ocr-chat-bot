"""
Intent Classifier for Phase 4 + Phase 6 + Phase 8 - Dynamic Query Routing with Gemini Flash

This module classifies user queries into different intent categories and outputs
a structured Execution Plan with dynamic parameters for optimal retrieval.

PHASE 8 UPGRADE:
- Switched from Claude Haiku to Gemini 2.5 Flash for faster, cheaper classification
- Added structured JSON output with execution parameters
- New intents: precision, exploratory, exhaustive, comparison
- Dynamic alpha, rerank limits, and agent strategy per intent

Intent Categories:
- precision: Single value lookup (fast path, single agent)
- exploratory: General Q&A, multiple values (parallel 5 agents)
- exhaustive: Extract ALL instances (parallel 8 agents, max recall)
- comparison: Compare two or more items (dual-path search)
- structural: Page finding, table navigation (Neo4j only)
- hybrid_semantic_structural: Column extraction + export (Weaviate + Neo4j)
- visual_audit: Verification with Gemini Vision
- clarification: Ambiguous queries

Updated: February 26, 2026 - Phase 8 Dynamic Query Routing
"""

import os
import json
import logging
import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ocr-chatbot.intent_classifier")


# =============================================================================
# INTENT AND STRATEGY ENUMS
# =============================================================================

class QueryIntent(str, Enum):
    """Query intent categories."""
    PRECISION = "precision"
    EXPLORATORY = "exploratory"
    EXHAUSTIVE = "exhaustive"
    COMPARISON = "comparison"
    STRUCTURAL = "structural"
    HYBRID_SEMANTIC_STRUCTURAL = "hybrid_semantic_structural"
    EXTRACTION = "extraction"
    VISUAL_AUDIT = "visual_audit"
    CROSS_REFERENCE = "cross_reference"
    CLARIFICATION = "clarification"

    # Legacy mappings for backward compatibility
    VECTOR_ONLY = "vector_only"  # Maps to precision/exploratory


class AgentStrategy(str, Enum):
    """Agent execution strategies."""
    SINGLE = "single"                       # Fast path - 1 agent
    PARALLEL_5 = "parallel_5"               # Standard - 5 parallel agents
    PARALLEL_8 = "parallel_8"               # Heavy lift - 8 parallel agents
    DUAL_PATH = "dual_path"                 # Comparison - search each target
    NEO4J_TEMPLATE = "neo4j_template"       # Structural - Neo4j templates
    MULTI_AGENT_CYPHER = "multi_agent_cypher"  # Hybrid - dynamic Cypher
    VISION = "vision"                       # Visual audit - Gemini Vision


# =============================================================================
# EXECUTION PLAN DATA CLASS
# =============================================================================

@dataclass
class ExecutionPlan:
    """
    Structured execution plan from intent classifier.
    Contains all parameters needed to route and execute the query.
    """
    intent: QueryIntent
    bm25_limit: int
    vector_limit: int
    rerank_limit: int
    alpha: float  # Hybrid search weight: 0=BM25, 1=semantic
    agent_strategy: AgentStrategy
    confidence: float
    reasoning: str
    comparison_targets: Optional[List[str]] = None
    search_keywords: Optional[List[str]] = None
    page_filter: Optional[int] = None
    sub_queries: Optional[List[Dict[str, str]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "intent": self.intent.value,
            "bm25_limit": self.bm25_limit,
            "vector_limit": self.vector_limit,
            "rerank_limit": self.rerank_limit,
            "alpha": self.alpha,
            "agent_strategy": self.agent_strategy.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "comparison_targets": self.comparison_targets,
            "search_keywords": self.search_keywords,
            "page_filter": self.page_filter,
            "sub_queries": self.sub_queries
        }


# =============================================================================
# CONFIGURATION
# =============================================================================

# Iliad API configuration
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Model configuration - Using Gemini 2.5 Flash for fast, reliable classification
INTENT_CLASSIFIER_MODEL = "gemini-2.5-flash"
INTENT_CLASSIFIER_TIMEOUT = 10  # seconds


# =============================================================================
# JSON SCHEMA FOR STRUCTURED OUTPUT
# =============================================================================

EXECUTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["precision", "exploratory", "exhaustive", "cross_reference", "comparison",
                     "hybrid_semantic_structural", "visual_audit", "clarification"]
        },
        "bm25_limit": {
            "type": "integer",
            "description": "Number of BM25 keyword search results to retrieve"
        },
        "vector_limit": {
            "type": "integer",
            "description": "Number of semantic vector search results to retrieve"
        },
        "rerank_limit": {
            "type": "integer",
            "description": "Number of results to keep after FlashRank reranking"
        },
        "alpha": {
            "type": "number",
            "description": "Hybrid search weight: 0.0=pure BM25, 1.0=pure semantic"
        },
        "agent_strategy": {
            "type": "string",
            "enum": ["single", "parallel_5", "parallel_8", "dual_path",
                     "neo4j_template", "multi_agent_cypher", "vision"]
        },
        "confidence": {
            "type": "number",
            "description": "Confidence score 0.0-1.0"
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of classification"
        },
        "comparison_targets": {
            "type": "array",
            "items": {"type": "string"},
            "description": "For comparison intent: items being compared"
        },
        "search_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key terms to search for"
        },
        "page_filter": {
            "type": "integer",
            "description": "Specific page number if mentioned"
        },
        "sub_queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string", "enum": ["locate", "extract"]},
                    "query": {"type": "string"}
                }
            },
            "description": "For cross_reference intent: decomposed sub-queries (locate then extract)"
        }
    },
    "required": ["intent", "bm25_limit", "vector_limit", "rerank_limit",
                 "alpha", "agent_strategy", "confidence", "reasoning"]
}


# =============================================================================
# INTENT CLASSIFICATION PROMPT
# =============================================================================

INTENT_CLASSIFIER_PROMPT = """You are an intelligent query router for a document Q&A system processing Certificate of Analysis (COA) documents.

Analyze the user's query and determine the optimal execution plan.

## INTENT DEFINITIONS

### 1. precision
- **When**: Single specific value lookup (batch number, date, one cell value)
- **Examples**: "What is the batch number?", "When was this signed?", "What is the pH value?"
- **Parameters**: bm25_limit=10, vector_limit=10, rerank_limit=5, alpha=0.5, agent_strategy="single"

### 2. exploratory
- **When**: General Q&A, descriptions, multiple related values, OR finding where something is located
- **Examples**: "Tell me about the test results", "What specifications are listed?", "Which page has the batch info?", "Where is the concentration data?"
- **IMPORTANT**: Page-finding questions like "which page has X" should use exploratory (Weaviate search), NOT structural
- **Parameters**: bm25_limit=40, vector_limit=40, rerank_limit=25, alpha=0.5, agent_strategy="parallel_5"

### 3. exhaustive
- **When**: Extract ALL instances across entire document (keywords: "all", "every", "complete list", "entire")
- **Examples**: "List ALL batch numbers", "Show every test result", "Extract all concentration values"
- **Parameters**: bm25_limit=50, vector_limit=50, rerank_limit=35, alpha=0.3, agent_strategy="parallel_8"

### 4. cross_reference
- **When**: Query needs to LOCATE pages/sections by one criterion, then EXTRACT different data from those locations
- **Signal**: The search term and the desired data are DIFFERENT things. User wants data Y from wherever X appears.
- **Examples**:
  - "Find all test data where batch number 12345 is present" (locate: batch 12345, extract: test data)
  - "Show specifications on pages that have product ABC" (locate: product ABC, extract: specifications)
  - "What results are on the same pages as compound XYZ?" (locate: compound XYZ, extract: results)
  - "Get all data from pages containing approval signatures" (locate: approval signatures, extract: all data)
- **NOT cross_reference**: "Find all batch numbers" (single search term = exhaustive), "What is batch 12345?" (single lookup = precision)
- **Parameters**: bm25_limit=30, vector_limit=30, rerank_limit=25, alpha=0.3, agent_strategy="parallel_8"
- **REQUIRED**: Decompose into sub_queries array with exactly 2 entries:
  - {{"step": "locate", "query": "<the locating criterion>"}}
  - {{"step": "extract", "query": "<the data to extract from located pages>"}}

### 5. comparison
- **When**: Compare two or more items (keywords: "compare", "difference", "vs", "versus", "between")
- **Examples**: "Compare batch 123 vs 456", "What's the difference between test A and B?"
- **Parameters**: bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5, agent_strategy="dual_path"
- **IMPORTANT**: Extract the items being compared into comparison_targets array

### 5. hybrid_semantic_structural
- **When**: ONLY for bulk data extraction with export to file (Excel, CSV)
- **Keywords**: "export", "Excel", "CSV", "download", "save to file", "extract to"
- **Examples**: "Export concentration data to Excel", "Download all values as CSV", "Save results to Excel"
- **IMPORTANT**: This is ONLY for BULK DATA EXPORT operations. Simple data queries should use exploratory or exhaustive.
- **Parameters**: bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.5, agent_strategy="multi_agent_cypher"

### 6. visual_audit
- **When**: Verification, error checking, validation (keywords: "check", "verify", "correct", "audit", "validate")
- **Examples**: "Is this calculation correct?", "Verify step 7.3", "Check for errors in page 5"
- **Parameters**: bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5, agent_strategy="vision"

### 7. clarification
- **When**: ONLY for single words or pronouns without any context (NOT for questions about document content)
- **Examples**: "it", "that", "yes", "ok", "more", "hmm"
- **NEVER use for**: Questions like "who is X?", "what is X?", "when was X?" - these are PRECISION queries even if answer might not exist
- **Parameters**: bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0, agent_strategy="single"

## CRITICAL ROUTING RULES (IN PRIORITY ORDER - FOLLOW STRICTLY)
1. **HIGHEST PRIORITY**: If query mentions "Export to Excel", "CSV", "download", "save to file" → HYBRID_SEMANTIC_STRUCTURAL (even if query also says "all" or "every")
2. If query says "List ALL X" or "Show every X" WITHOUT export request → EXHAUSTIVE
3. If query asks for data Y "where" / "from pages that have" / "on pages with" X, and Y is DIFFERENT from X → CROSS_REFERENCE with sub_queries
4. **Questions are NEVER clarification**: "who is X?", "what is X?", "when was X?" → PRECISION (single value) or EXPLORATORY (multiple values)
4. When in doubt, choose EXPLORATORY - it handles most queries well
5. ONLY use CLARIFICATION for bare pronouns like "it", "that" with no context

**IMPORTANT**: Export/Excel/CSV keywords ALWAYS override "all/every" keywords. A query like "Get all X and export to Excel" is HYBRID_SEMANTIC_STRUCTURAL, NOT exhaustive.

## ALPHA VALUE GUIDE
- 0.3 = Favor BM25 (keyword matching) - Best for exact value extraction
- 0.5 = Balanced - Best for specific lookups and comparisons
- 0.7 = Favor semantic - Best for conceptual/exploratory queries

## PAGE FILTER
If user mentions a specific page (e.g., "on page 5", "from page 3"), extract the page number into page_filter.
**IMPORTANT**: When a specific page is mentioned, use agent_strategy="single" instead of "parallel_5" since scope is limited to one page.

## SEARCH KEYWORDS
Extract 2-5 key terms from the query that should be searched in the document.
**IMPORTANT**: Include common synonyms/alternatives for better matching:
- "batch number" → also include "batch id", "lot number", "lot id"
- "expiry date" → also include "expiration date", "exp date"
- "mix time" → also include "mixing time", "elapsed mix time"

## OUTPUT FORMAT
Return ONLY valid JSON matching this structure:
{{
    "intent": "<intent_name>",
    "bm25_limit": <number>,
    "vector_limit": <number>,
    "rerank_limit": <number>,
    "alpha": <number 0.0-1.0>,
    "agent_strategy": "<strategy>",
    "confidence": <number 0.0-1.0>,
    "reasoning": "<brief explanation>",
    "comparison_targets": ["item1", "item2"] or null,
    "search_keywords": ["keyword1", "keyword2"],
    "page_filter": <number> or null,
    "sub_queries": [{{"step": "locate", "query": "..."}}, {{"step": "extract", "query": "..."}}] or null
}}

Query: {query}
"""


# =============================================================================
# DEFAULT EXECUTION PLANS (for rule-based fast path)
# =============================================================================

DEFAULT_PLANS = {
    QueryIntent.PRECISION: ExecutionPlan(
        intent=QueryIntent.PRECISION,
        bm25_limit=10, vector_limit=10, rerank_limit=5, alpha=0.5,
        agent_strategy=AgentStrategy.SINGLE, confidence=0.9,
        reasoning="Single value lookup - fast path"
    ),
    QueryIntent.EXPLORATORY: ExecutionPlan(
        intent=QueryIntent.EXPLORATORY,
        bm25_limit=40, vector_limit=40, rerank_limit=25, alpha=0.5,
        agent_strategy=AgentStrategy.PARALLEL_5, confidence=0.9,
        reasoning="General Q&A - parallel agents"
    ),
    QueryIntent.EXHAUSTIVE: ExecutionPlan(
        intent=QueryIntent.EXHAUSTIVE,
        bm25_limit=50, vector_limit=50, rerank_limit=35, alpha=0.3,
        agent_strategy=AgentStrategy.PARALLEL_8, confidence=0.9,
        reasoning="Extract all instances - maximum recall"
    ),
    QueryIntent.COMPARISON: ExecutionPlan(
        intent=QueryIntent.COMPARISON,
        bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5,
        agent_strategy=AgentStrategy.DUAL_PATH, confidence=0.9,
        reasoning="Comparison query - dual path search"
    ),
    QueryIntent.STRUCTURAL: ExecutionPlan(
        intent=QueryIntent.STRUCTURAL,
        bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0,
        agent_strategy=AgentStrategy.NEO4J_TEMPLATE, confidence=0.9,
        reasoning="Document structure query - Neo4j"
    ),
    QueryIntent.HYBRID_SEMANTIC_STRUCTURAL: ExecutionPlan(
        intent=QueryIntent.HYBRID_SEMANTIC_STRUCTURAL,
        bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.5,
        agent_strategy=AgentStrategy.MULTI_AGENT_CYPHER, confidence=0.9,
        reasoning="Column extraction - Weaviate + Neo4j"
    ),
    QueryIntent.VISUAL_AUDIT: ExecutionPlan(
        intent=QueryIntent.VISUAL_AUDIT,
        bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5,
        agent_strategy=AgentStrategy.VISION, confidence=0.9,
        reasoning="Visual verification - Gemini Vision"
    ),
    QueryIntent.CROSS_REFERENCE: ExecutionPlan(
        intent=QueryIntent.CROSS_REFERENCE,
        bm25_limit=30, vector_limit=30, rerank_limit=25, alpha=0.3,
        agent_strategy=AgentStrategy.PARALLEL_8, confidence=0.9,
        reasoning="Multi-step cross-reference - locate then extract"
    ),
    QueryIntent.CLARIFICATION: ExecutionPlan(
        intent=QueryIntent.CLARIFICATION,
        bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0,
        agent_strategy=AgentStrategy.SINGLE, confidence=0.95,
        reasoning="Query too vague - needs clarification"
    ),
}


# =============================================================================
# RULE-BASED QUICK CLASSIFICATION
# =============================================================================

def classify_intent_rule_based(query: str) -> Optional[ExecutionPlan]:
    """
    Quick rule-based classification for obvious query patterns.
    Returns None if no clear pattern is found (falls back to LLM).

    This handles ~60% of queries without needing an LLM call.
    """
    # ALWAYS use LLM-based classification for better accuracy
    # Rule-based patterns cause edge case failures (e.g., "get all... export to excel" wrongly matched exhaustive)
    # Keeping code below commented out for future reference
    return None

    query_lower = query.lower().strip()

    # CLARIFICATION - very short or ambiguous
    if len(query_lower) < 5 or query_lower in ["it", "that", "this", "yes", "no", "ok", "okay"]:
        logger.debug("Rule-based: CLARIFICATION (too short)")
        plan = DEFAULT_PLANS[QueryIntent.CLARIFICATION]
        return ExecutionPlan(**{**plan.__dict__, "reasoning": "Query too short or ambiguous"})

    # VISUAL AUDIT - verification keywords
    audit_keywords = ["check", "verify", "correct", "audit", "validate", "is it right",
                      "strikethrough", "crossed out", "handwritten", "calculation error"]
    if any(kw in query_lower for kw in audit_keywords):
        logger.debug("Rule-based: VISUAL_AUDIT (verification keywords)")
        plan = DEFAULT_PLANS[QueryIntent.VISUAL_AUDIT]
        return ExecutionPlan(**{**plan.__dict__, "reasoning": "Verification/audit keywords detected"})

    # NOTE: HYBRID_SEMANTIC_STRUCTURAL and complex queries are handled by LLM
    # Only simple patterns are rule-based for speed

    # EXHAUSTIVE - extract ALL
    exhaustive_patterns = [
        r'\ball\b.*\b(values?|numbers?|results?|data)\b',
        r'\bevery\b.*\b(value|number|result|entry)\b',
        r'\bcomplete\s+list\b',
        r'\blist\s+all\b',
        r'\bextract\s+all\b',
        r'\bshow\s+all\b',
        r'\bget\s+all\b',
    ]
    for pattern in exhaustive_patterns:
        if re.search(pattern, query_lower):
            logger.debug("Rule-based: EXHAUSTIVE (extract all)")
            plan = DEFAULT_PLANS[QueryIntent.EXHAUSTIVE]
            keywords = extract_keywords_simple(query)
            return ExecutionPlan(**{**plan.__dict__,
                                   "reasoning": "Extract all instances requested",
                                   "search_keywords": keywords})

    # COMPARISON - compare items
    comparison_patterns = [
        r'\bcompare\b',
        r'\bvs\.?\b',
        r'\bversus\b',
        r'\bdifference\s+between\b',
        r'\bhow\s+does\s+.+\s+differ\b',
    ]
    for pattern in comparison_patterns:
        match = re.search(pattern, query_lower)
        if match:
            targets = extract_comparison_targets(query)
            if targets and len(targets) >= 2:
                logger.debug(f"Rule-based: COMPARISON (targets: {targets})")
                plan = DEFAULT_PLANS[QueryIntent.COMPARISON]
                return ExecutionPlan(**{**plan.__dict__,
                                       "reasoning": f"Comparison query: {' vs '.join(targets)}",
                                       "comparison_targets": targets})

    # PRECISION - single value lookup patterns
    precision_patterns = [
        r'^what\s+is\s+the\s+\w+(\s+\w+)?\??$',  # "What is the batch number?"
        r'^show\s+me\s+the\s+\w+\??$',            # "Show me the pH value"
        r'^what\'?s\s+the\s+\w+\??$',             # "What's the date?"
    ]
    for pattern in precision_patterns:
        if re.search(pattern, query_lower):
            logger.debug("Rule-based: PRECISION (single value)")
            plan = DEFAULT_PLANS[QueryIntent.PRECISION]
            keywords = extract_keywords_simple(query)
            return ExecutionPlan(**{**plan.__dict__,
                                   "reasoning": "Single value lookup",
                                   "search_keywords": keywords})

    # Check for page filter in any query
    page_filter = detect_page_filter_simple(query)

    # No clear pattern - return None to use LLM
    return None


def extract_keywords_simple(query: str) -> List[str]:
    """Extract simple keywords from query for search."""
    # Remove common words
    stopwords = {'what', 'is', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'from',
                 'show', 'me', 'get', 'find', 'tell', 'about', 'please', 'can', 'you'}
    words = query.lower().split()
    keywords = [w.strip('?.,!') for w in words if w.lower() not in stopwords and len(w) > 2]
    return keywords[:5]


def extract_comparison_targets(query: str) -> List[str]:
    """Extract comparison targets from query."""
    patterns = [
        r'compare\s+(.+?)\s+(?:vs|versus|and|with|to)\s+(.+?)(?:\s|$|\.|\?)',
        r'difference\s+between\s+(.+?)\s+and\s+(.+?)(?:\s|$|\.|\?)',
        r'(.+?)\s+vs\.?\s+(.+?)(?:\s|$|\.|\?)',
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return [match.group(1).strip(), match.group(2).strip()]

    return []


def detect_page_filter_simple(query: str) -> Optional[int]:
    """Extract page number from query if mentioned."""
    patterns = [
        r'(?:on|from|in)\s+page\s+(\d+)',
        r'page\s+(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


# =============================================================================
# LLM-BASED CLASSIFICATION (Gemini 2.5 Flash)
# =============================================================================

def classify_intent_llm(query: str) -> ExecutionPlan:
    """
    Classify query intent using Gemini 2.5 Flash via Iliad API.
    Returns structured ExecutionPlan with all parameters.
    """
    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        prompt = INTENT_CLASSIFIER_PROMPT.format(query=query)

        payload = {
            "model": INTENT_CLASSIFIER_MODEL,
            "messages": [{
                "role": "user",
                "content": prompt
            }],
            "max_tokens": 1000,  # Increased from 500 to prevent truncation
            "temperature": 0.0,  # Deterministic for routing
            # Note: Structured output via response_format if supported
        }

        response = requests.post(
            f"{ILIAD_URL}/api/llm/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=INTENT_CLASSIFIER_TIMEOUT
        )

        if response.status_code != 200:
            logger.error(f"Intent classifier API error: {response.status_code} - {response.text}")
            return _fallback_plan(query)

        result = response.json()

        # Extract content from response
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Parse JSON from response (handle markdown code blocks)
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        plan_data = json.loads(json_str.strip())

        # Build ExecutionPlan from response
        plan = ExecutionPlan(
            intent=QueryIntent(plan_data["intent"]),
            bm25_limit=plan_data.get("bm25_limit", 20),
            vector_limit=plan_data.get("vector_limit", 20),
            rerank_limit=plan_data.get("rerank_limit", 15),
            alpha=plan_data.get("alpha", 0.5),
            agent_strategy=AgentStrategy(plan_data.get("agent_strategy", "parallel_5")),
            confidence=plan_data.get("confidence", 0.8),
            reasoning=plan_data.get("reasoning", "LLM classification"),
            comparison_targets=plan_data.get("comparison_targets"),
            search_keywords=plan_data.get("search_keywords"),
            page_filter=plan_data.get("page_filter"),
            sub_queries=plan_data.get("sub_queries")
        )

        logger.info(f"LLM classified as: {plan.intent.value} (confidence: {plan.confidence})")
        return plan

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON response: {e}")
        logger.error(f"Raw LLM content was: {content[:500] if 'content' in dir() else 'N/A'}")

        # Try to recover intent from partial/truncated JSON
        if 'content' in dir() and content:
            recovered_plan = _recover_intent_from_partial_json(content, query)
            if recovered_plan:
                logger.info(f"Recovered intent from partial JSON: {recovered_plan.intent.value}")
                return recovered_plan

        return _fallback_plan(query)
    except requests.exceptions.Timeout:
        logger.warning("Intent classifier timeout, using fallback")
        return _fallback_plan(query)
    except Exception as e:
        logger.error(f"Intent classifier error: {e}")
        return _fallback_plan(query)


def _recover_intent_from_partial_json(content: str, query: str) -> Optional[ExecutionPlan]:
    """
    Try to recover intent from truncated/partial JSON response.

    When LLM returns truncated JSON like:
    {"intent": "hybrid_semantic_structural",

    We can still extract the intent and use default parameters.
    """
    # List of valid intents to search for
    valid_intents = [
        "hybrid_semantic_structural",
        "exhaustive",
        "cross_reference",
        "exploratory",
        "precision",
        "comparison",
        "visual_audit",
        "clarification"
    ]

    content_lower = content.lower()

    for intent_str in valid_intents:
        if f'"{intent_str}"' in content_lower or f"'{intent_str}'" in content_lower:
            try:
                intent = QueryIntent(intent_str)
                # Use default plan for this intent
                if intent in DEFAULT_PLANS:
                    plan = DEFAULT_PLANS[intent]
                    keywords = extract_keywords_simple(query)
                    page_filter = detect_page_filter_simple(query)

                    # Override to SINGLE agent if specific page is mentioned
                    agent_strategy = plan.agent_strategy
                    if page_filter is not None:
                        agent_strategy = AgentStrategy.SINGLE
                        logger.info(f"Page filter detected ({page_filter}), using SINGLE agent strategy")

                    return ExecutionPlan(
                        intent=plan.intent,
                        bm25_limit=plan.bm25_limit,
                        vector_limit=plan.vector_limit,
                        rerank_limit=plan.rerank_limit,
                        alpha=plan.alpha,
                        agent_strategy=agent_strategy,
                        confidence=0.7,  # Lower confidence since recovered
                        reasoning=f"Recovered from partial JSON - {intent_str}",
                        search_keywords=keywords,
                        page_filter=page_filter
                    )
            except ValueError:
                continue

    return None


def _fallback_plan(query: str) -> ExecutionPlan:
    """Fallback to exploratory if classification fails."""
    keywords = extract_keywords_simple(query)
    page_filter = detect_page_filter_simple(query)

    # Use DEFAULT_PLANS for consistent parameters
    default = DEFAULT_PLANS[QueryIntent.EXPLORATORY]

    # Override to SINGLE agent if specific page is mentioned
    agent_strategy = default.agent_strategy
    if page_filter is not None:
        agent_strategy = AgentStrategy.SINGLE
        logger.info(f"Fallback with page filter ({page_filter}), using SINGLE agent strategy")

    return ExecutionPlan(
        intent=QueryIntent.EXPLORATORY,
        bm25_limit=default.bm25_limit,
        vector_limit=default.vector_limit,
        rerank_limit=default.rerank_limit,
        alpha=default.alpha,
        agent_strategy=agent_strategy,
        confidence=0.5,
        reasoning="Fallback due to classification error",
        search_keywords=keywords,
        page_filter=page_filter
    )


# =============================================================================
# MAIN CLASSIFICATION FUNCTION
# =============================================================================

def classify_with_plan(query: str, use_llm: bool = True) -> ExecutionPlan:
    """
    Main entry point for intent classification with execution plan.

    Flow:
    1. Try quick rule-based classification (handles ~60% of queries)
    2. If no match, use Gemini Flash LLM classification
    3. Return structured ExecutionPlan with all routing parameters

    Args:
        query: User's query string
        use_llm: Whether to use LLM if rule-based fails (default: True)

    Returns:
        ExecutionPlan with intent and all execution parameters
    """
    logger.info(f"Classifying query: '{query[:50]}...'")

    # Step 1: Try rule-based classification
    plan = classify_intent_rule_based(query)

    if plan:
        logger.info(f"Rule-based classification: {plan.intent.value}")
        # Add page filter if detected
        if plan.page_filter is None:
            plan.page_filter = detect_page_filter_simple(query)
        return plan

    # Step 2: Use LLM classification
    if use_llm:
        plan = classify_intent_llm(query)
        logger.info(f"LLM classification: {plan.intent.value}")
        return plan

    # Step 3: Fallback
    return _fallback_plan(query)


# =============================================================================
# LEGACY COMPATIBILITY FUNCTIONS
# =============================================================================

def classify_intent_sync(query: str, use_llm_first: bool = True) -> QueryIntent:
    """
    Legacy synchronous version of intent classification.
    Returns only the QueryIntent enum for backward compatibility.

    DEPRECATED: Use classify_with_plan() instead for full execution plan.
    """
    plan = classify_with_plan(query, use_llm=use_llm_first)

    # Map new intents to legacy intents for backward compatibility
    intent_mapping = {
        QueryIntent.PRECISION: QueryIntent.VECTOR_ONLY,
        QueryIntent.EXPLORATORY: QueryIntent.VECTOR_ONLY,
        QueryIntent.EXHAUSTIVE: QueryIntent.VECTOR_ONLY,
        QueryIntent.COMPARISON: QueryIntent.VECTOR_ONLY,
    }

    return intent_mapping.get(plan.intent, plan.intent)


async def classify_intent(query: str, use_llm_fallback: bool = True) -> QueryIntent:
    """
    Legacy async version of intent classification.

    DEPRECATED: Use classify_with_plan() instead.
    """
    return classify_intent_sync(query, use_llm_first=use_llm_fallback)


def get_execution_plan(query: str) -> ExecutionPlan:
    """
    Get full execution plan for a query.
    Alias for classify_with_plan() for clarity.
    """
    return classify_with_plan(query)


def get_intent_description(intent: QueryIntent) -> str:
    """Get human-readable description of an intent."""
    descriptions = {
        QueryIntent.PRECISION: "Single value lookup (fast path)",
        QueryIntent.EXPLORATORY: "General Q&A with parallel agents",
        QueryIntent.EXHAUSTIVE: "Extract ALL instances (maximum recall)",
        QueryIntent.COMPARISON: "Compare two or more items",
        QueryIntent.STRUCTURAL: "Document structure query (Neo4j)",
        QueryIntent.HYBRID_SEMANTIC_STRUCTURAL: "Column extraction + export (Weaviate + Neo4j)",
        QueryIntent.EXTRACTION: "Full data export (Neo4j bulk)",
        QueryIntent.VISUAL_AUDIT: "Visual verification (Gemini Vision)",
        QueryIntent.CROSS_REFERENCE: "Locate + extract across pages (cross-reference)",
        QueryIntent.CLARIFICATION: "Query needs clarification",
        QueryIntent.VECTOR_ONLY: "Vector search (legacy)",
    }
    return descriptions.get(intent, "Unknown intent")


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Intent Classifier Test - Phase 8 (Gemini 2.5 Flash)")
    print("=" * 60)
    print(f"Model: {INTENT_CLASSIFIER_MODEL}")
    print(f"Endpoint: {ILIAD_URL}/api/llm/v1/chat/completions")
    print()

    test_queries = [
        # Precision
        "What is the batch number?",
        "Show me the pH value",

        # Exploratory
        "Tell me about the test results",
        "What specifications are listed?",

        # Exhaustive
        "List ALL batch numbers from the document",
        "Show every test result",
        "Extract all concentration values",

        # Comparison
        "Compare batch 123 vs batch 456",
        "What's the difference between test A and B?",

        # Structural
        "What page has the specifications?",
        "How many tables are there?",

        # Hybrid/Export
        "Export concentration data to Excel",
        "Download all test results as CSV",

        # Visual Audit
        "Is this calculation correct?",
        "Verify step 7.3",
        "Check for errors on page 5",

        # Clarification
        "it",
        "that",
    ]

    print("Testing queries...")
    print("-" * 60)

    for query in test_queries:
        plan = classify_with_plan(query, use_llm=False)  # Rule-based only for test
        print(f"\nQuery: {query}")
        print(f"  Intent: {plan.intent.value}")
        print(f"  Strategy: {plan.agent_strategy.value}")
        print(f"  Params: bm25={plan.bm25_limit}, vec={plan.vector_limit}, rerank={plan.rerank_limit}, alpha={plan.alpha}")
        if plan.comparison_targets:
            print(f"  Targets: {plan.comparison_targets}")
        print(f"  Reason: {plan.reasoning}")
