# Phase 4: Multi-Agent RAG Orchestration (Enhanced)

## Overview

This document describes the enhanced multi-agent RAG orchestration architecture for the COA chatbot. The system uses intelligent routing to direct queries to the appropriate processing pipeline based on intent classification.

**Status:** Ready for Implementation
**Phase:** 4 (Vector Search) + 6 (Neo4j Integration)
**Last Updated:** 2026-02-10

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUERY FLOW OVERVIEW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query                                                     │
│      │                                                          │
│      ▼                                                          │
│  [Semantic Cache] ──hit──> Return Cached Response               │
│      │ miss                                                     │
│      ▼                                                          │
│  [Intent Classifier]                                            │
│      │                                                          │
│      ├── vector_only (90%) ──> Weaviate Only                    │
│      │                                                          │
│      ├── structural (5%) ──> Weaviate + Neo4j                   │
│      │                                                          │
│      └── extraction (5%) ──> Weaviate + Neo4j + Excel           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Query Types & Routing

### 1. Vector Only (90% of queries) - Phase 4

**Handled by:** Weaviate hybrid search only
**No Neo4j required**

| Query Type | Example | How It Works |
|------------|---------|--------------|
| Simple Q&A | "What is the batch number?" | Semantic search → Answer synthesis |
| Value lookup | "Show me test results" | Hybrid search → Extract from chunks |
| **Row/Col queries** | "Value at row 7, column 3" | Search → Lookup `cell_grounding` where row=X, col=Y |

**Key Insight:** Simple row/column queries do NOT need Neo4j because `cell_grounding` already stores `row` and `col` for every cell.

### 2. Structural (5% of queries) - Phase 6

**Handled by:** Weaviate + Neo4j Cypher

| Query Type | Example | How It Works |
|------------|---------|--------------|
| Page finding | "What page has specifications?" | Neo4j: Find table by name → Return page |
| Table navigation | "Show tables on page 3" | Neo4j: Query tables by page number |
| Adjacent cells | "Cell next to Appearance" | Neo4j: Navigate cell relationships |

### 3. Extraction (5% of queries) - Phase 6

**Handled by:** Weaviate + Neo4j Cypher + Excel Generation

| Query Type | Example | How It Works |
|------------|---------|--------------|
| Export all rows | "Export test results to Excel" | Neo4j: Get ALL rows → Generate Excel |
| Complete table | "Give me ALL data from specs table" | Neo4j: Traverse table structure → Excel |

---

## Enhanced Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   MULTI-AGENT RAG ORCHESTRATION (ENHANCED)                      │
│              With Caching, Reranking, Parallel Search & Confidence              │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────┐
                              │  User Query  │
                              │  process_id  │
                              └──────┬───────┘
                                     │
                                     ▼
         ┌───────────────────────────────────────────────────────────┐
         │                   SEMANTIC CACHE                          │
         │                                                           │
         │  • Embed user query                                       │
         │  • Check similarity with cached queries (>0.95 = hit)     │
         │  • TTL: 30 minutes per process_id                         │
         │  • Scope: Same document only                              │
         └───────────────────────────┬───────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                     Cache Hit             Cache Miss
                          │                     │
                          ▼                     ▼
              ┌───────────────────┐            │
              │  Return Cached    │            │
              │  Response         │            │
              │  (Skip all steps) │            │
              └───────────────────┘            │
                                               ▼
         ┌───────────────────────────────────────────────────────────┐
         │                 INTENT CLASSIFIER                         │
         │                 (Claude Haiku)                            │
         │                                                           │
         │  Prompt:                                                  │
         │  """                                                      │
         │  Classify this query about a COA document:                │
         │  - vector_only: Simple Q&A, value lookups, row/col queries│
         │  - structural: Page finding, table navigation             │
         │  - extraction: Export ALL rows/data to Excel              │
         │  - clarification: Ambiguous, needs more info              │
         │  """                                                      │
         │                                                           │
         │  Examples:                                                │
         │  • "What is batch number?" → vector_only                  │
         │  • "Value at row 7, col 3" → vector_only                  │
         │  • "What page has specs?" → structural                    │
         │  • "Export all rows" → extraction                         │
         └───────────────────────────┬───────────────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────────┐
        │                            │                                │
        ▼                            ▼                                ▼
