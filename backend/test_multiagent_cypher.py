"""
Multi-Agent Dynamic Cypher Generation with Few-Shot + Logic-First Pipeline

IMPROVED ARCHITECTURE based on Text-to-Cypher research:

1. FEW-SHOT RETRIEVAL - Retrieve similar (question, cypher, explanation) from vector DB
2. SCHEMA LINKING - Provide ONLY relevant nodes/relationships (filtered)
3. SUB-GRAPH SNIPPETS - Show actual JSON data samples from Neo4j
4. LOGIC-FIRST PLANNING - Force step-by-step plan BEFORE Cypher code
5. CYPHER GENERATION - Generate Cypher with all context
6. SELF-CORRECTION LOOP - Feed errors back with specific guidance

Pipeline Flow:
+------------------------------------------------------------------+
| 1. WEAVIATE SEARCH → Find relevant chunks + column headers       |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 2. FEW-SHOT RETRIEVAL → Find similar (question, cypher) pairs    |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 3. SCHEMA LINKING → Extract ONLY relevant nodes from schema      |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 4. SUB-GRAPH SNIPPET → Get actual JSON data samples from Neo4j   |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 5. LOGIC-FIRST PLANNER → Generate step-by-step plan (no Cypher)  |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 6. CYPHER GENERATOR → Convert plan to Cypher query               |
+------------------------------------------------------------------+
                        |
                        v
+------------------------------------------------------------------+
| 7. VALIDATOR + SELF-CORRECTION → Execute, validate, retry if bad |
+------------------------------------------------------------------+

Created: February 11, 2026
"""

import os
import sys
import json
import logging
import re
from typing import Dict, List, Any, Optional, TypedDict
from difflib import SequenceMatcher

import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv

# LangGraph imports
from langgraph.graph import StateGraph, END

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

NEO4J_URI = "bolt://10.242.190.53:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = REDACTED

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://10.242.190.53:8080")

ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Model selection
MODELS = {
    "planner": "claude-haiku-4-5-20251001",       # Fast for planning
    "generator": "claude-sonnet-4-5-20250929",   # Best for code generation
    "validator": "claude-haiku-4-5-20251001",    # Fast for validation
}

# Test configuration
PROCESS_ID = "b3b00a67-2cf5-41c1-b0a7-ce0174828293"
USER_QUERY = "what is the number for the 3 minor defect row"

# =============================================================================
# FEW-SHOT EXAMPLES (GENERIC - No Domain-Specific Examples)
# =============================================================================

# GENERIC patterns that work for ANY document type
# These are STRUCTURAL patterns, not domain-specific (no ECD, COA, concentration, etc.)
FEW_SHOT_EXAMPLES = [
    {
        "question": "Find all cells containing a specific term and return values with page numbers",
        "intent": "simple_search",
        "node_types": ["Cell", "Line"],  # Works for both
        "plan": """
1. Search for cells/lines where text contains the search term (case-insensitive)
2. Return the text and page number
3. Order by page number
        """,
        "cypher": """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
WHERE toLower(coalesce(c.text, '')) CONTAINS toLower($search_term)
RETURN p.page_num AS page, c.text AS value, c.row_index AS row, c.col_index AS col
ORDER BY p.page_num, c.row_index
        """,
        "expected_rows": None,
        "explanation": "Generic cell search with text matching - adapt $search_term to user query."
    },
    {
        "question": "Get all rows from a table on a specific page",
        "intent": "table_extraction",
        "node_types": ["Cell"],
        "plan": """
1. Match tables on the specified page
2. Get all cells from those tables
3. Order by row_index and col_index
4. Return structured row data
        """,
        "cypher": """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page {page_num: $page_num})-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
WITH c ORDER BY c.row_index, c.col_index
RETURN c.row_index AS row, collect({col: c.col_index, text: c.text}) AS cells
ORDER BY row
        """,
        "expected_rows": None,
        "explanation": "Extract all rows from a specific page table."
    },
    {
        "question": "Extract column values where header contains a specific term",
        "intent": "column_extraction",
        "node_types": ["Cell"],
        "plan": """
1. Find header cells in row 0 or 1 where text contains the header term
2. Get the col_index of those header cells
3. Get all cells in the same column (same col_index) with row_index > 1
4. Return values with their row labels
        """,
        "cypher": """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
WHERE header.row_index IN [0, 1] AND toLower(coalesce(header.text, '')) CONTAINS toLower($header_term)
WITH t, p, header.col_index AS targetCol, header.text AS headerText
MATCH (t)-[:HAS_CELL]->(c:Cell)
WHERE c.col_index = targetCol AND c.row_index > 1
OPTIONAL MATCH (t)-[:HAS_CELL]->(label:Cell {row_index: c.row_index, col_index: 0})
RETURN p.page_num AS page, headerText AS column_header, label.text AS row_label, c.text AS value
ORDER BY p.page_num, c.row_index
        """,
        "expected_rows": None,
        "explanation": "Find header by term, then extract all values in that column."
    },
    {
        "question": "Find a row by label and extract all columns from that row",
        "intent": "row_extraction",
        "node_types": ["Cell"],
        "plan": """
1. Find cells in column 0 or 1 containing the row label
2. Get the row_index of that cell
3. Get all cells in the same row (same row_index)
4. Return all column values for that row
        """,
        "cypher": """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(label:Cell)
WHERE label.col_index IN [0, 1] AND toLower(coalesce(label.text, '')) CONTAINS toLower($row_label)
WITH t, p, label.row_index AS targetRow, label.text AS rowLabel
MATCH (t)-[:HAS_CELL]->(c:Cell {row_index: targetRow})
WITH p, rowLabel, c ORDER BY c.col_index
RETURN p.page_num AS page, rowLabel AS row_label, collect({col: c.col_index, text: c.text}) AS row_data
ORDER BY p.page_num
        """,
        "expected_rows": None,
        "explanation": "Find row by label term, then extract all columns from that row."
    },
    {
        "question": "Extract data from Line nodes (text paragraphs, not tables)",
        "intent": "line_extraction",
        "node_types": ["Line"],
        "plan": """
1. Search Line nodes for text containing the search term
2. Return line text with page number
3. Order by page
        """,
        "cypher": """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_LINE]->(l:Line)
WHERE toLower(coalesce(l.text, '')) CONTAINS toLower($search_term)
RETURN p.page_num AS page, l.text AS line_text
ORDER BY p.page_num
        """,
        "expected_rows": None,
        "explanation": "Search in Line nodes (non-table text) - use when data is in paragraphs."
    }
]

# =============================================================================
# STATE DEFINITION
# =============================================================================

class AgentState(TypedDict):
    """State passed between agents in the graph."""
    # Input
    user_query: str
    process_id: str

    # Weaviate context
    weaviate_chunks: List[Dict]
    weaviate_headers: List[str]
    weaviate_context: str

    # NEW: Structural Probe results (where data actually exists)
    structural_probe: Dict[str, Any]
    probe_context: str

    # Few-shot retrieval
    similar_examples: List[Dict]

    # Schema linking (filtered)
    filtered_schema: str

    # Sub-graph snippet (actual data)
    data_snippet: str

    # Logic-first plan
    logical_plan: str

    # Generated Cypher
    generated_cypher: str

    # Validation
    execution_results: List[Dict]
    result_count: int
    is_valid: bool
    validation_feedback: str
    execution_error: str

    # NEV (Named Entity Verification)
    nev_corrections: List[str]
    nev_verified: bool

    # Control flow
    iteration: int
    max_iterations: int
    final_answer: str
    error: str

    # Interpreter Agent output (NEW - converts JSON to natural language)
    natural_answer: str
    output_type: str  # "TABLE" or "TEXT" - decides whether to show table

    # Query Reformulation (NEW - expands vague queries using document context)
    original_query: str  # Original user query before reformulation
    reformulated_query: str  # Expanded query with document-specific terms
    was_reformulated: bool  # Whether query was reformulated

    # Query Entity Validation (NEW - validates user query terms against actual data)
    entity_validation: Dict[str, Any]  # Results of entity validation
    validated_entities: List[Dict]  # Valid entities with their locations
    invalid_entities: List[Dict]  # Invalid entities with suggested corrections
    entity_validation_context: str  # Formatted context for Logic Planner

# =============================================================================
# LLM HELPER
# =============================================================================

