"""
Test Retry Mechanism, Chunk Index Usage, and Fallback Logic

This test demonstrates:
1. How retry works when Cypher fails
2. How chunk_index bridges Weaviate → Neo4j
3. What data from chunks is used for Cypher generation
4. When and how template fallback is triggered

Run: python test_retry_and_chunk_index.py
"""

import os
import sys
import json
import logging

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Configure detailed logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger("retry_test")

print("=" * 80)
print("TEST: RETRY MECHANISM, CHUNK_INDEX USAGE, AND FALLBACK")
print("=" * 80)

PROCESS_ID = "3cf79126-10d2-44e9-ac91-edebc376bb90"

# ============================================================================
# PART 1: UNDERSTANDING CHUNK_INDEX - THE BRIDGE
# ============================================================================
print("\n" + "=" * 80)
print("PART 1: CHUNK_INDEX - THE BRIDGE BETWEEN WEAVIATE AND NEO4J")
print("=" * 80)

from services.weaviate_indexer import WeaviateIndexer

weaviate = WeaviateIndexer()

# Search for table chunks and show their chunk_index
print("\n[1a] Searching Weaviate for table chunks...")
results = weaviate.search_chunks(
    query="defect evaluation table",
    process_id=PROCESS_ID,
    limit=5,
    alpha=0.7
)

print(f"\n[1b] Analyzing chunk metadata:")
for i, chunk in enumerate(results, 1):
    chunk_type = chunk.get('chunk_type', 'unknown')
    chunk_index = chunk.get('chunk_index')  # THIS IS THE BRIDGE!
    page = chunk.get('page')

    print(f"\n     --- Chunk {i} ---")
    print(f"     chunk_type: {chunk_type}")
    print(f"     chunk_index: {chunk_index}  <-- THIS LINKS TO NEO4J Table.chunk_index!")
    print(f"     page: {page}")

    if chunk_type == 'table':
        # Show cell_grounding preview
        cell_grounding_str = chunk.get('cell_grounding', '')
        if cell_grounding_str:
            try:
                cg = json.loads(cell_grounding_str)
                cells = list(cg.items())[:3]
                print(f"     cell_grounding (first 3 cells):")
                for cell_id, data in cells:
                    print(f"       {cell_id}: row={data.get('row')}, col={data.get('col')}, text='{data.get('text', '')[:30]}'")
            except:
                pass

# ============================================================================
# PART 2: HOW CHUNK_INDEX IS USED IN CYPHER TEMPLATES
# ============================================================================
print("\n" + "=" * 80)
print("PART 2: CHUNK_INDEX IN CYPHER TEMPLATES")
print("=" * 80)

from services.cypher_templates import get_cypher_templates

templates = get_cypher_templates()

# Get a chunk_index from Weaviate
table_chunks = [c for c in results if c.get('chunk_type') == 'table']
if table_chunks:
    sample_chunk_index = table_chunks[0].get('chunk_index')
    print(f"\n[2a] Sample chunk_index from Weaviate: {sample_chunk_index}")

    if sample_chunk_index is not None:
        print(f"\n[2b] Template: extract_full_table_by_chunk_index")
        print(f"     This template uses chunk_index to get ALL cells from a specific table!")

        cypher, params = templates.extract_full_table_by_chunk_index(PROCESS_ID, int(sample_chunk_index))
        print(f"\n     Cypher Query:")
        print("-" * 60)
        print(cypher[:500] + "...")
        print("-" * 60)
        print(f"     Parameters: {params}")

        # Execute it
        from services.neo4j_service import get_neo4j_service
        neo4j = get_neo4j_service()

        if neo4j.is_connected:
            print(f"\n[2c] Executing chunk_index query on Neo4j...")
            result = neo4j.query(cypher, params)
            if result:
                print(f"     Result: Found table with {len(result)} rows of data")
                if result[0]:
                    print(f"     Table info: {result[0].get('row_count')} rows, {result[0].get('col_count')} cols")
            else:
                print(f"     Result: No data found for chunk_index {sample_chunk_index}")
    else:
        print(f"     WARNING: chunk_index is None in Weaviate chunks!")
        print(f"     This means the bridge between Weaviate and Neo4j is broken!")

# ============================================================================
# PART 3: SIMULATE RETRY MECHANISM
# ============================================================================
print("\n" + "=" * 80)
print("PART 3: SIMULATING RETRY MECHANISM")
print("=" * 80)

from services.langchain_neo4j_service import LangChainNeo4jService, CYPHER_GENERATION_TEMPLATE