┌───────────────────┐    ┌───────────────────┐            ┌───────────────────┐
│   vector_only     │    │    structural     │            │    extraction     │
│   (Phase 4)       │    │    (Phase 6)      │            │    (Phase 6)      │
└─────────┬─────────┘    └─────────┬─────────┘            └─────────┬─────────┘
          │                        │                                │
          ▼                        ▼                                ▼
┌─────────────────────┐  ┌─────────────────────┐          ┌─────────────────────┐
│ QUESTION REPHRASER  │  │ QUESTION REPHRASER  │          │ TABLE IDENTIFIER    │
│ (Claude Haiku)      │  │ (Claude Haiku)      │          │ (Claude Haiku)      │
│                     │  │                     │          │                     │
│ Generate 3-5        │  │ Generate 3-5        │          │ Identify target     │
│ COA-specific        │  │ variations for      │          │ table from query    │
│ variations          │  │ structural search   │          │                     │
│                     │  │                     │          │ "Export test        │
│ "batch number" →    │  │ "specs table" →     │          │  results" →         │
│ ["lot number",      │  │ ["specifications",  │          │ table: "Test        │
│  "batch ID",        │  │  "spec sheet",      │          │  Results Table"     │
│  "lot ID",          │  │  "requirements",    │          │                     │
│  "manufacturing #", │  │  "product specs",   │          │                     │
│  "batch identifier"]│  │  "quality specs"]   │          │                     │
└─────────┬───────────┘  └─────────┬───────────┘          └─────────┬───────────┘
          │                        │                                │
          ▼                        ▼                                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        PARALLEL WEAVIATE SEARCH                                 │
│                                                                                 │
│  Execute ALL query variations simultaneously:                                   │
│                                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│  │ Var 1   │  │ Var 2   │  │ Var 3   │  │ Var 4   │  │ Var 5   │              │
│  │ Hybrid  │  │ Hybrid  │  │ Hybrid  │  │ Hybrid  │  │ Hybrid  │              │
│  │ Search  │  │ Search  │  │ Search  │  │ Search  │  │ Search  │              │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘              │
│       │            │            │            │            │                    │
│       └────────────┴────────────┼────────────┴────────────┘                    │
│                                 │                                              │
│  Hybrid Config:                 │                                              │
│  • alpha = 0.7 (70% semantic, 30% BM25)                                        │
│  • Filter: process_id = "{uuid}"                                               │
│  • Limit: 10 per variation                                                     │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    RESULT AGGREGATOR & DEDUPLICATOR                             │
│                                                                                 │
│  1. Merge results from all parallel searches                                    │
│  2. Remove duplicates by chunk_id                                               │
│  3. Keep highest score for each unique chunk                                    │
│  4. Sort by combined score                                                      │
│                                                                                 │
│  Output: Top 15-20 unique chunks                                                │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       CROSS-ENCODER RERANKER                                    │
│                       (Optional Enhancement)                                    │
│                                                                                 │
│  Model: cross-encoder/ms-marco-MiniLM-L-12-v2                                   │
│                                                                                 │
│  For each (original_query, chunk) pair:                                         │
│  • Compute relevance score (0-1)                                                │
│  • More accurate than bi-encoder similarity                                     │
│  • Reorder by cross-encoder score                                               │
│  • Keep top 5-7 most relevant                                                   │
│                                                                                 │
│  Input: 15-20 chunks → Output: Top 5-7 chunks                                   │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────────────┐
         │                        │                                │
         ▼                        ▼                                ▼