def call_claude(prompt: str, model: str, max_tokens: int = 4000) -> str:
    """Call Claude via Iliad API."""
    try:
        headers = {
            "x-api-key": ILIAD_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}]
        }

        response = requests.post(
            f"{ILIAD_URL}/anthropic/v1/messages",
            headers=headers,
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            logger.error(f"Iliad API error: {response.status_code} - {response.text}")
            return f"Error: {response.status_code}"

        result = response.json()
        return result.get("content", [{}])[0].get("text", "")

    except Exception as e:
        logger.error(f"LLM call error: {e}")
        return f"Error: {str(e)}"

def strip_code_blocks(text: str) -> str:
    """Remove markdown code blocks from text."""
    # Try to extract content from code blocks
    patterns = [
        r'```cypher\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # If no code blocks, return as-is but strip leading/trailing whitespace
    return text.strip()

# =============================================================================
# WEAVIATE TOOLS
# =============================================================================

class WeaviateTools:
    """Tools for Weaviate exploration."""

    def __init__(self, weaviate_url: str = WEAVIATE_URL):
        self.weaviate_url = weaviate_url
        self.collection_name = "DocumentChunk"

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text."""
        try:
            response = requests.post(
                f"{ILIAD_URL}/api/v1/embed/text-embedding-3-large",
                headers={
                    "x-api-key": ILIAD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"input": [text[:8000]]},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
            return None
        except Exception as e:
            logger.error(f"Embedding error: {e}")
            return None

    def search_chunks(self, query: str, process_id: str, limit: int = 10) -> List[Dict]:
        """Search Weaviate for relevant chunks using hybrid search."""
        query_embedding = self.generate_embedding(query)
        if query_embedding is None:
            logger.error("Failed to generate query embedding")
            return []

        escaped_query = query.replace('"', '\\"')

        graphql_query = f'''
        {{
            Get {{
                {self.collection_name}(
                    hybrid: {{
                        query: "{escaped_query}"
                        alpha: 0.7
                        vector: {json.dumps(query_embedding)}
                    }}
                    where: {{
                        path: ["process_id"],
                        operator: Equal,
                        valueText: "{process_id}"
                    }}
                    limit: {limit}
                ) {{
                    chunk_id
                    page
                    chunk_index
                    chunk_type
                    content
                    cell_grounding
                    markdown
                    _additional {{
                        score
                    }}
                }}
            }}
        }}
        '''

        try:
            response = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                chunks = data.get("data", {}).get("Get", {}).get(self.collection_name, [])
                return chunks
            else:
                logger.error(f"Weaviate search error: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"Weaviate search error: {e}")
            return []

    def extract_headers_from_chunks(self, chunks: List[Dict]) -> List[str]:
        """Extract column headers from chunk cell_grounding."""
        all_headers = []

        for chunk in chunks:
            if chunk.get('chunk_type') != 'table':
                continue

            cell_grounding_str = chunk.get('cell_grounding')
            if not cell_grounding_str:
                continue

            try:
                cell_grounding = json.loads(cell_grounding_str)
                for cell_id, cell_data in cell_grounding.items():
                    row = cell_data.get('row', -1)
                    if row in [0, 1]:  # Header rows
                        header_text = cell_data.get('text', '').strip()
                        if header_text and len(header_text) > 1:
                            all_headers.append(header_text)
            except (json.JSONDecodeError, TypeError):
                continue

        # Deduplicate
        seen = set()
        unique_headers = []
        for h in all_headers:
            h_lower = h.lower()
            if h_lower not in seen:
                seen.add(h_lower)
                unique_headers.append(h)

        return unique_headers

# =============================================================================
# NEO4J TOOLS
# =============================================================================

class Neo4jTools:
    """Tools for Neo4j exploration and execution."""

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    def structural_probe(self, process_id: str, search_terms: List[str]) -> Dict[str, Any]:
        """
        STRUCTURAL PROBE - Find WHERE data actually exists before generating Cypher.

        This is the key fix for the "Table-Centric Bias" problem. Instead of blindly
        assuming data is in Cell nodes, we first probe to find which node type
        actually contains the data.

        Args:
            process_id: Document UUID
            search_terms: List of terms to search for (e.g., ['batch name', 'concentration'])

        Returns:
            Dict with:
            - found_in: Dict mapping search terms to node types where found
            - recommended_path: The relationship path to use for Cypher
            - node_counts: Count of each node type
        """
        probe_result = {
            "found_in": {},
            "node_counts": {},
            "recommended_paths": [],
            "data_locations": []
        }

        with self.driver.session(database="neo4j") as session:
            # Count ALL node types for this document
            node_counts_query = """
                MATCH (d:Document {process_id: $pid})
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
                OPTIONAL MATCH (t)-[:HAS_CELL]->(c:Cell)
                OPTIONAL MATCH (p)-[:CONTAINS_LINE]->(l:Line)
                OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
                RETURN
                    count(DISTINCT p) AS pages,
                    count(DISTINCT t) AS tables,
                    count(DISTINCT c) AS cells,
                    count(DISTINCT l) AS lines,
                    count(DISTINCT s) AS sections
            """
            counts = session.run(node_counts_query, {"pid": process_id}).single()
            probe_result["node_counts"] = {
                "Page": counts["pages"],
                "Table": counts["tables"],
                "Cell": counts["cells"],
                "Line": counts["lines"],
                "Section": counts["sections"]
            }

            # For each search term, find WHERE it exists
            for term in search_terms:
                if len(term) < 2:
                    continue

                term_lower = term.lower()
                found_locations = []

                # Check Cell nodes
                cell_check = session.run("""
                    MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
                    WHERE toLower(coalesce(c.text, '')) CONTAINS $term
                    RETURN 'Cell' as node_type, count(c) as count, collect(DISTINCT p.page_num)[0..3] as sample_pages
                """, {"pid": process_id, "term": term_lower}).single()

                if cell_check and cell_check["count"] > 0:
                    found_locations.append({
                        "node_type": "Cell",
                        "count": cell_check["count"],
                        "sample_pages": cell_check["sample_pages"],
                        "path": "Document -[:HAS_PAGE]-> Page -[:CONTAINS_TABLE]-> Table -[:HAS_CELL]-> Cell"
                    })

                # Check Line nodes
                line_check = session.run("""
                    MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_LINE]->(l:Line)
                    WHERE toLower(coalesce(l.text, '')) CONTAINS $term
                    RETURN 'Line' as node_type, count(l) as count, collect(DISTINCT p.page_num)[0..3] as sample_pages
                """, {"pid": process_id, "term": term_lower}).single()

                if line_check and line_check["count"] > 0:
                    found_locations.append({
                        "node_type": "Line",
                        "count": line_check["count"],
                        "sample_pages": line_check["sample_pages"],
                        "path": "Document -[:HAS_PAGE]-> Page -[:CONTAINS_LINE]-> Line"
                    })

                if found_locations:
                    probe_result["found_in"][term] = found_locations
                    probe_result["data_locations"].extend(found_locations)

            # Determine recommended paths based on what we found
            paths_used = set()
            for term, locations in probe_result["found_in"].items():
                for loc in locations:
                    paths_used.add(loc["path"])

            probe_result["recommended_paths"] = list(paths_used)

        return probe_result

    def get_filtered_schema(self, process_id: str) -> str:
        """
        Get COMPLETE FILTERED schema relevant to the document.

        IMPROVED: Now includes ALL node types (Cell, Line, Section, etc.)
        not just Table/Cell. This prevents Table-Centric Bias.
        """
        with self.driver.session(database="neo4j") as session:
            # Check ALL node types for this document
            doc_info = session.run("""
                MATCH (d:Document {process_id: $pid})
                OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
                OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
                OPTIONAL MATCH (t)-[:HAS_CELL]->(c:Cell)
                OPTIONAL MATCH (p)-[:CONTAINS_LINE]->(l:Line)
                OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
                RETURN
                    count(DISTINCT p) AS pages,
                    count(DISTINCT t) AS tables,
                    count(DISTINCT c) AS cells,
                    count(DISTINCT l) AS lines,
                    count(DISTINCT s) AS sections
            """, {"pid": process_id}).single()

            # Get Table properties (DYNAMICALLY - not hardcoded!)
            table_props = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_TABLE]->(t:Table)
                RETURN keys(t) AS props LIMIT 1
            """, {"pid": process_id}).data()

            # Get Cell properties
            cell_props = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_TABLE]->()-[:HAS_CELL]->(c:Cell)
                RETURN keys(c) AS props LIMIT 1
            """, {"pid": process_id}).data()

            # Get Line properties
            line_props = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_LINE]->(l:Line)
                RETURN keys(l) AS props LIMIT 1
            """, {"pid": process_id}).data()

            # Format Table properties (only show useful ones, filter out bbox)
            table_props_list = table_props[0]['props'] if table_props else ['table_id']
            table_props_useful = [p for p in table_props_list if not p.startswith('bbox_') and p not in ['doc_id', 'page_num']]

            schema = f"""
COMPLETE FILTERED SCHEMA (for this document):

NODES:
- Document (1 node) - has process_id, filename
- Page ({doc_info['pages']} nodes) - has page_num
- Table ({doc_info['tables']} nodes) - properties: {table_props_useful}
- Cell ({doc_info['cells']} nodes) - properties: {cell_props[0]['props'] if cell_props else 'text, row_index, col_index'}
- Line ({doc_info['lines']} nodes) - properties: {line_props[0]['props'] if line_props else 'text, line_id, bbox'}
- Section ({doc_info['sections']} nodes) - has section_id, text

RELATIONSHIP PATHS (use these in your MATCH clauses):

PATH 1 - For TABLE data (structured tables with rows/columns):
  Document -[:HAS_PAGE]-> Page -[:CONTAINS_TABLE]-> Table -[:HAS_CELL]-> Cell
  Use when: Data is in table format with row_index and col_index

PATH 2 - For TEXT/LINE data (paragraphs, labels, free text):
  Document -[:HAS_PAGE]-> Page -[:CONTAINS_LINE]-> Line
  Use when: Data is in text lines, not in tables (e.g., "Batch Name: XYZ" as a label)

PATH 3 - For CROSS-TABLE data on same page:
  MATCH (p:Page)-[:CONTAINS_TABLE]->(t1:Table), (p)-[:CONTAINS_TABLE]->(t2:Table)
  Use when: Need to join data from multiple tables on the same page

KEY PROPERTIES:
- Cell: text, row_index (0-based), col_index (0-based), is_header, bbox_left/top/right/bottom
- Line: text, line_id, bbox_left/top/right/bottom
- Page: page_num

IMPORTANT:
- ALWAYS start with: MATCH (d:Document {{process_id: $process_id}})
- Use toLower(coalesce(node.text, '')) for safe text matching
- row_index and col_index are 0-based integers
- Some data may be in Line nodes, NOT Cell nodes - check both if needed!
"""
            return schema

    def get_data_snippet(self, process_id: str, search_terms: List[str]) -> str:
        """Get actual JSON data snippet from Neo4j."""
        snippets = []

        with self.driver.session(database="neo4j") as session:
            # Get sample rows around key terms
            for term in search_terms[:3]:
                if len(term) < 3:
                    continue

                results = session.run("""
                    MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(target:Cell)
                    WHERE toLower(coalesce(target.text,'')) CONTAINS toLower($term)
                    WITH t, p, target.row_index AS target_row
                    LIMIT 1
                    MATCH (t)-[:HAS_CELL]->(c:Cell)
                    WHERE c.row_index >= target_row - 1 AND c.row_index <= target_row + 2
                    WITH p.page_num AS page, c.row_index AS row, c.col_index AS col, c.text AS text
                    ORDER BY row, col
                    RETURN page, row, collect({col: col, text: text}) AS cells
                    ORDER BY row
                    LIMIT 5
                """, {"pid": process_id, "term": term}).data()

                if results:
                    snippets.append({
                        "search_term": term,
                        "rows": results
                    })

            # =====================================================================
            # CRITICAL: Get cross-table structure for Batch Name
            # Batch Name could be in Cell, Line, or any node type - check all!
            # =====================================================================
            # First try: Check in Cell nodes (table cells)
            batch_name_info = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(label:Cell)
                WHERE toLower(coalesce(label.text,'')) CONTAINS 'batch name'
                OPTIONAL MATCH (t)-[:HAS_CELL]->(value:Cell)
                WHERE value.row_index = label.row_index AND value.col_index = label.col_index + 1
                RETURN p.page_num AS page, 'Cell' AS source_type, t.table_id AS table_id, label.text AS label_text, value.text AS value_text
                ORDER BY p.page_num
                LIMIT 5
            """, {"pid": process_id}).data()

            # Second try: Check in Line nodes (text lines)
            batch_name_lines = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_LINE]->(l:Line)
                WHERE toLower(coalesce(l.text,'')) CONTAINS 'batch'
                RETURN p.page_num AS page, 'Line' AS source_type, l.text AS line_text
                ORDER BY p.page_num
                LIMIT 5
            """, {"pid": process_id}).data()

            if batch_name_info or batch_name_lines:
                # Check for OCR artifacts in Cell data
                cell_has_artifacts = any(
                    "User:" in str(c.get("value_text", "")) or
                    "  " in str(c.get("value_text", ""))
                    for c in batch_name_info
                ) if batch_name_info else False

                quality_note = ""
                if cell_has_artifacts and batch_name_lines:
                    quality_note = "⚠️ CELL DATA HAS OCR ARTIFACTS (e.g., 'User:' appended). USE LINE DATA FOR CLEANER VALUES!"

                snippets.append({
                    "search_term": "BATCH_NAME_LOCATION",
                    "note": f"Batch Name found in both Cell and Line nodes. {quality_note}",
                    "recommendation": "For CLEAN Batch Name value, use LINE nodes (format: 'Batch Name: VALUE'). Extract with: split(l.text, ':')[1]",
                    "cell_data": batch_name_info if batch_name_info else [],
                    "line_data": batch_name_lines if batch_name_lines else []
                })

            # =====================================================================
            # Get page structure - how many tables per page
            # =====================================================================
            page_structure = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
                WITH p.page_num AS page, count(t) AS table_count
                WHERE table_count > 1
                RETURN page, table_count
                ORDER BY page
                LIMIT 5
            """, {"pid": process_id}).data()

            if page_structure:
                snippets.append({
                    "search_term": "PAGE_STRUCTURE",
                    "note": "Pages with MULTIPLE tables - Batch Name and ECD data are in DIFFERENT tables on same page",
                    "data": page_structure
                })

        if not snippets:
            return "No data snippets found."

        return json.dumps(snippets, indent=2, default=str)

    def execute_cypher(self, cypher: str, params: Dict) -> List[Dict]:
        """Execute a Cypher query."""
        with self.driver.session(database="neo4j") as session:
            try:
                results = session.run(cypher, params).data()
                return results
            except Exception as e:
                logger.error(f"Cypher execution error: {e}")
                return [{"error": str(e)}]

    def close(self):
        self.driver.close()

# =============================================================================
# FEW-SHOT RETRIEVAL (Phase 2 - Success Bank Integration)
# =============================================================================

def retrieve_similar_examples(
    query: str,
    process_id: str = None,
    probe: Dict = None,
    top_k: int = 2
) -> List[Dict]:
    """
    Retrieve similar examples from CypherSuccessBank using vector similarity.

    UPGRADED (Phase 2): Uses dynamic vector retrieval with structural compatibility check.
    Falls back to hardcoded FEW_SHOT_EXAMPLES if Success Bank is empty or unavailable.

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

        # Determine required node type from structural probe
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
                logger.info("  Success Bank filter: Line examples preferred")
            elif has_cell and not has_line:
                node_type_filter = "Cell"
                logger.info("  Success Bank filter: Cell examples preferred")

        # Query Success Bank via Weaviate
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
                logger.info(f"  Retrieved {len(results)} examples from Success Bank")

                # === STRUCTURAL COMPATIBILITY CHECK ===
                # If probe says Line, prefer Line examples; if Cell, prefer Cell examples
                if node_type_filter:
                    compatible = []
                    for r in results:
                        example_nodes = r.get("node_types_used", [])
                        if example_nodes and node_type_filter in example_nodes:
                            compatible.append(r)

                    if compatible:
                        results = compatible
                        logger.info(f"  Filtered to {len(results)} {node_type_filter}-compatible examples")
                    else:
                        logger.warning(f"  No {node_type_filter}-compatible examples in Success Bank, using fallback")
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

        logger.info("  Success Bank empty or unavailable, using fallback examples")
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

    # Generic intent keywords (NOT domain-specific)
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

        # Score based on keyword overlap (generic)
        query_words = set(query_lower.split())
        example_words = set(example_q.split())

        common_words = query_words.intersection(example_words)
        score = len(common_words) * 2  # Base score from word overlap

        # Boost for matching GENERIC intents (NOT domain-specific)
        if example_intent in generic_intents:
            intent_keywords = generic_intents[example_intent]
            for kw in intent_keywords:
                if kw in query_lower:
                    score += 3  # Boost for matching intent keywords

        # Boost if node_types match what user might need
        node_types = example.get("node_types", [])
        if "Cell" in node_types and ("table" in query_lower or "column" in query_lower or "row" in query_lower):
            score += 2
        if "Line" in node_types and ("text" in query_lower or "line" in query_lower or "paragraph" in query_lower):
            score += 2

        scored_examples.append((score, example))

    # Sort by score descending
    scored_examples.sort(key=lambda x: x[0], reverse=True)

    # Return top_k examples
    return [ex for score, ex in scored_examples[:top_k] if score > 0]

# =============================================================================
# QUERY ENTITY VALIDATION (Generic - validates ALL user query terms)
# =============================================================================

def extract_entities_from_query(user_query: str) -> List[Dict]:
    """
    Extract all potential entities from user query that need validation.

    Identifies:
    - Column headers (>=1, >=0.5, etc.)
    - Field names (batch name, project name, etc.)
    - Row labels (concentration, count, range, etc.)
    - Numeric patterns that might be column identifiers

    Returns:
        List of dicts with entity text and type
    """
    entities = []
    query_lower = user_query.lower()

    # Pattern 1: Range/threshold patterns like >=0.5, >=1, >=2, etc.
    threshold_pattern = r'[><=≥≤]+\s*\d+(?:\.\d+)?'
    thresholds = re.findall(threshold_pattern, user_query)
    for t in thresholds:
        # Normalize: remove spaces, convert >= to ≥
        normalized = t.replace(' ', '').replace('>=', '≥').replace('<=', '≤')
        entities.append({
            "text": normalized,
            "original": t,
            "type": "column_header",
            "normalized": normalized
        })

    # Pattern 2: Common field names (multi-word)
    field_patterns = [
        r'batch\s*name', r'project\s*name', r'user\s*name', r'file\s*name',
        r'sample\s*id', r'batch\s*id', r'lot\s*number', r'date\s*created',
        r'created\s*by', r'modified\s*by', r'document\s*title'
    ]
    for pattern in field_patterns:
        if re.search(pattern, query_lower):
            match = re.search(pattern, query_lower).group()
            entities.append({
                "text": match,
                "original": match,
                "type": "metadata_field",
                "normalized": match.lower().strip()
            })

    # Pattern 3: Row labels (single words that are common table row names)
    row_labels = ['concentration', 'count', 'range', 'mean', 'mode', 'total',
                  'average', 'sum', 'min', 'max', 'std', 'variance']
    for label in row_labels:
        if label in query_lower:
            entities.append({
                "text": label,
                "original": label,
                "type": "row_label",
                "normalized": label.lower()
            })

    return entities


def validate_entity_against_data(entity: Dict, available_terms: set,
                                  structural_probe: Dict, data_snippet: str) -> Dict:
    """
    Validate a single entity against available data.

    Args:
        entity: Entity dict with text, type, normalized
        available_terms: Set of all available terms from headers/snippet
        structural_probe: Results from structural probe (where data exists)
        data_snippet: JSON string of actual data samples

    Returns:
        Validation result with found status, location, and corrections
    """
    entity_text = entity["normalized"]
    entity_type = entity["type"]

    result = {
        "entity": entity["text"],
        "type": entity_type,
        "found": False,
        "location": None,
        "col_index": None,
        "closest_match": None,
        "action": "USE"
    }

    # Check if entity exists in available terms (fuzzy match)
    # For threshold patterns, normalize for comparison
    for term in available_terms:
        term_normalized = term.lower().replace(' ', '').replace('>=', '≥').replace('<=', '≤')

        # Exact match or close match
        if entity_text == term_normalized or entity_text in term_normalized or term_normalized in entity_text:
            result["found"] = True
            result["location"] = "available_terms"
            break

        # For thresholds, compare numeric values
        if entity_type == "column_header":
            # Extract numeric part
            entity_num = re.search(r'[\d.]+', entity_text)
            term_num = re.search(r'[\d.]+', term_normalized)
            if entity_num and term_num:
                try:
                    if float(entity_num.group()) == float(term_num.group()):
                        result["found"] = True
                        result["location"] = "available_terms"
                        result["closest_match"] = term
                        break
                except ValueError:
                    # Skip terms that can't be parsed as floats (e.g., concatenated OCR artifacts)
                    continue

    # Check in structural probe
    if not result["found"] and structural_probe.get("found_in"):
        for search_term, locations in structural_probe["found_in"].items():
            if entity_text in search_term.lower() or search_term.lower() in entity_text:
                result["found"] = True
                result["location"] = locations[0]["node_type"] if locations else "unknown"
                break

    # If still not found, try to find closest match
    if not result["found"]:
        result["action"] = "REMOVE"
        # Find closest match using simple similarity
        best_match = None
        best_score = 0
        for term in available_terms:
            # Simple containment check
            term_lower = term.lower()
            if entity_type == "column_header":
                # For thresholds, find closest numeric value
                entity_num = re.search(r'[\d.]+', entity_text)
                term_num = re.search(r'[\d.]+', term_lower)
                if entity_num and term_num:
                    try:
                        entity_val = float(entity_num.group())
                        term_val = float(term_num.group())
                        # Closest value
                        diff = abs(entity_val - term_val)
                        if diff < 10 and (best_match is None or diff < best_score):
                            best_score = diff
                            best_match = term
                    except ValueError:
                        # Skip terms that can't be parsed as floats
                        continue
            else:
                # For text fields, use containment
                score = SequenceMatcher(None, entity_text, term_lower).ratio()
                if score > 0.6 and score > best_score:
                    best_score = score
                    best_match = term

        if best_match:
            result["closest_match"] = best_match
            result["action"] = "REPLACE"

    return result