# Create a mock version to show retry logic
class MockLangChainNeo4j:
    """Mock class to demonstrate retry logic"""

    def __init__(self, real_service):
        self.real = real_service
        self.attempt_count = 0
        self.cypher_history = []
        self.error_history = []

    def simulate_query_with_retry(self, question, process_id, weaviate_chunks, simulate_failures=0):
        """
        Simulate the retry mechanism.

        Args:
            simulate_failures: Number of times to simulate failure before success
        """
        print(f"\n[3a] Starting query with max_retries=2, simulate_failures={simulate_failures}")

        # Extract context (same as real service)
        context = self.real._extract_weaviate_context(weaviate_chunks)
        print(f"\n[3b] Context extracted from Weaviate chunks:")
        print("-" * 60)
        print(context)
        print("-" * 60)

        last_error = None
        last_cypher = None
        max_retries = 2

        for attempt in range(max_retries + 1):
            print(f"\n{'='*20} ATTEMPT {attempt + 1} {'='*20}")
            self.attempt_count = attempt + 1

            # Build prompt with error feedback on retry
            retry_context = context
            if attempt > 0 and last_error:
                retry_context = f"""{context}

PREVIOUS ATTEMPT FAILED:
- Cypher: {last_cypher[:200]}...
- Error: {last_error}
- Please fix the query and try a different approach."""
                print(f"\n[ERROR FEEDBACK ADDED TO PROMPT]:")
                print(f"  Previous error: {last_error}")

            # Generate Cypher
            print(f"\n[Generating Cypher...]")
            cypher, params = self.real.generate_cypher(question, process_id, retry_context)

            self.cypher_history.append({
                'attempt': attempt + 1,
                'cypher': cypher,
                'had_error_feedback': attempt > 0
            })

            print(f"\n[Generated Cypher (attempt {attempt + 1})]:")
            print("-" * 60)
            print(cypher)
            print("-" * 60)

            # Simulate failure for first N attempts
            if attempt < simulate_failures:
                last_error = f"SIMULATED ERROR: Query returned 0 results (attempt {attempt + 1})"
                last_cypher = cypher
                self.error_history.append(last_error)
                print(f"\n[SIMULATED FAILURE]: {last_error}")
                print(f"[Will retry with error feedback...]")
                continue

            # Execute for real
            print(f"\n[Executing Cypher on Neo4j...]")
            try:
                results = self.real.graph.query(cypher, params=params)

                if not results:
                    last_error = f"Query returned 0 results"
                    last_cypher = cypher
                    self.error_history.append(last_error)
                    print(f"\n[EMPTY RESULTS]: {last_error}")
                    if attempt < max_retries:
                        print(f"[Will retry...]")
                    continue

                print(f"\n[SUCCESS!] Got {len(results)} results on attempt {attempt + 1}")
                return {
                    'success': True,
                    'results': results,
                    'attempts_made': attempt + 1,
                    'cypher_history': self.cypher_history,
                    'error_history': self.error_history
                }

            except Exception as e:
                last_error = str(e)
                last_cypher = cypher
                self.error_history.append(last_error)
                print(f"\n[EXECUTION ERROR]: {last_error}")
                if attempt < max_retries:
                    print(f"[Will retry...]")

        print(f"\n[ALL RETRIES EXHAUSTED]")
        return {
            'success': False,
            'attempts_made': max_retries + 1,
            'cypher_history': self.cypher_history,
            'error_history': self.error_history,
            'last_error': last_error
        }


# Initialize real service
print("\n[Initializing LangChain Neo4j service...]")
real_service = LangChainNeo4jService()

if real_service.is_connected:
    mock = MockLangChainNeo4j(real_service)

    # Test 1: Success on first try
    print("\n" + "=" * 80)
    print("TEST 3.1: SUCCESSFUL QUERY (no failures)")
    print("=" * 80)

    result1 = mock.simulate_query_with_retry(
        question="Find the row containing 3 Minor defect with all column values",
        process_id=PROCESS_ID,
        weaviate_chunks=results,
        simulate_failures=0  # No simulated failures
    )

    print(f"\n[TEST 3.1 RESULT]:")
    print(f"  Success: {result1['success']}")
    print(f"  Attempts made: {result1['attempts_made']}")
    print(f"  Result count: {len(result1.get('results', []))}")

    # Test 2: Simulate 1 failure, then success
    print("\n" + "=" * 80)
    print("TEST 3.2: RETRY AFTER 1 FAILURE")
    print("=" * 80)

    mock2 = MockLangChainNeo4j(real_service)
    result2 = mock2.simulate_query_with_retry(
        question="Find the row containing 3 Minor defect with all column values",
        process_id=PROCESS_ID,
        weaviate_chunks=results,
        simulate_failures=1  # Simulate 1 failure
    )

    print(f"\n[TEST 3.2 RESULT]:")
    print(f"  Success: {result2['success']}")
    print(f"  Attempts made: {result2['attempts_made']}")
    print(f"  Errors encountered: {result2['error_history']}")

    # Show how Cypher changed between attempts
    if len(result2['cypher_history']) > 1:
        print(f"\n[CYPHER EVOLUTION ACROSS ATTEMPTS]:")
        for entry in result2['cypher_history']:
            print(f"\n  Attempt {entry['attempt']} (error feedback: {entry['had_error_feedback']}):")
            print(f"    {entry['cypher'][:150]}...")