┌─────────────────────┐  ┌─────────────────────┐          ┌─────────────────────┐
│ vector_only PATH    │  │ structural PATH     │          │ extraction PATH     │
│                     │  │                     │          │                     │
│ Continue with       │  │ Continue with       │          │ Continue with       │
│ Weaviate results    │  │ Neo4j query         │          │ Neo4j query         │
└─────────┬───────────┘  └─────────┬───────────┘          └─────────┬───────────┘
          │                        │                                │
          │                        ▼                                ▼
          │              ┌─────────────────────┐          ┌─────────────────────┐
          │              │ NEO4J CYPHER QUERY  │          │ NEO4J CYPHER QUERY  │
          │              │                     │          │                     │
          │              │ // Find pages       │          │ // Get ALL rows     │
          │              │ MATCH (d:Document)  │          │ MATCH (t:Table)     │
          │              │ -[:HAS_PAGE]->(p)   │          │ -[:HAS_ROW]->(r:Row)│
          │              │ -[:HAS_TABLE]->(t)  │          │ -[:HAS_CELL]->(c)   │
          │              │ WHERE d.process_id  │          │ WHERE t.id = {id}   │
          │              │   = $process_id     │          │ RETURN r.index,     │
          │              │ AND t.name =~       │          │   collect(c.text)   │
          │              │   $pattern          │          │ ORDER BY r.index    │
          │              │ RETURN p.number,    │          │                     │
          │              │   t.bbox            │          │                     │
          │              └─────────┬───────────┘          └─────────┬───────────┘
          │                        │                                │
          ▼                        ▼                                ▼
┌─────────────────────┐  ┌─────────────────────┐          ┌─────────────────────┐
│ CONTEXT BUILDER     │  │ CONTEXT BUILDER     │          │ EXCEL GENERATOR     │
│                     │  │                     │          │                     │
│ For table chunks:   │  │ Combine Weaviate    │          │ • Create workbook   │
│ Include markdown    │  │ context + Neo4j     │          │ • Add headers       │
│ with cell IDs       │  │ structural info     │          │ • Add all rows      │
│                     │  │                     │          │ • Format columns    │
│ For row/col query:  │  │                     │          │ • Save to temp/     │
│ Include cell_       │  │                     │          │                     │
│ grounding data      │  │                     │          │                     │
└─────────┬───────────┘  └─────────┬───────────┘          └─────────┬───────────┘
          │                        │                                │
          ▼                        ▼                                │
┌─────────────────────┐  ┌─────────────────────┐                    │
│ ANSWER SYNTHESIZER  │  │ ANSWER SYNTHESIZER  │                    │
│ (Claude Sonnet)     │  │ (Claude Sonnet)     │                    │
│                     │  │                     │                    │
│ Prompt:             │  │ Prompt:             │                    │
│ """                 │  │ """                 │                    │
│ Answer using ONLY   │  │ Answer with page    │                    │
│ the context.        │  │ references from     │                    │
│                     │  │ Neo4j results.      │                    │
│ For table data:     │  │ Include table       │                    │
│ Include cell_ids    │  │ locations.          │                    │
│ [cell:X-Y] format.  │  │ """                 │                    │
│                     │  │                     │                    │
│ For row/col query:  │  │ Output:             │                    │
│ Find cell where     │  │ { answer, pages[],  │                    │
│ row=X AND col=Y     │  │   table_refs[] }    │                    │
│ in cell_grounding.  │  │                     │                    │
│ """                 │  │                     │                    │
│                     │  │                     │                    │
│ Output:             │  │                     │                    │
│ { answer, cell_ids[],│ │                     │                    │
│   confidence }      │  │                     │                    │
└─────────┬───────────┘  └─────────┬───────────┘                    │
          │                        │                                │
          ▼                        ▼                                │
┌─────────────────────┐  ┌─────────────────────┐                    │
│ CONFIDENCE CHECKER  │  │ CONFIDENCE CHECKER  │                    │
│                     │  │                     │                    │
│ confidence >= 0.7   │  │ confidence >= 0.7   │                    │
│ → Return answer     │  │ → Return answer     │                    │
│                     │  │                     │                    │
│ confidence < 0.7    │  │ confidence < 0.7    │                    │
│ → Add disclaimer:   │  │ → Add disclaimer    │                    │
│ "I'm not fully      │  │                     │                    │
│  confident..."      │  │                     │                    │
└─────────┬───────────┘  └─────────┬───────────┘                    │
          │                        │                                │
          ▼                        ▼                                │