def extract_column_structure_from_snippet(data_snippet: str) -> Dict:
    """
    Extract column structure (headers and indices) from data_snippet JSON.

    Parses the data_snippet to find:
    - Range header row with column names
    - Mapping of column indices to header values

    Returns:
        Dict with columns list and col_indices
    """
    structure = {
        "columns": [],
        "col_indices": [],
        "header_row_found": False
    }

    try:
        snippet_data = json.loads(data_snippet)

        for item in snippet_data:
            if isinstance(item, dict) and "rows" in item:
                for row in item.get("rows", []):
                    cells = row.get("cells", [])
                    # Check if this looks like a Range header row
                    for cell in cells:
                        cell_text = cell.get("text", "")
                        if "range" in cell_text.lower() and ("µm" in cell_text or "um" in cell_text.lower()):
                            # This is the Range row - extract column headers
                            structure["header_row_found"] = True
                            for c in cells:
                                col_idx = c.get("col", 0)
                                col_text = c.get("text", "")
                                if col_idx >= 2 and col_text and col_text != "-":
                                    # Normalize threshold format
                                    col_text_norm = col_text.replace('≥', '>=').strip()
                                    if '>=' in col_text_norm or '≥' in col_text:
                                        structure["columns"].append(col_text)
                                        structure["col_indices"].append(col_idx)
                            break
                    if structure["header_row_found"]:
                        break
            if structure["header_row_found"]:
                break

    except (json.JSONDecodeError, TypeError, KeyError) as e:
        logger.warning(f"Could not parse data_snippet for column structure: {e}")

    return structure


def validate_query_entities(user_query: str, weaviate_headers: List[str],
                           data_snippet: str, structural_probe: Dict) -> Dict:
    """
    GENERIC ENTITY VALIDATION - Validates ALL user query terms against actual data.

    This is the key function that prevents the ">=0.5 not found" type errors by:
    1. Extracting all entities from user query
    2. Validating each against available data (headers, snippet, probe)
    3. Generating corrections for invalid entities
    4. Detecting column structure for table queries

    Args:
        user_query: User's natural language query
        weaviate_headers: Headers extracted from Weaviate chunks
        data_snippet: JSON string of actual data samples from Neo4j
        structural_probe: Results from Neo4j structural probe

    Returns:
        Dict with validated_entities, invalid_entities, corrections, column_structure
    """
    # Step 1: Extract entities from user query
    entities = extract_entities_from_query(user_query)

    # Step 2: Build searchable index from all sources
    available_terms = set()

    # Add Weaviate headers
    for header in weaviate_headers:
        available_terms.add(header)
        available_terms.add(header.lower())

    # Add terms from data_snippet
    try:
        snippet_data = json.loads(data_snippet)
        for item in snippet_data:
            if isinstance(item, dict):
                if "rows" in item:
                    for row in item["rows"]:
                        for cell in row.get("cells", []):
                            text = cell.get("text", "")
                            if text and len(text) > 1:
                                available_terms.add(text)
                                available_terms.add(text.lower())
    except (json.JSONDecodeError, TypeError):
        pass

    # Add terms from structural probe
    if structural_probe.get("found_in"):
        for term in structural_probe["found_in"].keys():
            available_terms.add(term)
            available_terms.add(term.lower())

    # Step 3: Validate each entity
    validated_entities = []
    invalid_entities = []

    for entity in entities:
        validation = validate_entity_against_data(
            entity, available_terms, structural_probe, data_snippet
        )

        if validation["found"]:
            validated_entities.append(validation)
        else:
            invalid_entities.append(validation)

    # Step 4: Extract column structure from data_snippet
    column_structure = extract_column_structure_from_snippet(data_snippet)

    # Step 5: Generate corrections summary
    corrections = []
    for inv in invalid_entities:
        if inv["closest_match"]:
            corrections.append(f"'{inv['entity']}' NOT FOUND → Closest: '{inv['closest_match']}'")
        else:
            corrections.append(f"'{inv['entity']}' NOT FOUND → REMOVED from query")

    return {
        "validated_entities": validated_entities,
        "invalid_entities": invalid_entities,
        "corrections": corrections,
        "column_structure": column_structure,
        "available_terms_count": len(available_terms)
    }


def format_entity_validation_context(validation_result: Dict) -> str:
    """
    Format entity validation results as context block for Logic Planner.

    Creates a clear, structured block that tells the LLM:
    - Which entities are valid and where to find them
    - Which entities are invalid and what corrections to apply
    - Exact column structure to use
    """
    if not validation_result.get("validated_entities") and not validation_result.get("invalid_entities"):
        return ""

    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("QUERY ENTITY VALIDATION RESULTS (AUTO-DETECTED FROM DATA)")
    lines.append("=" * 80)

    # Valid entities
    if validation_result.get("validated_entities"):
        lines.append("")
        lines.append("✅ VALID ENTITIES (found in document):")
        for ent in validation_result["validated_entities"]:
            location = ent.get("location", "unknown")
            lines.append(f"   • '{ent['entity']}' ({ent['type']}) → Found in {location}")

    # Invalid entities with corrections
    if validation_result.get("invalid_entities"):
        lines.append("")
        lines.append("❌ INVALID ENTITIES (NOT in document - DO NOT USE):")
        for ent in validation_result["invalid_entities"]:
            if ent.get("closest_match"):
                lines.append(f"   • '{ent['entity']}' → NOT FOUND! Closest: '{ent['closest_match']}'")
            else:
                lines.append(f"   • '{ent['entity']}' → NOT FOUND! REMOVED from query")

    # Column structure
    col_struct = validation_result.get("column_structure", {})
    if col_struct.get("columns"):
        lines.append("")
        lines.append("📋 ACTUAL COLUMN STRUCTURE DETECTED:")
        lines.append(f"   • Valid columns: {col_struct['columns']}")
        lines.append(f"   • Column indices: {col_struct['col_indices']}")
        lines.append(f"   • USE: col_index IN {col_struct['col_indices']}")
        lines.append(f"   • DO NOT USE: col_index >= 2 (catches empty columns)")

    # Corrections summary
    if validation_result.get("corrections"):
        lines.append("")
        lines.append("⚠️ CORRECTIONS APPLIED:")
        for corr in validation_result["corrections"]:
            lines.append(f"   • {corr}")

    lines.append("")
    lines.append(">>> USE ONLY VALID ENTITIES ABOVE. INVALID ENTITIES WILL RETURN NULL! <<<")
    lines.append("=" * 80)

    return "\n".join(lines)


# =============================================================================
# AGENT 0: QUERY REFORMULATOR (Expands vague queries for ANY document type)
# =============================================================================

def query_reformulator_agent(state: AgentState) -> AgentState:
    """
    QUERY REFORMULATOR AGENT (For Generic Document Support)

    Purpose: Transform vague/ambiguous user queries into specific queries
    using actual column headers and terms found in the document.

    This is CRITICAL for generic documents where:
    - User says "show totals" but document has "Grand Total", "Subtotal"
    - User says "get amounts" but document has "Amount Due", "Line Amount"
    - User says "extract data" but we need to know WHICH data

    Flow:
    1. Check if query is vague (short, generic terms)
    2. Quick Weaviate search to discover document headers
    3. If vague: Use LLM to reformulate with actual document terms
    4. If specific: Pass through unchanged

    This runs BEFORE Context Gatherer to improve downstream accuracy.
    """
    logger.info("=" * 60)
    logger.info("AGENT 0: QUERY REFORMULATOR (Generic Document Support)")
    logger.info("=" * 60)

    weaviate_tools = WeaviateTools()
    original_query = state["user_query"]
    state["original_query"] = original_query

    try:
        # =================================================================
        # STEP 1: Check if query needs reformulation
        # =================================================================
        query_lower = original_query.lower().strip()
        word_count = len(query_lower.split())

        # Vague query indicators - patterns that suggest vagueness
        vague_patterns = [
            r'^show\s+(me\s+)?(the\s+)?',
            r'^get\s+(all\s+)?(the\s+)?',
            r'^extract\s+',
            r'^list\s+(all\s+)?',
            r'^what\s+(is|are)\s+(the\s+)?$',
            r'^find\s+(the\s+)?',
            r'^give\s+(me\s+)?',
        ]

        # Generic terms that need document context
        generic_terms = {'data', 'values', 'results', 'numbers', 'info', 'information',
                        'stuff', 'things', 'items', 'records', 'entries', 'totals',
                        'amounts', 'counts', 'details', 'everything', 'all'}

        # Check if query is vague
        query_words = set(query_lower.split())
        has_generic_terms = bool(generic_terms.intersection(query_words))
        matches_vague_pattern = any(re.search(p, query_lower) for p in vague_patterns)

        # Query needs reformulation if:
        # - Very short (<=3 words) OR
        # - Has generic terms and is short (<=5 words)
        needs_reformulation = (word_count <= 3) or (has_generic_terms and word_count <= 5)

        if not needs_reformulation:
            # Query is specific enough - pass through
            logger.info(f"Query is specific ({word_count} words) - no reformulation needed")
            state["reformulated_query"] = original_query
            state["was_reformulated"] = False
            return state

        logger.info(f"Query may be vague (words={word_count}, generic_terms={has_generic_terms})")
        logger.info("Step 1: Quick Weaviate search to discover document headers...")

        # =================================================================
        # STEP 2: Quick Weaviate search to get document context
        # =================================================================
        chunks = weaviate_tools.search_chunks(
            query=original_query,
            process_id=state["process_id"],
            limit=15
        )

        # Extract headers from chunks
        headers = weaviate_tools.extract_headers_from_chunks(chunks)

        # Also get sample content to understand document type
        sample_content = []
        for chunk in chunks[:5]:
            content = chunk.get('content', '')[:200]
            chunk_type = chunk.get('chunk_type', 'unknown')
            if content:
                sample_content.append(f"[{chunk_type}]: {content}")

        if not headers and not sample_content:
            # No context found - can't reformulate
            logger.info("No document context found - using original query")
            state["reformulated_query"] = original_query
            state["was_reformulated"] = False
            return state

        logger.info(f"Found {len(headers)} headers: {headers[:10]}")

        # =================================================================
        # STEP 3: Use LLM to reformulate query with document context
        # =================================================================
        logger.info("Step 2: Reformulating query with document context...")

        reformulate_prompt = f"""You are a query reformulation expert. Your task is to expand a vague user query into a specific, actionable query using the actual terms found in the document.

ORIGINAL USER QUERY: "{original_query}"

DOCUMENT CONTEXT:
Headers/Column Names Found: {headers[:20]}

Sample Content:
{chr(10).join(sample_content[:3])}

YOUR TASK:
1. Identify what the user is likely asking for based on the document context
2. Reformulate the query to be specific, using ACTUAL column names/headers from the document
3. Keep the reformulated query natural and clear

RULES:
- Use the EXACT header names found in the document (don't invent new terms)
- If user says "totals" and document has "Grand Total", use "Grand Total"
- If user says "amounts" and document has "Amount Due", use "Amount Due"
- If the query is already specific enough, return it unchanged
- Keep the reformulated query concise (1-2 sentences max)

EXAMPLES:
- "show data" + headers ["Batch Name", "Count", "Range"] → "Extract Batch Name, Count, and Range values from all tables"
- "get totals" + headers ["Subtotal", "Tax", "Grand Total"] → "Get Subtotal, Tax, and Grand Total values"
- "concentration values" + headers ["Concentration", "Range"] → "Extract Concentration values from all tables"

OUTPUT: Write ONLY the reformulated query. No explanation, no quotes, just the query."""

        reformulated = call_claude(reformulate_prompt, MODELS["planner"], max_tokens=200)
        reformulated = reformulated.strip().strip('"').strip("'")

        # Validate reformulation
        if reformulated and len(reformulated) > 5 and len(reformulated) < 500:
            state["reformulated_query"] = reformulated
            state["was_reformulated"] = True
            state["user_query"] = reformulated  # Update user_query for downstream agents

            logger.info(f"Query reformulated successfully")
            print("\n" + "=" * 60)
            print("QUERY REFORMULATION:")
            print("=" * 60)
            print(f"Original:     {original_query}")
            print(f"Reformulated: {reformulated}")
            print("=" * 60 + "\n")
        else:
            # Reformulation failed - use original
            logger.warning("Reformulation returned invalid result - using original")
            state["reformulated_query"] = original_query
            state["was_reformulated"] = False

    except Exception as e:
        logger.error(f"Query reformulator error: {e}")
        state["reformulated_query"] = original_query
        state["was_reformulated"] = False

    return state


# =============================================================================
# AGENT 1: CONTEXT GATHERER (Weaviate + Few-Shot + Schema)
# =============================================================================

