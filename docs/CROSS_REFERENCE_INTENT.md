# Cross-Reference Intent - Implementation Guide

## Overview

The `cross_reference` intent handles **ambiguous multi-step queries** where the user needs to LOCATE data by one criterion, then EXTRACT different data from those same pages.

## Problem Solved

**Before:** A query like *"Find all test data where batch number 12345 is present"* was treated as a single search, searching for both "batch number 12345" AND "test data" together. This missed test data tables that don't contain "batch number" text.

**After:** The query is decomposed into two steps:
1. **Locate:** Find pages containing "batch number 12345"
2. **Extract:** Get all test data from those discovered pages

## How It Works

### Intent Classification

The Gemini 2.5 Flash classifier detects `cross_reference` when the user asks for **data Y from wherever X appears**, and X != Y.

The classifier also decomposes the query into `sub_queries`:
```json
{
  "intent": "cross_reference",
  "sub_queries": [
    {"step": "locate", "query": "batch number 12345"},
    {"step": "extract", "query": "test data"}
  ]
}
```

### Processing Pipeline

```
User Query: "Find all test data where batch number 12345 is present"
    |
    v
[Intent Classifier] -> cross_reference + sub_queries
    |
    v
[Phase B: LOCATE]
    - Search Weaviate for "batch number 12345" (alpha=0.3, BM25-heavy)
    - Extract unique page numbers: [1, 15, 32]
    |
    v
[Phase C: EXTRACT]
    - For each page [1, 15, 32]:
      - Search Weaviate for "test data" with page_filter=page_num
    - Collect all chunks across pages
    |
    v
[Phase D: DEDUPLICATE + RERANK]
    - Remove duplicate chunks (by chunk_id)
    - FlashRank rerank using FULL original query
    |
    v
[Phase E: PARALLEL AGENTS]
    - 8 parallel agents process chunks
    - Merge results with cell references
    |
    v
Response with answer + PDF highlights
```

### Example Queries

| Query | Locate | Extract |
|-------|--------|---------|
| "Find all test data where batch 12345 is" | batch 12345 | test data |
| "Show specs on pages with product ABC" | product ABC | specifications |
| "What results are on same pages as compound XYZ?" | compound XYZ | results |

### NOT Cross-Reference

| Query | Correct Intent | Why |
|-------|---------------|-----|
| "Find all batch numbers" | exhaustive | Single search term |
| "What is batch 12345?" | precision | Single value lookup |
| "List all test results" | exhaustive | No cross-page logic needed |

## Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| bm25_limit | 30 | Moderate fetch for both locate + extract |
| vector_limit | 30 | Balanced |
| rerank_limit | 25 | Good coverage after dedup |
| alpha | 0.3 | Favor BM25 for identifier matching |
| agent_strategy | parallel_8 | Maximum recall across pages |

## Edge Cases

- **No pages found:** Returns helpful message with the locate term
- **>10 pages:** Caps at top 10 by locate score
- **Extract finds nothing:** Reports which pages had the locate term but no extract data
- **Decomposition fails:** Falls through to exhaustive handler as safety net

## Files Modified

- `backend/services/intent_classifier.py` - Enum, schema, prompt, defaults
- `backend/services/rag_orchestrator.py` - Routing + handler method