┌─────────────────────┐  ┌─────────────────────┐                    │
│ REFERENCE EXTRACTOR │  │ REFERENCE EXTRACTOR │                    │
│                     │  │                     │                    │
│ Parse cell_ids from │  │ Extract page        │                    │
│ answer text         │  │ numbers and table   │                    │
│ [cell:X-Y] format   │  │ bboxes from Neo4j   │                    │
│                     │  │ results             │                    │
│ Lookup each cell_id │  │                     │                    │
│ in cell_grounding:  │  │                     │                    │
│                     │  │                     │                    │
│ cell_grounding[id]= │  │                     │                    │
│ {                   │  │                     │                    │
│   bbox: {...},      │  │                     │                    │
│   text: "...",      │  │                     │                    │
│   row: 7,           │  │                     │                    │
│   col: 3            │  │                     │                    │
│ }                   │  │                     │                    │
│                     │  │                     │                    │
│ For row/col query:  │  │                     │                    │
│ Direct lookup where │  │                     │                    │
│ row=X AND col=Y     │  │                     │                    │
└─────────┬───────────┘  └─────────┬───────────┘                    │
          │                        │                                │
          └────────────────────────┼────────────────────────────────┘
                                   │
                                   ▼
         ┌───────────────────────────────────────────────────────────┐
         │                     CACHE UPDATER                         │
         │                                                           │
         │  Store in semantic cache:                                 │
         │  • Query embedding (for similarity matching)              │
         │  • Complete response (answer + references)                │
         │  • TTL: 30 minutes                                        │
         │  • Scope: process_id (document-specific)                  │
         └───────────────────────────┬───────────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │         FINAL RESPONSE          │
                    └─────────────────────────────────┘
```

---

## Component Details

### 1. Semantic Cache

**Purpose:** Avoid redundant processing for repeated/similar queries

```python
class SemanticCache:
    """
    Cache responses based on query semantic similarity.
    """

    def __init__(self, ttl_minutes: int = 30, similarity_threshold: float = 0.95):
        self.ttl = ttl_minutes * 60  # Convert to seconds
        self.threshold = similarity_threshold
        self.cache = {}  # {process_id: [(embedding, response, timestamp), ...]}

    async def get(self, process_id: str, query_embedding: List[float]) -> Optional[Dict]:
        """Check if similar query exists in cache."""
        if process_id not in self.cache:
            return None

        current_time = time.time()
        valid_entries = []

        for embedding, response, timestamp in self.cache[process_id]:
            # Check TTL
            if current_time - timestamp > self.ttl:
                continue

            # Check similarity
            similarity = cosine_similarity(query_embedding, embedding)
            if similarity >= self.threshold:
                return response

            valid_entries.append((embedding, response, timestamp))

        # Clean expired entries
        self.cache[process_id] = valid_entries
        return None

    async def set(self, process_id: str, query_embedding: List[float], response: Dict):
        """Store response in cache."""
        if process_id not in self.cache:
            self.cache[process_id] = []

        self.cache[process_id].append((
            query_embedding,
            response,
            time.time()
        ))
```

### 2. Intent Classifier

**Purpose:** Route queries to appropriate processing pipeline

```python
INTENT_CLASSIFIER_PROMPT = """
You are a query classifier for a Certificate of Analysis (COA) document system.

Classify the user's query into ONE of these categories:

1. **vector_only** - Simple questions answered by searching document content
   - General Q&A: "What is the batch number?", "Show test results"
   - Value lookups: "What does the appearance test say?"
   - Row/column queries: "Value at row 7, column 3", "What's in row 5, col 2?"

2. **structural** - Questions about document structure requiring navigation
   - Page finding: "What page has the specifications table?"
   - Table location: "Show me all tables on page 3"
   - Cell navigation: "What's next to the Appearance cell?"

3. **extraction** - Requests to export ALL data from tables
   - Full export: "Export all test results to Excel"
   - Complete table: "Give me ALL rows from the specifications table"
   - Data dump: "Extract complete table data"

4. **clarification** - Ambiguous queries needing more information
   - Unclear references: "Show me that table" (which table?)
   - Missing context: "What about the other one?"

User Query: {query}

Respond with ONLY the category name (vector_only, structural, extraction, or clarification).
"""