# ============================================================================
# PART 4: TEMPLATE FALLBACK MECHANISM
# ============================================================================
print("\n" + "=" * 80)
print("PART 4: TEMPLATE FALLBACK MECHANISM")
print("=" * 80)

print("""
[4a] HOW FALLBACK WORKS:

    1. Dynamic Cypher tries up to 3 times (initial + 2 retries)
    2. If all 3 fail, fallback checks query type:

       a) ROW EXTRACTION queries ("find row containing X"):
          - Extracts search term from question
          - Uses: find_row_by_cell_value(process_id, search_term)

       b) COLUMN EXTRACTION queries ("get all X values"):
          - Extracts header patterns from Weaviate context
          - Uses: extract_column_by_header(process_id, header_pattern)

    3. If template also fails, return empty results
""")

# Show the fallback code path
print(f"\n[4b] Template Fallback Code Analysis:")
print(f"""
    From rag_orchestrator.py -> query_with_context_and_fallback():

    # First try dynamic generation with retry
    result = self.query_with_context(question, process_id, weaviate_chunks)

    if result.get("success") and result.get("results"):
        result["method"] = "dynamic_cypher"
        return result

    # Dynamic failed - try template fallback
    if cypher_templates:
        logger.info("Dynamic Cypher failed, trying template fallback...")

        if "row" in question_lower and ("all" in question_lower or "column" in question_lower):
            # ROW EXTRACTION - use find_row_by_cell_value
            search_term = extract_search_term(question)
            cypher, params = cypher_templates.find_row_by_cell_value(process_id, search_term)
            results = self.graph.query(cypher, params=params)

        elif "column" in question_lower or "values" in question_lower:
            # COLUMN EXTRACTION - use extract_column_by_header
            headers = self._extract_header_names_from_context(context)
            for header in headers[:3]:
                cypher, params = cypher_templates.extract_column_by_header(process_id, header)
                results = self.graph.query(cypher, params=params)
""")

# ============================================================================
# PART 5: IS CHUNK_INDEX ACTUALLY BEING USED?
# ============================================================================
print("\n" + "=" * 80)
print("PART 5: IS CHUNK_INDEX BEING USED? ANALYSIS")
print("=" * 80)

print("""
[5a] CURRENT STATE OF CHUNK_INDEX USAGE:

    1. Weaviate stores chunk_index for each table chunk
       - Set during indexing in weaviate_indexer.py
       - Links table chunks to Neo4j Table nodes

    2. Neo4j stores chunk_index on Table nodes
       - Set during neo4j_ingestion.py
       - Allows direct table lookup: Table {chunk_index: X}

    3. Template exists: extract_full_table_by_chunk_index()
       - Takes chunk_index from Weaviate
       - Returns ALL cells from that specific table

    4. HOWEVER: Current LLM Cypher generation does NOT use chunk_index!
       - It generates Cypher based on content/headers
       - chunk_index is available but not passed to the prompt
""")

# Check if chunk_index is in the context
print(f"\n[5b] Checking if chunk_index is in Weaviate context:")

if real_service.is_connected:
    context = real_service._extract_weaviate_context(results)

    if 'chunk_index' in context.lower() or 'chunk index' in context.lower():
        print(f"     [✓] chunk_index IS mentioned in context")
    else:
        print(f"     [✗] chunk_index is NOT in context")
        print(f"     This means LLM doesn't know about chunk_index!")

    # Check what IS in context
    print(f"\n[5c] What IS in the Weaviate context:")
    print("-" * 60)
    print(context)
    print("-" * 60)

# ============================================================================
# PART 6: RECOMMENDATION - SHOULD WE USE CHUNK_INDEX?
# ============================================================================
print("\n" + "=" * 80)
print("PART 6: RECOMMENDATION - SHOULD CHUNK_INDEX BE USED?")
print("=" * 80)