def context_gatherer_agent(state: AgentState) -> AgentState:
    """
    CONTEXT GATHERER AGENT (IMPROVED with Structural Probe)

    Collects all context needed for Cypher generation:
    1. Weaviate chunks and headers (with chunk_type metadata)
    2. STRUCTURAL PROBE - Find WHERE data actually exists in Neo4j
    3. Similar few-shot examples (filtered by data types found)
    4. Filtered Neo4j schema (ALL node types)
    5. Actual data snippets from Neo4j

    NEW: Extracts chunk_type from Weaviate and runs Structural Probe
    to guide the LLM to use the correct relationship path.
    """
    logger.info("=" * 60)
    logger.info("AGENT 1: CONTEXT GATHERER (with Structural Probe)")
    logger.info("=" * 60)

    weaviate_tools = WeaviateTools()
    neo4j_tools = Neo4jTools()

    try:
        # =================================================================
        # STEP 1: Search Weaviate for relevant chunks
        # =================================================================
        logger.info("Step 1: Searching Weaviate...")

        # Extract key terms from user query DYNAMICALLY - NO HARDCODED TERMS
        # This makes the system 100% generic for ANY document type
        user_query_lower = state["user_query"].lower()

        # Stop words to filter out (common English words that don't help search)
        stop_words = {
            'from', 'with', 'that', 'this', 'what', 'where', 'which', 'when',
            'have', 'has', 'had', 'the', 'and', 'for', 'are', 'but', 'not',
            'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'get',
            'find', 'show', 'give', 'extract', 'list', 'return', 'across',
            'pages', 'page', 'table', 'tables', 'row', 'rows', 'column',
            'columns', 'value', 'values', 'data', 'document', 'cell', 'cells'
        }

        # Extract meaningful terms from user query ONLY
        search_terms = []
        for word in user_query_lower.split():
            # Keep words > 2 chars that are not stop words
            if len(word) > 2 and word not in stop_words:
                if word not in search_terms:
                    search_terms.append(word)

        all_chunks = []

        for term in search_terms[:8]:  # Limit to 8 terms
            chunks = weaviate_tools.search_chunks(
                query=term,
                process_id=state["process_id"],
                limit=5
            )
            all_chunks.extend(chunks)

        # Also search with user query
        query_chunks = weaviate_tools.search_chunks(
            query=state["user_query"],
            process_id=state["process_id"],
            limit=10
        )
        all_chunks.extend(query_chunks)

        # Deduplicate
        seen_ids = set()
        unique_chunks = []
        for chunk in all_chunks:
            chunk_id = chunk.get('chunk_id')
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                unique_chunks.append(chunk)

        state["weaviate_chunks"] = unique_chunks

        # Extract headers
        headers = weaviate_tools.extract_headers_from_chunks(unique_chunks)
        state["weaviate_headers"] = headers

        # =================================================================
        # STEP 1.5: EXTRACT CHUNK TYPES (NEW - for Metadata-Steered Planning)
        # =================================================================
        chunk_type_counts = {"table": 0, "text": 0, "other": 0}
        for chunk in unique_chunks:
            ct = chunk.get('chunk_type', 'other').lower()
            if 'table' in ct:
                chunk_type_counts["table"] += 1
            elif 'text' in ct or 'line' in ct:
                chunk_type_counts["text"] += 1
            else:
                chunk_type_counts["other"] += 1

        logger.info(f"  Found {len(unique_chunks)} chunks, {len(headers)} headers")
        logger.info(f"  Chunk types: {chunk_type_counts}")

        # Build context string WITH chunk_type info AND cell_grounding
        weaviate_context = f"HEADERS FOUND: {headers[:15]}\n"
        weaviate_context += f"CHUNK TYPES IN WEAVIATE: table={chunk_type_counts['table']}, text={chunk_type_counts['text']}\n\n"

        for chunk in unique_chunks[:5]:
            content = chunk.get('content', '')[:250]
            chunk_type = chunk.get('chunk_type', 'unknown')
            page = chunk.get('page', '?')
            weaviate_context += f"[Page {page}, TYPE={chunk_type}]: {content}...\n"

            # CRITICAL: Include cell_grounding so LLM knows exact col_index for each header/cell
            cell_grounding_str = chunk.get('cell_grounding', '')
            if cell_grounding_str and chunk_type == 'table':
                try:
                    cell_grounding = json.loads(cell_grounding_str)
                    # Sort by row then col for clear structure
                    sorted_cells = sorted(
                        cell_grounding.items(),
                        key=lambda x: (x[1].get('row', 0), x[1].get('col', 0))
                    )
                    # Format cell_grounding for LLM understanding - SHOW ALL cells sorted by row/col
                    weaviate_context += f"\nCELL_GROUNDING (EXACT row/col indices - USE THESE for col_index!):\n"
                    for cell_id, cell_data in sorted_cells:
                        row = cell_data.get('row', '?')
                        col = cell_data.get('col', '?')
                        text = cell_data.get('text', '')[:50]
                        weaviate_context += f"  row={row}, col={col}: \"{text}\"\n"
                except (json.JSONDecodeError, TypeError):
                    pass
            weaviate_context += "\n"
        state["weaviate_context"] = weaviate_context

        # =================================================================
        # STEP 2: STRUCTURAL PROBE (NEW - Find WHERE data exists)
        # =================================================================
        logger.info("Step 2: Running Structural Probe...")

        # Extract key terms to probe for - DYNAMICALLY from user query ONLY
        # NO hardcoded domain terms - makes system 100% generic
        probe_terms = list(set([t.lower() for t in search_terms[:8]]))

        probe_result = neo4j_tools.structural_probe(state["process_id"], probe_terms)

        state["structural_probe"] = probe_result
        logger.info(f"  Node counts: {probe_result['node_counts']}")
        logger.info(f"  Data found in: {list(probe_result['found_in'].keys())}")
        logger.info(f"  Recommended paths: {probe_result['recommended_paths']}")

        # Build structural probe context for LLM
        probe_context = "\n=== STRUCTURAL PROBE RESULTS (WHERE DATA ACTUALLY EXISTS) ===\n"
        probe_context += f"Node counts: {json.dumps(probe_result['node_counts'])}\n\n"

        if probe_result["found_in"]:
            probe_context += "DATA LOCATIONS FOUND:\n"
            for term, locations in probe_result["found_in"].items():
                for loc in locations:
                    probe_context += f"  - '{term}' found in {loc['node_type']} nodes ({loc['count']} matches, pages {loc['sample_pages']})\n"
                    probe_context += f"    PATH TO USE: {loc['path']}\n"

        if probe_result["recommended_paths"]:
            probe_context += f"\nRECOMMENDED RELATIONSHIP PATHS:\n"
            for path in probe_result["recommended_paths"]:
                probe_context += f"  - {path}\n"

        state["probe_context"] = probe_context

        # =================================================================
        # STEP 3: Retrieve similar few-shot examples (UPGRADED - Phase 2)
        # Now uses Success Bank with structural compatibility filtering
        # =================================================================
        logger.info("Step 3: Retrieving few-shot examples from Success Bank...")

        similar_examples = retrieve_similar_examples(
            query=state["user_query"],
            process_id=state["process_id"],
            probe=probe_result,  # Pass structural probe for compatibility filtering
            top_k=2
        )
        state["similar_examples"] = similar_examples
        logger.info(f"  Found {len(similar_examples)} similar examples")

        # =================================================================
        # STEP 4: Get filtered Neo4j schema (IMPROVED - ALL node types)
        # =================================================================
        logger.info("Step 4: Getting complete filtered schema...")

        filtered_schema = neo4j_tools.get_filtered_schema(state["process_id"])
        state["filtered_schema"] = filtered_schema
        logger.info(f"  Schema: {len(filtered_schema)} chars")

        # =================================================================
        # STEP 5: Get actual data snippet from Neo4j
        # =================================================================
        logger.info("Step 5: Getting data snippets...")

        # Use headers from Weaviate to find relevant data
        search_for = ["range", "concentration", "batch", "count"] + headers[:3]
        data_snippet = neo4j_tools.get_data_snippet(state["process_id"], search_for)
        state["data_snippet"] = data_snippet
        logger.info(f"  Data snippet: {len(data_snippet)} chars")

        # =================================================================
        # STEP 6: QUERY ENTITY VALIDATION (NEW - Generic Entity Validation)
        # Validates ALL user query terms against actual data
        # =================================================================
        logger.info("Step 6: Validating query entities against actual data...")

        entity_validation = validate_query_entities(
            user_query=state["user_query"],
            weaviate_headers=headers,
            data_snippet=data_snippet,
            structural_probe=probe_result
        )

        state["entity_validation"] = entity_validation
        state["validated_entities"] = entity_validation.get("validated_entities", [])
        state["invalid_entities"] = entity_validation.get("invalid_entities", [])
        state["entity_validation_context"] = format_entity_validation_context(entity_validation)

        logger.info(f"  Valid entities: {len(entity_validation.get('validated_entities', []))}")
        logger.info(f"  Invalid entities: {len(entity_validation.get('invalid_entities', []))}")
        if entity_validation.get("corrections"):
            for corr in entity_validation["corrections"]:
                logger.warning(f"  CORRECTION: {corr}")

        # Print summary
        print("\n" + "=" * 60)
        print("CONTEXT GATHERED (with Structural Probe + Entity Validation):")
        print("=" * 60)
        print(f"Weaviate chunks: {len(unique_chunks)}")
        print(f"Chunk types: {chunk_type_counts}")
        print(f"Headers: {headers[:10]}")
        print(f"Structural Probe - Node counts: {probe_result['node_counts']}")
        print(f"Structural Probe - Data found in: {list(probe_result['found_in'].keys())[:5]}")
        print(f"Few-shot examples: {len(similar_examples)}")
        if similar_examples:
            print(f"  Best match: {similar_examples[0]['question'][:50]}...")
        # Entity Validation summary
        print(f"Entity Validation - Valid: {len(entity_validation.get('validated_entities', []))}")
        print(f"Entity Validation - Invalid: {len(entity_validation.get('invalid_entities', []))}")
        if entity_validation.get("corrections"):
            print(f"  Corrections applied:")
            for corr in entity_validation["corrections"][:3]:
                # Handle Unicode for Windows console
                try:
                    print(f"    - {corr}")
                except UnicodeEncodeError:
                    print(f"    - {corr.encode('ascii', 'replace').decode('ascii')}")
        if entity_validation.get("column_structure", {}).get("columns"):
            # Handle Unicode in column names (e.g., ≥ symbol)
            cols = entity_validation['column_structure']['columns']
            try:
                print(f"  Detected columns: {cols}")
            except UnicodeEncodeError:
                cols_safe = [str(c).replace('≥', '>=').replace('≤', '<=') for c in cols]
                print(f"  Detected columns: {cols_safe}")
        print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"Context gatherer error: {e}")
        import traceback
        traceback.print_exc()
        state["error"] = str(e)
    finally:
        neo4j_tools.close()

    return state

# =============================================================================
# AGENT 2: LOGIC-FIRST PLANNER
# =============================================================================

def logic_planner_agent(state: AgentState) -> AgentState:
    """
    LOGIC-FIRST PLANNER AGENT (IMPROVED with Hard Constraints - Phase 3)

    Generates a step-by-step logical plan BEFORE any Cypher code.
    This forces the LLM to reason about the problem first.

    UPGRADED (Phase 3): Now includes MANDATORY CONSTRAINTS from structural probe.
    These are not hints - they are laws the LLM must follow or get 0 rows.
    """
    logger.info("=" * 60)
    logger.info("AGENT 2: LOGIC-FIRST PLANNER (with Hard Constraints)")
    logger.info("=" * 60)

    # Check for previous feedback
    feedback = state.get("validation_feedback", "")
    iteration = state.get("iteration", 1)

    # =================================================================
    # NEW (Phase 3): Extract and format hard constraints
    # IMPROVED (v2): Now passes user_query for smart constraint decisions
    # =================================================================
    constraints = extract_hard_constraints(
        state.get("structural_probe", {}),
        state.get("weaviate_chunks", []),
        state.get("user_query", "")  # Pass user query for smart decisions
    )
    constraint_block = format_constraint_block(constraints)

    if constraint_block:
        logger.info(f"Hard constraints: PRIMARY={constraints['primary_node']}, FORBIDDEN={constraints['forbidden_nodes']}")
    else:
        logger.info("No hard constraints generated (probe may not have found_in data)")

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

    # Get structural probe context (tells LLM WHERE data actually exists)
    probe_context = state.get("probe_context", "")

    # Build the planning prompt (IMPROVED with HARD CONSTRAINTS + DATA SOURCE ROUTING)
    plan_prompt = f"""You are a Cypher query planning expert. Your task is to create a LOGICAL PLAN for querying Neo4j.

DO NOT WRITE ANY CYPHER CODE. Only write a step-by-step plan in plain English.

USER QUERY: {state["user_query"]}
{constraint_block}

=== DATA SOURCE ROUTING RULES (CRITICAL FOR DATA QUALITY) ===
Your Neo4j graph has TWO data sources. Choose wisely based on query type:

1. LINE NODES - Use for LABEL/METADATA lookups (cleaner OCR, no merge artifacts):
   - Path: (Page)-[:CONTAINS_LINE]->(Line)
   - Best for: "What is Batch Name?", "What is Project Name?", "Who is the User?"
   - Properties: text (contains "Label: Value" format)
   - WHY: Line nodes have 99% clean text, Cell nodes may have OCR merge artifacts

2. CELL NODES - Use for TABULAR/STRUCTURAL queries (has row/column indexing):
   - Path: (Page)-[:CONTAINS_TABLE]->(Table)-[:HAS_CELL]->(Cell)
   - Best for: "Get Count row", "Column 3 values", "Second row of table"
   - Properties: text, row_index, col_index
   - WHY: Only Cell nodes have row_index/col_index for table navigation

3. HYBRID (Both Line + Cell) - Use when query needs BOTH metadata AND table data:
   - Example: "Get Batch Name AND Count values"
   - Strategy:
     a) Get Batch Name from LINE nodes (cleaner)
     b) Get Count values from CELL nodes (structural)
     c) JOIN via Page: (p:Page)-[:CONTAINS_LINE]->(l), (p)-[:CONTAINS_TABLE]->(t)
   - WHY: Combines clean text (Line) with table structure (Cell)

ROUTING DECISION:
- Query mentions "Batch Name", "Project Name", "User", "Date" as standalone lookup → Use LINE
- Query mentions "row", "column", "Count", "Concentration", "table data" → Use CELL
- Query needs BOTH metadata AND table data → Use HYBRID (join on Page)

=== DOCUMENT CONTEXT (from Weaviate) ===
{state.get("weaviate_context", "No context")}
{probe_context}
{examples_section}
=== FILTERED NEO4J SCHEMA ===
{state.get("filtered_schema", "No schema")}

=== ACTUAL DATA SAMPLES FROM NEO4J ===
{state.get("data_snippet", "No data")}
{state.get("entity_validation_context", "")}

{("PREVIOUS ATTEMPT FAILED WITH:" + chr(10) + feedback + chr(10) + "Adjust your plan to fix this issue.") if feedback else ""}

TASK: Write a numbered step-by-step plan that explains:
1. Which NODE TYPE to use based on DATA SOURCE ROUTING RULES above
2. What relationship path to use (MUST follow REQUIRED PATH if specified in constraints)
3. How to identify the correct rows/data (be specific about row_index if using Cell)
4. How to filter/match the data
5. How to structure the output

CRITICAL RULES:
- If MANDATORY CONSTRAINTS specify a PRIMARY NODE TYPE, you MUST use it
- If MANDATORY CONSTRAINTS specify FORBIDDEN NODES, you MUST NOT use them
- If PRIMARY NODE is Line: use 'text' and 'line_id' properties (no row_index/col_index)
- If PRIMARY NODE is Cell: use 'text', 'row_index', 'col_index' properties
- If PRIMARY NODE is BOTH: use Page as join point between tables and lines
- For HYBRID queries: Get metadata from LINE, get table data from CELL, join via PAGE

MULTI-PAGE QUERIES (CRITICAL):
- If query says "each page", "all pages", "every page", "per page", or "across pages":
  * DO NOT use a global LIMIT at the end - this limits TOTAL results, not per-page!
  * Use aggregation to get ONE result per page: WITH p.page_num AS page, collect(...) AS values
  * If you need to limit per page, do it BEFORE the final aggregation, not after
  * WRONG: ORDER BY page LIMIT 1 (returns only 1 page!)
  * RIGHT: GROUP BY page and return results for ALL pages

IMPORTANT:
- Reference specific row_index values you see in the data samples
- Note any patterns like "second Range row" or "Concentration is row_index + 1 from Range"
- Be specific about column indices for pivoting
- Pay attention to the STRUCTURAL PROBE - it tells you WHERE data ACTUALLY exists!
- If QUERY ENTITY VALIDATION is provided above, ONLY use VALID entities and IGNORE invalid ones
- If column indices are provided in validation (e.g., col_index IN [2,3,4,5,6,7]), use them EXACTLY
- DO NOT use open-ended col_index filters like "col_index >= 2" - use explicit lists from validation
- CELL_GROUNDING shows EXACT row/col values from the actual table - READ these values directly, do NOT assume 0-based indexing

Write your plan now (NO CYPHER CODE):"""

    plan = call_claude(plan_prompt, MODELS["planner"], max_tokens=1500)
    state["logical_plan"] = plan

    logger.info(f"Generated logical plan ({len(plan)} chars)")
    print("\n" + "=" * 60)
    print(f"LOGICAL PLAN (Iteration {iteration}):")
    print("=" * 60)
    # Handle encoding issues
    try:
        print(plan[:1500])
    except UnicodeEncodeError:
        print(plan[:1500].encode('ascii', 'replace').decode('ascii'))
    print("=" * 60 + "\n")

    return state

# =============================================================================
# AGENT 3: CYPHER GENERATOR
# =============================================================================