async def classify_intent(query: str) -> str:
    """Classify query intent using Claude Haiku."""
    response = await claude_client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=REDACTED
        messages=[{
            "role": "user",
            "content": INTENT_CLASSIFIER_PROMPT.format(query=query)
        }]
    )

    intent = response.content[0].text.strip().lower()

    # Validate intent
    valid_intents = ["vector_only", "structural", "extraction", "clarification"]
    if intent not in valid_intents:
        return "vector_only"  # Default fallback

    return intent
```

### 3. Question Rephraser

**Purpose:** Generate query variations for better search recall

```python
REPHRASER_PROMPT = """
You are a search query optimizer for Certificate of Analysis (COA) documents.

Given a user question, generate 3-5 alternative phrasings that might match
relevant content in the document. Use COA-specific terminology.

Original question: {query}

Generate variations that:
1. Use synonyms (batch number → lot number, lot ID)
2. Use industry terms (specifications → specs, requirements)
3. Rephrase the question structure
4. Include abbreviations and full forms

Return ONLY a JSON array of strings, no explanation.
Example: ["variation 1", "variation 2", "variation 3"]
"""

async def rephrase_question(query: str) -> List[str]:
    """Generate query variations using Claude Haiku."""
    response = await claude_client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=REDACTED
        messages=[{
            "role": "user",
            "content": REPHRASER_PROMPT.format(query=query)
        }]
    )

    try:
        variations = json.loads(response.content[0].text)
        # Always include original query
        return [query] + variations
    except json.JSONDecodeError:
        return [query]
```

### 4. Parallel Weaviate Search

**Purpose:** Execute all query variations simultaneously for better recall

```python
async def parallel_hybrid_search(
    queries: List[str],
    process_id: str,
    limit_per_query: int = 10
) -> List[Dict]:
    """Execute hybrid search for all queries in parallel."""

    async def single_search(query: str) -> List[Dict]:
        """Execute single hybrid search."""
        response = weaviate_client.query.get(
            "DocumentChunk",
            ["chunk_id", "content", "page", "chunk_type",
             "cell_grounding", "line_grounding", "bbox_left",
             "bbox_top", "bbox_right", "bbox_bottom"]
        ).with_hybrid(
            query=query,
            alpha=0.7,  # 70% semantic, 30% BM25
            properties=["content", "keywords", "filename"]
        ).with_where({
            "path": ["process_id"],
            "operator": "Equal",
            "valueText": process_id
        }).with_limit(limit_per_query).do()

        return response.get("data", {}).get("Get", {}).get("DocumentChunk", [])

    # Execute all searches in parallel
    tasks = [single_search(q) for q in queries]
    results = await asyncio.gather(*tasks)

    # Flatten results
    all_chunks = []
    for chunk_list in results:
        all_chunks.extend(chunk_list)

    return all_chunks
```

### 5. Result Aggregator & Deduplicator

**Purpose:** Merge and deduplicate results from parallel searches

```python
def aggregate_and_deduplicate(chunks: List[Dict]) -> List[Dict]:
    """Merge results and keep highest score for duplicates."""

    seen = {}  # chunk_id -> chunk with highest score

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        score = chunk.get("_additional", {}).get("score", 0)

        if chunk_id not in seen or score > seen[chunk_id].get("_additional", {}).get("score", 0):
            seen[chunk_id] = chunk

    # Sort by score descending
    unique_chunks = list(seen.values())
    unique_chunks.sort(
        key=lambda x: x.get("_additional", {}).get("score", 0),
        reverse=True
    )

    return unique_chunks[:20]  # Keep top 20
```

### 6. Cross-Encoder Reranker (Optional)

**Purpose:** More accurate relevance scoring using cross-encoder model

```python
from sentence_transformers import CrossEncoder

class Reranker:
    """Rerank chunks using cross-encoder for better accuracy."""

    def __init__(self):
        self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')

    def rerank(self, query: str, chunks: List[Dict], top_k: int = 7) -> List[Dict]:
        """Rerank chunks by cross-encoder relevance score."""

        # Prepare pairs for scoring
        pairs = [(query, chunk.get("content", "")) for chunk in chunks]

        # Get cross-encoder scores
        scores = self.model.predict(pairs)

        # Add scores to chunks
        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        # Sort by rerank score
        chunks.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

        return chunks[:top_k]