print("""
[6a] PROS OF USING CHUNK_INDEX:

    1. PRECISION: Direct table lookup - no need for pattern matching
       - Current: WHERE header.text =~ '(?i).*defect.*'
       - With chunk_index: Table {chunk_index: 5}

    2. PERFORMANCE: Single index lookup vs full-text search

    3. RELIABILITY: No false positives from similar text in other tables

    4. BRIDGE: True Weaviate -> Neo4j linking as designed

[6b] CONS OF USING CHUNK_INDEX:

    1. COMPLEXITY: Need to track which chunk_index to use

    2. MULTI-TABLE: If query spans multiple tables, need multiple chunk_indices

    3. CURRENT WORKING: Dynamic Cypher is working without it

[6c] RECOMMENDATION:

    USE CHUNK_INDEX AS OPTIMIZATION FOR:
    - "Show me this table" -> Use chunk_index from top Weaviate result
    - "Get all data from the defect table" -> Use chunk_index

    DON'T USE CHUNK_INDEX FOR:
    - "Find rows containing X" -> Need to search across ALL tables
    - "Get all concentration values" -> Need to check all tables

    HYBRID APPROACH (BEST):
    1. Weaviate finds relevant chunks with chunk_indices
    2. Pass chunk_indices to Cypher generation prompt
    3. LLM can optionally use them for targeted queries
""")

# ============================================================================
# PART 7: VERIFY chunk_index IN CURRENT DATA
# ============================================================================
print("\n" + "=" * 80)
print("PART 7: VERIFY CHUNK_INDEX IN NEO4J")
print("=" * 80)

if neo4j.is_connected:
    print("\n[7a] Checking Table nodes in Neo4j for chunk_index:")

    verify_query = """
    MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
    RETURN t.chunk_index as chunk_index, t.table_key as table_key,
           t.row_count as rows, t.col_count as cols, p.page_num as page
    ORDER BY t.chunk_index
    """

    tables = neo4j.query(verify_query, {'process_id': PROCESS_ID})

    if tables:
        print(f"\n     Found {len(tables)} tables in Neo4j:")
        for t in tables:
            print(f"       - chunk_index: {t.get('chunk_index')}, "
                  f"page: {t.get('page')}, "
                  f"rows: {t.get('rows')}, cols: {t.get('cols')}")
    else:
        print(f"     No tables found in Neo4j for this process_id")

    # Compare with Weaviate
    print(f"\n[7b] Comparing chunk_indices between Weaviate and Neo4j:")

    weaviate_indices = set()
    for chunk in results:
        if chunk.get('chunk_type') == 'table' and chunk.get('chunk_index') is not None:
            weaviate_indices.add(chunk.get('chunk_index'))

    neo4j_indices = set()
    for t in tables:
        if t.get('chunk_index') is not None:
            neo4j_indices.add(t.get('chunk_index'))

    print(f"     Weaviate chunk_indices: {sorted(weaviate_indices)}")
    print(f"     Neo4j chunk_indices: {sorted(neo4j_indices)}")

    if weaviate_indices & neo4j_indices:
        print(f"     [✓] OVERLAP EXISTS - chunk_index bridge is working!")
        print(f"     Matching indices: {sorted(weaviate_indices & neo4j_indices)}")
    else:
        print(f"     [✗] NO OVERLAP - chunk_index bridge is broken!")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print("""
RETRY MECHANISM:
================
- Max retries: 2 (total 3 attempts)
- On failure: Error message added to prompt
- LLM sees: "PREVIOUS ATTEMPT FAILED: [error]"
- LLM adjusts: Generates different Cypher approach

WHAT DATA IS USED:
==================
1. From Weaviate chunks:
   - Column headers (row 0/1 cells)
   - Sample values (preview of data)
   - Row range info (rows 2-6, ~5 data rows)
   - Content snippet (first 200 chars)

2. NOT currently used:
   - chunk_index (could be used for direct table lookup)
   - Full cell_grounding (only headers extracted)

CHUNK_INDEX BRIDGE:
===================
- Weaviate HAS chunk_index on table chunks
- Neo4j HAS chunk_index on Table nodes
- Template EXISTS: extract_full_table_by_chunk_index()
- CURRENTLY: Not used in dynamic Cypher generation
- RECOMMENDATION: Add chunk_index to context for LLM

FALLBACK ORDER:
===============
1. Dynamic Cypher (LLM-generated) - 3 attempts
2. Template-based Cypher (find_row_by_cell_value, etc.)
3. Return empty/error if all fail
""")

print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
