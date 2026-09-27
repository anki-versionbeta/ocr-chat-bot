# RAG Query vs Extraction Strategy

> **Document Purpose:** Clear explanation of search strategy differences between Q&A and Extraction
> **Created:** January 2026
> **Updated:** January 2026
> **Key Insight:** Q&A uses semantic search with top_k limit, Extraction uses keyword search without limit

---

## Table of Contents

1. [The Two User Intents](#the-two-user-intents)
2. [Search Strategy by Intent](#search-strategy-by-intent)
3. [Why This Matters](#why-this-matters)
4. [Real Database Example](#real-database-example)
5. [Implementation Flow](#implementation-flow)
6. [Intent Classification](#intent-classification)
7. [Code Implementation](#code-implementation)
8. [Industry Standard: Hybrid Search](#industry-standard-hybrid-search)
9. [Same Database - Two Search Types](#same-database---two-search-types)
10. [Hybrid Search Implementation](#hybrid-search-implementation)

---

## The Two User Intents

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
                    Agent classifies intent
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
┌─────────────────────┐               ┌─────────────────────┐
│       Q&A           │               │     EXTRACTION      │
│                     │               │                     │
│  "What is the pH?"  │               │  "Process all       │
│  "Show me batch"    │               │   Sample Summary    │
│  "Find the date"    │               │   to Excel"         │
│                     │               │                     │
│  Need: Best match   │               │  Need: ALL matches  │
│  Output: Answer     │               │  Output: Excel/JSON │
└─────────────────────┘               └─────────────────────┘
```

---

## Search Strategy by Intent

### Q&A Intent → Semantic Search (top_k limited)

```
User: "What is the pH value in this document?"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  SEMANTIC SEARCH (Vector Similarity)                        │
│                                                             │
│  1. Convert query to embedding vector                       │
│     Model: text-embedding-3-large (1536 dimensions)         │
│                                                             │
│  2. Cosine similarity search in Elasticsearch               │
│     ORDER BY embedding <=> query_embedding                  │
│                                                             │
│  3. Return top_k=10 results                                 │
│     Get best 10 matches by similarity score                 │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
            Returns: 10 best matches
                    │
                    ▼
            Generate answer from matches
```

**Why semantic search for Q&A:**
- ✅ Finds contextually relevant content
- ✅ Handles paraphrased questions
- ✅ Fast (no complex scoring)
- ✅ Good enough for top 10 results

---

### Extraction Intent → Keyword Search WITHOUT Limit

```
User: "Extract all Sample Summary concentration data to Excel"
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  HYBRID SEARCH (BM25 30% + Semantic 70%)                    │
│                                                             │
│  Same hybrid approach as Q&A, but:                          │
│  • NO top_k limit (returns ALL matches)                     │
│  • Minimum score threshold instead                          │
│  • Ensures all relevant pages are found                     │
│                                                             │
│  Return ALL chunks above relevance threshold                │
└─────────────────────────────────────────────────────────────┘
                    │
                    ▼
            Returns: ALL matching pages
                    │
                    ▼
            Claude processes each page → Excel
```

**Why no limit for Extraction:**
- User wants ALL data
- Missing pages = incomplete extraction
- Must find every Sample Summary page

---

## Why This Matters

### The Problem with Using Semantic Search for Extraction

```
Document: 258 pages
Sample Summary pages: 20 (scattered throughout)

User: "Extract all Sample Summary data"

❌ WRONG: Semantic search with top_k=10
   Result: Only 10 pages found
   MISSED: 10 Sample Summary pages!

✅ CORRECT: Keyword search with no limit
   Result: All 20 pages found
   Complete extraction!
```

### Comparison Table

| Aspect | Semantic Search | Keyword Search |
|--------|-----------------|----------------|
| **How it works** | Vector embedding similarity | Text pattern matching (ILIKE) |
| **Query type** | `ORDER BY embedding <=> query LIMIT 10` | `WHERE content ILIKE '%keyword%'` |
| **Has limit?** | ✅ YES (top_k) | ❌ NO |
| **Finds all?** | ❌ NO | ✅ YES |
| **Best for** | Q&A (find best) | Extraction (find all) |
| **Speed** | Fast | Fast |
| **Handles variations** | ✅ YES ("concentration" finds "density") | ❌ NO (exact match only) |

---

## Real Database Example

### What's Stored (500 chunks from 258 pages)

```
TABLE: document_chunks
┌────────┬────────────────────────────────────────┬────────┬─────────────────┐
│ id     │ content                                │ page   │ section_title   │
├────────┼────────────────────────────────────────┼────────┼─────────────────┤
│ ch-001 │ "Certificate of Analysis\nBatch: X1"   │ 1      │ NULL            │
│ ch-002 │ "Product: Humira 10mg"                 │ 1      │ "Header"        │
│ ch-003 │ "| pH | 7.2 | 6.5-7.5 |"               │ 2      │ "Test Results"  │
│ ch-004 │ "Sample Summary\n| Conc | 10.5 |"     │ 5      │ "Sample Summary"│ ← Target
│ ch-005 │ "Deviation report..."                  │ 6      │ "Deviations"    │
│ ...    │ ...                                    │ ...    │ ...             │
│ ch-089 │ "Sample Summary\n| Conc | 11.2 |"     │ 45     │ "Sample Summary"│ ← Target
│ ...    │ ...                                    │ ...    │ ...             │
│ ch-134 │ "Sample Summary\n| Conc | 10.8 |"     │ 89     │ "Sample Summary"│ ← Target
│ ...    │ ...                                    │ ...    │ ...             │
│ ch-178 │ "Sample Summary\n| Conc | 10.9 |"     │ 134    │ "Sample Summary"│ ← Target
│ ...    │ (more chunks)                          │ ...    │ ...             │
│ ch-498 │ "Sample Summary\n| Conc | 10.8 |"     │ 265    │ "Sample Summary"│ ← Target
└────────┴────────────────────────────────────────┴────────┴─────────────────┘

Total chunks: 500
Sample Summary chunks: 20 (pages 5, 45, 89, 134, 156, 178, 195, 210, 225, 240, 245, 250, 252, 255, 256, 257, 258, 259, 260, 265)
```

### Semantic Search Result (top_k=10)

```sql
-- Semantic search query
SELECT * FROM document_chunks
WHERE document_id = 'doc-123'
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

```
Result: Only 10 rows
┌────────┬────────────────────────────────────┬────────┬──────────────┐
│ id     │ content                            │ page   │ similarity   │
├────────┼────────────────────────────────────┼────────┼──────────────┤
│ ch-004 │ "Sample Summary\n| Conc | 10.5 |"  │ 5      │ 0.95         │
│ ch-089 │ "Sample Summary\n| Conc | 11.2 |"  │ 45     │ 0.93         │
│ ch-134 │ "Sample Summary\n| Conc | 10.8 |"  │ 89     │ 0.91         │
│ ch-178 │ "Sample Summary\n| Conc | 10.9 |"  │ 134    │ 0.90         │
│ ch-201 │ "Sample Summary\n| Conc | 11.0 |"  │ 156    │ 0.89         │
│ ch-245 │ "Sample Summary\n| Conc | 10.7 |"  │ 178    │ 0.84         │
│ ch-267 │ "Sample Summary\n| Conc | 11.1 |"  │ 195    │ 0.83         │
│ ch-289 │ "Sample Summary\n| Conc | 10.6 |"  │ 210    │ 0.82         │
│ ch-312 │ "Sample Summary\n| Conc | 10.4 |"  │ 225    │ 0.81         │
│ ch-334 │ "Sample Summary\n| Conc | 10.3 |"  │ 240    │ 0.80         │
└────────┴────────────────────────────────────┴────────┴──────────────┘

❌ ONLY 10 pages found!
❌ MISSED: Pages 245, 250, 252, 255, 256, 257, 258, 259, 260, 265
```

### Keyword Search Result (NO limit)

```sql
-- Keyword search query
SELECT DISTINCT page FROM document_chunks
WHERE document_id = 'doc-123'
AND (content ILIKE '%Sample Summary%' OR section_title ILIKE '%Sample Summary%')
AND content ILIKE '%Conc%'
ORDER BY page;
```

```
Result: ALL 20 pages
┌────────┐
│ page   │
├────────┤
│ 5      │
│ 45     │
│ 89     │
│ 134    │
│ 156    │
│ 178    │
│ 195    │
│ 210    │
│ 225    │
│ 240    │
│ 245    │
│ 250    │
│ 252    │
│ 255    │
│ 256    │
│ 257    │
│ 258    │
│ 259    │
│ 260    │
│ 265    │
└────────┘

✅ ALL 20 pages found!
✅ Complete extraction possible!
```

---

## Implementation Flow

### Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
│  "Extract all Sample Summary concentration data to Excel"   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: INTENT CLASSIFICATION                              │
│                                                             │
│  Detect keywords:                                           │
│  • "Extract", "all", "Excel" → EXTRACTION intent           │
│  • "What is", "Show me" → Q&A intent                       │
│                                                             │
│  Result: EXTRACTION                                         │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: EXTRACT KEYWORDS                                   │
│                                                             │
│  From query: "Sample Summary concentration data"            │
│  Keywords: ["Sample Summary", "concentration"]              │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: KEYWORD SEARCH (Find ALL pages)                    │
│                                                             │
│  SQL: SELECT DISTINCT page FROM document_chunks             │
│       WHERE content ILIKE '%Sample Summary%'                │
│       AND content ILIKE '%concentration%'                   │
│                                                             │
│  Result: [5, 45, 89, 134, 156, 178, 195, 210, 225, 240,    │
│           245, 250, 252, 255, 256, 257, 258, 259, 260, 265]│
│                                                             │
│  ALL 20 pages found!                                        │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: CLAUDE EXTRACTION (Parallel)                       │
│                                                             │
│  Send 20 pages to Claude (15 parallel at a time)           │
│  Extract concentration values from each page                │
│  ~15 seconds total                                         │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: GENERATE OUTPUT                                    │
│                                                             │
│  Consolidate all extracted data                             │
│  Generate Excel file                                        │
│  Return download link                                       │
└─────────────────────────────────────────────────────────────┘
```

### Q&A Flow (For Comparison)

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
│              "What is the pH value?"                        │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: INTENT CLASSIFICATION                              │
│                                                             │
│  Detect keywords:                                           │
│  • "What is" → Q&A intent                                  │
│                                                             │
│  Result: Q&A                                                │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: SEMANTIC SEARCH (top_k limited)                    │
│                                                             │
│  Convert query to embedding                                 │
│  Find top 10 similar chunks                                │
│                                                             │
│  Result: 10 most relevant chunks                           │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: GENERATE ANSWER                                    │
│                                                             │
│  Use LLM to answer based on retrieved chunks               │
│  Include visual references (page, bbox)                    │
│                                                             │
│  Answer: "The pH value is 7.2 (specification: 6.5-7.5)"   │
│  Reference: Page 5, Table                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Intent Classification

### Keywords for Each Intent

```python
EXTRACTION_KEYWORDS = [
    # Action words
    "extract", "process", "export", "download", "generate",

    # Output formats
    "excel", "csv", "json", "spreadsheet", "file",

    # Quantity words
    "all", "every", "each", "complete", "full",

    # Aggregation words
    "list", "compile", "collect", "gather", "summarize all"
]

QA_KEYWORDS = [
    # Question words
    "what", "where", "when", "how", "why", "which",

    # Request words
    "show", "find", "tell", "give me", "display",

    # Singular focus
    "the", "this", "that", "specific"
]
```

### Classification Logic

```python
def classify_intent(query: str) -> str:
    """
    Classify user query as Q&A or EXTRACTION
    """
    query_lower = query.lower()

    # Check for extraction signals
    extraction_signals = 0
    for keyword in EXTRACTION_KEYWORDS:
        if keyword in query_lower:
            extraction_signals += 1

    # Strong extraction indicators
    if any(word in query_lower for word in ["excel", "csv", "extract all", "process all"]):
        return "EXTRACTION"

    # Multiple extraction keywords
    if extraction_signals >= 2:
        return "EXTRACTION"

    # Default to Q&A
    return "QA"
```

---

## Code Implementation

### Complete Search Functions

```python
def search_for_qa(query: str, document_id: str, top_k: int = 10) -> list[dict]:
    """
    Semantic search for Q&A queries.
    Returns top_k most similar chunks.
    """
    # Create query embedding
    query_embedding = create_query_embedding(query)

    # Semantic search with limit
    results = db.execute("""
        SELECT
            id,
            content,
            page,
            chunk_type,
            section_title,
            bbox_left, bbox_top, bbox_right, bbox_bottom,
            1 - (embedding <=> %s::vector) AS similarity
        FROM document_chunks
        WHERE document_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, [query_embedding, document_id, query_embedding, top_k])

    return [
        {
            "id": r.id,
            "content": r.content,
            "page": r.page,
            "type": r.chunk_type,
            "section": r.section_title,
            "bbox": {
                "left": r.bbox_left,
                "top": r.bbox_top,
                "right": r.bbox_right,
                "bottom": r.bbox_bottom
            },
            "similarity": r.similarity
        }
        for r in results
    ]


def search_for_extraction(keywords: list[str], document_id: str) -> list[int]:
    """
    Keyword search for extraction queries.
    Returns ALL matching page numbers (no limit).
    """
    # Build dynamic SQL
    sql = """
        SELECT DISTINCT page
        FROM document_chunks
        WHERE document_id = %s
    """
    params = [document_id]

    # Add keyword conditions
    conditions = []
    for keyword in keywords:
        conditions.append(
            "(content ILIKE %s OR section_title ILIKE %s)"
        )
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")

    if conditions:
        sql += " AND " + " AND ".join(conditions)

    sql += " ORDER BY page"

    # Execute - returns ALL matching pages
    results = db.execute(sql, params)

    return [r.page for r in results]


def handle_user_query(query: str, document_id: str):
    """
    Main handler that routes to appropriate search strategy.
    """
    # Step 1: Classify intent
    intent = classify_intent(query)

    if intent == "QA":
        # Q&A: Use semantic search (top_k limited)
        chunks = search_for_qa(query, document_id, top_k=10)
        answer = generate_answer(query, chunks)
        return {
            "type": "answer",
            "answer": answer,
            "references": [{"page": c["page"], "bbox": c["bbox"]} for c in chunks[:3]]
        }

    else:  # EXTRACTION
        # Extraction: Use keyword search (find ALL)
        keywords = extract_keywords(query)
        pages = search_for_extraction(keywords, document_id)

        # Process all pages with Claude
        extracted_data = process_pages_with_claude(pages, document_id)

        # Generate output
        excel_url = generate_excel(extracted_data)

        return {
            "type": "extraction",
            "pages_processed": len(pages),
            "download_url": excel_url
        }
```

### Keyword Extraction Function

```python
def extract_keywords(query: str) -> list[str]:
    """
    Extract search keywords from user query.
    Can use simple parsing or Claude for complex queries.
    """
    # Remove common words
    stop_words = {"extract", "all", "the", "to", "excel", "from", "data",
                  "process", "get", "find", "every", "each", "please", "i", "need"}

    # Simple extraction
    words = query.lower().split()
    keywords = [w for w in words if w not in stop_words and len(w) > 2]

    # Look for phrases (consecutive capitalized words in original)
    # e.g., "Sample Summary" should stay together
    phrases = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', query)
    keywords.extend(phrases)

    # Deduplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)

    return unique_keywords

# Example:
# Input: "Extract all Sample Summary concentration data to Excel"
# Output: ["Sample Summary", "concentration"]
```

---

## Summary

### Decision Matrix

| User Says | Intent | Search Type | Limit | Result |
|-----------|--------|-------------|-------|--------|
| "What is the pH?" | Q&A | Semantic | top_k=10 | Answer + reference |
| "Show me test results" | Q&A | Semantic | top_k=10 | Answer + reference |
| "Extract all data to Excel" | Extraction | Keyword | NO limit | ALL pages → Excel |
| "Process Sample Summary" | Extraction | Keyword | NO limit | ALL pages → Claude |
| "List every batch number" | Extraction | Keyword | NO limit | ALL pages → List |

### Key Takeaways

```
┌─────────────────────────────────────────────────────────────┐
│                     Q&A QUERIES                             │
│                                                             │
│  • Use SEMANTIC search (vector similarity)                  │
│  • top_k = 10 (or similar small number)                    │
│  • Finds BEST matches                                       │
│  • Returns ANSWER with visual reference                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  EXTRACTION QUERIES                         │
│                                                             │
│  • Use KEYWORD search (SQL ILIKE)                          │
│  • NO LIMIT                                                 │
│  • Finds ALL matches                                        │
│  • Returns ALL PAGES for Claude processing                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Industry Standard: Hybrid Search

### Why Not Just Use top_k = 100?

| Approach | Pros | Cons |
|----------|------|------|
| **top_k = 100** | Simple | Wasteful (80 irrelevant), still might miss if >100 matches |
| **Keyword only** | Finds ALL, fast | Might miss variations ("Sample Summary" won't find "Summary of Samples") |
| **Hybrid (BEST)** | Finds all + handles variations | Industry standard |

### What Industry Leaders Use

| Company/Product | Approach |
|-----------------|----------|
| **OpenAI (ChatGPT)** | Hybrid: semantic + keyword |
| **Anthropic (Claude)** | Hybrid: semantic + metadata filtering |
| **Google (Vertex AI)** | Hybrid search built-in |
| **Pinecone** | Hybrid search (sparse + dense vectors) |
| **Weaviate** | Hybrid search (BM25 + vector) |
| **LangChain** | Recommends hybrid for production |
| **LlamaIndex** | Hybrid retrieval as default |

**Everyone uses Hybrid Search!**

---

## Same Database - Two Search Types

### Clarification: It's ONE Database

```
┌─────────────────────────────────────────────────────────────┐
│                    VECTOR DATABASE                          │
│              (Pinecone / Weaviate / pgvector)               │
│                                                             │
│  Each record stores:                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  embedding: [0.1, 0.2, 0.3, ...]  ← For SEMANTIC    │   │
│  │  content: "Sample Summary..."      ← For KEYWORD     │   │
│  │  page: 5                           ← Metadata        │   │
│  │  section_title: "Sample Summary"   ← Metadata        │   │
│  │  bbox: {...}                       ← Metadata        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  SAME database supports BOTH search types!                 │
└─────────────────────────────────────────────────────────────┘
```

**NOT two separate databases - ONE database with TWO search capabilities!**

### How Hybrid Search Works

```
User: "Extract all Sample Summary concentration data"
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    HYBRID SEARCH                            │
│                                                             │
│  ┌─────────────────────┐    ┌─────────────────────┐        │
│  │  KEYWORD FILTER     │    │  SEMANTIC RANK      │        │
│  │  (Step 1 - Filter)  │    │  (Step 2 - Sort)    │        │
│  │                     │    │                     │        │
│  │  WHERE content      │    │  ORDER BY           │        │
│  │  ILIKE '%Sample%'   │    │  embedding <=>      │        │
│  │                     │    │  query_embedding    │        │
│  │  Reduces: 500 → 50  │    │  Best matches first │        │
│  │  chunks             │    │                     │        │
│  └─────────────────────┘    └─────────────────────┘        │
│              │                        │                     │
│              └──────────┬─────────────┘                     │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │  COMBINED RESULT    │                        │
│              │                     │                        │
│              │  All 50 matching    │                        │
│              │  chunks, sorted by  │                        │
│              │  relevance          │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### The Best Approach: Filter Then Rank

```
Step 1: KEYWORD FILTER (fast, reduces search space)
        "Find all chunks containing 'Sample Summary'"
        Result: 50 chunks (from 500 total)
                         │
                         ▼
Step 2: SEMANTIC RANK (on filtered set only)
        "Rank these 50 by relevance to query"
        Result: 50 chunks, sorted by relevance
                         │
                         ▼
Step 3: RETURN BASED ON INTENT
        If Q&A: Take top 10
        If Extraction: Take ALL 50 (no limit)
```

---

## Hybrid Search Implementation

### Real Example with pgvector (PostgreSQL)

```sql
-- HYBRID SEARCH: Keyword Filter + Semantic Rank

SELECT
    id,
    content,
    page,
    section_title,
    bbox_left, bbox_top, bbox_right, bbox_bottom,
    1 - (embedding <=> query_embedding) AS similarity
FROM document_chunks
WHERE document_id = 'doc-123'
-- Step 1: KEYWORD FILTER (runs first, reduces data)
AND (
    content ILIKE '%Sample Summary%'
    OR section_title ILIKE '%Sample Summary%'
)
AND content ILIKE '%concentration%'
-- Step 2: SEMANTIC RANK (on filtered results)
ORDER BY embedding <=> query_embedding;
-- NO LIMIT for extraction (gets ALL matches)
-- Add LIMIT 10 for Q&A
```

### Real Example with Pinecone

```python
import pinecone

# Pinecone supports hybrid search natively
results = index.query(
    vector=query_embedding,           # Semantic component
    sparse_vector=bm25_sparse_vector, # Keyword component (BM25)
    top_k=1000,                       # High limit for extraction
    filter={                          # Metadata filter
        "document_id": {"$eq": "doc-123"},
        "section_title": {"$eq": "Sample Summary"}
    },
    include_metadata=True
)
```

### Real Example with Weaviate

```python
import weaviate

# Weaviate hybrid search (combines BM25 + vector)
results = client.query.get(
    "DocumentChunk",
    ["content", "page", "section_title"]
).with_hybrid(
    query="Sample Summary concentration",
    alpha=0.5  # Balance: 0=keyword only, 1=semantic only, 0.5=balanced
).with_where({
    "path": ["document_id"],
    "operator": "Equal",
    "valueString": "doc-123"
}).do()
```

### Complete Hybrid Search Function

```python
def hybrid_search(
    query: str,
    document_id: str,
    keywords: list[str],
    intent: str  # "QA" or "EXTRACTION"
) -> list[dict]:
    """
    Industry-standard hybrid search:
    1. Keyword filter (find all matching)
    2. Semantic ranking (sort by relevance)
    3. Return based on intent
    """

    # Create query embedding for semantic ranking
    query_embedding = create_embedding(query)

    # Build SQL with hybrid approach
    sql = """
        SELECT
            id,
            content,
            page,
            section_title,
            bbox_left, bbox_top, bbox_right, bbox_bottom,
            1 - (embedding <=> %s::vector) AS similarity
        FROM document_chunks
        WHERE document_id = %s
    """
    params = [query_embedding, document_id]

    # STEP 1: Add keyword filters (reduces search space)
    if keywords:
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(
                "(content ILIKE %s OR section_title ILIKE %s)"
            )
            params.extend([f"%{kw}%", f"%{kw}%"])
        sql += " AND (" + " OR ".join(keyword_conditions) + ")"

    # STEP 2: Sort by semantic similarity
    sql += " ORDER BY embedding <=> %s::vector"
    params.append(query_embedding)

    # STEP 3: Limit based on intent
    if intent == "QA":
        sql += " LIMIT 10"  # Just need best matches
    # For EXTRACTION: no limit, get ALL matching chunks

    results = db.execute(sql, params)

    return [
        {
            "id": r.id,
            "content": r.content,
            "page": r.page,
            "section": r.section_title,
            "bbox": {
                "left": r.bbox_left,
                "top": r.bbox_top,
                "right": r.bbox_right,
                "bottom": r.bbox_bottom
            },
            "similarity": r.similarity
        }
        for r in results
    ]
```

### Updated Main Handler with Hybrid Search

```python
def handle_user_query(query: str, document_id: str):
    """
    Main handler using HYBRID search for both Q&A and Extraction.
    """
    # Step 1: Classify intent
    intent = classify_intent(query)

    # Step 2: Extract keywords from query
    keywords = extract_keywords(query)

    # Step 3: HYBRID SEARCH (same function, different limits)
    results = hybrid_search(
        query=query,
        document_id=document_id,
        keywords=keywords,
        intent=intent  # "QA" → LIMIT 10, "EXTRACTION" → NO LIMIT
    )

    if intent == "QA":
        # Generate answer from top results
        answer = generate_answer(query, results)
        return {
            "type": "answer",
            "answer": answer,
            "references": [{"page": r["page"], "bbox": r["bbox"]} for r in results[:3]]
        }

    else:  # EXTRACTION
        # Get unique pages from ALL results
        pages = list(set(r["page"] for r in results))

        # Process all pages with Claude
        extracted_data = process_pages_with_claude(pages, document_id)

        # Generate output
        excel_url = generate_excel(extracted_data)

        return {
            "type": "extraction",
            "pages_found": len(pages),
            "chunks_matched": len(results),
            "download_url": excel_url
        }
```

---

## Final Summary: Hybrid Search Strategy

### The Complete Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: CLASSIFY INTENT                                    │
│                                                             │
│  Q&A: "What is...", "Show me..."                           │
│  EXTRACTION: "Extract all...", "Process...", "Excel"       │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: EXTRACT KEYWORDS                                   │
│                                                             │
│  "Sample Summary", "concentration", etc.                   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: HYBRID SEARCH (Same for both intents!)            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Keyword Filter: WHERE content ILIKE '%keyword%'    │   │
│  │  Semantic Rank:  ORDER BY embedding <=> query       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                              ▼
┌─────────────────────────┐    ┌─────────────────────────┐
│         Q&A             │    │      EXTRACTION         │
│                         │    │                         │
│  LIMIT 10               │    │  NO LIMIT               │
│  Return answer          │    │  Return ALL pages       │
│  + visual reference     │    │  → Claude → Excel       │
└─────────────────────────┘    └─────────────────────────┘
```

### Why Hybrid is Best

| Benefit | Explanation |
|---------|-------------|
| **Finds ALL matches** | Keyword filter has no limit |
| **Handles variations** | Semantic search finds "Summary of Samples" when searching "Sample Summary" |
| **Fast** | Keyword filter reduces data BEFORE semantic comparison |
| **Accurate ranking** | Semantic similarity sorts best matches first |
| **Industry standard** | Used by OpenAI, Anthropic, Google, Pinecone, Weaviate |

### Decision Matrix (Updated)

| User Query | Intent | Search | Filter | Rank | Limit | Output |
|------------|--------|--------|--------|------|-------|--------|
| "What is the pH?" | Q&A | Hybrid | `%pH%` | Semantic | 10 | Answer |
| "Extract all Sample Summary" | Extraction | Hybrid | `%Sample Summary%` | Semantic | NONE | Excel |
| "Process concentration data" | Extraction | Hybrid | `%concentration%` | Semantic | NONE | Excel |

---

*Document Version: 2.0*
*Last Updated: January 2026*
*Author: Claude Code Analysis*
*Update: Added Industry Standard Hybrid Search Strategy*