```

### 7. Answer Synthesizer

**Purpose:** Generate natural language answers from retrieved context

```python
ANSWER_PROMPT = """
You are analyzing a Certificate of Analysis (COA) document.

Context from the document:
{context}

Cell Grounding Data (for highlighting):
{cell_grounding}

User Question: {query}

Instructions:
1. Answer using ONLY information from the provided context
2. For any values from tables, include the cell ID in format [cell:X-Y]
3. For row/column queries (e.g., "value at row 7, col 3"):
   - Look up the cell_grounding data to find the cell at that position
   - Return the exact value with its cell_id
4. Be concise and accurate
5. If the answer is not in the context, say "I couldn't find this information in the document"

Respond with JSON:
{{
    "answer": "Your answer here with [cell:X-Y] references",
    "cell_ids": ["X-Y", "X-Y"],  // List of cell IDs referenced
    "confidence": 0.95  // 0-1 confidence score
}}
"""

async def synthesize_answer(
    query: str,
    chunks: List[Dict],
    query_type: str = "vector_only"
) -> Dict:
    """Generate answer from retrieved chunks."""

    # Build context from chunks
    context_parts = []
    all_cell_grounding = {}

    for chunk in chunks:
        context_parts.append(f"[{chunk.get('chunk_type', 'text').upper()}] Page {chunk.get('page', '?')}:")
        context_parts.append(chunk.get("content", ""))
        context_parts.append("")

        # Collect cell grounding
        if chunk.get("cell_grounding"):
            grounding = json.loads(chunk["cell_grounding"])
            all_cell_grounding.update(grounding)

    context = "\n".join(context_parts)

    # Format cell grounding for row/col lookups
    grounding_str = "\n".join([
        f"{cid}: row={data.get('row')}, col={data.get('col')}, text=\"{data.get('text', '')[:50]}\""
        for cid, data in all_cell_grounding.items()
    ])

    response = await claude_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=REDACTED
        messages=[{
            "role": "user",
            "content": ANSWER_PROMPT.format(
                context=context,
                cell_grounding=grounding_str,
                query=query
            )
        }]
    )

    try:
        return json.loads(response.content[0].text)
    except json.JSONDecodeError:
        return {
            "answer": response.content[0].text,
            "cell_ids": [],
            "confidence": 0.5
        }
```

### 8. Confidence Checker

**Purpose:** Add disclaimers for low-confidence answers

```python
def check_confidence(response: Dict) -> Dict:
    """Add disclaimer if confidence is below threshold."""

    confidence = response.get("confidence", 0.5)

    if confidence < 0.7:
        response["answer"] = (
            "I'm not fully confident in this answer, but based on the document: " +
            response.get("answer", "")
        )
        response["low_confidence"] = True

    return response
```

### 9. Reference Extractor

**Purpose:** Convert cell_ids to bbox coordinates for PDF highlighting

```python
def extract_references(
    answer_data: Dict,
    chunks: List[Dict]
) -> List[Dict]:
    """Extract bbox references from cell_ids for highlighting."""

    cell_ids = answer_data.get("cell_ids", [])
    references = []

    # Build complete cell_grounding map
    all_grounding = {}
    chunk_pages = {}

    for chunk in chunks:
        if chunk.get("cell_grounding"):
            grounding = json.loads(chunk["cell_grounding"])
            for cid, data in grounding.items():
                all_grounding[cid] = data
                chunk_pages[cid] = chunk.get("page", 1)

    # Lookup each cell_id
    for cell_id in cell_ids:
        if cell_id in all_grounding:
            data = all_grounding[cell_id]
            references.append({
                "page": chunk_pages.get(cell_id, 1),
                "bbox": data.get("bbox", {}),
                "cell_id": cell_id,
                "text": data.get("text", ""),
                "row": data.get("row"),
                "col": data.get("col")
            })

    return references


