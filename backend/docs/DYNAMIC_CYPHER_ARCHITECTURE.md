# Dynamic Cypher Query Generation Architecture

## Problem Statement

**Current Issue:** The LLM (Claude Haiku) generates **simple, naive Cypher queries** that don't capture the complex logic needed for ECD/MFI concentration extraction.

### What LLM Generated (Wrong):
```cypher
MATCH (c:Cell)
WHERE toLower(c.text) CONTAINS 'concentration'
RETURN c.text AS value
```

### What We Actually Need (Complex Logic):
```cypher
-- Find the SECOND Range row (with threshold markers 5.00/25.00/50.00)
-- Then find the FIRST Concentration row AFTER that header
-- Then pivot data into columns aligned to thresholds
-- 50+ lines of complex Cypher with multiple WITH clauses
```

**Root Cause:** LLMs are good at generating simple pattern-matching queries, but struggle with:
1. Multi-step traversal logic (find X, then find Y relative to X)
2. Domain-specific business rules (second Range row, not first)
3. Pivoting/aggregation patterns
4. Complex WHERE conditions with positional logic

---

## Current Architecture (Hybrid with Fallback)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     CURRENT FLOW (Phase 6)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User Query: "Extract all concentration values from ECD tables"         │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────┐                                                    │
│  │ Intent Classifier│ → hybrid_semantic_structural                      │
│  └────────┬────────┘                                                    │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ ECD DETECTION (NEW - Pattern Matching)                      │        │
│  │ if 'concentration' + 'ecd' in query → USE TEMPLATE          │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │                                                             │
│           ├── YES → Use pre-built extract_ecd_concentration_pivoted()   │
│           │         Returns 9 rows, 95% confidence ✅                   │
│           │                                                             │
│           └── NO → Fall through to LLM Cypher Generation                │
│                    │                                                    │
│                    ▼                                                    │
│           ┌─────────────────────────────────────────────────────┐       │
│           │ Weaviate Search (find relevant chunks)              │       │
│           │ → Provides context: headers, sample values          │       │
│           └────────┬────────────────────────────────────────────┘       │
│                    │                                                    │
│                    ▼                                                    │
│           ┌─────────────────────────────────────────────────────┐       │
│           │ LLM Cypher Generation (Claude Haiku)                │       │
│           │ → Generates simple queries                          │       │
│           │ → Often returns 24 rows instead of 9 ❌              │       │
│           └────────┬────────────────────────────────────────────┘       │
│                    │                                                    │
│                    ▼                                                    │
│           ┌─────────────────────────────────────────────────────┐       │
│           │ Retry + Template Fallback                           │       │
│           │ → If LLM fails, try cypher_templates library        │       │
│           └─────────────────────────────────────────────────────┘       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why LLM Fails at Complex Queries

| Reason | Example |
|--------|---------|
| **No Schema Traversal** | LLM doesn't explore Neo4j to see actual data patterns |
| **No Domain Knowledge** | Doesn't know "second Range row" rule for ECD tables |
| **Limited Context Window** | Few-shot examples can't cover all complex patterns |
| **No Feedback Loop** | Can't test query, see results, then refine |

---

## Proposed Solutions

### Solution 1: Query Pattern Library (Current Approach - Extended)

**Concept:** Pre-build complex Cypher templates for known query patterns, detect patterns via keywords.

```python
QUERY_PATTERNS = {
    # ECD/MFI Concentration Extraction
    'ecd_concentration': {
        'keywords': ['concentration', 'ecd', 'mfi', 'particle', 'threshold'],
        'template': 'extract_ecd_concentration_pivoted',
        'description': 'Extract pivoted concentration data from ECD tables'
    },

    # Row extraction with all columns
    'row_with_columns': {
        'keywords': ['row', 'all columns', 'entire row', 'full row'],
        'template': 'find_row_by_cell_value',
        'description': 'Find row containing X and return all column values'
    },

    # Column extraction across pages
    'column_across_pages': {
        'keywords': ['all pages', 'every page', 'across document', 'column'],
        'template': 'extract_column_by_header',
        'description': 'Extract all values from a column across all pages'
    },

    # Validation/Range queries
    'value_validation': {
        'keywords': ['within range', 'out of spec', 'exceeds', 'below'],
        'template': 'find_values_in_range',
        'description': 'Find values outside specification limits'
    }
}

def detect_query_pattern(query: str) -> Optional[str]:
    """Match user query to pre-built pattern."""
    query_lower = query.lower()

    for pattern_name, config in QUERY_PATTERNS.items():
        keyword_matches = sum(1 for kw in config['keywords'] if kw in query_lower)
        if keyword_matches >= 2:  # Require 2+ keyword matches
            return pattern_name

    return None  # Fall back to LLM generation
```

