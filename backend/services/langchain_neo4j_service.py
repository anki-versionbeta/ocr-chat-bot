"""
LangChain Neo4j Service for Phase 6 - Dynamic Cypher Generation

This module provides dynamic Cypher query generation using LangChain's
Neo4j integration. Instead of hardcoded Cypher templates, we use:
1. Neo4jGraph - Auto-fetch schema (nodes, relationships, properties)
2. GraphCypherQAChain - LLM generates Cypher based on schema + user question

Key Features:
- Schema-aware: Automatically discovers Neo4j graph structure
- Dynamic Cypher: LLM generates queries based on actual schema
- Context-enhanced: Uses Weaviate context to improve query accuracy
- Iliad API: Uses existing Iliad gateway for Claude access

Graph Model:
- Document → Page → Table/Section → Cell/Line
- Relationships: CONTAINS_PAGE, CONTAINS_TABLE, HAS_CELL, SAME_ROW, SAME_COL

Updated: February 11, 2026
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache

import requests
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.prompts import PromptTemplate
from langchain_core.language_models.llms import LLM
from langchain_core.callbacks import CallbackManagerForLLMRun

load_dotenv()

logger = logging.getLogger("ocr-chatbot.langchain_neo4j")


# Configuration - Use same hardcoded values as neo4j_service.py for consistency
# Note: .env may have different values, so we hardcode to match neo4j_service.py
NEO4J_URI = "bolt://10.242.190.53:7687"
NEO4J_USERNAME = "neo4j"
NEO4J_PASSWORD = REDACTED
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED


class IliadClaudeLLM(LLM):
    """
    Custom LangChain LLM wrapper for Iliad API (Claude).

    This allows GraphCypherQAChain to use our existing Iliad gateway
    instead of direct Anthropic API calls.
    """

    model: str = "claude-haiku-4-5-20251001"
    temperature: float = 0.0
    max_tokens: int = 2000

    @property
    def _llm_type(self) -> str:
        return "iliad_claude"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> str:
        """Call the Iliad API to generate a response."""
        return self._call_iliad(prompt)

    def _call_iliad(self, prompt: str) -> str:
        """Call Iliad API with prompt."""
        try:
            headers = {
                "x-api-key": ILIAD_API_KEY,
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [{"role": "user", "content": prompt}]
            }

            response = requests.post(
                f"{ILIAD_URL}/anthropic/v1/messages",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Iliad API error: {response.status_code} - {response.text}")
                return f"Error calling LLM: {response.status_code}"

            result = response.json()
            return result.get("content", [{}])[0].get("text", "")

        except Exception as e:
            logger.error(f"Iliad LLM call error: {e}")
            return f"Error: {str(e)}"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model": self.model, "temperature": self.temperature}


# Custom prompt for COA document Cypher generation with FEW-SHOT EXAMPLES
CYPHER_GENERATION_TEMPLATE = """You are a Cypher query expert for a Certificate of Analysis (COA) document database.

## DATABASE SCHEMA
{schema}

## CRITICAL RULES
- ALWAYS filter by process_id = $process_id to isolate the specific document
- Cell nodes have: text, row_index, col_index, is_header, bbox_* properties
- Table nodes link to cells via HAS_CELL relationship
- NEVER generate destructive queries (DELETE, DROP, etc.)

## IMPORTANT: UNDERSTAND USER INTENT
- When user says "cell 3" or "row with 3 minor defect", they mean: find cell where cell.text CONTAINS '3 minor defect'
- DO NOT interpret numbers as column indices unless user explicitly says "column 3" or "col 3"
- "get me the row that have cell 3 minor defect" = search for cell.text containing '3 minor defect', then get entire row
- ALWAYS search by TEXT content (cell.text), not by position (col_index)

## FEW-SHOT EXAMPLES (Copy these patterns!)

**Example 1: Find row containing specific text with all column values**
Question: "get me the row that have cell 3 minor defect"
Question: "Find the row containing '3 Minor defect' with all column values"
Intent: Search for cell TEXT containing '3 minor defect', then return ALL cells in that row
```cypher
MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(target:Cell)
WHERE toLower(target.text) CONTAINS toLower('3 minor defect')
WITH target, t, p
MATCH (t)-[:HAS_CELL]->(rowCell:Cell)
WHERE rowCell.row_index = target.row_index
OPTIONAL MATCH (t)-[:HAS_CELL]->(header:Cell)
WHERE header.col_index = rowCell.col_index AND (header.is_header = true OR header.row_index = 0 OR header.row_index = 1)
RETURN rowCell.col_index as col, rowCell.text as value, header.text as column_header, rowCell.row_index as row, p.page_num as page
ORDER BY rowCell.col_index
```

