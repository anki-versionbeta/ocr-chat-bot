# Intent Classifier Upgrade Plan: Dynamic Query Routing with Gemini Flash

**Document Version:** 2.0
**Created:** 2026-02-26
**Author:** Claude Code Analysis
**Status:** Implementation Ready

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Analysis](#current-architecture-analysis)
3. [Proposed Architecture](#proposed-architecture)
4. [Intent Definitions](#intent-definitions)
5. [Implementation Plan](#implementation-plan)
6. [Code Implementation](#code-implementation)
7. [Performance Expectations](#performance-expectations)
8. [Testing Strategy](#testing-strategy)
9. [Migration Guide](#migration-guide)

---

## Executive Summary

### Problem Statement

The current COA RAG v2 system uses a **one-size-fits-all approach** for vector queries:

- ALL `vector_only` queries (90% of traffic) trigger 5 parallel agents
- Simple lookups like "What is the batch number?" waste compute on 4 agents that return "not found"
- Complex extraction queries may not retrieve enough chunks (only 25)

### Solution

Implement a **Dynamic Query Router** using Gemini 2.5 Flash that:

1. Classifies queries into 7 distinct intents
2. Outputs a structured **Execution Plan** with dynamic parameters
3. Routes to optimized handlers for each intent type

### Expected Improvements

| Metric                    | Current   | After Implementation |
| ------------------------- | --------- | -------------------- |
| Precision Query Latency   | 2-3s      | **0.8-1.2s** (-60%)  |
| Precision Query LLM Calls | 5-6       | **2** (-66%)         |
| Exhaustive Query Recall   | 25 chunks | **40 chunks** (+60%) |
| Token Usage (precision)   | ~4000     | **~1500** (-62%)     |
| Cache-able Responses      | 15-25%    | **30-40%**           |

---

## Current Architecture Analysis

### Existing Intent System (6 Intents)

| Intent                       | % Traffic | Current Handler              |
| ---------------------------- | --------- | ---------------------------- |
| `vector_only`                | 90%       | 5 parallel agents, 25 chunks |
| `structural`                 | 5%        | Neo4j templates              |
| `hybrid_semantic_structural` | 3%        | Multi-Agent Cypher           |
| `extraction`                 | 2%        | Neo4j bulk export            |
| `visual_audit`               | 1%        | Gemini Vision                |
| `clarification`              | <1%       | Return clarification request |

### Issues Identified

1. **vector_only is too broad** - Handles everything from "What is batch number?" to "Tell me about all test results"
2. **5 parallel agents always run** - Wasteful for simple lookups
3. **Fixed parameters** - No dynamic adjustment based on query complexity
4. **No comparison support** - Common in COA documents ("Compare batch X vs Y")

---

## Proposed Architecture

### New Intent System (7 Intents)

```
┌─────────────────────────────────────────────────────────────────┐
│                    INTENT CLASSIFICATION                         │
│                   (Gemini 2.0 Flash + JSON Schema)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
    ┌───────────────────────┼───────────────────────────────────┐
    │                       │                                   │
    ▼                       ▼                                   ▼
┌─────────┐          ┌─────────────┐                    ┌─────────────┐
│ VECTOR  │          │ STRUCTURAL  │                    │   VISUAL    │
│ QUERIES │          │   (Neo4j)   │                    │   AUDIT     │
└────┬────┘          └─────────────┘                    └─────────────┘
     │                (Keep as-is)                      (Keep as-is)
     │
     ├────────────────┬────────────────┬────────────────┐
     ▼                ▼                ▼                ▼
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│PRECISION│    │EXPLORATORY│    │EXHAUSTIVE │    │COMPARISON │
│  (NEW)  │    │ (CURRENT) │    │   (NEW)   │    │   (NEW)   │
└─────────┘    └───────────┘    └───────────┘    └───────────┘
Single Agent   Parallel 5      Parallel 8       Dual-Path
0.8-1.2s       2-3s            4-5s             2-3s
```

### Why Gemini 2.5 Flash?

| Feature                 | Claude Haiku    | Gemini 2.5 Flash     |
| ----------------------- | --------------- | -------------------- |
| Latency                 | ~300-500ms      | **~150-250ms**       |
| JSON Schema Enforcement | Text-based      | **Native support**   |
| Cost                    | $0.25/1M tokens | **$0.075/1M tokens** |
| Structured Output       | Sometimes fails | **100% reliable**    |

**Note:** Model name confirmed via API call: `gemini-2.5-flash` (Feb 2026)

---

## Intent Definitions

### Complete Intent Matrix

| Intent              | Trigger Keywords              | BM25 | Vector | Rerank | Alpha | Strategy           | Latency  |
| ------------------- | ----------------------------- | ---- | ------ | ------ | ----- | ------------------ | -------- |
| `precision`         | Single value lookup           | 10   | 10     | 3-5    | 0.5   | single             | 0.8-1.2s |
| `exploratory`       | General Q&A                   | 20   | 20     | 15-20  | 0.7   | parallel_5         | 2-3s     |
| `exhaustive`        | "all", "every", "complete"    | 50   | 50     | 30-40  | 0.3   | parallel_8         | 4-6s     |
| `comparison`        | "compare", "vs", "difference" | 30   | 30     | 20     | 0.5   | dual_path          | 2-3s     |
| `structural`        | "page", "table", "how many"   | 0    | 0      | 0      | 0     | neo4j_template     | 0.5-1s   |
| `hybrid_structural` | "export", "excel", "column"   | 20   | 20     | 15     | 0.5   | multi_agent_cypher | 3-5s     |
| `visual_audit`      | "check", "verify", "audit"    | 30   | 30     | 20     | 0.5   | vision             | 8-15s    |

### Detailed Intent Descriptions

#### 1. PRECISION (NEW - Fast Path)

**Purpose:** Single specific value lookup
**Examples:**

- "What is the batch number?"
- "When was this signed?"
- "What is the pH value?"
- "Show me the expiration date"

**Execution Plan:**

```json
{
  "intent": "precision",
  "bm25_limit": 10,
  "vector_limit": 10,
  "rerank_limit": 5,
  "alpha": 0.5,
  "agent_strategy": "single"
}
```

#### 2. EXPLORATORY (Current vector_only behavior)

**Purpose:** General Q&A, multiple related values
**Examples:**

- "Tell me about the test results"
- "What specifications are listed?"
- "Describe the product characteristics"

**Execution Plan:**

```json
{
  "intent": "exploratory",
  "bm25_limit": 20,
  "vector_limit": 20,
  "rerank_limit": 15,
  "alpha": 0.7,
  "agent_strategy": "parallel_5"
}
```

#### 3. EXHAUSTIVE (NEW - Heavy Lift)

**Purpose:** Extract ALL instances across document
**Examples:**

- "List ALL batch numbers from every page"
- "Show every test result in the document"
- "Extract all concentration values"

**Execution Plan:**

```json
{
  "intent": "exhaustive",
  "bm25_limit": 50,
  "vector_limit": 50,
  "rerank_limit": 35,
  "alpha": 0.3,
  "agent_strategy": "parallel_8"
}
```

#### 4. COMPARISON (NEW)

**Purpose:** Compare two or more items
**Examples:**

- "Compare batch 123 vs batch 456"
- "What's the difference between test A and B?"
- "How does specification X differ from Y?"

**Execution Plan:**

```json
{
  "intent": "comparison",
  "bm25_limit": 30,
  "vector_limit": 30,
  "rerank_limit": 20,
  "alpha": 0.5,
  "agent_strategy": "dual_path",
  "comparison_targets": ["batch 123", "batch 456"]
}
```

---

## Implementation Plan

### Phase 1: Intent Classifier (Day 1 - Morning)

**Tasks:**

- [ ] Create new `GeminiFlashIntentClassifier` class
- [ ] Define JSON schema for structured output
- [ ] Implement quick rule-based classification
- [ ] Implement LLM-based classification with schema
- [ ] Add fallback handling

**Files to modify:**

- `services/intent_classifier.py` (complete rewrite)

### Phase 2: RAG Orchestrator Routing (Day 1 - Afternoon)

**Tasks:**

- [ ] Add execution plan parsing to orchestrator
- [ ] Create handler routing map
- [ ] Implement `_process_precision_query`
- [ ] Update cache logic for new intents

**Files to modify:**

- `services/rag_orchestrator.py`

### Phase 3: New Query Handlers (Day 2)

**Tasks:**

- [ ] Implement `_process_exhaustive_query`
- [ ] Implement `_process_comparison_query`
- [ ] Add `_synthesize_comparison_answer`
- [ ] Add deduplication for exhaustive results

**Files to modify:**

- `services/rag_orchestrator.py`

### Phase 4: Parallel Agent Updates (Day 3)

**Tasks:**

- [ ] Make `max_agents` configurable
- [ ] Add `_single_agent_fast_path`
- [ ] Update merge logic for variable agent counts

**Files to modify:**

- `services/parallel_agent_graph.py`

### Phase 5: Testing & Validation (Day 3-4)

**Tasks:**

- [ ] Unit tests for intent classification
- [ ] Integration tests for each handler
- [ ] Performance benchmarking
- [ ] A/B testing against current system

---

## Code Implementation

### File 1: `services/intent_classifier.py`

```python
import json
import httpx
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================================
# INTENT DEFINITIONS
# ============================================================================

class QueryIntent(str, Enum):
    PRECISION = "precision"
    EXPLORATORY = "exploratory"
    EXHAUSTIVE = "exhaustive"
    COMPARISON = "comparison"
    STRUCTURAL = "structural"
    HYBRID_STRUCTURAL = "hybrid_structural"
    VISUAL_AUDIT = "visual_audit"
    CLARIFICATION = "clarification"

class AgentStrategy(str, Enum):
    SINGLE = "single"
    PARALLEL_5 = "parallel_5"
    PARALLEL_8 = "parallel_8"
    DUAL_PATH = "dual_path"
    NEO4J_TEMPLATE = "neo4j_template"
    MULTI_AGENT_CYPHER = "multi_agent_cypher"
    VISION = "vision"

@dataclass
class ExecutionPlan:
    """Structured execution plan from intent classifier"""
    intent: QueryIntent
    bm25_limit: int
    vector_limit: int
    rerank_limit: int
    alpha: float
    agent_strategy: AgentStrategy
    confidence: float
    reasoning: str
    comparison_targets: Optional[List[str]] = None
    search_keywords: Optional[List[str]] = None
    page_filter: Optional[int] = None

# ============================================================================
# JSON SCHEMA FOR STRUCTURED OUTPUT (CRITICAL!)
# ============================================================================

EXECUTION_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["precision", "exploratory", "exhaustive", "comparison",
                     "structural", "hybrid_structural", "visual_audit", "clarification"]
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
        }
    },
    "required": ["intent", "bm25_limit", "vector_limit", "rerank_limit",
                 "alpha", "agent_strategy", "confidence", "reasoning"]
}

# ============================================================================
# INTENT CLASSIFICATION PROMPT
# ============================================================================

INTENT_CLASSIFIER_PROMPT = """You are an intelligent query router for a document Q&A system processing Certificate of Analysis (COA) documents.

Analyze the user's query and determine the optimal execution plan.

## INTENT DEFINITIONS

### 1. precision
- **When**: Single specific value lookup (batch number, date, one cell value)
- **Examples**: "What is the batch number?", "When was this signed?", "What is the pH value?"
- **Parameters**: bm25_limit=10, vector_limit=10, rerank_limit=5, alpha=0.5, agent_strategy="single"

### 2. exploratory
- **When**: General Q&A, descriptions, multiple related values
- **Examples**: "Tell me about the test results", "What specifications are listed?"
- **Parameters**: bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.7, agent_strategy="parallel_5"

### 3. exhaustive
- **When**: Extract ALL instances across entire document (keywords: "all", "every", "complete list")
- **Examples**: "List ALL batch numbers", "Show every test result", "Extract all concentrations"
- **Parameters**: bm25_limit=50, vector_limit=50, rerank_limit=35, alpha=0.3, agent_strategy="parallel_8"

### 4. comparison
- **When**: Compare two or more items (keywords: "compare", "difference", "vs", "versus")
- **Examples**: "Compare batch 123 vs 456", "What's the difference between test A and B?"
- **Parameters**: bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5, agent_strategy="dual_path"
- **IMPORTANT**: Extract comparison items into comparison_targets array

### 5. structural
- **When**: Document navigation, page/table info (keywords: "page", "table", "how many")
- **Examples**: "What page has specifications?", "How many tables?", "Show structure"
- **Parameters**: bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0, agent_strategy="neo4j_template"

### 6. hybrid_structural
- **When**: Column/row extraction with export (keywords: "extract column", "export", "Excel")
- **Examples**: "Extract all concentration values to Excel", "Get column 3 from all pages"
- **Parameters**: bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.5, agent_strategy="multi_agent_cypher"

### 7. visual_audit
- **When**: Verification, error checking (keywords: "check", "verify", "correct", "audit")
- **Examples**: "Is this calculation correct?", "Verify step 7.3", "Check for errors"
- **Parameters**: bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5, agent_strategy="vision"

### 8. clarification
- **When**: Query is too vague or ambiguous
- **Examples**: "it", "that", "yes", "ok", "more"
- **Parameters**: bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0, agent_strategy="single"

## ALPHA VALUE GUIDE
- 0.3 = Favor BM25 (keyword matching) - Best for exact value extraction
- 0.5 = Balanced - Best for specific lookups and comparisons
- 0.7 = Favor semantic - Best for conceptual/exploratory queries

## PAGE FILTER
If user mentions a specific page (e.g., "on page 5"), extract the page number.

## SEARCH KEYWORDS
Extract 2-5 key terms from the query to search in the document.

Query: {query}
"""

# ============================================================================
# GEMINI FLASH CLASSIFIER
# ============================================================================

class GeminiFlashIntentClassifier:
    """Intent classifier using Gemini 2.0 Flash with structured output"""

    def __init__(self, iliad_url: str, api_key: str):
        self.iliad_url = iliad_url
        self.api_key = api_key
        self.model = "gemini-2.5-flash"
        self.timeout = 10.0

    async def classify_with_plan(self, query: str) -> ExecutionPlan:
        """Classify query and return structured execution plan."""

        # Step 1: Quick rule-based classification
        quick_result = self._quick_classify(query)
        if quick_result:
            logger.info(f"Quick classification: {quick_result.intent}")
            return quick_result

        # Step 2: LLM-based classification
        try:
            plan = await self._llm_classify(query)
            logger.info(f"LLM classification: {plan.intent} (confidence: {plan.confidence})")
            return plan
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._fallback_plan(query)

    def _quick_classify(self, query: str) -> Optional[ExecutionPlan]:
        """Rule-based fast path for obvious intents"""
        query_lower = query.lower().strip()

        # Clarification
        if len(query_lower) < 5 or query_lower in ["it", "that", "this", "yes", "no", "ok"]:
            return ExecutionPlan(
                intent=QueryIntent.CLARIFICATION,
                bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0,
                agent_strategy=AgentStrategy.SINGLE,
                confidence=0.95,
                reasoning="Query too short or ambiguous"
            )

        # Visual audit
        audit_keywords = ["check", "verify", "correct", "audit", "validate", "is it right"]
        if any(kw in query_lower for kw in audit_keywords):
            return ExecutionPlan(
                intent=QueryIntent.VISUAL_AUDIT,
                bm25_limit=30, vector_limit=30, rerank_limit=20, alpha=0.5,
                agent_strategy=AgentStrategy.VISION,
                confidence=0.90,
                reasoning="Verification/audit keywords detected"
            )

        # Export
        if "export" in query_lower or "excel" in query_lower or "csv" in query_lower:
            return ExecutionPlan(
                intent=QueryIntent.HYBRID_STRUCTURAL,
                bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.5,
                agent_strategy=AgentStrategy.MULTI_AGENT_CYPHER,
                confidence=0.90,
                reasoning="Export keywords detected"
            )

        # Structural
        structural_patterns = ["how many table", "what page", "document structure", "which page"]
        if any(p in query_lower for p in structural_patterns):
            return ExecutionPlan(
                intent=QueryIntent.STRUCTURAL,
                bm25_limit=0, vector_limit=0, rerank_limit=0, alpha=0,
                agent_strategy=AgentStrategy.NEO4J_TEMPLATE,
                confidence=0.90,
                reasoning="Structural navigation query"
            )

        return None

    async def _llm_classify(self, query: str) -> ExecutionPlan:
        """LLM classification with structured JSON output"""

        prompt = INTENT_CLASSIFIER_PROMPT.format(query=query)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key
        }

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "execution_plan",
                    "strict": True,
                    "schema": EXECUTION_PLAN_SCHEMA
                }
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.iliad_url}/api/llm/v1/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]
            plan_data = json.loads(content)

            return ExecutionPlan(
                intent=QueryIntent(plan_data["intent"]),
                bm25_limit=plan_data["bm25_limit"],
                vector_limit=plan_data["vector_limit"],
                rerank_limit=plan_data["rerank_limit"],
                alpha=plan_data["alpha"],
                agent_strategy=AgentStrategy(plan_data["agent_strategy"]),
                confidence=plan_data["confidence"],
                reasoning=plan_data["reasoning"],
                comparison_targets=plan_data.get("comparison_targets"),
                search_keywords=plan_data.get("search_keywords"),
                page_filter=plan_data.get("page_filter")
            )

    def _fallback_plan(self, query: str) -> ExecutionPlan:
        """Fallback to exploratory if classification fails"""
        return ExecutionPlan(
            intent=QueryIntent.EXPLORATORY,
            bm25_limit=20, vector_limit=20, rerank_limit=15, alpha=0.7,
            agent_strategy=AgentStrategy.PARALLEL_5,
            confidence=0.5,
            reasoning="Fallback due to classification error",
            search_keywords=query.split()[:5]
        )

    def classify_with_plan_sync(self, query: str) -> ExecutionPlan:
        """Synchronous version for non-async contexts"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.classify_with_plan(query))
                return future.result(timeout=15)
        except RuntimeError:
            return asyncio.run(self.classify_with_plan(query))
```

### File 2: RAG Orchestrator Updates

Add to `services/rag_orchestrator.py`:

```python
from services.intent_classifier import (
    GeminiFlashIntentClassifier,
    ExecutionPlan,
    QueryIntent,
    AgentStrategy
)

class RAGOrchestrator:
    def __init__(self, ...):
        # ... existing init ...

        # NEW: Gemini Flash Intent Classifier
        self.intent_classifier = GeminiFlashIntentClassifier(
            iliad_url=ILIAD_URL,
            api_key=REDACTED
        )

    async def process_query(self, query: str, process_id: str, filename: str) -> dict:
        """Main entry point with dynamic routing"""

        # Get execution plan
        plan = await self.intent_classifier.classify_with_plan(query)
        logger.info(f"Execution plan: {plan.intent} | strategy: {plan.agent_strategy}")

        # Check cache
        if plan.intent not in [QueryIntent.STRUCTURAL, QueryIntent.CLARIFICATION]:
            cached = await self._check_cache(query, process_id)
            if cached:
                return cached

        # Route to handler
        handler_map = {
            QueryIntent.PRECISION: self._process_precision_query,
            QueryIntent.EXPLORATORY: self._process_exploratory_query,
            QueryIntent.EXHAUSTIVE: self._process_exhaustive_query,
            QueryIntent.COMPARISON: self._process_comparison_query,
            QueryIntent.STRUCTURAL: self._process_structural_query,
            QueryIntent.HYBRID_STRUCTURAL: self._process_hybrid_structural_query,
            QueryIntent.VISUAL_AUDIT: self._process_visual_audit_query,
            QueryIntent.CLARIFICATION: self._process_clarification,
        }

        handler = handler_map.get(plan.intent, self._process_exploratory_query)
        result = await handler(query, process_id, filename, plan)

        # Cache result
        if plan.intent not in [QueryIntent.STRUCTURAL, QueryIntent.CLARIFICATION]:
            await self._update_cache(query, process_id, result)

        return result

    async def _process_precision_query(self, query, process_id, filename, plan):
        """Fast path for single-value lookups"""

        chunks = await self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=plan.alpha,
            page_filter=plan.page_filter
        )

        if not chunks:
            return self._empty_response("precision")

        reranked = self.reranker.rerank(query, chunks, top_k=plan.rerank_limit)

        # SINGLE AGENT - no parallel overhead
        answer_data = await synthesize_answer_sync(
            query=query,
            chunks=reranked[:5],
            filename=filename
        )

        references = extract_references(answer_data, reranked)

        return {
            "success": True,
            "answer": answer_data.get("answer", ""),
            "references": references,
            "confidence": answer_data.get("confidence", 0.8),
            "query_type": "precision",
            "intent": plan.intent.value,
            "chunks_used": len(reranked),
            "latency_optimized": True
        }

    async def _process_exhaustive_query(self, query, process_id, filename, plan):
        """Heavy path for complete extraction"""

        chunks = await self.weaviate.search_chunks(
            query=query,
            process_id=process_id,
            limit=plan.bm25_limit,
            alpha=plan.alpha,
            page_filter=plan.page_filter
        )

        if not chunks:
            return self._empty_response("exhaustive")

        reranked = self.reranker.rerank(query, chunks, top_k=plan.rerank_limit)

        # 8 parallel agents for maximum coverage
        result = await run_parallel_agents_sync(
            query=query,
            chunks=reranked[:40],
            filename=filename,
            max_agents=8,
            chunks_per_agent=5
        )

        answer = self._deduplicate_extracted_items(result["final_answer"])

        return {
            "success": True,
            "answer": answer,
            "references": result["final_references"],
            "confidence": result["final_confidence"],
            "query_type": "exhaustive",
            "intent": plan.intent.value,
            "chunks_used": len(reranked),
            "items_extracted": self._count_extracted_items(answer)
        }

    async def _process_comparison_query(self, query, process_id, filename, plan):
        """Dual-path search for comparison queries"""

        targets = plan.comparison_targets or []

        if not targets:
            targets = self._extract_comparison_targets_fallback(query)

        if len(targets) < 2:
            return await self._process_exploratory_query(query, process_id, filename, plan)

        # Parallel search for each target
        all_chunks = []
        chunks_per_target = plan.bm25_limit // len(targets)

        search_tasks = [
            self.weaviate.search_chunks(
                query=target,
                process_id=process_id,
                limit=chunks_per_target,
                alpha=plan.alpha
            )
            for target in targets
        ]

        target_results = await asyncio.gather(*search_tasks)

        for i, (target, chunks) in enumerate(zip(targets, target_results)):
            for chunk in chunks:
                chunk["comparison_target"] = target
            all_chunks.extend(chunks)

        reranked = self.reranker.rerank(query, all_chunks, top_k=plan.rerank_limit)

        answer_data = await self._synthesize_comparison_answer(
            query, reranked, targets, filename
        )

        return {
            "success": True,
            "answer": answer_data.get("answer", ""),
            "references": extract_references(answer_data, reranked),
            "confidence": answer_data.get("confidence", 0.8),
            "query_type": "comparison",
            "compared_items": targets
        }
```

### File 3: Parallel Agent Graph Updates

Add to `services/parallel_agent_graph.py`:

```python
def run_parallel_agents_sync(
    query: str,
    chunks: list,
    filename: str,
    max_agents: int = 5,
    chunks_per_agent: int = 5
) -> dict:
    """Configurable parallel agent execution"""

    # Fast path: Single agent
    if max_agents == 1 or len(chunks) <= chunks_per_agent:
        return _single_agent_fast_path(query, chunks[:chunks_per_agent], filename)

    # Calculate groups
    num_chunks = len(chunks)
    num_groups = min(max_agents, (num_chunks + chunks_per_agent - 1) // chunks_per_agent)

    # Split chunks
    chunk_groups = []
    for i in range(0, num_chunks, chunks_per_agent):
        group = chunks[i:i + chunks_per_agent]
        if group:
            chunk_groups.append(group)
        if len(chunk_groups) >= max_agents:
            break

    # Run parallel
    agent_results = []
    with ThreadPoolExecutor(max_workers=num_groups) as executor:
        futures = [
            executor.submit(process_agent_group, query, group, filename, idx)
            for idx, group in enumerate(chunk_groups)
        ]

        for future in futures:
            try:
                result = future.result(timeout=30)
                agent_results.append(result)
            except Exception as e:
                logger.error(f"Agent failed: {e}")
                agent_results.append({"answer": "", "cell_ids": [], "confidence": 0})

    return merge_agent_results(agent_results, query, chunks)


def _single_agent_fast_path(query: str, chunks: list, filename: str) -> dict:
    """Fast path skipping parallel overhead"""

    if not chunks:
        return {
            "final_answer": "No relevant information found.",
            "final_references": [],
            "final_confidence": 0.0
        }

    answer_data = synthesize_answer_sync(query=query, chunks=chunks, filename=filename)

    grounding_map = build_grounding_map(chunks)
    cell_ids = answer_data.get("cell_ids", [])
    references = []

    for cell_id in cell_ids:
        if cell_id in grounding_map:
            ref_data = grounding_map[cell_id]
            references.append({
                "page": ref_data.get("page"),
                "bbox": ref_data.get("bbox"),
                "cell_id": cell_id,
                "text": ref_data.get("text", "")[:100],
                "type": "cell"
            })

    return {
        "final_answer": answer_data.get("answer", ""),
        "final_references": references,
        "final_confidence": answer_data.get("confidence", 0.7)
    }
```

---

## Performance Expectations

### Latency Improvements

| Query Type                   | Before | After    | Improvement          |
| ---------------------------- | ------ | -------- | -------------------- |
| "What is the batch number?"  | 2-3s   | 0.8-1.2s | **-60%**             |
| "Tell me about test results" | 2-3s   | 2-2.5s   | -15%                 |
| "List ALL batch numbers"     | 3-4s   | 4-5s     | +25% (better recall) |
| "Compare batch X vs Y"       | N/A    | 2-3s     | New capability       |

### LLM Call Reduction

| Query Type  | Before    | After     | Reduction            |
| ----------- | --------- | --------- | -------------------- |
| Precision   | 5-6 calls | 2 calls   | **-66%**             |
| Exploratory | 5-6 calls | 5-6 calls | 0%                   |
| Exhaustive  | 5-6 calls | 8-9 calls | +50% (better recall) |

### Token Usage

| Query Type  | Before       | After         | Savings              |
| ----------- | ------------ | ------------- | -------------------- |
| Precision   | ~4000 tokens | ~1500 tokens  | **-62%**             |
| Exploratory | ~8000 tokens | ~8000 tokens  | 0%                   |
| Exhaustive  | ~8000 tokens | ~12000 tokens | +50% (better recall) |

---

## Testing Strategy

### Unit Tests

```python
# test_intent_classifier.py

import pytest
from services.intent_classifier import GeminiFlashIntentClassifier, QueryIntent

@pytest.fixture
def classifier():
    return GeminiFlashIntentClassifier(
        iliad_url="http://test",
        api_key=REDACTED
    )

class TestQuickClassification:
    def test_clarification_short_query(self, classifier):
        plan = classifier._quick_classify("it")
        assert plan.intent == QueryIntent.CLARIFICATION

    def test_visual_audit_check(self, classifier):
        plan = classifier._quick_classify("check if this is correct")
        assert plan.intent == QueryIntent.VISUAL_AUDIT

    def test_export_excel(self, classifier):
        plan = classifier._quick_classify("export to excel")
        assert plan.intent == QueryIntent.HYBRID_STRUCTURAL

    def test_structural_page(self, classifier):
        plan = classifier._quick_classify("what page has specifications")
        assert plan.intent == QueryIntent.STRUCTURAL

class TestIntentRouting:
    @pytest.mark.asyncio
    async def test_precision_single_value(self, classifier):
        plan = await classifier.classify_with_plan("What is the batch number?")
        assert plan.intent == QueryIntent.PRECISION
        assert plan.agent_strategy.value == "single"

    @pytest.mark.asyncio
    async def test_exhaustive_all_values(self, classifier):
        plan = await classifier.classify_with_plan("List ALL test results")
        assert plan.intent == QueryIntent.EXHAUSTIVE
        assert plan.agent_strategy.value == "parallel_8"

    @pytest.mark.asyncio
    async def test_comparison_vs(self, classifier):
        plan = await classifier.classify_with_plan("Compare batch 123 vs 456")
        assert plan.intent == QueryIntent.COMPARISON
        assert "123" in plan.comparison_targets
        assert "456" in plan.comparison_targets
```

### Integration Tests

```python
# test_intent_handlers.py

@pytest.mark.asyncio
async def test_precision_handler_fast(orchestrator, sample_process_id):
    """Precision queries should complete in <1.5s"""
    import time

    start = time.time()
    result = await orchestrator.process_query(
        "What is the batch number?",
        sample_process_id,
        "test.pdf"
    )
    elapsed = time.time() - start

    assert elapsed < 1.5
    assert result["query_type"] == "precision"
    assert result["latency_optimized"] == True

@pytest.mark.asyncio
async def test_exhaustive_handler_recall(orchestrator, sample_process_id):
    """Exhaustive queries should find more items"""
    result = await orchestrator.process_query(
        "List ALL concentration values",
        sample_process_id,
        "test.pdf"
    )

    assert result["query_type"] == "exhaustive"
    assert result["chunks_used"] >= 30
```

---

## Migration Guide

### Step 1: Deploy New Classifier (No Breaking Changes)

```python
# Add feature flag
USE_NEW_INTENT_CLASSIFIER = os.getenv("USE_NEW_INTENT_CLASSIFIER", "false") == "true"

# In orchestrator
if USE_NEW_INTENT_CLASSIFIER:
    plan = await self.gemini_intent_classifier.classify_with_plan(query)
else:
    intent = await self.legacy_intent_classifier.classify(query)
```

### Step 2: A/B Test

- Route 10% of traffic to new classifier
- Monitor latency, accuracy, and user feedback
- Compare token usage

### Step 3: Gradual Rollout

- Week 1: 10% traffic
- Week 2: 25% traffic
- Week 3: 50% traffic
- Week 4: 100% traffic

### Step 4: Remove Legacy Code

- Delete old `classify_intent_sync` function
- Remove feature flag
- Update documentation

---

## Appendix: Files Modified

| File                               | Change Type | Description                                  |
| ---------------------------------- | ----------- | -------------------------------------------- |
| `services/intent_classifier.py`    | **Rewrite** | New Gemini Flash classifier with JSON schema |
| `services/rag_orchestrator.py`     | **Modify**  | Add new handlers, routing logic              |
| `services/parallel_agent_graph.py` | **Modify**  | Make agents configurable                     |
| `services/answer_synthesizer.py`   | **Minor**   | Add comparison synthesis                     |

---

## Appendix: Configuration

### Environment Variables

```bash
# Gemini Flash Configuration
GEMINI_MODEL=gemini-2.5-flash
INTENT_CLASSIFIER_TIMEOUT=10.0
INTENT_CLASSIFIER_TEMPERATURE=0.0

# Feature Flags
USE_NEW_INTENT_CLASSIFIER=true
ENABLE_PRECISION_FAST_PATH=true
ENABLE_EXHAUSTIVE_MODE=true
ENABLE_COMPARISON_MODE=true
```

### Default Parameters

```python
DEFAULT_EXECUTION_PLANS = {
    "precision": {
        "bm25_limit": 10,
        "vector_limit": 10,
        "rerank_limit": 5,
        "alpha": 0.5,
        "agent_strategy": "single"
    },
    "exploratory": {
        "bm25_limit": 20,
        "vector_limit": 20,
        "rerank_limit": 15,
        "alpha": 0.7,
        "agent_strategy": "parallel_5"
    },
    "exhaustive": {
        "bm25_limit": 50,
        "vector_limit": 50,
        "rerank_limit": 35,
        "alpha": 0.3,
        "agent_strategy": "parallel_8"
    },
    "comparison": {
        "bm25_limit": 30,
        "vector_limit": 30,
        "rerank_limit": 20,
        "alpha": 0.5,
        "agent_strategy": "dual_path"
    }
}
```

---

**Document End**