**Pros:**
- Guaranteed correct results for known patterns
- Fast execution (no LLM call)
- Maintainable - add new patterns as needed

**Cons:**
- Requires manual pattern creation
- Can't handle novel queries
- Keyword matching can be fragile

---

### Solution 2: Schema-Guided Query Decomposition

**Concept:** Break complex queries into smaller steps, let LLM generate each step, then compose.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   DECOMPOSITION APPROACH                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User Query: "Extract concentration values from ECD tables"             │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ STEP 1: Query Decomposer (LLM)                              │        │
│  │ "What sub-queries are needed?"                              │        │
│  │                                                             │        │
│  │ Output:                                                     │        │
│  │ 1. Find all tables with "Range" cells                       │        │
│  │ 2. Find the Range row with threshold markers (5.00, 25.00)  │        │
│  │ 3. Find the Concentration row after that Range row          │        │
│  │ 4. Extract values aligned to threshold columns              │        │
│  │ 5. Pivot results by page                                    │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ STEP 2: Schema Explorer                                     │        │
│  │ For each sub-query, explore Neo4j schema:                   │        │
│  │                                                             │        │
│  │ Q1: "Find Range cells"                                      │        │
│  │ → Run: MATCH (c:Cell) WHERE c.text CONTAINS 'Range'         │        │
│  │        RETURN c.row_index, count(*) LIMIT 10                │        │
│  │ → Learn: Range appears at row_index 2, 8 in tables          │        │
│  │                                                             │        │
│  │ Q2: "Find threshold markers"                                │        │
│  │ → Run: MATCH (c:Cell) WHERE c.text CONTAINS '5.00'          │        │
│  │        RETURN c.row_index, c.col_index LIMIT 10             │        │
│  │ → Learn: Thresholds at row 8, columns 2-7                   │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ STEP 3: Query Composer                                      │        │
│  │ LLM composes final Cypher using learned patterns            │        │
│  │                                                             │        │
│  │ "Based on exploration, Range with thresholds is at row 8,   │        │
│  │  Concentration follows at row 9. Generate Cypher that..."   │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Pros:**
- Can handle novel queries
- Self-improving through exploration
- Learns actual data patterns

**Cons:**
- Multiple LLM calls (slow, expensive)
- Complex implementation
- Exploration queries may timeout

---

### Solution 3: ReAct Agent with Neo4j Tools

**Concept:** Give LLM tools to explore Neo4j, let it reason step-by-step.

```python
from langchain.agents import AgentExecutor, create_react_agent

# Define Neo4j exploration tools
tools = [
    Tool(
        name="explore_schema",
        func=neo4j.get_schema,
        description="Get Neo4j node types, relationships, and properties"
    ),
    Tool(
        name="sample_data",
        func=lambda query: neo4j.query(query + " LIMIT 5"),
        description="Run a Cypher query and see sample results"
    ),
    Tool(
        name="count_matches",
        func=lambda pattern: neo4j.query(f"MATCH (c:Cell) WHERE c.text =~ '{pattern}' RETURN count(c)"),
        description="Count cells matching a pattern"
    ),
    Tool(
        name="execute_cypher",
        func=neo4j.query,
        description="Execute final Cypher query"
    )
]

# ReAct prompt
REACT_PROMPT = """
You are a Cypher query expert. To answer the user's question, you can:
1. explore_schema - See what nodes/relationships exist
2. sample_data - Run test queries to understand data patterns
3. count_matches - Count cells matching patterns
4. execute_cypher - Run the final query

Think step by step:
1. What data structure am I looking for?
2. Let me explore the schema...
3. Let me sample some data to understand patterns...
4. Now I can compose the final query...

User Question: {question}
Process ID: {process_id}

{agent_scratchpad}
"""

agent = create_react_agent(llm, tools, REACT_PROMPT)
executor = AgentExecutor(agent=agent, tools=tools, max_iterations=5)
```

**Pros:**
- Most flexible approach
- LLM can discover patterns dynamically
- Self-correcting through tool feedback

**Cons:**
- Slowest option (multiple tool calls)
- Expensive (many LLM tokens)
- Can get stuck in loops
- Requires careful prompt engineering

---

### Solution 4: Hybrid Pattern + RAG Context (Recommended)