**Example 2: Extract all values from a specific column**
Question: "Get all Defect Class values"
```cypher
MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
WHERE (header.is_header = true OR header.row_index = 0 OR header.row_index = 1) AND toLower(header.text) CONTAINS toLower('defect class')
WITH t, header, p
MATCH (t)-[:HAS_CELL]->(dataCell:Cell)
WHERE dataCell.col_index = header.col_index AND dataCell.row_index > 1
RETURN dataCell.text as value, dataCell.row_index as row, header.text as column_header, p.page_num as page
ORDER BY dataCell.row_index
```

**Example 3: Count tables in document**
Question: "How many tables are in this document?"
```cypher
MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
RETURN count(DISTINCT p) as pages, count(DISTINCT t) as tables
```

**Example 4: Get all column headers**
Question: "What columns are in the table?"
```cypher
MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
WHERE c.is_header = true OR c.row_index = 0 OR c.row_index = 1
RETURN DISTINCT c.text as header, c.col_index as col
ORDER BY c.col_index
```

## CURRENT USER QUERY
Question: {question}

## CONTEXT FROM WEAVIATE (Use this to understand what data exists!)
{context}

## YOUR TASK
1. READ the Weaviate context above - it shows actual cell values in the document
2. Generate Cypher that searches cell.text for the user's search term
3. Use $process_id parameter for document filtering
4. DO NOT use col_index to search - use toLower(cell.text) CONTAINS toLower('search term')

Generate ONLY the Cypher query. No explanations."""


CYPHER_QA_TEMPLATE = """Based on the Neo4j query results, answer the user's question.

Question: {question}
Query Results: {context}

