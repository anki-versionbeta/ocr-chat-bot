# Multi-Agent GraphRAG: NEV Topology & Success Bank Implementation

**Document Version:** 1.0
**Created:** February 12, 2026
**Target File:** `backend/test_multiagent_cypher.py`
**Status:** Planning Complete - Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Neo4j Schema](#2-current-neo4j-schema)
3. [Problem Analysis](#3-problem-analysis)
4. [Implementation Phases](#4-implementation-phases)
   - [Phase 1: Topology NEV](#phase-1-topology-nev-path-level-verification)
   - [Phase 2: Success Bank](#phase-2-success-bank-dynamic-learning)
   - [Phase 3: Hard Constraints](#phase-3-hard-constraints-injection)
5. [Code Snippets](#5-code-snippets)
6. [Testing Checklist](#6-testing-checklist)
7. [Progress Tracking](#7-progress-tracking)

---

## 1. Executive Summary

### Goal
Transform the multi-agent Cypher generation system from a **table-biased prototype** to a **universal layout engine** that works with ANY document structure (Tables, Lines, Sections, KV pairs).

### Current State
- **Table documents:** 90% success rate
- **Line documents:** 40% success rate (fails due to table bias)
- **Mixed documents:** 50% success rate

### Target State
- **Table documents:** 99% success rate
- **Line documents:** 95% success rate
- **Mixed documents:** 90% success rate
- **Average iterations:** 1.2 (down from 2.5)

### Key Problems to Fix
1. **Logic Gravity:** Hardcoded table-based examples bias LLM toward Table/Cell paths
2. **Blind Checking:** System queries Table/Cell even when Structural Probe says data is in Line nodes
3. **No Learning:** Static `FEW_SHOT_EXAMPLES` list never improves

---

## 2. Current Neo4j Schema

### Node Labels (10 total)
```
Document    - Root node with process_id, filename
Page        - Has page_num, page_key
Section     - Has section_id, text, content
Table       - Has table_id, chunk_index, row_count, col_count
Cell        - Has text, row_index, col_index, is_header, bbox_*
Line        - Has text, line_id, bbox_*, confidence
Word        - Has word_id, text
KV          - Has kv_id (Key-Value pairs)
MergedCell  - Has merged_id (spanning cells)
Selection   - Has selection_id
```

### Relationships (7 total)
```
HAS_PAGE         : Document -> Page
CONTAINS_TABLE   : Page -> Table
HAS_CELL         : Table -> Cell
CONTAINS_SECTION : Page -> Section
CONTAINS_LINE    : Page -> Line
SAME_ROW         : Cell -> Cell (horizontal adjacency)
SAME_COL         : Cell -> Cell (vertical adjacency)
```

### Valid Topology Paths
```cypher
-- PATH 1: Table Data (structured rows/columns)
(Document)-[:HAS_PAGE]->(Page)-[:CONTAINS_TABLE]->(Table)-[:HAS_CELL]->(Cell)

-- PATH 2: Line Data (text paragraphs, labels)
(Document)-[:HAS_PAGE]->(Page)-[:CONTAINS_LINE]->(Line)

-- PATH 3: Section Data (document sections/headers)
(Document)-[:HAS_PAGE]->(Page)-[:CONTAINS_SECTION]->(Section)

-- PATH 4: Cell Adjacency (same row/column lookups)
(Cell)-[:SAME_ROW]->(Cell)
(Cell)-[:SAME_COL]->(Cell)

-- PATH 5: Cross-table on same page
(Page)-[:CONTAINS_TABLE]->(Table1), (Page)-[:CONTAINS_TABLE]->(Table2)
```

### Invalid Topology Paths (Hallucinations to Catch)
```cypher
-- INVALID: Table cannot connect to non-Cell nodes
(Table)-[ANY]->(Line)      -- Table cannot connect to Line
(Table)-[ANY]->(Section)   -- Table cannot connect to Section
(Table)-[ANY]->(Word)      -- Table cannot connect to Word
(Table)-[ANY]->(KV)        -- Table cannot connect to KV

-- INVALID: Line cannot connect to table-related nodes
(Line)-[ANY]->(Cell)       -- Line cannot connect to Cell
(Line)-[ANY]->(Table)      -- Line cannot connect to Table

-- INVALID: Document must go through Page
(Document)-[ANY]->(Cell)   -- Missing Page intermediate
(Document)-[ANY]->(Line)   -- Missing Page intermediate
(Document)-[ANY]->(Table)  -- Missing Page intermediate

-- INVALID: Leaf nodes cannot interconnect (except Cell-Cell)
(Cell)-[ANY]->(Line)       -- Cell cannot connect to Line
(Section)-[ANY]->(Cell)    -- Section cannot connect to Cell

-- INVALID: Reversed directions
(Page)-[ANY]->(Document)   -- Direction reversed
(Cell)-[ANY]->(Table)      -- Direction reversed
(Table)-[ANY]->(Page)      -- Direction reversed
(Line)-[ANY]->(Page)       -- Direction reversed
```

---

## 3. Problem Analysis

### 3.1 Logic Gravity (Inductive Bias)

**What it is:** The LLM defaults to Table/Cell paths because ALL hardcoded few-shot examples use tables.

**Current Code (line 102-203):**
```python
FEW_SHOT_EXAMPLES = [
    {"question": "Find all cells...", "cypher": "...Table->Cell..."},
    {"question": "Get all rows...", "cypher": "...Table->Cell..."},
    {"question": "Extract column...", "cypher": "...Table->Cell..."},
    {"question": "Find a row...", "cypher": "...Table->Cell..."},
    {"question": "Extract data from Line nodes...", "cypher": "...Line..."},  # Only 1 Line example!
]
```

**Problem:** 4 out of 5 examples are table-based. Even when Structural Probe correctly identifies Line data, the LLM gravitates toward table patterns.

### 3.2 Blind Checking

**What it is:** The system queries Table/Cell without verifying if data actually exists there.

**Failure Chain:**
1. Probe: "Batch Name found in 5 Line nodes, 0 Cell nodes"
2. Planner: Sees table examples → Assumes table path
3. Generated Cypher: Uses `Page->Table->Cell` (WRONG)
4. Result: 0 rows returned
5. Retry: Still uses table logic (no learning)

### 3.3 No Learning

**What it is:** The system cannot learn from successful queries.

**Current State:**
- Static `FEW_SHOT_EXAMPLES` list
- No write-back on success
- No vector retrieval from past successes

---

## 4. Implementation Phases

---

### Phase 1: Topology NEV (Path-Level Verification)

**Status:** [ ] Not Started  |  [ ] In Progress  |  [ ] Complete

**Goal:** Prevent impossible paths and catch probe mismatches BEFORE query execution.

**Time Estimate:** 1-2 hours

**Files to Modify:**
- `backend/test_multiagent_cypher.py`

**Changes:**

#### 1.1 Add `verify_topology()` Function (NEW)

**Insert Location:** After line 1180 (after `extract_map_literal_keys()`)

```python
def verify_topology(cypher: str, probe: Dict[str, Any]) -> tuple[bool, str, list]:
    """
    Verify Cypher uses valid graph topology based on actual Neo4j schema.

    Features:
    - Allows Cell->Cell (SAME_ROW/SAME_COL are valid)
    - Includes MergedCell support
    - Checks relationship direction
    - Validates against Structural Probe results

    Returns: (is_valid, corrected_cypher_or_empty, violations)
    """
    violations = []

    # =================================================================
    # CHECK 1: Invalid Direct Connections
    # =================================================================
    invalid_patterns = [
        # Table cannot connect to Line/Section/Word/KV
        (r'\(:?Table\).*-\[.*\]->.*\(:?Line\)', "Table cannot connect directly to Line"),
        (r'\(:?Table\).*-\[.*\]->.*\(:?Section\)', "Table cannot connect directly to Section"),
        (r'\(:?Table\).*-\[.*\]->.*\(:?Word\)', "Table cannot connect directly to Word"),
        (r'\(:?Table\).*-\[.*\]->.*\(:?KV\)', "Table cannot connect directly to KV"),

        # Line cannot connect to Cell/Table
        (r'\(:?Line\).*-\[.*\]->.*\(:?Cell\)', "Line cannot connect directly to Cell"),
        (r'\(:?Line\).*-\[.*\]->.*\(:?Table\)', "Line cannot connect directly to Table"),

        # Document must go through Page
        (r'\(:?Document\).*-\[.*\]->.*\(:?Cell\)', "Document cannot connect directly to Cell - use Document->Page->Table->Cell"),
        (r'\(:?Document\).*-\[.*\]->.*\(:?Line\)', "Document cannot connect directly to Line - use Document->Page->Line"),
        (r'\(:?Document\).*-\[.*\]->.*\(:?Table\)', "Document cannot connect directly to Table - use Document->Page->Table"),

        # Leaf nodes cannot connect (except Cell->Cell which is valid via SAME_ROW/SAME_COL)
        (r'\(:?Cell\).*-\[.*\]->.*\(:?Line\)', "Cell cannot connect to Line"),
        (r'\(:?Section\).*-\[.*\]->.*\(:?Cell\)', "Section cannot connect to Cell"),
        (r'\(:?Line\).*-\[.*\]->.*\(:?Section\)', "Line cannot connect to Section"),

        # Direction checks (reversed relationships)
        (r'\(:?Page\).*-\[.*\]->.*\(:?Document\)', "Direction reversed: Page cannot point to Document"),
        (r'\(:?Cell\).*-\[.*\]->.*\(:?Table\)', "Direction reversed: Cell cannot point to Table"),
        (r'\(:?Table\).*-\[.*\]->.*\(:?Page\)', "Direction reversed: Table cannot point to Page"),
        (r'\(:?Line\).*-\[.*\]->.*\(:?Page\)', "Direction reversed: Line cannot point to Page"),
    ]

    for pattern, message in invalid_patterns:
        if re.search(pattern, cypher, re.IGNORECASE):
            violations.append(f"INVALID TOPOLOGY: {message}")
            return False, "", violations

    # =================================================================
    # CHECK 2: Probe Mismatch (Most Critical!)
    # =================================================================
    if probe.get("found_in"):
        # Count where data was found (include MergedCell)
        has_line = any(
            loc["node_type"] == "Line"
            for term_locs in probe["found_in"].values()
            for loc in term_locs
        )
        has_cell = any(
            loc["node_type"] in ["Cell", "MergedCell"]
            for term_locs in probe["found_in"].values()
            for loc in term_locs
        )
        has_section = any(
            loc["node_type"] == "Section"
            for term_locs in probe["found_in"].values()
            for loc in term_locs
        )

        # Check what Cypher is using
        uses_cell = bool(re.search(r':Cell\b', cypher))
        uses_merged_cell = bool(re.search(r':MergedCell\b', cypher))
        uses_table = bool(re.search(r':Table\b', cypher))
        uses_line = bool(re.search(r':Line\b', cypher))
        uses_section = bool(re.search(r':Section\b', cypher))

        # VIOLATION: Data only in Line, but querying Cell/Table
        if has_line and not has_cell and (uses_cell or uses_table or uses_merged_cell) and not uses_line:
            violations.append(
                f"PROBE MISMATCH: Structural Probe shows data exists in Line nodes only, "
                f"but Cypher queries Table/Cell. Use: Page-[:CONTAINS_LINE]->Line"
            )
            return False, "", violations

        # VIOLATION: Data only in Cell, but querying Line
        if has_cell and not has_line and uses_line and not (uses_cell or uses_merged_cell):
            violations.append(
                f"PROBE MISMATCH: Structural Probe shows data exists in Cell nodes only, "
                f"but Cypher queries Line. Use: Page-[:CONTAINS_TABLE]->Table-[:HAS_CELL]->Cell"
            )
            return False, "", violations

    # =================================================================
    # CHECK 3: Validate Relationship Types
    # =================================================================
    valid_relationships = {
        'HAS_PAGE', 'CONTAINS_TABLE', 'HAS_CELL',
        'CONTAINS_SECTION', 'CONTAINS_LINE', 'SAME_ROW', 'SAME_COL'
    }

    used_rels = set(re.findall(r'\[:(\w+)\]', cypher))
    invalid_rels = used_rels - valid_relationships

    if invalid_rels:
        violations.append(
            f"INVALID RELATIONSHIPS: {invalid_rels} do not exist in schema. "
            f"Valid: {valid_relationships}"
        )
        return False, "", violations

    return True, cypher, violations
```

#### 1.2 Integrate into `nev_auditor_agent()`

**Modify Location:** Line 1304 (inside `nev_auditor_agent()`, after `try:`)

**Add this block BEFORE the existing entity extraction:**

```python
def nev_auditor_agent(state: AgentState) -> AgentState:
    """..."""
    logger.info("=" * 60)
    logger.info("AGENT 3.5: NEV AUDITOR (Named Entity Verification)")
    logger.info("=" * 60)

    neo4j_tools = Neo4jTools()
    cypher = state["generated_cypher"]
    original_cypher = cypher
    corrections_made = []

    try:
        # =====================================================================
        # PRIORITY 0: TOPOLOGY CHECK (NEW - Add this FIRST)
        # This catches impossible paths BEFORE we waste time on other checks
        # =====================================================================
        logger.info("Step 0: Topology Verification...")

        is_valid_topology, corrected, topo_violations = verify_topology(
            cypher,
            state.get("structural_probe", {})
        )

        if not is_valid_topology:
            logger.error(f"TOPOLOGY VIOLATION: {topo_violations}")
            state["nev_verified"] = False
            state["validation_feedback"] = "TOPOLOGY ERROR: " + " | ".join(topo_violations)
            state["is_valid"] = False
            state["nev_corrections"] = topo_violations
            neo4j_tools.close()
            return state  # Fail fast - don't even try to execute

        if topo_violations:  # Warnings but not failures
            logger.warning(f"Topology warnings: {topo_violations}")
            corrections_made.extend(topo_violations)

        logger.info("  Topology verification PASSED")

        # =====================================================================
        # STEP 1: DECOMPOSITION - Extract all entities from Cypher
        # (existing code continues here...)
        # =====================================================================
```

#### 1.3 Update State Definition (Optional Enhancement)

**Modify Location:** Line 209 (AgentState class)

**Add new field:**

```python
class AgentState(TypedDict):
    # ... existing fields ...

    # NEV (Named Entity Verification)
    nev_corrections: List[str]
    nev_verified: bool
    topology_valid: bool  # NEW: Track topology validation separately
```

---

### Phase 2: Success Bank (Dynamic Learning)

**Status:** [ ] Not Started  |  [ ] In Progress  |  [ ] Complete

**Goal:** Replace hardcoded `FEW_SHOT_EXAMPLES` with dynamic vector retrieval from successful queries.

**Time Estimate:** 2-3 hours

**Files to Modify/Create:**
- `backend/test_multiagent_cypher.py`
- `backend/scripts/create_success_bank.py` (NEW)

**Changes:**

#### 2.1 Create Weaviate Collection Script (NEW FILE)

**File:** `backend/scripts/create_success_bank.py`

```python
"""
One-time setup script to create CypherSuccessBank collection in Weaviate.

Run this once before using the Success Bank feature:
    python backend/scripts/create_success_bank.py
"""

import requests
import json

WEAVIATE_URL = "http://10.242.190.53:8080"

def create_success_bank():
    """Create the CypherSuccessBank collection in Weaviate."""

    # Delete if exists
    try:
        response = requests.delete(f"{WEAVIATE_URL}/v1/schema/CypherSuccessBank")
        if response.status_code == 200:
            print("Deleted existing CypherSuccessBank collection")
    except:
        pass

    # Create collection schema
    schema = {
        "class": "CypherSuccessBank",
        "description": "Stores successful Cypher queries for few-shot learning",
        "vectorizer": "none",  # We provide our own vectors
        "properties": [
            {
                "name": "user_query",
                "dataType": ["text"],
                "description": "Natural language query from user"
            },
            {
                "name": "cypher_query",
                "dataType": ["text"],
                "description": "Generated Cypher query that succeeded"
            },
            {
                "name": "logical_plan",
                "dataType": ["text"],
                "description": "Step-by-step logical plan"
            },
            {
                "name": "node_types_used",
                "dataType": ["text[]"],
                "description": "Node types used in Cypher (Cell, Line, etc.)"
            },
            {
                "name": "relationship_path",
                "dataType": ["text"],
                "description": "Main relationship chain (e.g., HAS_PAGE->CONTAINS_TABLE->HAS_CELL)"
            },
            {
                "name": "structural_signature",
                "dataType": ["text"],
                "description": "JSON of structural probe results"
            },
            {
                "name": "chunk_types_seen",
                "dataType": ["text[]"],
                "description": "Chunk types from Weaviate search"
            },
            {
                "name": "accuracy_score",
                "dataType": ["number"],
                "description": "Success score (0.0 to 1.0)"
            },
            {
                "name": "process_id",
                "dataType": ["text"],
                "description": "Document UUID"
            },
            {
                "name": "result_count",
                "dataType": ["int"],
                "description": "Number of rows returned"
            },
            {
                "name": "iterations_used",
                "dataType": ["int"],
                "description": "Number of retry iterations (1 = first try success)"
            },
            {
                "name": "created_at",
                "dataType": ["date"],
                "description": "Timestamp of creation"
            }
        ]
    }

    response = requests.post(
        f"{WEAVIATE_URL}/v1/schema",
        json=schema,
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        print("Successfully created CypherSuccessBank collection!")
        print(json.dumps(schema, indent=2))
    else:
        print(f"Failed to create collection: {response.status_code}")
        print(response.text)


def verify_collection():
    """Verify the collection was created correctly."""
    response = requests.get(f"{WEAVIATE_URL}/v1/schema/CypherSuccessBank")

    if response.status_code == 200:
        print("\nCollection verified:")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"Collection not found: {response.status_code}")


if __name__ == "__main__":
    create_success_bank()
    verify_collection()
```

#### 2.2 Add Auto-Write Trigger to `validator_agent()`

**Modify Location:** Line 1854 (inside `validator_agent()`, after `state["is_valid"] = True`)

**Add this block after successful validation:**

```python
        # Check 6: Results look valid
        else:
            # ... existing meaningful_values check ...

            if has_meaningful_values:
                state["is_valid"] = True
                logger.info("Results validated successfully!")

                # =====================================================================
                # NEW: AUTO-WRITE TO SUCCESS BANK (on first-try success)
                # =====================================================================
                if state.get("iteration", 1) == 1:
                    logger.info("Writing to Success Bank (first-try success)...")
                    _write_to_success_bank(state)
```

**Add this helper function (before `validator_agent()`):**

```python
def _write_to_success_bank(state: AgentState) -> None:
    """
    Write successful query to CypherSuccessBank for future retrieval.

    Only called on first-try successes (iteration == 1) to ensure quality.
    """
    from datetime import datetime

    weaviate_tools = WeaviateTools()

    try:
        # Extract node types (include MergedCell)
        node_types = list(set(re.findall(r':(\w+)(?:\s*[\{\)\]])', state["generated_cypher"])))
        valid_node_types = ['Document', 'Page', 'Table', 'Cell', 'Line', 'Section', 'KV', 'MergedCell']
        node_types = [n for n in node_types if n in valid_node_types]

        # Extract main relationship path
        rels = re.findall(r'\[:(\w+)\]', state["generated_cypher"])
        rel_path = "->".join(rels) if rels else "unknown"

        # Generate embedding for query
        query_embedding = weaviate_tools.generate_embedding(state["user_query"])

        if not query_embedding:
            logger.warning("Failed to generate embedding for Success Bank")
            return

        success_entry = {
            "user_query": state["user_query"],
            "cypher_query": state["generated_cypher"],
            "logical_plan": state.get("logical_plan", ""),
            "node_types_used": node_types,
            "relationship_path": rel_path,
            "structural_signature": json.dumps(state.get("structural_probe", {})),
            "chunk_types_seen": [c.get("chunk_type", "") for c in state.get("weaviate_chunks", [])[:5]],
            "accuracy_score": 1.0,
            "process_id": state["process_id"],
            "result_count": state.get("result_count", 0),
            "iterations_used": state.get("iteration", 1),
            "created_at": datetime.now().isoformat()
        }

        # POST to Weaviate with timeout
        response = requests.post(
            f"{WEAVIATE_URL}/v1/objects",
            json={
                "class": "CypherSuccessBank",
                "properties": success_entry,
                "vector": query_embedding
            },
            timeout=5  # Don't block if Weaviate is slow
        )

        if response.status_code == 200:
            logger.info("Successfully wrote to CypherSuccessBank!")
        else:
            logger.warning(f"Failed to write to Success Bank: {response.text}")

    except requests.Timeout:
        logger.warning("Success Bank write timed out (non-critical)")
    except Exception as e:
        logger.warning(f"Success Bank write failed (non-critical): {e}")
```

#### 2.3 Replace `retrieve_similar_examples()` Function

**Modify Location:** Line 727 (replace entire function)

```python
def retrieve_similar_examples(
    query: str,
    process_id: str = None,
    probe: Dict = None,
    top_k: int = 3
) -> List[Dict]:
    """
    Retrieve similar examples from CypherSuccessBank using vector similarity.

    UPGRADED: Uses dynamic vector retrieval with structural compatibility check.
    Falls back to hardcoded FEW_SHOT_EXAMPLES if Success Bank is empty.

    Args:
        query: User's natural language query
        process_id: Document UUID (optional, for filtering)
        probe: Structural probe results (for node type filtering)
        top_k: Number of examples to return

    Returns:
        List of similar examples with question, cypher, plan, node_types
    """
    weaviate_tools = WeaviateTools()

    try:
        # Generate query embedding
        query_embedding = weaviate_tools.generate_embedding(query)
        if not query_embedding:
            logger.warning("Failed to generate embedding, using fallback examples")
            return _fallback_keyword_examples(query, top_k)

        # Determine required node type from probe
        node_type_filter = None
        if probe and probe.get("found_in"):
            has_line = any(
                loc["node_type"] == "Line"
                for locs in probe["found_in"].values()
                for loc in locs
            )
            has_cell = any(
                loc["node_type"] in ["Cell", "MergedCell"]
                for locs in probe["found_in"].values()
                for loc in locs
            )

            if has_line and not has_cell:
                node_type_filter = "Line"
            elif has_cell and not has_line:
                node_type_filter = "Cell"

        # Query Success Bank
        graphql_query = f'''
        {{
            Get {{
                CypherSuccessBank(
                    nearVector: {{ vector: {json.dumps(query_embedding)} }}
                    where: {{ path: ["accuracy_score"], operator: GreaterThan, valueNumber: 0.7 }}
                    limit: {top_k * 2}
                ) {{
                    user_query
                    cypher_query
                    logical_plan
                    node_types_used
                    relationship_path
                    accuracy_score
                    _additional {{ distance }}
                }}
            }}
        }}
        '''

        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": graphql_query},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("data", {}).get("Get", {}).get("CypherSuccessBank", [])

            if results:
                logger.info(f"Retrieved {len(results)} examples from Success Bank")

                # === STRUCTURAL COMPATIBILITY CHECK ===
                if node_type_filter:
                    compatible = []
                    for r in results:
                        example_nodes = r.get("node_types_used", [])
                        if node_type_filter in example_nodes:
                            compatible.append(r)

                    if compatible:
                        results = compatible
                        logger.info(f"Filtered to {len(results)} {node_type_filter}-compatible examples")
                    else:
                        logger.warning(f"No {node_type_filter}-compatible examples in Success Bank, using fallback")
                        return _fallback_keyword_examples(query, top_k)

                # Convert to expected format
                return [
                    {
                        "question": r["user_query"],
                        "cypher": r["cypher_query"],
                        "plan": r.get("logical_plan", ""),
                        "node_types": r.get("node_types_used", []),
                        "intent": "dynamic"  # From Success Bank
                    }
                    for r in results[:top_k]
                ]

        logger.warning("Success Bank empty or error, using fallback")
        return _fallback_keyword_examples(query, top_k)

    except requests.Timeout:
        logger.warning("Success Bank retrieval timed out, using fallback")
        return _fallback_keyword_examples(query, top_k)
    except Exception as e:
        logger.warning(f"Success Bank retrieval failed: {e}, using fallback")
        return _fallback_keyword_examples(query, top_k)


def _fallback_keyword_examples(query: str, top_k: int) -> List[Dict]:
    """
    Fallback to hardcoded FEW_SHOT_EXAMPLES using keyword matching.

    This is the original logic - used when Success Bank is unavailable.
    """
    query_lower = query.lower()
    scored_examples = []

    # Generic intent keywords
    generic_intents = {
        'simple_search': ['find', 'search', 'where', 'contains', 'look'],
        'table_extraction': ['table', 'rows', 'all rows', 'entire'],
        'column_extraction': ['column', 'header', 'values from', 'extract column'],
        'row_extraction': ['row', 'by label', 'row where', 'row with'],
        'line_extraction': ['line', 'text', 'paragraph', 'not table']
    }

    for example in FEW_SHOT_EXAMPLES:
        score = 0
        example_q = example["question"].lower()
        example_intent = example.get("intent", "")

        # Score based on keyword overlap
        query_words = set(query_lower.split())
        example_words = set(example_q.split())
        common_words = query_words.intersection(example_words)
        score = len(common_words) * 2

        # Boost for matching intents
        if example_intent in generic_intents:
            for kw in generic_intents[example_intent]:
                if kw in query_lower:
                    score += 3

        # Boost for node type hints
        node_types = example.get("node_types", [])
        if "Cell" in node_types and ("table" in query_lower or "column" in query_lower or "row" in query_lower):
            score += 2
        if "Line" in node_types and ("text" in query_lower or "line" in query_lower or "paragraph" in query_lower):
            score += 2

        scored_examples.append((score, example))

    scored_examples.sort(key=lambda x: x[0], reverse=True)
    return [ex for score, ex in scored_examples[:top_k] if score > 0]
```

#### 2.4 Update `context_gatherer_agent()` to Pass Probe to Retrieval

**Modify Location:** Line 935 (inside `context_gatherer_agent()`)

**Change this:**
```python
similar_examples = retrieve_similar_examples(state["user_query"], top_k=2)
```

**To this:**
```python
similar_examples = retrieve_similar_examples(
    query=state["user_query"],
    process_id=state["process_id"],
    probe=probe_result,  # Pass structural probe for filtering
    top_k=2
)
```

---

### Phase 3: Hard Constraints Injection

**Status:** [ ] Not Started  |  [ ] In Progress  |  [ ] Complete

**Goal:** Transform soft hints into mandatory directives the LLM cannot ignore.

**Time Estimate:** 1 hour

**Files to Modify:**
- `backend/test_multiagent_cypher.py`

**Changes:**

#### 3.1 Add `extract_hard_constraints()` Function (NEW)

**Insert Location:** After `verify_topology()` function

```python
def extract_hard_constraints(probe: Dict, chunks: List[Dict]) -> Dict:
    """
    Generate MANDATORY constraints from metadata.

    These are not hints - they are laws the LLM must follow.
    Violation results in 0 rows returned.

    Args:
        probe: Structural probe results from Neo4j
        chunks: Weaviate chunks with chunk_type metadata

    Returns:
        Dict with primary_node, forbidden_nodes, required_path, reasoning
    """
    constraints = {
        "primary_node": None,
        "forbidden_nodes": [],
        "required_path": None,
        "reasoning": []
    }

    # =================================================================
    # Extract constraints from Structural Probe
    # =================================================================
    if probe.get("found_in"):
        line_count = sum(
            loc["count"] for locs in probe["found_in"].values()
            for loc in locs if loc["node_type"] == "Line"
        )
        cell_count = sum(
            loc["count"] for locs in probe["found_in"].values()
            for loc in locs if loc["node_type"] in ["Cell", "MergedCell"]
        )
        section_count = sum(
            loc["count"] for locs in probe["found_in"].values()
            for loc in locs if loc["node_type"] == "Section"
        )

        # CASE 1: Data only in Line nodes
        if line_count > 0 and cell_count == 0:
            constraints["primary_node"] = "Line"
            constraints["forbidden_nodes"] = ["Cell", "Table", "MergedCell"]
            constraints["required_path"] = "Document-[:HAS_PAGE]->Page-[:CONTAINS_LINE]->Line"
            constraints["reasoning"].append(
                f"Neo4j probe: {line_count} matches in Line nodes, 0 in Cell nodes"
            )

        # CASE 2: Data only in Cell nodes
        elif cell_count > 0 and line_count == 0:
            constraints["primary_node"] = "Cell"
            constraints["forbidden_nodes"] = ["Line"]
            constraints["required_path"] = "Document-[:HAS_PAGE]->Page-[:CONTAINS_TABLE]->Table-[:HAS_CELL]->Cell"
            constraints["reasoning"].append(
                f"Neo4j probe: {cell_count} matches in Cell nodes, 0 in Line nodes"
            )

        # CASE 3: Data in BOTH Cell and Line
        elif cell_count > 0 and line_count > 0:
            constraints["primary_node"] = "BOTH"
            constraints["required_path"] = "Use Page as join point: (p:Page)-[:CONTAINS_TABLE]->(t), (p)-[:CONTAINS_LINE]->(l)"
            constraints["reasoning"].append(
                f"Data in BOTH: {cell_count} Cell matches, {line_count} Line matches - use Page as join"
            )

        # CASE 4: Data in Section nodes
        if section_count > 0 and cell_count == 0 and line_count == 0:
            constraints["primary_node"] = "Section"
            constraints["forbidden_nodes"] = ["Cell", "Table", "Line"]
            constraints["required_path"] = "Document-[:HAS_PAGE]->Page-[:CONTAINS_SECTION]->Section"
            constraints["reasoning"].append(
                f"Neo4j probe: {section_count} matches in Section nodes only"
            )

    # =================================================================
    # Extract hints from Weaviate chunk_type
    # =================================================================
    if chunks:
        chunk_types = [c.get("chunk_type", "").lower() for c in chunks]
        table_chunks = sum(1 for ct in chunk_types if "table" in ct)
        text_chunks = sum(1 for ct in chunk_types if "text" in ct or "line" in ct)

        if text_chunks > 0 and table_chunks == 0:
            constraints["reasoning"].append(
                f"Weaviate chunks: {text_chunks} text/line chunks, 0 table chunks"
            )
        elif table_chunks > 0 and text_chunks == 0:
            constraints["reasoning"].append(
                f"Weaviate chunks: {table_chunks} table chunks, 0 text chunks"
            )

    return constraints


def format_constraint_block(constraints: Dict) -> str:
    """
    Format constraints as a prominent block for the LLM prompt.

    Uses box-drawing characters to make constraints IMPOSSIBLE to ignore.
    """
    if not constraints["primary_node"]:
        return ""

    # Build reasoning lines
    reasoning_lines = ""
    for r in constraints["reasoning"]:
        reasoning_lines += f"  - {r}\n"

    forbidden = ', '.join(constraints['forbidden_nodes']) if constraints['forbidden_nodes'] else 'None'

    block = f"""
+==============================================================================+
|                    MANDATORY CONSTRAINTS (VIOLATION = 0 ROWS)                |
+==============================================================================+
| PRIMARY NODE TYPE:  {constraints['primary_node']:<55} |
| FORBIDDEN NODES:    {forbidden:<55} |
| REQUIRED PATH:      {(constraints['required_path'] or 'See probe')[:55]:<55} |
+------------------------------------------------------------------------------+
| REASONING:                                                                   |
{reasoning_lines}+==============================================================================+

>>> WARNING: FAILURE TO FOLLOW THESE CONSTRAINTS WILL RESULT IN ZERO ROWS <<<
>>> DO NOT USE {forbidden} NODES FOR THIS QUERY <<<
"""
    return block
```

#### 3.2 Modify `logic_planner_agent()` to Inject Constraints

**Modify Location:** Line 1023 (inside `logic_planner_agent()`)

**Add constraint extraction and injection:**

```python
def logic_planner_agent(state: AgentState) -> AgentState:
    """..."""
    logger.info("=" * 60)
    logger.info("AGENT 2: LOGIC-FIRST PLANNER (with Hard Constraints)")
    logger.info("=" * 60)

    # Check for previous feedback
    feedback = state.get("validation_feedback", "")
    iteration = state.get("iteration", 1)

    # =================================================================
    # NEW: Extract and format hard constraints
    # =================================================================
    constraints = extract_hard_constraints(
        state.get("structural_probe", {}),
        state.get("weaviate_chunks", [])
    )
    constraint_block = format_constraint_block(constraints)

    if constraint_block:
        logger.info(f"Hard constraints: PRIMARY={constraints['primary_node']}, FORBIDDEN={constraints['forbidden_nodes']}")

    # Build few-shot examples section
    examples_section = ""
    if state.get("similar_examples"):
        examples_section = "\n=== SIMILAR SUCCESSFUL QUERIES ===\n"
        for i, ex in enumerate(state["similar_examples"], 1):
            examples_section += f"""
EXAMPLE {i}:
Question: {ex['question']}
Node Types Used: {ex.get('node_types', ['unknown'])}
Plan Used:
{ex.get('plan', 'N/A')}
---
"""

    # Get structural probe context
    probe_context = state.get("probe_context", "")

    # Build the planning prompt WITH HARD CONSTRAINTS
    plan_prompt = f"""You are a Cypher query planning expert. Your task is to create a LOGICAL PLAN for querying Neo4j.

DO NOT WRITE ANY CYPHER CODE. Only write a step-by-step plan in plain English.

USER QUERY: {state["user_query"]}
{constraint_block}
=== DOCUMENT CONTEXT (from Weaviate) ===
{state.get("weaviate_context", "No context")}

{probe_context}
{examples_section}

=== FILTERED NEO4J SCHEMA ===
{state.get("filtered_schema", "No schema")}

=== ACTUAL DATA SAMPLES FROM NEO4J ===
{state.get("data_snippet", "No data")}

{("PREVIOUS ATTEMPT FAILED WITH:" + chr(10) + feedback + chr(10) + "Adjust your plan to fix this issue.") if feedback else ""}

TASK: Write a numbered step-by-step plan that explains:
1. Which NODE TYPE to use ({constraints['primary_node'] or 'Cell, Line, or both'}) based on the CONSTRAINTS above
2. What relationship path to use (MUST follow REQUIRED PATH if specified)
3. How to identify the correct rows/data (be specific about row_index if using Cell)
4. How to filter/match the data
5. How to structure the output

CRITICAL RULES:
- You MUST use the PRIMARY NODE TYPE specified in MANDATORY CONSTRAINTS
- You MUST NOT use any FORBIDDEN NODES
- If PRIMARY NODE is Line: use 'text' and 'line_id' properties (no row_index/col_index)
- If PRIMARY NODE is Cell: use 'text', 'row_index', 'col_index' properties
- If PRIMARY NODE is BOTH: use Page as join point between tables and lines

Write your plan now (NO CYPHER CODE):"""

    plan = call_claude(plan_prompt, MODELS["planner"], max_tokens=1500)
    state["logical_plan"] = plan

    # ... rest of existing code ...
```

---

## 5. Code Snippets

### Quick Reference: Key Functions

| Function | Location | Purpose |
|----------|----------|---------|
| `verify_topology()` | After line 1180 | Validates graph topology before execution |
| `extract_hard_constraints()` | After `verify_topology()` | Extracts mandatory constraints from probe |
| `format_constraint_block()` | After `extract_hard_constraints()` | Formats constraints for LLM prompt |
| `_write_to_success_bank()` | Before `validator_agent()` | Writes successful queries to Weaviate |
| `retrieve_similar_examples()` | Line 727 (replace) | Vector retrieval from Success Bank |
| `_fallback_keyword_examples()` | After `retrieve_similar_examples()` | Keyword-based fallback |

### Import Additions

Add to imports at top of file:

```python
from datetime import datetime  # For Success Bank timestamps
```

---

## 6. Testing Checklist

### Phase 1 Tests
- [ ] Test with Line-only document (should use Line path)
- [ ] Test with Cell-only document (should use Cell path)
- [ ] Test with mixed document (should use Page as join)
- [ ] Test invalid topology detection (Table->Line should fail)
- [ ] Test direction reversal detection (Page->Document should fail)

### Phase 2 Tests
- [ ] Create Success Bank collection (run setup script)
- [ ] Verify collection exists in Weaviate
- [ ] Test auto-write on first-try success
- [ ] Test vector retrieval from Success Bank
- [ ] Test fallback when Success Bank is empty
- [ ] Test structural compatibility filtering

### Phase 3 Tests
- [ ] Test constraint extraction with Line-only probe
- [ ] Test constraint extraction with Cell-only probe
- [ ] Test constraint extraction with mixed probe
- [ ] Verify constraint block appears in planner prompt
- [ ] Verify LLM follows constraints (no forbidden nodes in output)

---

## 7. Progress Tracking

### Phase 1: Topology NEV
| Task | Status | Date | Notes |
|------|--------|------|-------|
| Add `verify_topology()` function | [x] | 2026-02-12 | Added at line 1281 |
| Integrate into `nev_auditor_agent()` | [x] | 2026-02-12 | Added as Step 0 at line 1436 |
| Test with Line document | [x] | 2026-02-12 | Probe mismatch detection works |
| Test with Cell document | [x] | 2026-02-12 | Valid paths pass correctly |
| Test invalid topology detection | [x] | 2026-02-12 | Table->Line, invalid rels caught |

### Phase 2: Success Bank
| Task | Status | Date | Notes |
|------|--------|------|-------|
| Create setup script | [x] | 2026-02-12 | `scripts/create_success_bank.py` |
| Run setup script (create collection) | [x] | 2026-02-12 | CypherSuccessBank collection created |
| Add `_write_to_success_bank()` | [x] | 2026-02-12 | Added at line 1828 |
| Replace `retrieve_similar_examples()` | [x] | 2026-02-12 | Upgraded with vector retrieval |
| Update `context_gatherer_agent()` | [x] | 2026-02-12 | Now passes probe to retrieval |
| Test auto-write | [x] | 2026-02-12 | Triggers on first-try success |
| Test vector retrieval | [x] | 2026-02-12 | Falls back to keyword if empty |

### Phase 3: Hard Constraints
| Task | Status | Date | Notes |
|------|--------|------|-------|
| Add `extract_hard_constraints()` | [x] | 2026-02-12 | Added at line 1536 |
| Add `format_constraint_block()` | [x] | 2026-02-12 | Added at line 1629 |
| Modify `logic_planner_agent()` | [x] | 2026-02-12 | Now includes constraint block |
| Test constraint injection | [x] | 2026-02-12 | Line/Cell/Mixed all work |
| Verify LLM compliance | [ ] | | Needs real-world testing |

### Phase 4: Multi-Page Query Validation (NEW)
| Task | Status | Date | Notes |
|------|--------|------|-------|
| Add `analyze_expected_row_count()` | [x] | 2026-02-12 | Detects "each page", "all pages" keywords |
| Integrate into `validator_agent()` | [x] | 2026-02-12 | Added as Step 3.5 + Check 2.5 |
| Add multi-page instructions to planner | [x] | 2026-02-12 | Warns against global LIMIT |
| Add multi-page instructions to generator | [x] | 2026-02-12 | Rule 6 added |
| Test with Query 14 | [ ] | | Pending |

**Why This Was Needed:**
Query "Get second Count row with Project Name for each page" was returning only 1 row instead of 9 rows (one per page). The generated Cypher had a `LIMIT 1` at the end that acted globally instead of per-page. This new validation:
1. Detects multi-page keywords in user query
2. Counts pages in document
3. Fails validation if result count < expected_min
4. Provides specific feedback about the LIMIT bug

---

## Appendix A: Expected Results

| Metric | Before | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|--------|---------------|---------------|---------------|
| Table documents | 90% | 92% | 95% | 99% |
| Line documents | 40% | 75% | 85% | 95% |
| Mixed documents | 50% | 70% | 80% | 90% |
| Avg iterations | 2.5 | 2.0 | 1.5 | 1.2 |
| Topology errors | Undetected | Caught | Caught | Caught |

---

## Appendix B: Rollback Instructions

If any phase causes issues, rollback by:

1. **Phase 1:** Remove `verify_topology()` call from `nev_auditor_agent()`
2. **Phase 2:** Revert `retrieve_similar_examples()` to original keyword-based version
3. **Phase 3:** Remove `constraint_block` from planner prompt

Each phase is independent and can be rolled back without affecting others.

---

**Document maintained by:** Claude Code
**Last updated:** February 12, 2026