**Concept:** Combine pattern detection with Weaviate context to select the right template.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   RECOMMENDED HYBRID APPROACH                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  User Query                                                             │
│       │                                                                 │
│       ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ LAYER 1: Query Pattern Detection                            │        │
│  │                                                             │        │
│  │ Pattern Library:                                            │        │
│  │ ┌──────────────────┬────────────────────────────────────┐   │        │
│  │ │ Pattern          │ Template                           │   │        │
│  │ ├──────────────────┼────────────────────────────────────┤   │        │
│  │ │ ECD/MFI Conc.    │ extract_ecd_concentration_pivoted  │   │        │
│  │ │ Row + All Cols   │ find_row_by_cell_value             │   │        │
│  │ │ Column Extract   │ extract_column_by_header           │   │        │
│  │ │ Value Validation │ find_values_in_range               │   │        │
│  │ │ Table Structure  │ get_document_structure             │   │        │
│  │ └──────────────────┴────────────────────────────────────┘   │        │
│  │                                                             │        │
│  │ if pattern_detected → USE TEMPLATE (fast, accurate)         │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │ no pattern matched                                          │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ LAYER 2: Weaviate Context Enrichment                        │        │
│  │                                                             │        │
│  │ Search Weaviate for relevant chunks:                        │        │
│  │ - Extract column headers found                              │        │
│  │ - Extract sample cell values                                │        │
│  │ - Identify table structure (rows, cols)                     │        │
│  │                                                             │        │
│  │ Context: "Headers: [Defect Class, Count, Severity]          │        │
│  │          Sample: row 3, col 2 = 'Critical'"                 │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ LAYER 3: LLM Cypher Generation (with enhanced prompt)       │        │
│  │                                                             │        │
│  │ Enhanced prompt includes:                                   │        │
│  │ 1. Full Neo4j schema                                        │        │
│  │ 2. Weaviate context (actual headers/values)                 │        │
│  │ 3. Few-shot examples for complex patterns                   │        │
│  │ 4. Common error patterns to avoid                           │        │
│  │                                                             │        │
│  │ FEW-SHOT EXAMPLES:                                          │        │
│  │ - Row extraction with all columns                           │        │
│  │ - Column extraction across pages                            │        │
│  │ - Pivot/aggregation patterns                                │        │
│  └────────┬────────────────────────────────────────────────────┘        │
│           │                                                             │
│           ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐        │
│  │ LAYER 4: Self-Testing + Retry                               │        │
│  │                                                             │        │
│  │ 1. Execute generated Cypher                                 │        │
│  │ 2. Validate results:                                        │        │
│  │    - Not empty?                                             │        │
│  │    - Expected columns present?                              │        │
│  │    - Row count reasonable?                                  │        │
│  │ 3. If invalid → Retry with error feedback                   │        │
│  │ 4. If still fails → Fall back to template library           │        │
│  └─────────────────────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Expand Pattern Library (Immediate)

Add more pre-built templates for common COA query patterns:

```python
# cypher_templates.py - Add these patterns

class CypherTemplates:

    # ===== EXISTING =====
    # extract_ecd_concentration_pivoted
    # find_row_by_cell_value
    # extract_column_by_header

    # ===== ADD THESE =====

    @staticmethod
    def extract_test_results_by_parameter(process_id: str, parameter: str):
        """Extract Test, Specification, Method, Result for a parameter."""
        pass

    @staticmethod
    def find_out_of_spec_values(process_id: str, column: str, min_val: float, max_val: float):
        """Find values outside specification range."""
        pass

    @staticmethod
    def extract_batch_info(process_id: str):
        """Extract batch number, lot number, expiry date, etc."""
        pass

    @staticmethod
    def compare_values_across_pages(process_id: str, column: str):
        """Compare same column values across different pages."""
        pass
```

### Phase 2: Improve LLM Prompt (Short-term)

Add more few-shot examples for complex patterns:

```python
CYPHER_GENERATION_TEMPLATE = """
## FEW-SHOT EXAMPLES FOR COMPLEX QUERIES

**Pattern: Multi-step traversal (find X, then find Y relative to X)**
Question: "Find rows where column A > 100 and return column B values"
```cypher
// Step 1: Find cells in column A
MATCH (t:Table)-[:HAS_CELL]->(header:Cell)
WHERE header.row_index IN [0,1] AND header.text =~ '(?i).*column a.*'
WITH t, header.col_index AS colA

// Step 2: Find data cells in column A > 100
MATCH (t)-[:HAS_CELL]->(dataA:Cell)
WHERE dataA.col_index = colA AND dataA.row_index > 1
  AND toFloat(dataA.text) > 100
WITH t, dataA.row_index AS targetRow

// Step 3: Find column B header
MATCH (t)-[:HAS_CELL]->(headerB:Cell)
WHERE headerB.row_index IN [0,1] AND headerB.text =~ '(?i).*column b.*'
WITH t, targetRow, headerB.col_index AS colB