def lookup_by_row_col(
    row: int,
    col: int,
    chunks: List[Dict]
) -> Optional[Dict]:
    """Find cell by row/column position in cell_grounding."""

    for chunk in chunks:
        if chunk.get("chunk_type") != "table":
            continue

        if chunk.get("cell_grounding"):
            grounding = json.loads(chunk["cell_grounding"])

            for cell_id, data in grounding.items():
                if data.get("row") == row and data.get("col") == col:
                    return {
                        "found": True,
                        "page": chunk.get("page", 1),
                        "bbox": data.get("bbox", {}),
                        "cell_id": cell_id,
                        "text": data.get("text", ""),
                        "row": row,
                        "col": col
                    }

    return {"found": False, "message": f"No cell found at row {row}, column {col}"}
```

### 10. Cache Updater

**Purpose:** Store successful responses for future similar queries

```python
async def update_cache(
    cache: SemanticCache,
    process_id: str,
    query: str,
    response: Dict
):
    """Store response in semantic cache."""

    # Generate query embedding
    embedding = await generate_embedding(query)

    # Store in cache
    await cache.set(process_id, embedding, response)
```

---

## Response Formats

### Vector Only Response

```json
{
    "answer": "The batch number is 12345 [cell:2-5]",
    "references": [
        {
            "page": 1,
            "bbox": {
                "left": 0.45,
                "top": 0.32,
                "width": 0.15,
                "height": 0.03
            },
            "cell_id": "2-5",
            "text": "12345",
            "row": 2,
            "col": 5
        }
    ],
    "confidence": 0.95,
    "query_type": "vector_only"
}
```

### Structural Response

```json
{
    "answer": "The specifications table is on page 2",
    "pages": [2],
    "tables": [
        {
            "name": "Specifications",
            "page": 2,
            "bbox": {
                "left": 0.1,
                "top": 0.2,
                "width": 0.8,
                "height": 0.5
            }
        }
    ],
    "query_type": "structural"
}
```

### Extraction Response

```json
{
    "message": "Exported 25 rows to Excel",
    "excel_url": "/download/export_abc123.xlsx",
    "row_count": 25,
    "table_name": "Test Results",
    "query_type": "extraction"
}
```

---

## Implementation Phases

### Phase 4 (Current) - Vector Only

Implement:
- [x] Semantic Cache
- [x] Intent Classifier (vector_only + clarification only)
- [x] Question Rephraser
- [x] Parallel Weaviate Search
- [x] Result Aggregator
- [x] Cross-Encoder Reranker (optional)
- [x] Answer Synthesizer
- [x] Confidence Checker
- [x] Reference Extractor (cell_grounding lookup)
- [x] Cache Updater
- [x] Simple row/col queries via cell_grounding

### Phase 6 (Future) - Neo4j Integration

Implement:
- [ ] Intent Classifier (add structural + extraction)
- [ ] Neo4j Cypher queries for structural navigation
- [ ] Neo4j Cypher queries for data extraction
- [ ] Excel Generator for extraction queries
- [ ] Page-level reference extraction

---

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `backend/services/rag_orchestrator.py` | Main orchestration logic |
| `backend/services/intent_classifier.py` | Query intent classification |
| `backend/services/question_rephraser.py` | Query variation generation |
| `backend/services/semantic_cache.py` | Query caching |
| `backend/services/reranker.py` | Cross-encoder reranking |
| `backend/services/answer_synthesizer.py` | Answer generation |
| `backend/services/reference_extractor.py` | Bbox extraction |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app.py` | Update `/api/chat/coa-rag/{process_id}` endpoint |
| `backend/services/weaviate_indexer.py` | Add parallel search support |

---

## Summary

This enhanced multi-agent RAG orchestration provides:

1. **Intelligent Routing** - Queries directed to optimal pipeline
2. **Semantic Caching** - Avoid redundant processing
3. **Parallel Search** - Better recall with query variations
4. **Cross-Encoder Reranking** - More accurate relevance scoring
5. **Confidence Checking** - Transparent uncertainty handling
6. **Simple Row/Col Support** - Direct cell_grounding lookup (no Neo4j needed)
7. **Extensible Architecture** - Ready for Phase 6 Neo4j integration

The key insight is that **90% of queries** can be handled by vector search alone, with simple row/column queries using the existing `cell_grounding` metadata rather than requiring Neo4j graph traversal.