Provide a clear, concise answer. If the results contain table data, format it nicely.
If no results were found, say so clearly."""


class LangChainNeo4jService:
    """
    Service for dynamic Cypher generation using LangChain Neo4j.

    This replaces hardcoded Cypher templates with LLM-generated queries
    based on the actual Neo4j schema.
    """

    def __init__(self):
        """Initialize the LangChain Neo4j service."""
        self.graph: Optional[Neo4jGraph] = None
        self.llm: Optional[IliadClaudeLLM] = None
        self.qa_chain: Optional[GraphCypherQAChain] = None
        self._schema_cache: Optional[str] = None
        self._native_driver = None  # Native neo4j driver for fallback

        self._initialize()

    def _initialize(self, retry_count: int = 3) -> None:
        """Initialize Neo4j graph and LLM with driver injection workaround.

        Uses native neo4j driver first (which works reliably) then passes to
        Neo4jGraph to bypass its internal connection issues.
        """
        import time

        for attempt in range(retry_count):
            try:
                logger.info(f"[LangChain-Neo4j] Attempting connection (attempt {attempt + 1}/{retry_count})...")
                logger.info(f"[LangChain-Neo4j] URI: {NEO4J_URI}, User: {NEO4J_USERNAME}")

                # Step 1: Create native driver first (this works reliably)
                self._native_driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
                )

                # Step 2: Verify native driver works
                with self._native_driver.session(database="neo4j") as session:
                    result = session.run("RETURN 1 as test")
                    test_val = result.single()["test"]
                    logger.info(f"[LangChain-Neo4j] Native driver verified: test={test_val}")

                # Step 3: Initialize Neo4jGraph using the working driver
                # Try driver injection if supported, otherwise use standard params
                try:
                    # Some versions support driver parameter
                    self.graph = Neo4jGraph(
                        driver=self._native_driver,
                        database="neo4j",
                        enhanced_schema=True
                    )
                    logger.info("[LangChain-Neo4j] Using driver injection method")
                except TypeError:
                    # Fallback: standard parameter method
                    logger.info("[LangChain-Neo4j] Driver injection not supported, using standard params")
                    self.graph = Neo4jGraph(
                        url=NEO4J_URI,
                        username=NEO4J_USERNAME,
                        password=REDACTED
                        database="neo4j",
                        enhanced_schema=True
                    )

                # Initialize Iliad Claude LLM
                self.llm = IliadClaudeLLM(
                    model="claude-haiku-4-5-20251001",
                    temperature=0.0,
                    max_tokens=REDACTED
                )

                # Cache schema
                self._schema_cache = self.graph.get_schema

                logger.info("✅ LangChain Neo4j service initialized successfully")
                logger.info(f"[LangChain-Neo4j] Schema (first 300 chars): {self._schema_cache[:300]}..." if self._schema_cache else "No schema")
                return  # Success, exit retry loop

            except Exception as e:
                logger.error(f"[LangChain-Neo4j] Attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                if attempt < retry_count - 1:
                    logger.info(f"[LangChain-Neo4j] Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    logger.error(f"[LangChain-Neo4j] All {retry_count} attempts failed")
                    self.graph = None
                    self.llm = None
                    self._native_driver = None

    @property
    def is_connected(self) -> bool:
        """Check if service is properly connected."""
        return self.graph is not None and self.llm is not None

    @property
    def schema(self) -> str:
        """Get cached Neo4j schema."""
        if self._schema_cache:
            return self._schema_cache
        if self.graph:
            self._schema_cache = self.graph.get_schema
            return self._schema_cache
        return "Schema not available"

    # =========================================================================
    # IMPROVEMENT METHODS (The 20% from the AI analysis)
    # =========================================================================

    def _inject_limit_if_missing(self, cypher: str, default_limit: int = 5000) -> str:
        """
        IMPROVEMENT B: Add LIMIT clause if not present (safety measure).
        Prevents runaway queries that return millions of rows.

        NOTE: Increased default from 100 to 5000 to support multi-page extraction.
        For a 104-page document with ~50 concentration values per page, we need ~5000+ rows.
        """
        if not cypher:
            return cypher

        cypher_upper = cypher.upper()
        # Check if LIMIT is already present
        if "LIMIT" in cypher_upper:
            return cypher

        # Don't add LIMIT to aggregate queries (they typically return 1 row)
        aggregate_keywords = ["COUNT(", "SUM(", "AVG(", "MAX(", "MIN(", "COLLECT("]
        if any(kw in cypher_upper for kw in aggregate_keywords):
            return cypher

        # Inject LIMIT at the end
        cypher = cypher.rstrip().rstrip(';')
        cypher = f"{cypher} LIMIT {default_limit}"
        logger.debug(f"Injected LIMIT {default_limit} into Cypher query")

        return cypher

    def _validate_cypher_syntax(self, cypher: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        IMPROVEMENT C: Validate Cypher syntax using EXPLAIN before execution.
        This catches syntax errors without actually running the query.
        """
        if not cypher or not self._native_driver:
            return True, ""  # Skip validation if no driver

        try:
            with self._native_driver.session(database="neo4j") as session:
                # EXPLAIN validates syntax without executing
                session.run(f"EXPLAIN {cypher}", params)
            return True, ""

        except Exception as e:
            error_msg = str(e)
            logger.debug(f"Cypher syntax validation failed: {error_msg}")
            return False, error_msg

    def validate_question_against_schema(self, question: str) -> Tuple[bool, str]:
        """
        IMPROVEMENT D: Validate if user question can be answered from schema.
        Uses a quick LLM check before generating full Cypher.

        Returns:
            Tuple of (is_valid, guidance_message)
        """
        if not self.is_connected:
            return True, ""  # Skip validation if not connected

        try:
            validation_prompt = f"""
You are validating if a user question can be answered from a Neo4j database.

DATABASE SCHEMA:
{self.schema[:2000]}

USER QUESTION: {question}

TASK: Can this question be answered using the schema above?
- If YES, respond with exactly: VALID
- If NO, respond with a brief explanation of what IS available in the database.

Example valid questions: find rows, get column data, count tables, find cells containing text
Example invalid questions: send email, calculate tax, connect to external API

Response:"""

            response = self.llm._call_iliad(validation_prompt).strip()

            if response.upper() == "VALID":
                return True, ""
            else:
                return False, response

        except Exception as e:
            logger.warning(f"Schema validation error: {e}")
            return True, ""  # On error, allow the query to proceed

    def generate_cypher(
        self,
        question: str,
        process_id: str,
        weaviate_context: str = ""
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate Cypher query dynamically using LLM.

        Args:
            question: User's question
            process_id: Document UUID for filtering
            weaviate_context: Optional context from Weaviate (column hints, etc.)

        Returns:
            Tuple of (cypher_query, parameters)
        """
        if not self.is_connected:
            logger.warning("LangChain Neo4j not connected, returning empty query")
            return "", {}

        try:
            # Build prompt with schema and context
            prompt = CYPHER_GENERATION_TEMPLATE.format(
                schema=self.schema,
                question=question,
                context=weaviate_context or "No additional context"
            )

            # Generate Cypher using LLM
            cypher = self.llm._call_iliad(prompt).strip()

            # Clean up the Cypher (remove markdown code blocks if present)
            if "```" in cypher:
                import re
                cypher_match = re.search(r'```(?:cypher)?\s*(.*?)\s*```', cypher, re.DOTALL)
                if cypher_match:
                    cypher = cypher_match.group(1).strip()

            # IMPROVEMENT B: Add LIMIT if not present (safety)
            cypher = self._inject_limit_if_missing(cypher)

            # Parameters always include process_id
            params = {"process_id": process_id}

            # IMPROVEMENT C: Validate Cypher syntax before returning
            is_valid, validation_error = self._validate_cypher_syntax(cypher, params)
            if not is_valid:
                logger.warning(f"Generated Cypher has syntax error: {validation_error}")
                # Return it anyway - the retry mechanism will handle it
                # But log the error so we know

            logger.info(f"Generated Cypher: {cypher[:200]}...")

            return cypher, params

        except Exception as e:
            logger.error(f"Cypher generation error: {e}")
            return "", {}

    def execute_dynamic_query(
        self,
        question: str,
        process_id: str,
        weaviate_context: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Generate and execute Cypher query dynamically.

        Args:
            question: User's question
            process_id: Document UUID
            weaviate_context: Context from Weaviate (headers, values found)

        Returns:
            Query results as list of dicts
        """
        if not self.is_connected:
            logger.warning("LangChain Neo4j not connected")
            return []

        try:
            # Generate Cypher
            cypher, params = self.generate_cypher(question, process_id, weaviate_context)

            if not cypher:
                return []

            # Execute query
            results = self.graph.query(cypher, params=params)

            logger.info(f"Dynamic query returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Dynamic query execution error: {e}")
            return []

    def query_with_context(
        self,
        question: str,
        process_id: str,
        weaviate_chunks: List[Dict[str, Any]],
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Execute query using Weaviate context with SELF-TESTING and RETRY.

        This is the main entry point for hybrid Weaviate+Neo4j queries.

        NEW: Self-testing mechanism:
        1. Generate Cypher from LLM
        2. Execute and TEST the results
        3. If results are empty/invalid, RETRY with error feedback
        4. Fall back to template-based Cypher if dynamic fails

        Args:
            question: User's question
            process_id: Document UUID
            weaviate_chunks: Chunks from Weaviate search (contain headers, values)
            max_retries: Maximum retry attempts (default 2)

        Returns:
            Dict with results and metadata
        """
        if not self.is_connected:
            return {
                "success": False,
                "error": "LangChain Neo4j not connected",
                "results": [],
                "cypher": ""
            }

        # Extract context from Weaviate chunks ONCE
        context = self._extract_weaviate_context(weaviate_chunks)
        logger.info(f"Weaviate context for Cypher generation:\n{context[:500]}...")

        last_error = None
        last_cypher = None
        all_attempts = []

        for attempt in range(max_retries + 1):
            try:
                # On retry, add error feedback to prompt
                retry_context = context
                if attempt > 0 and last_error:
                    retry_context = f"{context}\n\nPREVIOUS ATTEMPT FAILED:\n- Cypher: {last_cypher[:200]}...\n- Error: {last_error}\n- Please fix the query and try a different approach."
                    logger.info(f"Retry {attempt}: Adding error feedback to prompt")

                # Generate Cypher
                cypher, params = self.generate_cypher(question, process_id, retry_context)

                if not cypher:
                    last_error = "Failed to generate Cypher query"
                    continue

                last_cypher = cypher
                all_attempts.append({"attempt": attempt + 1, "cypher": cypher[:300]})

                # TEST: Execute the query
                logger.info(f"[Attempt {attempt + 1}] Testing Cypher: {cypher[:150]}...")
                results = self.graph.query(cypher, params=params)

                # VALIDATE: Check if results are meaningful
                if not results:
                    last_error = f"Query returned 0 results. Expected data for question: '{question}'"
                    logger.warning(f"[Attempt {attempt + 1}] Empty results, will retry...")
                    continue

                # Check if results have expected structure
                sample = results[0] if results else {}
                if isinstance(sample, dict):
                    # Good - we have structured data
                    logger.info(f"[Attempt {attempt + 1}] SUCCESS: Got {len(results)} results with keys: {list(sample.keys())[:5]}")
                else:
                    last_error = f"Results have unexpected format: {type(sample)}"
                    continue

                # SUCCESS - Return results
                return {
                    "success": True,
                    "results": results,
                    "cypher": cypher,
                    "params": params,
                    "result_count": len(results),
                    "attempts": all_attempts,
                    "retries_used": attempt
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"[Attempt {attempt + 1}] Query execution error: {e}")

        # All retries failed - return best effort
        logger.warning(f"All {max_retries + 1} attempts failed. Last error: {last_error}")

        # Try to return whatever we got, even if empty
        return {
            "success": False,
            "error": f"Failed after {max_retries + 1} attempts: {last_error}",
            "results": [],
            "cypher": last_cypher or "",
            "attempts": all_attempts
        }

    def query_with_context_and_fallback(
        self,
        question: str,
        process_id: str,
        weaviate_chunks: List[Dict[str, Any]],
        cypher_templates = None
    ) -> Dict[str, Any]:
        """
        Execute query with fallback to template-based Cypher.

        Flow:
        1. Try dynamic LLM-generated Cypher (with retry)
        2. If fails, fall back to cypher_templates library
        3. Return best available results

        Args:
            question: User's question
            process_id: Document UUID
            weaviate_chunks: Weaviate search results
            cypher_templates: Optional CypherTemplates instance for fallback

        Returns:
            Dict with results
        """
        # First try dynamic generation with retry
        result = self.query_with_context(question, process_id, weaviate_chunks)

        if result.get("success") and result.get("results"):
            result["method"] = "dynamic_cypher"
            return result

        # Dynamic failed - try template fallback if available
        if cypher_templates:
            logger.info("Dynamic Cypher failed, trying template fallback...")

            try:
                # Extract potential header patterns from context
                context = self._extract_weaviate_context(weaviate_chunks)

                # Detect query type and use appropriate template
                question_lower = question.lower()

                if "row" in question_lower and ("all" in question_lower or "column" in question_lower):
                    # Row extraction query - find cell then get SAME_ROW
                    # Extract search term from question
                    import re
                    match = re.search(r'(?:containing?|with|has)\s+["\']?([^"\']+)["\']?', question_lower)
                    if match:
                        search_term = match.group(1).strip()
                        cypher, params = cypher_templates.find_row_by_cell_value(process_id, search_term)
                        results = self.graph.query(cypher, params=params)
                        if results:
                            return {
                                "success": True,
                                "results": results,
                                "cypher": cypher,
                                "method": "template_fallback",
                                "result_count": len(results)
                            }

                elif "column" in question_lower or "values" in question_lower:
                    # Column extraction query
                    headers = self._extract_header_names_from_context(context)
                    for header in headers[:3]:
                        cypher, params = cypher_templates.extract_column_by_header(process_id, header)
                        results = self.graph.query(cypher, params=params)
                        if results:
                            return {
                                "success": True,
                                "results": results,
                                "cypher": cypher,
                                "method": "template_fallback",
                                "result_count": len(results)
                            }

            except Exception as e:
                logger.error(f"Template fallback also failed: {e}")

        # Return the original failed result
        result["method"] = "dynamic_cypher_failed"
        return result

    def _extract_header_names_from_context(self, context: str) -> List[str]:
        """Extract header names from Weaviate context string."""
        import re
        headers = []
        # Pattern: "Column headers: Name (col 0), Age (col 1), ..."
        match = re.search(r'Column headers:\s*([^\n]+)', context)
        if match:
            header_str = match.group(1)
            # Extract just the names before (col X)
            for part in header_str.split(','):
                name_match = re.match(r'\s*([^(]+)', part)
                if name_match:
                    headers.append(name_match.group(1).strip())
        return headers

    def _query_with_context_original(
        self,
        question: str,
        process_id: str,
        weaviate_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Original implementation without retry (kept for reference)."""
        if not self.is_connected:
            return {
                "success": False,
                "error": "LangChain Neo4j not connected",
                "results": [],
                "cypher": ""
            }

        try:
            context = self._extract_weaviate_context(weaviate_chunks)
            cypher, params = self.generate_cypher(question, process_id, context)

            if not cypher:
                return {
                    "success": False,
                    "error": "Failed to generate Cypher",
                    "results": [],
                    "cypher": ""
                }

            results = self.graph.query(cypher, params=params)

            return {
                "success": True,
                "results": results,
                "cypher": cypher,
                "params": params,
                "result_count": len(results)
            }

        except Exception as e:
            logger.error(f"Context query error: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "cypher": ""
            }

    def _extract_weaviate_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Extract relevant context from Weaviate chunks for Cypher generation.

        IMPROVED: Extracts more detailed information for better Cypher generation:
        - Column headers with their column indices
        - Sample cell values to understand data types
        - Row structure information
        - Table/chunk indices for targeting
        """
        context_parts = []
        headers_found = {}  # {col_num: header_text}
        sample_values = []
        chunk_indices = set()
        row_info = set()

        for chunk in chunks[:7]:  # Check top 7 chunks
            chunk_type = chunk.get('chunk_type', '')

            if chunk_type == 'table':
                # Extract headers and sample data from cell_grounding
                cell_grounding_str = chunk.get('cell_grounding', '')
                if cell_grounding_str:
                    try:
                        cell_grounding = json.loads(cell_grounding_str)
                        for cell_id, data in cell_grounding.items():
                            row = data.get('row', -1)
                            col = data.get('col', -1)
                            text = data.get('text', '').strip()

                            # Headers (row 0 or 1)
                            if row in [0, 1] and text and len(text) > 1:
                                headers_found[col] = text

                            # Sample values (non-header rows)
                            if row > 1 and text and len(text) > 0:
                                sample_values.append({
                                    'row': row,
                                    'col': col,
                                    'text': text[:50]  # Truncate long values
                                })
                                row_info.add(row)

                    except json.JSONDecodeError:
                        pass

                # Track chunk index (bridge to Neo4j Table nodes)
                chunk_idx = chunk.get('chunk_index')
                if chunk_idx is not None:
                    chunk_indices.add(chunk_idx)

            # Extract content snippet
            content = chunk.get('content', '')[:300]
            if content:
                context_parts.append(content)

        # Build comprehensive context string
        context = []

        if headers_found:
            header_list = [f"{headers_found[col]} (col {col})" for col in sorted(headers_found.keys())]
            context.append(f"Column headers: {', '.join(header_list[:8])}")

        if sample_values:
            # Show a few sample values
            samples = sample_values[:5]
            sample_str = "; ".join([f"row {s['row']}, col {s['col']}: '{s['text']}'" for s in samples])
            context.append(f"Sample values: {sample_str}")

        if row_info:
            context.append(f"Rows in data: {min(row_info)} to {max(row_info)} (total ~{len(row_info)} data rows)")

        if chunk_indices:
            context.append(f"Relevant table indices: {', '.join(map(str, sorted(chunk_indices)))}")

        if context_parts:
            # Add a snippet of content for semantic understanding
            context.append(f"Content snippet: {context_parts[0][:200]}...")

        final_context = "\n".join(context) if context else "No specific context available"
        logger.debug(f"Extracted Weaviate context for Cypher generation:\n{final_context}")

        return final_context

    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the Neo4j schema for debugging."""
        if not self.is_connected:
            return {"connected": False, "schema": None}

        return {
            "connected": True,
            "schema": self.schema,
            "schema_length": len(self.schema) if self.schema else 0
        }


# Global service instance
_langchain_neo4j_service: Optional[LangChainNeo4jService] = None


def get_langchain_neo4j_service() -> LangChainNeo4jService:
    """Get or create the global LangChain Neo4j service instance."""
    global _langchain_neo4j_service
    if _langchain_neo4j_service is None:
        _langchain_neo4j_service = LangChainNeo4jService()
    return _langchain_neo4j_service


# Convenience function for hybrid queries
def execute_hybrid_query(
    question: str,
    process_id: str,
    weaviate_chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Execute a hybrid Weaviate+Neo4j query.

    Weaviate provides context (what to look for),
    Neo4j extracts all matching structured data.

    Args:
        question: User's question
        process_id: Document UUID
        weaviate_chunks: Chunks from Weaviate semantic search

    Returns:
        Dict with Neo4j results
    """
    service = get_langchain_neo4j_service()
    return service.query_with_context(question, process_id, weaviate_chunks)