// Step 4: Get column B value for that row
MATCH (t)-[:HAS_CELL]->(dataB:Cell)
WHERE dataB.row_index = targetRow AND dataB.col_index = colB
RETURN dataB.text AS value
```

**Pattern: Pivot/aggregation by page**
...
"""
```

### Phase 3: Add Query Validator (Medium-term)

Validate LLM-generated Cypher before execution:

```python
def validate_generated_cypher(cypher: str, expected_output: Dict) -> Tuple[bool, str]:
    """
    Validate Cypher query structure before execution.

    Checks:
    1. Has MATCH clause with process_id filter
    2. Has RETURN clause with expected columns
    3. Doesn't contain destructive operations
    4. Uses correct relationship patterns
    """

    errors = []

    # Check process_id filter
    if '$process_id' not in cypher and 'process_id' not in cypher:
        errors.append("Missing process_id filter - query may return data from other documents")

    # Check for RETURN clause
    if 'RETURN' not in cypher.upper():
        errors.append("Missing RETURN clause")

    # Check for destructive operations
    destructive = ['DELETE', 'REMOVE', 'DROP', 'CREATE', 'MERGE', 'SET']
    for op in destructive:
        if op in cypher.upper():
            errors.append(f"Contains destructive operation: {op}")

    # Check relationship patterns match schema
    valid_rels = ['HAS_PAGE', 'CONTAINS_TABLE', 'HAS_CELL', 'SAME_ROW', 'SAME_COL']
    # ... validate relationships

    return len(errors) == 0, "; ".join(errors)
```

### Phase 4: Schema-Guided Exploration (Long-term)

Add Neo4j exploration before query generation:

```python
async def explore_before_query(self, query: str, process_id: str) -> Dict:
    """
    Explore Neo4j data patterns before generating Cypher.

    Returns context about:
    - What tables exist
    - What headers are present
    - Sample data patterns
    """

    exploration = {}

    # Get table count
    table_count = self.neo4j.query("""
        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
        RETURN count(t) AS tables, collect(DISTINCT p.page_num) AS pages
    """, {"pid": process_id})
    exploration['tables'] = table_count

    # Get unique headers
    headers = self.neo4j.query("""
        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
        WHERE c.row_index IN [0, 1]
        RETURN DISTINCT c.text AS header, count(*) AS occurrences
        ORDER BY occurrences DESC LIMIT 20
    """, {"pid": process_id})
    exploration['headers'] = headers

    # Get sample values for key columns
    # ...

    return exploration
```

---

## Decision Matrix: When to Use What

| Query Type | Approach | Why |
|------------|----------|-----|
| ECD/MFI concentration extraction | **Pattern Template** | Complex pivoting logic, domain-specific rules |
| Simple column extraction | **LLM + Context** | Headers known from Weaviate, straightforward pattern |
| Row with all columns | **Pattern Template** | SAME_ROW traversal needs specific pattern |
| Value validation (in/out of spec) | **Pattern Template** | Range comparison logic is standard |
| Novel/unknown query | **LLM + Retry + Fallback** | Let LLM try, fall back to similar template |
| Document structure overview | **Pattern Template** | Standard aggregation query |

---

## Metrics to Track

```python
# Track query generation effectiveness
metrics = {
    'template_hits': 0,      # Queries handled by patterns
    'llm_success': 0,        # LLM generated correct query
    'llm_retry_success': 0,  # LLM succeeded after retry
    'fallback_used': 0,      # Had to use template fallback
    'total_failures': 0,     # No method worked

    'avg_template_time': 0,  # ms for template queries
    'avg_llm_time': 0,       # ms for LLM queries
}

# Goal: 80%+ template hits, <10% failures
```

---

## Summary

**Best Architecture:** Hybrid Pattern Library + Enhanced LLM Fallback

1. **First Line:** Pattern detection with pre-built templates (fast, accurate)
2. **Second Line:** LLM generation with rich context + few-shot examples
3. **Third Line:** Self-testing with retry on failure
4. **Fourth Line:** Template fallback for failed LLM queries

**Key Insight:** For domain-specific queries like ECD concentration extraction, **pre-built templates always beat LLM generation**. The LLM doesn't understand business rules like "find the SECOND Range row with threshold markers."

**Action Items:**
1. Expand pattern library with 10-15 common COA query patterns
2. Improve LLM prompt with more few-shot examples
3. Add query validator before execution
4. Track metrics to identify new patterns to add

---

*Created: February 11, 2026*
*Phase: 6 - Neo4j Structural Integration*