def cypher_generator_agent(state: AgentState) -> AgentState:
    """
    CYPHER GENERATOR AGENT (with Dynamic Path Rules)

    Converts the logical plan into executable Cypher code.
    Uses few-shot examples as reference.

    UPGRADED: Rules 2 and 3 are now DYNAMIC based on Structural Probe constraints.
    This eliminates "Hallucination by Instruction" where hardcoded Table/Cell rules
    cause the LLM to force Line data into Cell patterns.
    """
    logger.info("=" * 60)
    logger.info("AGENT 3: CYPHER GENERATOR (Claude Sonnet)")
    logger.info("=" * 60)

    iteration = state.get("iteration", 1)

    # =================================================================
    # DYNAMIC PATH RULES (based on Structural Probe constraints)
    # This is the key fix to eliminate Table-Centric Bias in generation
    # IMPROVED (v2): Now passes user_query for smart constraint decisions
    # =================================================================
    constraints = extract_hard_constraints(
        state.get("structural_probe", {}),
        state.get("weaviate_chunks", []),
        state.get("user_query", "")  # Pass user query for smart decisions
    )
    primary_node = constraints.get("primary_node")

    # Generate dynamic rules based on where data actually exists
    if primary_node == "Line":
        path_rule = "MUST USE: Document -[:HAS_PAGE]-> Page -[:CONTAINS_LINE]-> Line"
        props_rule = "Line properties: text, line_id, bbox_left/top/right/bottom (NO row_index/col_index!)"
        forbidden_rule = "DO NOT use Table or Cell nodes - data is in Line nodes only!"
    elif primary_node == "Cell":
        path_rule = "MUST USE: Document -[:HAS_PAGE]-> Page -[:CONTAINS_TABLE]-> Table -[:HAS_CELL]-> Cell"
        props_rule = "Cell properties: text, row_index (0-based), col_index (0-based), is_header"
        forbidden_rule = "DO NOT use Line nodes for table data - use Cell nodes!"
    elif primary_node == "Section":
        path_rule = "MUST USE: Document -[:HAS_PAGE]-> Page -[:CONTAINS_SECTION]-> Section"
        props_rule = "Section properties: section_id, text, content"
        forbidden_rule = "DO NOT use Table, Cell, or Line nodes - data is in Section nodes only!"
    elif primary_node == "BOTH":
        path_rule = "USE BOTH paths with Page as join point:\n   - For table data: Page -[:CONTAINS_TABLE]-> Table -[:HAS_CELL]-> Cell\n   - For text data: Page -[:CONTAINS_LINE]-> Line\n   - JOIN via: (p:Page)-[:CONTAINS_TABLE]->(t), (p)-[:CONTAINS_LINE]->(l)"
        props_rule = "Cell: text, row_index, col_index | Line: text, line_id"
        forbidden_rule = "Use the correct node type for each field based on where the data exists!"
    else:
        # Default - provide both options
        path_rule = "Choose path based on data type:\n   - For table data: Page -[:CONTAINS_TABLE]-> Table -[:HAS_CELL]-> Cell\n   - For text data: Page -[:CONTAINS_LINE]-> Line"
        props_rule = "Cell: text, row_index, col_index | Line: text, line_id"
        forbidden_rule = "Match your path to where the Structural Probe found the data!"

    logger.info(f"Dynamic path rule: PRIMARY_NODE={primary_node}")

    # Build few-shot examples section with actual Cypher
    examples_section = ""
    if state.get("similar_examples"):
        examples_section = "\n=== REFERENCE CYPHER QUERIES THAT WORKED ===\n"
        for i, ex in enumerate(state["similar_examples"], 1):
            examples_section += f"""
EXAMPLE {i} - "{ex['question'][:50]}...":
{ex['cypher']}
---
"""

    # Previous error feedback
    error_section = ""
    if state.get("execution_error"):
        error_section = f"""
=== PREVIOUS CYPHER FAILED WITH ERROR ===
{state["execution_error"]}

Fix the syntax error in your Cypher. Common fixes:
- Use coalesce(text, '') for null safety
- Use toLower() for case-insensitive matching
- Use proper escaping in regex patterns
- Make sure all MATCH patterns have valid relationships
"""

    generation_prompt = f"""You are an expert Cypher developer. Convert the logical plan into executable Cypher.

USER QUERY: {state["user_query"]}
PROCESS_ID: {state["process_id"]}

=== LOGICAL PLAN TO IMPLEMENT ===
{state.get("logical_plan", "No plan")}

=== FILTERED SCHEMA ===
{state.get("filtered_schema", "No schema")}
{state.get("entity_validation_context", "")}
{examples_section}
{error_section}

RULES:
1. ALWAYS start with: MATCH (d:Document {{process_id: $process_id}})
2. {path_rule}
3. {props_rule}
4. {forbidden_rule}
5. Use toLower(coalesce(node.text, '')) for safe text matching
6. For regex with dots, escape them: '5\\.00' or '5[.]00'
7. MULTI-PAGE QUERIES: If query says "each page"/"all pages"/"per page":
   - DO NOT use LIMIT at the very end (this limits TOTAL rows, not per-page!)
   - Use: WITH p, collect(...) to aggregate per page, then RETURN for ALL pages
   - If you need per-page limits, use subquery or early WITH before final aggregation
8. COLUMN INDEX VALIDATION: If QUERY ENTITY VALIDATION above provides col_indices, use them EXACTLY:
   - USE: col_index IN [2,3,4,5,6,7] (explicit list from validation)
   - DO NOT USE: col_index >= 2 (open-ended, catches empty columns!)
   - IGNORE invalid entities marked in validation - they don't exist in the data

HYBRID QUERY PATTERN (when plan says use BOTH Line and Cell):
- For metadata (Batch Name, Project Name): Get from LINE nodes (cleaner OCR)
- For tabular data (Count, Concentration): Get from CELL nodes (has row_index)
- JOIN via Page node using OPTIONAL MATCH:
  ```
  MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)
  OPTIONAL MATCH (p)-[:CONTAINS_LINE]->(l:Line) WHERE l.text CONTAINS 'batch'
  OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell) WHERE c.text CONTAINS 'count'
  ```
- Extract value from Line text using: split(l.text, ':')[1] or regex

OUTPUT: Write ONLY the Cypher query. No explanations, no markdown code blocks, just the query."""

    cypher = call_claude(generation_prompt, MODELS["generator"], max_tokens=3000)

    # Clean up the response - strip code blocks
    cypher = strip_code_blocks(cypher)

    state["generated_cypher"] = cypher

    logger.info(f"Generated Cypher ({len(cypher)} chars)")
    print("\n" + "=" * 60)
    print(f"GENERATED CYPHER (Iteration {iteration}):")
    print("=" * 60)
    print(cypher[:2000])
    print("=" * 60 + "\n")

    return state

# =============================================================================
# NEV HELPER FUNCTIONS (Named Entity Verification)
# =============================================================================

def levenshtein_similarity(s1: str, s2: str) -> float:
    """Calculate normalized Levenshtein similarity (0-1)."""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def find_closest_match(target: str, candidates: List[str], threshold: float = 0.6) -> Optional[str]:
    """Find the closest match from candidates using Levenshtein similarity."""
    best_match = None
    best_score = threshold

    for candidate in candidates:
        score = levenshtein_similarity(target, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate

    return best_match


def extract_map_literal_keys(cypher: str) -> set:
    """
    Extract keys from map literals like {header: x.text, value: y.text}.

    These are NOT Neo4j properties and should NOT be corrected by NEV.
    Map literals appear in:
    - collect({key: value, ...})
    - RETURN {key: value}
    - List comprehensions [x IN list | {key: x.prop}]
    """
    map_keys = set()

    # Pattern 1: Simple map literals {key: value, key2: value2}
    # Match content inside {...} that's not a node pattern
    map_patterns = re.findall(r'\{([^{}]+)\}', cypher)

    for map_content in map_patterns:
        # Skip if it looks like a node property filter (e.g., {process_id: $pid})
        # Node filters have : followed by $ or a quoted string or a variable
        if re.match(r'^\s*\w+\s*:\s*[\$\'\"]', map_content):
            continue

        # Skip if it's a node label pattern like (d:Document {process_id: ...})
        # These have format: property: $param or property: "value"
        if ':' in map_content and ('$' in map_content or re.search(r':\s*[\'"]', map_content)):
            # Check if ALL entries look like property filters
            entries = map_content.split(',')
            all_filters = all(
                re.match(r'\s*\w+\s*:\s*[\$\'"\w]', entry.strip())
                for entry in entries if entry.strip()
            )
            if all_filters and '$' in map_content:
                continue

        # Extract keys from map literal entries like "header: h.text"
        # Pattern: word followed by : and then an expression (not $param)
        keys = re.findall(r'(\w+)\s*:\s*(?!\$)[^,}]+', map_content)
        map_keys.update(keys)

    return map_keys


def extract_entities_from_cypher(cypher: str) -> Dict[str, List[str]]:
    """
    Extract all entities from a Cypher query.

    IMPROVED V2:
    1. Properly distinguishes between node labels and relationship types
    2. CONTEXT-AWARE: Excludes map literal keys from property corrections

    Map literal keys like {header: x.text} are NOT Neo4j properties!
    They are user-defined keys in result maps and should NOT be "corrected".

    Returns:
        Dict with keys: labels, relationships, properties, string_values, map_keys
    """
    # First, extract relationship types from [...] patterns
    # Pattern: -[:REL_TYPE]-> or -[:REL_TYPE]- or [:REL_TYPE]
    relationships = list(set(re.findall(r'\[(?:\w+)?:(\w+)\]', cypher)))

    # Create a set of relationship types to exclude from labels
    rel_set = set(relationships)

    # Extract node labels - pattern: (var:Label) or (:Label)
    all_colon_words = re.findall(r':(\w+)', cypher)

    # Filter out relationship types from labels
    labels = list(set([w for w in all_colon_words if w not in rel_set]))

    # Extract map literal keys (these should NOT be corrected)
    map_keys = extract_map_literal_keys(cypher)

    # Extract property keys (e.g., process_id, text, row_index)
    # Pattern: .property_name
    all_properties = list(set(re.findall(r'\.(\w+)', cypher)))

    # CONTEXT-AWARE: Filter out map literal keys from properties
    # If we see "x.header" where "header" is also a map key like {header: ...},
    # it's likely accessing a map result, not a Neo4j property
    properties = [p for p in all_properties if p not in map_keys]

    # Extract string values in CONTAINS/regex patterns
    string_values = re.findall(r"CONTAINS\s+['\"]([^'\"]+)['\"]", cypher, re.IGNORECASE)
    string_values += re.findall(r"=~\s+['\"](?:\.\*)?([a-zA-Z]{3,})", cypher)
    string_values = list(set([v for v in string_values if len(v) >= 3]))

    return {
        "labels": labels,
        "relationships": relationships,
        "properties": properties,
        "string_values": string_values,
        "map_keys": list(map_keys)  # Track these for logging
    }


# =============================================================================
# TOPOLOGY VERIFICATION (Phase 1 - NEV Enhancement)
# =============================================================================

def verify_topology(cypher: str, probe: Dict[str, Any]) -> tuple[bool, str, list]:
    """
    Verify Cypher uses valid graph topology based on actual Neo4j schema.

    This is the key fix for "Blind Checking" - prevents querying Table/Cell
    when Structural Probe shows data is in Line nodes.

    Features:
    - Allows Cell->Cell (SAME_ROW/SAME_COL are valid)
    - Includes MergedCell support
    - Checks relationship direction
    - Validates against Structural Probe results

    Args:
        cypher: Generated Cypher query to validate
        probe: Structural probe results from Neo4j

    Returns:
        tuple: (is_valid, corrected_cypher_or_empty, violations_list)
    """
    violations = []

    # =================================================================
    # CHECK 1: Invalid Direct Connections
    # Based on actual Neo4j schema - these paths are IMPOSSIBLE
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

        # Document must go through Page (cannot skip)
        (r'\(:?Document\).*-\[.*\]->.*\(:?Cell\)', "Document cannot connect directly to Cell - use Document->Page->Table->Cell"),
        (r'\(:?Document\).*-\[.*\]->.*\(:?Line\)', "Document cannot connect directly to Line - use Document->Page->Line"),
        (r'\(:?Document\).*-\[.*\]->.*\(:?Table\)', "Document cannot connect directly to Table - use Document->Page->Table"),

        # Leaf nodes cannot connect (except Cell->Cell which is valid via SAME_ROW/SAME_COL)
        (r'\(:?Cell\).*-\[.*\]->.*\(:?Line\)', "Cell cannot connect to Line"),
        (r'\(:?Section\).*-\[.*\]->.*\(:?Cell\)', "Section cannot connect to Cell"),
        (r'\(:?Line\).*-\[.*\]->.*\(:?Section\)', "Line cannot connect to Section"),

        # Direction checks (reversed relationships are invalid)
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
    # If probe says data is ONLY in Line, but Cypher uses Cell/Table
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
    # Only these relationships exist in the schema
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


# =============================================================================
# HARD CONSTRAINTS EXTRACTION (Phase 3)
# =============================================================================

def extract_hard_constraints(probe: Dict, chunks: List[Dict], user_query: str = "") -> Dict:
    """
    Generate MANDATORY constraints from metadata.

    These are not hints - they are laws the LLM must follow.
    Violation results in 0 rows returned.

    IMPROVED (v2): Now considers query type to make smarter decisions.
    For simple lookups ("What is X?"), prefer Cell over BOTH to avoid
    complex UNION queries that often fail with syntax errors.

    Args:
        probe: Structural probe results from Neo4j
        chunks: Weaviate chunks with chunk_type metadata
        user_query: Original user query (for query type detection)

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
    # Detect query type to make smarter constraint decisions
    # =================================================================
    query_lower = user_query.lower() if user_query else ""

    # Simple lookup patterns - these benefit from single-node queries
    simple_lookup_patterns = [
        r"^what is the\b",
        r"^what's the\b",
        r"^find the\b",
        r"^get the\b.*\bvalue\b",
        r"^show me the\b",
        r"^tell me the\b",
        r"^what are the\b.*\bvalues?\b",
    ]
    is_simple_lookup = any(re.search(p, query_lower) for p in simple_lookup_patterns)

    # Multi-value extraction patterns - these may need BOTH nodes
    extraction_patterns = [
        r"\ball\b.*\bvalues?\b",
        r"\bevery\b",
        r"\beach\b",
        r"\bextract\b",
        r"\blist\b.*\ball\b",
        r"\bget all\b",
    ]
    is_extraction_query = any(re.search(p, query_lower) for p in extraction_patterns)

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
            # Let LLM decide based on data quality shown in data_snippet
            # data_snippet shows if Cell has OCR artifacts and Line is cleaner
            # Don't force Cell - it may have dirty data
            constraints["primary_node"] = "BOTH"
            constraints["required_path"] = "Choose based on data quality: Line for cleaner text, Cell for table structure"
            constraints["reasoning"].append(
                f"Data in BOTH: {cell_count} Cell matches, {line_count} Line matches. "
                f"Check DATA SAMPLES to see which has cleaner values - Line often has cleaner OCR text."
            )

        # CASE 4: Data in Section nodes only
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

    Uses box-drawing to make constraints IMPOSSIBLE to ignore.
    """
    if not constraints["primary_node"]:
        return ""

    # Build reasoning lines
    reasoning_lines = ""
    for r in constraints["reasoning"]:
        reasoning_lines += f"  - {r}\n"

    forbidden = ', '.join(constraints['forbidden_nodes']) if constraints['forbidden_nodes'] else 'None'
    required_path = constraints['required_path'] or 'See probe recommendations'

    # Truncate required_path if too long
    if len(required_path) > 70:
        required_path = required_path[:67] + "..."

    block = f"""
+==============================================================================+
|                    MANDATORY CONSTRAINTS (VIOLATION = 0 ROWS)                |
+==============================================================================+
| PRIMARY NODE TYPE:  {constraints['primary_node']:<55} |
| FORBIDDEN NODES:    {forbidden:<55} |
| REQUIRED PATH:      {required_path:<55} |
+------------------------------------------------------------------------------+
| REASONING:                                                                   |
{reasoning_lines}+==============================================================================+

>>> WARNING: FAILURE TO FOLLOW THESE CONSTRAINTS WILL RESULT IN ZERO ROWS <<<
>>> DO NOT USE {forbidden} NODES FOR THIS QUERY <<<
"""
    return block


# =============================================================================
# AGENT 3.5: NEV AUDITOR (Named Entity Verification)
# =============================================================================

def nev_auditor_agent(state: AgentState) -> AgentState:
    """
    NAMED ENTITY VERIFICATION (NEV) AUDITOR

    This agent extracts all entities from the generated Cypher query,
    verifies them against the actual Neo4j schema, and auto-corrects
    any hallucinated entities using Levenshtein similarity matching.

    Key Steps:
    0. TOPOLOGY CHECK - Validate graph paths (NEW - Phase 1)
    1. DECOMPOSITION - Extract labels, relationships, properties, values
    2. VERIFICATION - Check each entity against Neo4j schema
    3. RECOVERY - Use Levenshtein similarity to find correct matches
    4. CORRECTION - Auto-correct the Cypher query
    """
    logger.info("=" * 60)
    logger.info("AGENT 3.5: NEV AUDITOR (Named Entity Verification)")
    logger.info("=" * 60)

    neo4j_tools = Neo4jTools()
    cypher = state["generated_cypher"]
    original_cypher = cypher
    corrections_made = []

    try:
        # =====================================================================
        # STEP 0: TOPOLOGY CHECK (NEW - Phase 1)
        # This catches impossible paths BEFORE we waste time on other checks
        # Prevents "Blind Checking" - querying Table/Cell when data is in Line
        # =====================================================================
        logger.info("Step 0: Topology Verification...")

        is_valid_topology, corrected, topo_violations = verify_topology(
            cypher,
            state.get("structural_probe", {})
        )

        if not is_valid_topology:
            logger.error(f"TOPOLOGY VIOLATION: {topo_violations}")
            print("\n" + "=" * 60)
            print("NEV AUDITOR: TOPOLOGY VIOLATION DETECTED!")
            print("=" * 60)
            for v in topo_violations:
                print(f"  X {v}")
            print("=" * 60 + "\n")

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
        # =====================================================================
        logger.info("Step 1: Extracting entities from Cypher...")

        entities = extract_entities_from_cypher(cypher)

        logger.info(f"  Labels: {entities['labels']}")
        logger.info(f"  Relationships: {entities['relationships']}")
        logger.info(f"  Properties: {entities['properties']}")
        logger.info(f"  String values: {entities['string_values']}")
        logger.info(f"  Map literal keys (SKIPPED): {entities.get('map_keys', [])}")

        # =====================================================================
        # STEP 2: VERIFICATION - Check against Neo4j schema
        # =====================================================================
        logger.info("Step 2: Verifying entities against Neo4j schema...")

        with neo4j_tools.driver.session(database="neo4j") as session:
            # Get actual labels from Neo4j
            actual_labels_result = session.run("CALL db.labels()").data()
            actual_labels = [r.get("label", "") for r in actual_labels_result]
            logger.info(f"  Actual DB labels: {actual_labels}")

            # Get actual relationship types
            actual_rels_result = session.run("CALL db.relationshipTypes()").data()
            actual_rels = [r.get("relationshipType", "") for r in actual_rels_result]
            logger.info(f"  Actual DB relationships: {actual_rels}")

            # Get actual property keys
            actual_props_result = session.run("CALL db.propertyKeys()").data()
            actual_props = [r.get("propertyKey", "") for r in actual_props_result]
            logger.info(f"  Actual DB properties: {actual_props[:20]}...")

            # =====================================================================
            # STEP 3: VERIFY AND CORRECT LABELS
            # =====================================================================
            for label in entities["labels"]:
                if label not in actual_labels:
                    best_match = find_closest_match(label, actual_labels, threshold=0.5)
                    if best_match:
                        logger.warning(f"  LABEL '{label}' NOT FOUND -> Closest: '{best_match}'")
                        # Replace in cypher (careful with word boundaries)
                        cypher = re.sub(rf':({label})(?=\s*[\{{\)\]\-])', f':{best_match}', cypher)
                        corrections_made.append(f"Label: {label} -> {best_match}")
                    else:
                        logger.warning(f"  LABEL '{label}' NOT FOUND -> No close match found")
                else:
                    logger.info(f"  Label '{label}' verified OK")

            # =====================================================================
            # STEP 4: VERIFY AND CORRECT RELATIONSHIPS
            # =====================================================================
            for rel in entities["relationships"]:
                if rel not in actual_rels:
                    best_match = find_closest_match(rel, actual_rels, threshold=0.5)
                    if best_match:
                        logger.warning(f"  RELATIONSHIP '{rel}' NOT FOUND -> Closest: '{best_match}'")
                        cypher = cypher.replace(f"[:{rel}]", f"[:{best_match}]")
                        corrections_made.append(f"Relationship: {rel} -> {best_match}")
                    else:
                        logger.warning(f"  RELATIONSHIP '{rel}' NOT FOUND -> No close match found")
                else:
                    logger.info(f"  Relationship '{rel}' verified OK")

            # =====================================================================
            # STEP 5: VERIFY AND CORRECT PROPERTIES
            # =====================================================================
            for prop in entities["properties"]:
                if prop not in actual_props:
                    best_match = find_closest_match(prop, actual_props, threshold=0.6)
                    if best_match:
                        logger.warning(f"  PROPERTY '{prop}' NOT FOUND -> Closest: '{best_match}'")
                        cypher = re.sub(rf'\.{prop}\b', f'.{best_match}', cypher)
                        corrections_made.append(f"Property: {prop} -> {best_match}")
                    else:
                        logger.warning(f"  PROPERTY '{prop}' NOT FOUND -> No close match found")
                else:
                    logger.info(f"  Property '{prop}' verified OK")

            # =====================================================================
            # STEP 6: VERIFY STRING VALUES EXIST IN DATA (IMPROVED - Cell + Line)
            # =====================================================================
            logger.info("Step 3: Verifying string values in data (Cell + Line nodes)...")

            process_id = state["process_id"]
            for value in entities["string_values"][:5]:  # Limit to 5 values
                if len(value) < 3:
                    continue

                # IMPROVED: Check BOTH Cell AND Line nodes
                # First check Cell nodes
                cell_check_query = """
                    MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_TABLE]->()-[:HAS_CELL]->(c:Cell)
                    WHERE toLower(coalesce(c.text, '')) CONTAINS toLower($value)
                    RETURN count(c) AS count
                """
                cell_result = session.run(cell_check_query, {"pid": process_id, "value": value}).single()
                cell_count = cell_result["count"] if cell_result else 0

                # Also check Line nodes
                line_check_query = """
                    MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_LINE]->(l:Line)
                    WHERE toLower(coalesce(l.text, '')) CONTAINS toLower($value)
                    RETURN count(l) AS count
                """
                line_result = session.run(line_check_query, {"pid": process_id, "value": value}).single()
                line_count = line_result["count"] if line_result else 0

                total_count = cell_count + line_count

                if total_count == 0:
                    # Value not found in EITHER Cell or Line - try to find similar values
                    logger.warning(f"  VALUE '{value}' not found in Cell or Line nodes, searching similar...")

                    # Search both Cell and Line nodes for similar values
                    similar_cell_query = """
                        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_TABLE]->()-[:HAS_CELL]->(c:Cell)
                        WHERE toLower(coalesce(c.text, '')) CONTAINS toLower($partial)
                        RETURN DISTINCT c.text AS text LIMIT 10
                    """
                    similar_line_query = """
                        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->()-[:CONTAINS_LINE]->(l:Line)
                        WHERE toLower(coalesce(l.text, '')) CONTAINS toLower($partial)
                        RETURN DISTINCT l.text AS text LIMIT 10
                    """
                    # Search with partial match (first 4 chars)
                    partial = value[:4] if len(value) >= 4 else value

                    cell_similar = session.run(similar_cell_query, {"pid": process_id, "partial": partial}).data()
                    line_similar = session.run(similar_line_query, {"pid": process_id, "partial": partial}).data()

                    all_similar = cell_similar + line_similar

                    if all_similar:
                        candidates = [r["text"] for r in all_similar if r.get("text")]
                        best_match = find_closest_match(value, candidates, threshold=0.7)
                        if best_match:
                            logger.warning(f"  VALUE '{value}' -> Closest in data: '{best_match}'")
                            # Replace in cypher (be careful with case)
                            old_pattern = f"'{value}'"
                            new_value = best_match.lower() if "toLower" in cypher else best_match
                            cypher = cypher.replace(old_pattern, f"'{new_value}'")
                            corrections_made.append(f"Value: {value} -> {new_value}")
                else:
                    found_in = []
                    if cell_count > 0:
                        found_in.append(f"Cell({cell_count})")
                    if line_count > 0:
                        found_in.append(f"Line({line_count})")
                    logger.info(f"  Value '{value}' found in {', '.join(found_in)}")

        # =====================================================================
        # FINAL: UPDATE STATE
        # =====================================================================
        state["nev_corrections"] = corrections_made
        state["nev_verified"] = True

        if corrections_made:
            logger.info(f"\nNEV made {len(corrections_made)} corrections:")
            for c in corrections_made:
                logger.info(f"  * {c}")
            state["generated_cypher"] = cypher

            print("\n" + "=" * 60)
            print("NEV AUDITOR CORRECTIONS:")
            print("=" * 60)
            for c in corrections_made:
                print(f"  * {c}")
            print("-" * 60)
            print("CORRECTED CYPHER (first 500 chars):")
            print(cypher[:500])
            print("=" * 60 + "\n")
        else:
            logger.info("NEV: All entities verified successfully - no corrections needed")
            print("\n" + "=" * 60)
            print("NEV AUDITOR: All entities verified OK - no corrections needed")
            print("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"NEV Auditor error: {e}")
        import traceback
        traceback.print_exc()
        state["nev_corrections"] = []
        state["nev_verified"] = False
    finally:
        neo4j_tools.close()

    return state


# =============================================================================
# AGENT 4: VALIDATOR WITH SELF-CORRECTION
# =============================================================================

def analyze_query_profile(driver, cypher: str, params: Dict) -> Dict[str, Any]:
    """
    Run PROFILE on the Cypher query to analyze execution efficiency.

    This implements Google AI's PROFILE-based feedback recommendation:
    - Analyze Database Hits to detect inefficient queries
    - Look for NodeByLabelScan which indicates missing anchors
    - Provide specific feedback to help the LLM optimize

    Returns:
        Dict with db_hits, has_label_scan, operators, and feedback
    """
    profile_info = {
        "db_hits": 0,
        "has_label_scan": False,
        "has_all_nodes_scan": False,
        "operators": [],
        "feedback": ""
    }

    try:
        with driver.session(database="neo4j") as session:
            # Prepend PROFILE to the query
            profile_cypher = f"PROFILE {cypher}"
            result = session.run(profile_cypher, params)

            # Consume all results to get the profile
            records = list(result)

            # Get the query profile summary
            summary = result.consume()
            profile = summary.profile

            if profile:
                # Extract key metrics
                # Note: Neo4j driver returns profile as dict or object depending on version
                def extract_profile_info(plan, depth=0):
                    if plan is None:
                        return

                    # Handle both dict and object access patterns
                    if isinstance(plan, dict):
                        operator = plan.get('operatorType', plan.get('operator_type', 'Unknown'))
                        db_hits = plan.get('dbHits', plan.get('db_hits', 0))
                        children = plan.get('children', [])
                    else:
                        # Object-based access (older driver versions)
                        operator = getattr(plan, 'operator_type', 'Unknown')
                        db_hits = getattr(plan, 'db_hits', 0)
                        children = getattr(plan, 'children', [])

                    profile_info["db_hits"] += db_hits
                    profile_info["operators"].append({
                        "operator": operator,
                        "db_hits": db_hits,
                        "depth": depth
                    })

                    # Check for expensive operators
                    if "NodeByLabelScan" in str(operator):
                        profile_info["has_label_scan"] = True
                    if "AllNodesScan" in str(operator):
                        profile_info["has_all_nodes_scan"] = True

                    # Recursively process children
                    for child in children:
                        extract_profile_info(child, depth + 1)

                extract_profile_info(profile)

                # Generate feedback based on profile analysis
                feedback_parts = []

                if profile_info["has_all_nodes_scan"]:
                    feedback_parts.append(
                        "WARNING: AllNodesScan detected - query scans ALL nodes in database. "
                        "Add a process_id anchor: MATCH (d:Document {process_id: $process_id})"
                    )

                if profile_info["has_label_scan"] and profile_info["db_hits"] > 10000:
                    feedback_parts.append(
                        f"WARNING: NodeByLabelScan with {profile_info['db_hits']} DB hits. "
                        "Consider adding index hints or narrowing the search path with row_index filters."
                    )

                if profile_info["db_hits"] > 50000:
                    feedback_parts.append(
                        f"PERFORMANCE: Query had {profile_info['db_hits']} DB hits (very high). "
                        "Add filters early in the query to reduce traversal."
                    )

                profile_info["feedback"] = " ".join(feedback_parts)

    except Exception as e:
        logger.warning(f"PROFILE analysis failed (non-critical): {e}")

    return profile_info


def analyze_null_pattern(results: List[Dict]) -> Dict[str, Any]:
    """
    Analyze NULL value patterns in results to provide specific feedback.

    This addresses the issue where we got 9 rows but all values were NULL.
    The validator needs to detect this and provide actionable feedback.

    Returns:
        Dict with null analysis and specific feedback
    """
    if not results:
        return {"all_null": False, "null_columns": [], "feedback": ""}

    # Analyze which columns have all NULL values
    null_columns = []
    non_null_columns = []
    sample_values = {}

    # Get all column names from first result
    if results:
        columns = list(results[0].keys())

        for col in columns:
            values = [row.get(col) for row in results]
            non_null_values = [v for v in values if v is not None and str(v).strip()]

            if not non_null_values:
                null_columns.append(col)
            else:
                non_null_columns.append(col)
                sample_values[col] = non_null_values[0]

    # Generate specific feedback
    feedback_parts = []

    if null_columns and not non_null_columns:
        feedback_parts.append(
            f"ALL COLUMNS ARE NULL: {null_columns}. "
            "The query structure executed but data extraction failed completely."
        )
        feedback_parts.append(
            "This usually means:\n"
            "1. OPTIONAL MATCH returned no matches for value cells\n"
            "2. The col_index for value cells doesn't align with header col_index\n"
            "3. The row_index for the target row is incorrect\n"
            "4. Map literal keys don't match the actual property names being accessed"
        )

    elif null_columns:
        feedback_parts.append(
            f"PARTIAL NULL: Columns with all NULLs: {null_columns}. "
            f"Columns with values: {non_null_columns}."
        )
        if 'page' in non_null_columns and len(null_columns) > 3:
            feedback_parts.append(
                "Page numbers work but concentration values are NULL. "
                "Check that the header-to-value column mapping is correct."
            )

    return {
        "all_null": len(null_columns) > 0 and len(non_null_columns) == 0,
        "mostly_null": len(null_columns) > len(non_null_columns),
        "null_columns": null_columns,
        "non_null_columns": non_null_columns,
        "sample_values": sample_values,
        "feedback": "\n".join(feedback_parts)
    }


def analyze_expected_row_count(user_query: str, result_count: int, process_id: str) -> Dict[str, Any]:
    """
    Detect expected row count from query keywords and validate against actual results.

    GENERIC VALIDATION LOGIC:
    This only catches CLEAR bugs where "each page" returns exactly 1 row (global LIMIT bug).

    We do NOT assume a specific expected count because:
    - "second X for each page" only returns rows for pages that HAVE 2+ X rows
    - "X for each page" only returns rows for pages that HAVE X
    - The actual count depends on the data, not on total page count

    The ONLY suspicious case is returning exactly 1 row when query says "each page"
    because that's a clear indicator of a global LIMIT 1 bug.

    Args:
        user_query: User's natural language query
        result_count: Number of rows returned by the query
        process_id: Document UUID to count pages

    Returns:
        Dict with expects_multiple, expected_min, is_suspicious, feedback
    """
    analysis = {
        "expects_multiple": False,
        "expected_min": 1,
        "page_count": 0,
        "is_suspicious": False,
        "feedback": ""
    }

    query_lower = user_query.lower()

    # Keywords that indicate multi-page/multi-row results expected
    multi_page_keywords = [
        "each page", "every page", "all pages", "from all pages",
        "across pages", "per page", "for each page", "across all",
        "from every", "on all pages"
    ]

    # Check if any multi-page keyword is present
    for keyword in multi_page_keywords:
        if keyword in query_lower:
            analysis["expects_multiple"] = True
            break

    if not analysis["expects_multiple"]:
        return analysis

    # Get actual page count from Neo4j (for informational purposes only)
    try:
        neo4j_tools = Neo4jTools()
        with neo4j_tools.driver.session(database="neo4j") as session:
            page_count_result = session.run("""
                MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)
                RETURN count(p) AS page_count
            """, {"pid": process_id}).single()

            if page_count_result:
                analysis["page_count"] = page_count_result["page_count"]

        neo4j_tools.close()
    except Exception as e:
        logger.warning(f"Could not get page count for row validation: {e}")

    # GENERIC VALIDATION: Only flag as suspicious if EXACTLY 1 row returned
    # This catches the clear LIMIT 1 bug without making assumptions about data
    #
    # Why only check for 1 row:
    # - "second X for each page" may only match pages with 2+ X rows (could be 9 out of 104)
    # - "X for each page" may only match pages that have X (could be any number)
    # - We can't know the expected count without understanding the data filtering
    # - But returning EXACTLY 1 row when asking for "each page" is almost always a bug
    #
    # The minimum is 2 because "each page" implies multiple pages should match
    analysis["expected_min"] = 2

    # Detect filtering patterns in query (for better logging)
    filtering_patterns = {
        "nth_row": bool(re.search(r'\b(first|second|third|fourth|fifth|\d+(?:st|nd|rd|th))\b', query_lower)),
        "conditional": bool(re.search(r'\b(only|where|if|when|having)\b', query_lower)),
        "exclusion": bool(re.search(r'\b(not|except|exclude|without)\b', query_lower)),
    }
    has_filtering = any(filtering_patterns.values())

    if result_count == 1:
        analysis["is_suspicious"] = True
        analysis["feedback"] = f"""
SUSPICIOUS ROW COUNT: Query asks for data from "each page" but returned only 1 row.

This is almost certainly caused by a global LIMIT 1 clause at the end of the query.

Document has {analysis['page_count']} pages. Even with filtering (e.g., "second X" only matches
pages with 2+ X rows), returning exactly 1 row indicates a LIMIT bug.

FIX: Remove the global LIMIT clause, or restructure the query:
WRONG: ... ORDER BY page LIMIT 1  (limits ALL results to 1)
RIGHT: ... WITH page, head(collect(...)) AS first_match ...  (limits per page, returns all pages)

The query should return one row PER PAGE that matches the criteria, not one row total.
"""
    elif result_count > 1 and result_count < analysis["page_count"]:
        # Valid result - filtering reduced the count, not a bug
        filter_reasons = []
        if filtering_patterns["nth_row"]:
            filter_reasons.append("nth-row selection (e.g., 'second Count row')")
        if filtering_patterns["conditional"]:
            filter_reasons.append("conditional filtering")
        if filtering_patterns["exclusion"]:
            filter_reasons.append("exclusion criteria")

        filter_explanation = ", ".join(filter_reasons) if filter_reasons else "query-specific filtering"

        analysis["feedback"] = (
            f"VALID: Query returned {result_count} rows from {analysis['page_count']} pages. "
            f"Fewer rows than pages is expected due to: {filter_explanation}. "
            f"Only pages matching the filter criteria return results."
        )
        logger.info(f"  Row count validation: {result_count}/{analysis['page_count']} pages - VALID (filtered query)")

    return analysis


# =============================================================================
# SUCCESS BANK AUTO-WRITE (Phase 2)
# =============================================================================

def _write_to_success_bank(state: Dict[str, Any]) -> bool:
    """
    Write successful query to CypherSuccessBank for future retrieval.

    Only called on first-try successes (iteration == 1) to ensure quality.
    This enables the system to learn from successful queries and improve
    over time by providing better few-shot examples.

    Args:
        state: The agent state containing query, cypher, and results

    Returns:
        bool: True if write succeeded, False otherwise
    """
    from datetime import datetime

    weaviate_tools = WeaviateTools()

    try:
        # Extract node types from Cypher (include MergedCell)
        node_types = list(set(re.findall(r':(\w+)(?:\s*[\{\)\]])', state["generated_cypher"])))
        valid_node_types = ['Document', 'Page', 'Table', 'Cell', 'Line', 'Section', 'KV', 'MergedCell']
        node_types = [n for n in node_types if n in valid_node_types]

        # Extract main relationship path
        rels = re.findall(r'\[:(\w+)\]', state["generated_cypher"])
        rel_path = "->".join(rels) if rels else "unknown"

        # Generate embedding for user query
        query_embedding = weaviate_tools.generate_embedding(state["user_query"])

        if not query_embedding:
            logger.warning("Failed to generate embedding for Success Bank write")
            return False

        # Prepare success entry
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
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        # POST to Weaviate with timeout (don't block if slow)
        response = requests.post(
            f"{WEAVIATE_URL}/v1/objects",
            json={
                "class": "CypherSuccessBank",
                "properties": success_entry,
                "vector": query_embedding
            },
            timeout=5
        )

        if response.status_code == 200:
            logger.info(f"Successfully wrote to CypherSuccessBank! (node_types: {node_types})")
            return True
        else:
            logger.warning(f"Failed to write to Success Bank: {response.status_code} - {response.text[:200]}")
            return False

    except requests.Timeout:
        logger.warning("Success Bank write timed out (non-critical)")
        return False
    except Exception as e:
        logger.warning(f"Success Bank write failed (non-critical): {e}")
        return False


def validator_agent(state: AgentState) -> AgentState:
    """
    VALIDATOR AGENT with Self-Correction + PROFILE Analysis + NULL Detection

    UPGRADED per Google AI recommendations:
    1. PROFILE-based execution feedback (analyze DB hits, detect label scans)
    2. NULL value pattern detection with specific feedback
    3. Row count validation against expected values

    Provides specific, actionable feedback for retry if validation fails.
    """
    logger.info("=" * 60)
    logger.info("AGENT 4: VALIDATOR (with PROFILE + NULL Analysis)")
    logger.info("=" * 60)

    neo4j_tools = Neo4jTools()

    try:
        cypher = state["generated_cypher"]
        process_id = state["process_id"]

        # =====================================================================
        # STEP 1: Execute the query and get results
        # =====================================================================
        logger.info("Step 1: Executing Cypher query...")
        results = neo4j_tools.execute_cypher(cypher, {"process_id": process_id})

        state["execution_results"] = results[:20]
        state["result_count"] = len(results)

        # Check for errors
        if results and "error" in results[0]:
            error_msg = results[0]["error"]
            logger.error(f"Cypher execution error: {error_msg}")
            state["is_valid"] = False
            state["execution_error"] = error_msg
            state["validation_feedback"] = f"""
CYPHER EXECUTION ERROR: {error_msg}

This is a SYNTAX error. The Cypher query failed to execute.
Please check:
- All MATCH patterns are valid
- Property names are correct (text, row_index, col_index)
- Regex patterns are properly escaped
- All variables are defined before use
"""
            return state

        # Clear execution error on success
        state["execution_error"] = ""
        logger.info(f"Query returned {len(results)} rows")

        # =====================================================================
        # STEP 2: PROFILE Analysis (Google AI recommendation)
        # =====================================================================
        logger.info("Step 2: Running PROFILE analysis...")
        profile_info = analyze_query_profile(
            neo4j_tools.driver, cypher, {"process_id": process_id}
        )
        logger.info(f"  DB Hits: {profile_info['db_hits']}")
        logger.info(f"  Label Scan: {profile_info['has_label_scan']}")
        if profile_info['feedback']:
            logger.warning(f"  Profile Feedback: {profile_info['feedback']}")

        # =====================================================================
        # STEP 3: NULL Pattern Analysis (addresses the 9-rows-all-NULL issue)
        # =====================================================================
        logger.info("Step 3: Analyzing NULL patterns...")
        null_analysis = analyze_null_pattern(results)
        logger.info(f"  Null columns: {null_analysis['null_columns']}")
        logger.info(f"  Non-null columns: {null_analysis['non_null_columns']}")
        if null_analysis['feedback']:
            logger.warning(f"  NULL Feedback: {null_analysis['feedback'][:200]}")

        # Check if we have an expected row count from few-shot
        expected_rows = None
        for ex in state.get("similar_examples", []):
            if ex.get("expected_rows"):
                expected_rows = ex["expected_rows"]
                break

        # =====================================================================
        # STEP 3.5: ROW COUNT ANALYSIS (NEW - catches "each page" returning 1 row)
        # =====================================================================
        logger.info("Step 3.5: Analyzing expected row count from query keywords...")
        row_count_analysis = analyze_expected_row_count(
            state["user_query"],
            len(results),
            process_id
        )
        if row_count_analysis["expects_multiple"]:
            logger.info(f"  Query expects multi-page results: True")
            logger.info(f"  Document pages: {row_count_analysis['page_count']}")
            logger.info(f"  Expected min rows: {row_count_analysis['expected_min']}")
            logger.info(f"  Actual rows: {len(results)}")
            logger.info(f"  Suspicious: {row_count_analysis['is_suspicious']}")

        # =====================================================================
        # STEP 4: Comprehensive Validation with Combined Feedback
        # =====================================================================
        logger.info("Step 4: Validating results...")

        feedback_parts = []

        # Check 1: Zero rows
        if len(results) == 0:
            state["is_valid"] = False
            feedback_parts.append("""
VALIDATION FAILED: Query returned 0 rows.

The query executed but found no data. This usually means:
- Wrong row_index logic for finding the target row
- Text matching pattern doesn't match actual cell content
- The CONTAINS or regex pattern is too strict

Review the data snippet and adjust row_index logic.
""")

        # Check 2: Row count mismatch
        elif expected_rows and len(results) != expected_rows:
            state["is_valid"] = False
            if len(results) > expected_rows:
                feedback_parts.append(f"""
VALIDATION FAILED: Got {len(results)} rows but expected {expected_rows}.

Too many rows usually means:
- Missing aggregation/pivot logic
- Need to use collect() and list comprehension to pivot
- Need to group by page

Look at the reference Cypher that works and add the pivoting logic.
""")
            else:
                feedback_parts.append(f"""
VALIDATION FAILED: Got {len(results)} rows but expected {expected_rows}.

Too few rows usually means:
- Some pages are being filtered out
- Matching logic is too strict
- Check if all pages have the expected table structure
""")

        # Check 2.5: SUSPICIOUS ROW COUNT (NEW - catches "each page" returning 1 row)
        elif row_count_analysis["is_suspicious"]:
            state["is_valid"] = False
            feedback_parts.append(row_count_analysis["feedback"])

        # Check 3: ALL values are NULL (the key issue we encountered!)
        elif null_analysis["all_null"]:
            state["is_valid"] = False
            feedback_parts.append(f"""
VALIDATION FAILED: Got {len(results)} rows but ALL values are NULL!

{null_analysis['feedback']}

CRITICAL: Check that you're NOT modifying map literal keys.
Map literals like {{header: h.text, value: v.text}} use user-defined keys.
When you later access x.header or x.value, these are map keys, NOT Neo4j properties.
Do NOT "correct" them to Neo4j property names like is_header!
""")

        # Check 4: MOSTLY NULL (e.g., page works but values don't)
        elif null_analysis["mostly_null"]:
            state["is_valid"] = False
            feedback_parts.append(f"""
VALIDATION WARNING: Got {len(results)} rows but most columns are NULL.

{null_analysis['feedback']}

Working columns: {null_analysis['non_null_columns']}
NULL columns: {null_analysis['null_columns']}

The query structure is partially correct. Fix the value extraction:
- Verify the col_index alignment between headers and values
- Check OPTIONAL MATCH conditions
""")

        # Check 5: ANY column has all NULL values - trigger retry
        elif null_analysis["null_columns"]:
            state["is_valid"] = False
            feedback_parts.append(f"""
VALIDATION FAILED: Column(s) {null_analysis['null_columns']} have ALL NULL values.

The query executed and returned data for some columns, but these columns are missing:
{null_analysis['null_columns']}

IMPORTANT: The data for these columns might be in a DIFFERENT TABLE on the same PAGE.
For example, 'Batch Name' is often in a separate metadata table, not the ECD data table.

To fix: Instead of searching within the same table (t), search across ALL tables on the same PAGE (p):
- Change: OPTIONAL MATCH (t)-[:HAS_CELL]->(bn:Cell) WHERE ... 'batch name'
- To: OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t2:Table)-[:HAS_CELL]->(bn:Cell) WHERE ... 'batch name'

This searches ALL tables on the page, not just the ECD table.
""")

        # Check 6: Results look valid
        else:
            # Additional check: ensure we have meaningful non-null values
            has_meaningful_values = False
            for row in results[:5]:
                for key, val in row.items():
                    if val is not None and str(val).strip() and key != 'page':
                        has_meaningful_values = True
                        break

            if has_meaningful_values:
                state["is_valid"] = True
                logger.info("Results validated successfully!")

                # =====================================================================
                # AUTO-WRITE TO SUCCESS BANK (Phase 2)
                # Only write on first-try successes for quality assurance
                # =====================================================================
                if state.get("iteration", 1) == 1:
                    logger.info("First-try success! Writing to Success Bank...")
                    _write_to_success_bank(state)
            else:
                state["is_valid"] = False
                feedback_parts.append("""
VALIDATION FAILED: Results contain only page numbers but no actual data values.

Check the value extraction logic - OPTIONAL MATCH may be failing.
""")

        # Add PROFILE feedback if there are performance issues
        if profile_info['feedback']:
            feedback_parts.append(f"\nPROFILE ANALYSIS:\n{profile_info['feedback']}")

        state["validation_feedback"] = "\n".join(feedback_parts)

        # Print validation result (handle Unicode encoding for Windows)
        try:
            print("\n" + "=" * 60)
            print("VALIDATION RESULT:")
            print("=" * 60)
            print(f"Rows returned: {len(results)}")
            print(f"Valid: {state['is_valid']}")
            if results and len(results) > 0:
                # Convert to ASCII-safe string for Windows console
                sample_str = str(results[0])[:200]
                print(f"Sample: {sample_str.encode('ascii', 'replace').decode('ascii')}")
            if state.get("validation_feedback"):
                print(f"Feedback: {state['validation_feedback'][:300]}")
            print("=" * 60 + "\n")
        except UnicodeEncodeError:
            print("\n[Validation output contains Unicode - skipping display]\n")

    except Exception as e:
        logger.error(f"Validator error: {e}")
        # Don't mark as invalid for encoding errors if results were already validated
        if not state.get("is_valid"):
            state["is_valid"] = False
            state["validation_feedback"] = f"Execution error: {str(e)}"
    finally:
        neo4j_tools.close()

    return state

# =============================================================================
# AGENT 5: INTERPRETER AGENT (NEW - Converts JSON to Natural Language)
# =============================================================================

def interpreter_agent(state: AgentState) -> AgentState:
    """
    AGENT 5: Interpreter Agent

    Converts raw JSON query results into a clear, natural language answer.
    This improves UX by providing human-readable responses instead of raw data.

    Based on: Research paper recommendation #1 (arXiv:2511.08274v1)
    """
    logger.info("\n" + "=" * 60)
    logger.info("AGENT 5: INTERPRETER (JSON -> Natural Language)")
    logger.info("=" * 60)

    # Skip if query failed or no results
    if not state.get("is_valid") or not state.get("execution_results"):
        state["natural_answer"] = ""
        logger.info("Skipping interpretation - no valid results")
        return state

    results = state.get("execution_results", [])
    user_query = state.get("user_query", "")
    result_count = state.get("result_count", len(results))

    # Build a summary of the results for the LLM
    # Limit results shown to avoid token overflow
    results_preview = results[:20] if len(results) > 20 else results
    results_json = json.dumps(results_preview, indent=2, default=str)

    # Check if results were truncated
    truncation_note = ""
    if len(results) > 20:
        truncation_note = f"\n(Note: Showing first 20 of {len(results)} total results)"

    prompt = f"""You are a helpful assistant that converts database query results into natural language answers.

USER QUESTION: {user_query}

QUERY RESULTS ({result_count} rows total):
{results_json}{truncation_note}

YOUR TASK: Generate a response with TWO parts:

PART 1 - OUTPUT_TYPE: Decide if the user needs a TABLE or just a TEXT answer.
- OUTPUT_TYPE: TABLE - Use when user asks for multiple rows, "all values", "list", "extract", "table", "across pages", "each page", "row data", etc.
- OUTPUT_TYPE: TEXT - Use when user asks for a single value like "what is the batch name?", "find the date", "get the ID", etc.

PART 2 - ANSWER: Generate the natural language answer.

EXAMPLES:

Example 1:
User: "What is the Batch Name?"
Results: [{{"batch_name": "ABC-123"}}]
Response:
OUTPUT_TYPE: TEXT
ANSWER: The Batch Name is **ABC-123**.

Example 2:
User: "Get all concentration values from ECD tables"
Results: [{{"page": 1, "c1": "71.45", "c2": "362.34"}}, {{"page": 2, "c1": "64.19", "c2": "449.16"}}]
Response:
OUTPUT_TYPE: TABLE
ANSWER: Found concentration values across 2 pages. Page 1 shows c1=71.45, c2=362.34. Page 2 shows c1=64.19, c2=449.16.

Example 3:
User: "What is the Project Name?"
Results: [{{"project_name": "Project Alpha"}}]
Response:
OUTPUT_TYPE: TEXT
ANSWER: The Project Name is **Project Alpha**.

Example 4:
User: "Extract all row data from ECD tables with batch number"
Results: [{{"page": 1, "batch": "X1", "count": 100}}, {{"page": 2, "batch": "X1", "count": 150}}]
Response:
OUTPUT_TYPE: TABLE
ANSWER: Found ECD data for batch X1 across 2 pages with count values of 100 (page 1) and 150 (page 2).

NOW GENERATE YOUR RESPONSE:
OUTPUT_TYPE: [TABLE or TEXT]
ANSWER: [Your natural language answer]"""

    try:
        # Use fast model (Haiku) for interpretation
        response = call_claude(prompt, MODELS["validator"], max_tokens=500)
        response = response.strip()

        # Parse OUTPUT_TYPE and ANSWER from response
        output_type = "TABLE"  # Default to table
        natural_answer = response

        # Extract OUTPUT_TYPE
        if "OUTPUT_TYPE:" in response:
            lines = response.split("\n")
            for line in lines:
                if line.strip().startswith("OUTPUT_TYPE:"):
                    type_value = line.replace("OUTPUT_TYPE:", "").strip().upper()
                    if "TEXT" in type_value:
                        output_type = "TEXT"
                    elif "TABLE" in type_value:
                        output_type = "TABLE"
                    break

        # Extract ANSWER
        if "ANSWER:" in response:
            answer_start = response.find("ANSWER:")
            natural_answer = response[answer_start + 7:].strip()
        else:
            # If no ANSWER: marker, use the whole response
            natural_answer = response

        # If the LLM returned nothing useful, create a basic answer
        if not natural_answer or len(natural_answer) < 10:
            natural_answer = f"Found {result_count} matching results for your query."
            output_type = "TABLE" if result_count > 1 else "TEXT"

        state["natural_answer"] = natural_answer
        state["output_type"] = output_type  # Store the output type decision

        logger.info(f"Interpreter: OUTPUT_TYPE={output_type}, Answer length={len(natural_answer)} chars")

        # Print for debugging
        try:
            print("\n" + "-" * 60)
            print(f"INTERPRETER OUTPUT (TYPE: {output_type}):")
            print("-" * 60)
            # Handle potential Unicode
            print(natural_answer.encode('ascii', 'replace').decode('ascii'))
            print("-" * 60 + "\n")
        except UnicodeEncodeError:
            print("\n[Natural answer contains Unicode - see logs]\n")

    except Exception as e:
        logger.error(f"Interpreter error: {e}")
        state["natural_answer"] = f"Found {result_count} results for your query."
        state["output_type"] = "TABLE"  # Default to table on error

    return state

# =============================================================================
# ROUTING LOGIC
# =============================================================================

def should_retry(state: AgentState) -> str:
    """Determine if we should retry generation or finish."""
    iteration = state.get("iteration", 1)
    max_iterations = state.get("max_iterations", 3)
    is_valid = state.get("is_valid", False)

    if is_valid:
        logger.info("Results valid - finishing")
        return "finish"

    if iteration >= max_iterations:
        logger.warning(f"Max iterations ({max_iterations}) reached - finishing")
        return "finish"

    logger.info(f"Retrying (iteration {iteration + 1}/{max_iterations})")
    state["iteration"] = iteration + 1
    return "retry"

def prepare_final_answer(state: AgentState) -> AgentState:
    """Prepare the final answer - SMART OUTPUT: table only when needed."""
    import pandas as pd

    if state.get("is_valid"):
        results = state.get("execution_results", [])

        if results:
            # Convert to pandas DataFrame for better display
            df = pd.DataFrame(results)

            # Sanitize column names - replace Unicode >= symbols with ASCII
            new_cols = {}
            for col in df.columns:
                new_col = str(col)
                # Replace common Unicode symbols
                new_col = new_col.replace('\u2265', '>=')  # ≥ -> >=
                new_col = new_col.replace('\u2264', '<=')  # ≤ -> <=
                new_col = new_col.replace('\u03bc', 'u')   # μ -> u
                if new_col != col:
                    new_cols[col] = new_col
            if new_cols:
                df = df.rename(columns=new_cols)

            # Reorder columns to put page/Batch_Name first if they exist
            priority_cols = ['page', 'Page', 'Batch_Name', 'batch_name']
            cols = list(df.columns)
            ordered_cols = []
            for pc in priority_cols:
                if pc in cols:
                    ordered_cols.append(pc)
                    cols.remove(pc)
            ordered_cols.extend(cols)
            df = df[ordered_cols]

            # Get output_type from Interpreter Agent (TEXT = no table, TABLE = show table)
            output_type = state.get("output_type", "TABLE")

            answer_lines = ["Query executed successfully!", ""]

            # Include natural language answer if available
            natural_answer = state.get("natural_answer", "")
            if natural_answer:
                answer_lines.append("=" * 100)
                answer_lines.append("ANSWER:")
                answer_lines.append("=" * 100)
                try:
                    answer_lines.append(natural_answer.encode('ascii', 'replace').decode('ascii'))
                except Exception:
                    answer_lines.append(natural_answer)
                answer_lines.append("")

            # SMART OUTPUT: Only show table if output_type is TABLE
            if output_type == "TABLE":
                answer_lines.append("=" * 100)
                answer_lines.append("RESULTS AS DATAFRAME:")
                answer_lines.append("=" * 100)
                # Handle potential Unicode in data values
                try:
                    df_str = df.to_string(index=False)
                    answer_lines.append(df_str.encode('ascii', 'replace').decode('ascii'))
                except Exception:
                    answer_lines.append(df.to_string(index=False))
                answer_lines.append("=" * 100)
                answer_lines.append(f"Total rows: {state.get('result_count', len(results))}")
            else:
                # TEXT output - no table, just show row count for reference
                answer_lines.append(f"(Query returned {state.get('result_count', len(results))} row(s))")

            state["final_answer"] = "\n".join(answer_lines)
        else:
            state["final_answer"] = "Query executed but returned no results."
    else:
        state["final_answer"] = f"Query generation failed after {state.get('iteration', 1)} attempts.\nLast feedback: {state.get('validation_feedback', 'Unknown')[:500]}"

    return state

# =============================================================================
# BUILD LANGGRAPH
# =============================================================================

def build_fewshot_pipeline():
    """Build the Few-Shot + Logic-First pipeline with NEV (Named Entity Verification) + Interpreter."""

    workflow = StateGraph(AgentState)

    # Add nodes - INCLUDING REFORMULATOR (Agent 0), NEV AUDITOR (Agent 3.5) and INTERPRETER (Agent 5)
    workflow.add_node("reformulate", query_reformulator_agent)  # Agent 0: Query Reformulation
    workflow.add_node("gather_context", context_gatherer_agent)
    workflow.add_node("plan", logic_planner_agent)
    workflow.add_node("generate", cypher_generator_agent)
    workflow.add_node("nev_audit", nev_auditor_agent)  # Agent 3.5: Named Entity Verification
    workflow.add_node("validate", validator_agent)
    workflow.add_node("interpret", interpreter_agent)  # Agent 5: JSON -> Natural Language
    workflow.add_node("finalize", prepare_final_answer)

    # Add edges - Reformulator runs FIRST, then NEV sits between generator and validator
    workflow.set_entry_point("reformulate")  # Start with query reformulation
    workflow.add_edge("reformulate", "gather_context")  # Then gather context
    workflow.add_edge("gather_context", "plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "nev_audit")   # Generator -> NEV Auditor
    workflow.add_edge("nev_audit", "validate")   # NEV Auditor -> Validator

    # Conditional edge: retry or finish (now goes to interpret first)
    workflow.add_conditional_edges(
        "validate",
        should_retry,
        {
            "retry": "plan",      # Go back to planning with feedback
            "finish": "interpret"  # Go to interpreter before finalize
        }
    )

    # Interpreter -> Finalize
    workflow.add_edge("interpret", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()

# =============================================================================
# MAIN EXECUTION
# =============================================================================

def run_fewshot_cypher_generation(
    user_query: str,
    process_id: str,
    max_iterations: int = 3
) -> Dict[str, Any]:
    """
    Run the Few-Shot + Logic-First Cypher generation pipeline.
    """
    logger.info("=" * 80)
    logger.info("FEW-SHOT + LOGIC-FIRST CYPHER GENERATION")
    logger.info("=" * 80)
    logger.info(f"Query: {user_query}")
    logger.info(f"Process ID: {process_id}")
    logger.info(f"Max iterations: {max_iterations}")
    logger.info("=" * 80)

    # Build graph
    graph = build_fewshot_pipeline()

    # Initial state
    initial_state = {
        "user_query": user_query,
        "process_id": process_id,
        "weaviate_chunks": [],
        "weaviate_headers": [],
        "weaviate_context": "",
        # NEW: Structural Probe results (where data actually exists)
        "structural_probe": {},
        "probe_context": "",
        "similar_examples": [],
        "filtered_schema": "",
        "data_snippet": "",
        "logical_plan": "",
        "generated_cypher": "",
        "execution_results": [],
        "result_count": 0,
        "is_valid": False,
        "validation_feedback": "",
        "execution_error": "",
        "nev_corrections": [],  # NEV corrections made
        "nev_verified": False,  # NEV verification status
        "iteration": 1,
        "max_iterations": max_iterations,
        "final_answer": "",
        "error": "",
        "natural_answer": "",  # Interpreter Agent output (JSON -> Natural Language)
        "output_type": "TABLE",  # Default to TABLE, Interpreter decides TEXT vs TABLE
        # Query Entity Validation (NEW - validates user query terms against actual data)
        "entity_validation": {},
        "validated_entities": [],
        "invalid_entities": [],
        "entity_validation_context": ""
    }

    # Run the graph
    try:
        final_state = graph.invoke(initial_state)

        print("\n" + "=" * 80)
        print("FINAL RESULT")
        print("=" * 80)
        print(f"Success: {final_state.get('is_valid', False)}")
        print(f"Iterations used: {final_state.get('iteration', 1)}")
        print(f"Result count: {final_state.get('result_count', 0)}")
        print(f"Few-shot examples used: {len(final_state.get('similar_examples', []))}")
        print(f"NEV corrections made: {len(final_state.get('nev_corrections', []))}")
        if final_state.get('nev_corrections'):
            print(f"  Corrections: {final_state.get('nev_corrections')}")
        print("")
        print("FINAL CYPHER:")
        print("-" * 40)
        print(final_state.get("generated_cypher", "N/A")[:1500])
        print("-" * 40)
        print("")
        print("ANSWER:")
        print("-" * 40)
        print(final_state.get("final_answer", "N/A"))
        print("=" * 80)

        return {
            "success": final_state.get("is_valid", False),
            "cypher": final_state.get("generated_cypher", ""),
            "results": final_state.get("execution_results", []),
            "result_count": final_state.get("result_count", 0),
            "iterations": final_state.get("iteration", 1),
            "logical_plan": final_state.get("logical_plan", ""),
            "answer": final_state.get("final_answer", ""),
            "natural_answer": final_state.get("natural_answer", "")  # NEW: Natural language summary
        }

    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("TESTING FEW-SHOT + LOGIC-FIRST CYPHER GENERATION")
    print("=" * 80)
    print(f"Process ID: {PROCESS_ID}")
    print(f"Query: {USER_QUERY}")
    print(f"Models: Planner={MODELS['planner']}, Generator={MODELS['generator']}, Validator={MODELS['validator']}")
    print("=" * 80 + "\n")

    result = run_fewshot_cypher_generation(
        user_query=USER_QUERY,
        process_id=PROCESS_ID,
        max_iterations=3
    )

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print(f"Success: {result.get('success')}")
    print(f"Result count: {result.get('result_count', 0)}")
    print(f"Iterations: {result.get('iterations', 0)}")
