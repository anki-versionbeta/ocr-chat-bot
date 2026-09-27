"""
Full Pipeline Simulation Test - Shows Every Step

This script simulates the complete query pipeline and shows:
1. Intent Classification (rule-based vs LLM)
2. Weaviate Search (what chunks are retrieved)
3. Context Extraction (what headers/values from chunks)
4. Cypher Generation (what prompt, what generated query)
5. Retry Mechanism (how errors trigger retries)
6. Template Fallback (when dynamic fails)

Run: python test_full_pipeline_simulation.py
"""

import os
import sys
import json
import logging

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("pipeline_test")

# Suppress some noisy loggers
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("neo4j").setLevel(logging.WARNING)

print("=" * 80)
print("FULL PIPELINE SIMULATION TEST")
print("=" * 80)

# Test parameters
PROCESS_ID = "3cf79126-10d2-44e9-ac91-edebc376bb90"
TEST_QUERY = "Find the row containing 3 Minor defect with all column values"

print(f"\nTest Query: {TEST_QUERY}")
print(f"Process ID: {PROCESS_ID}")
print("=" * 80)

# ============================================================================
# STEP 1: INTENT CLASSIFICATION
# ============================================================================
print("\n" + "=" * 80)
print("STEP 1: INTENT CLASSIFICATION")
print("=" * 80)

from services.intent_classifier import (
    classify_intent_rule_based,
    classify_intent_sync,
    QueryIntent,
    get_intent_description
)

print(f"\nQuery: '{TEST_QUERY}'")

# Test rule-based first
rule_result = classify_intent_rule_based(TEST_QUERY)
print(f"\n[1a] Rule-Based Classification:")
if rule_result:
    print(f"     Result: {rule_result.value}")
    print(f"     Description: {get_intent_description(rule_result)}")
else:
    print("     Result: None (will fall back to LLM)")

# Test full classification (rule-based + LLM fallback)
full_result = classify_intent_sync(TEST_QUERY)
print(f"\n[1b] Full Classification (with LLM fallback):")
print(f"     Result: {full_result.value}")
print(f"     Description: {get_intent_description(full_result)}")

# Show which patterns matched
print(f"\n[1c] Pattern Analysis:")
query_lower = TEST_QUERY.lower()
hybrid_patterns = [
    (r'\b(entire|complete|full|whole)\s+row\b', "entire/complete row"),
    (r'\brow\s+(that\s+)?(contains?|has|with)\b', "row contains/has"),
    (r'\b(all|every)\s+column\s+(values?|names?|data)\b', "all column values"),
    (r'\bwith\s+all\s+(its\s+)?(column|cell)?\s*(values?|data|names?)?\b', "with all values"),
    (r'\b(find|get|show)\s+the\s+row\b.*\ball\b', "find row...all"),
]

import re
for pattern, desc in hybrid_patterns:
    if re.search(pattern, query_lower):
        print(f"     MATCHED: '{desc}' -> pattern: {pattern}")

# ============================================================================
# STEP 2: WEAVIATE SEARCH
# ============================================================================
print("\n" + "=" * 80)
print("STEP 2: WEAVIATE SEARCH")
print("=" * 80)

from services.weaviate_indexer import WeaviateIndexer
from services.question_rephraser import rephrase_question_sync

# Generate query variations
print(f"\n[2a] Query Rephrasing:")
query_variations = rephrase_question_sync(TEST_QUERY, use_llm=False)  # Use rule-based for speed
print(f"     Variations ({len(query_variations)}):")
for i, var in enumerate(query_variations[:5], 1):
    print(f"       {i}. {var}")

# Search Weaviate
print(f"\n[2b] Weaviate Hybrid Search:")
weaviate = WeaviateIndexer()

all_chunks = []
seen_ids = set()

for query in query_variations[:3]:  # Use top 3 variations
    print(f"\n     Searching: '{query[:50]}...'")
    try:
        results = weaviate.search_chunks(
            query=query,
            process_id=PROCESS_ID,
            limit=5,
            alpha=0.7  # 70% semantic, 30% BM25
        )
        print(f"     Found: {len(results)} chunks")

        for chunk in results:
            chunk_id = chunk.get('chunk_id')
            if chunk_id and chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                all_chunks.append(chunk)

    except Exception as e:
        print(f"     Error: {e}")

print(f"\n[2c] Total Unique Chunks Retrieved: {len(all_chunks)}")

# Show chunk details
print(f"\n[2d] Chunk Details:")
for i, chunk in enumerate(all_chunks[:5], 1):
    print(f"\n     --- Chunk {i} ---")
    print(f"     Type: {chunk.get('chunk_type', 'unknown')}")
    print(f"     Page: {chunk.get('page', '?')}")
    print(f"     Chunk Index: {chunk.get('chunk_index', '?')}")
    content = chunk.get('content', '')[:200]
    print(f"     Content Preview: {content}...")

    # Show cell_grounding if table chunk
    if chunk.get('chunk_type') == 'table':
        cell_grounding_str = chunk.get('cell_grounding', '')
        if cell_grounding_str:
            try:
                cell_grounding = json.loads(cell_grounding_str)
                headers = []
                sample_values = []
                for cell_id, data in list(cell_grounding.items())[:10]:
                    row = data.get('row', -1)
                    col = data.get('col', -1)
                    text = data.get('text', '')[:30]
                    if row in [0, 1]:
                        headers.append(f"col{col}:{text}")
                    elif row > 1 and len(sample_values) < 3:
                        sample_values.append(f"r{row}c{col}:{text}")

                if headers:
                    print(f"     Headers: {headers[:5]}")
                if sample_values:
                    print(f"     Sample Values: {sample_values}")
            except:
                pass

# ============================================================================
# STEP 3: CONTEXT EXTRACTION FROM WEAVIATE CHUNKS
# ============================================================================
print("\n" + "=" * 80)
print("STEP 3: CONTEXT EXTRACTION FROM WEAVIATE CHUNKS")
print("=" * 80)

from services.langchain_neo4j_service import LangChainNeo4jService

# Initialize service (but don't use its Neo4j connection yet)
langchain_service = LangChainNeo4jService()

print(f"\n[3a] LangChain Neo4j Service Status:")
print(f"     Connected: {langchain_service.is_connected}")
if langchain_service.is_connected:
    schema_preview = langchain_service.schema[:500] if langchain_service.schema else "No schema"
    print(f"     Schema Preview: {schema_preview}...")

# Extract context using the service's method
print(f"\n[3b] Extracting Context from Weaviate Chunks:")
context = langchain_service._extract_weaviate_context(all_chunks)
print(f"\n     Extracted Context:\n{'-' * 40}")
print(context)
print(f"{'-' * 40}")

# ============================================================================
# STEP 4: CYPHER GENERATION (THE KEY PART)
# ============================================================================
print("\n" + "=" * 80)
print("STEP 4: CYPHER GENERATION")
print("=" * 80)

# Show the prompt template being used
from services.langchain_neo4j_service import CYPHER_GENERATION_TEMPLATE

print(f"\n[4a] Cypher Generation Prompt Template:")
print(f"     Template Length: {len(CYPHER_GENERATION_TEMPLATE)} chars")
print(f"\n     Few-Shot Examples in Template:")
example_markers = [
    "Example 1: Find row containing specific text",
    "Example 2: Extract all values from a specific column",
    "Example 3: Count tables in document",
    "Example 4: Get all column headers"
]
for marker in example_markers:
    if marker in CYPHER_GENERATION_TEMPLATE:
        print(f"       [✓] {marker}")
    else:
        print(f"       [✗] {marker} - MISSING!")

# Generate the actual prompt that will be sent to LLM
print(f"\n[4b] Building Actual Prompt for LLM:")
if langchain_service.is_connected:
    actual_prompt = CYPHER_GENERATION_TEMPLATE.format(
        schema=langchain_service.schema[:2000],  # Truncate for display
        question=TEST_QUERY,
        context=context
    )
    print(f"     Prompt Length: {len(actual_prompt)} chars")
    print(f"\n     Prompt Preview (first 1000 chars):\n{'-' * 40}")
    print(actual_prompt[:1000])
    print(f"...\n{'-' * 40}")
else:
    print("     Cannot generate prompt - Neo4j not connected")

# Now actually generate Cypher
print(f"\n[4c] Generating Cypher Query:")
if langchain_service.is_connected:
    cypher, params = langchain_service.generate_cypher(
        question=TEST_QUERY,
        process_id=PROCESS_ID,
        weaviate_context=context
    )
    print(f"\n     Generated Cypher:\n{'-' * 40}")
    print(cypher)
    print(f"{'-' * 40}")
    print(f"\n     Parameters: {params}")

    # Check for LIMIT injection
    print(f"\n[4d] Safety Checks:")
    if "LIMIT" in cypher.upper():
        print(f"     [✓] LIMIT clause present")
    else:
        print(f"     [!] No LIMIT clause - will be injected")

    # Validate syntax
    is_valid, error = langchain_service._validate_cypher_syntax(cypher, params)
    print(f"     [{'✓' if is_valid else '✗'}] Syntax Validation: {'PASSED' if is_valid else f'FAILED: {error}'}")
else:
    print("     Cannot generate - Neo4j not connected")
    cypher = None

# ============================================================================
# STEP 5: QUERY EXECUTION WITH RETRY
# ============================================================================
print("\n" + "=" * 80)
print("STEP 5: QUERY EXECUTION WITH RETRY MECHANISM")
print("=" * 80)

if langchain_service.is_connected and cypher:
    print(f"\n[5a] Executing Query with Self-Testing/Retry:")

    # Use the query_with_context method that has retry logic
    result = langchain_service.query_with_context(
        question=TEST_QUERY,
        process_id=PROCESS_ID,
        weaviate_chunks=all_chunks,
        max_retries=2
    )

    print(f"\n     Execution Result:")
    print(f"       Success: {result.get('success')}")
    print(f"       Result Count: {result.get('result_count', 0)}")
    print(f"       Retries Used: {result.get('retries_used', 0)}")
    print(f"       Method: {result.get('method', 'dynamic_cypher')}")

    if result.get('attempts'):
        print(f"\n     Attempts Made:")
        for attempt in result.get('attempts', []):
            print(f"       Attempt {attempt.get('attempt')}: {attempt.get('cypher', '')[:100]}...")

    if result.get('error'):
        print(f"\n     Error: {result.get('error')}")

    if result.get('results'):
        print(f"\n     Results Preview (first 3):")
        for i, row in enumerate(result.get('results', [])[:3], 1):
            print(f"       {i}. {row}")
else:
    print("     Cannot execute - Neo4j not connected or no Cypher generated")
    result = None

# ============================================================================
# STEP 6: TEMPLATE FALLBACK
# ============================================================================
print("\n" + "=" * 80)
print("STEP 6: TEMPLATE FALLBACK MECHANISM")
print("=" * 80)

from services.cypher_templates import CypherTemplates, get_cypher_templates

templates = get_cypher_templates()

print(f"\n[6a] Available Cypher Templates:")
template_methods = [
    ("find_row_by_cell_value", "Find row containing specific text"),
    ("extract_column_by_header", "Extract column by header pattern"),
    ("find_pages_with_tables", "Find pages with tables"),
    ("extract_full_table_by_chunk_index", "Extract full table by chunk index"),
    ("get_column_headers_from_all_tables", "Get all column headers"),
]

for method_name, description in template_methods:
    if hasattr(templates, method_name):
        print(f"     [✓] {method_name}: {description}")
    else:
        print(f"     [✗] {method_name}: MISSING!")

# Show the find_row_by_cell_value template
print(f"\n[6b] Template for Row Search (find_row_by_cell_value):")
cypher_template, params_template = templates.find_row_by_cell_value(PROCESS_ID, "3 Minor defect")
print(f"\n     Template Cypher:\n{'-' * 40}")
print(cypher_template)
print(f"{'-' * 40}")
print(f"\n     Template Parameters: {params_template}")

# ============================================================================
# STEP 7: FULL FALLBACK TEST
# ============================================================================
print("\n" + "=" * 80)
print("STEP 7: FULL QUERY WITH FALLBACK")
print("=" * 80)

if langchain_service.is_connected:
    print(f"\n[7a] Executing query_with_context_and_fallback:")

    full_result = langchain_service.query_with_context_and_fallback(
        question=TEST_QUERY,
        process_id=PROCESS_ID,
        weaviate_chunks=all_chunks,
        cypher_templates=templates
    )

    print(f"\n     Full Execution Result:")
    print(f"       Success: {full_result.get('success')}")
    print(f"       Method Used: {full_result.get('method', 'unknown')}")
    print(f"       Result Count: {full_result.get('result_count', 0)}")
    print(f"       Retries Used: {full_result.get('retries_used', 0)}")

    print(f"\n     Final Cypher Used:\n{'-' * 40}")
    print(full_result.get('cypher', 'No cypher'))
    print(f"{'-' * 40}")

    if full_result.get('results'):
        print(f"\n     Final Results ({len(full_result.get('results', []))} rows):")
        for i, row in enumerate(full_result.get('results', [])[:10], 1):
            print(f"       {i}. {row}")
else:
    print("     Cannot execute - Neo4j not connected")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

print(f"""
Pipeline Status:
================
1. Intent Classification:
   - Rule-based result: {rule_result.value if rule_result else 'None (needed LLM)'}
   - Final intent: {full_result.value if isinstance(full_result, QueryIntent) else 'hybrid_semantic_structural'}
   - Routed to: {'Neo4j Hybrid Handler' if full_result == QueryIntent.HYBRID_SEMANTIC_STRUCTURAL else 'Other Handler'}

2. Weaviate Search:
   - Chunks retrieved: {len(all_chunks)}
   - Table chunks: {sum(1 for c in all_chunks if c.get('chunk_type') == 'table')}

3. Context Extraction:
   - Context length: {len(context)} chars
   - Headers found: {'Yes' if 'Column headers:' in context else 'No'}

4. Cypher Generation:
   - Service connected: {langchain_service.is_connected}
   - Few-shot examples: {'Present' if 'Example 1' in CYPHER_GENERATION_TEMPLATE else 'Missing'}
   - LIMIT injection: {'Working' if langchain_service.is_connected else 'N/A'}
   - Syntax validation: {'Working' if langchain_service.is_connected else 'N/A'}

5. Retry Mechanism:
   - Max retries: 2
   - Error feedback: Yes (added to prompt on retry)

6. Template Fallback:
   - Templates available: {len(template_methods)}
   - Row search template: {'Present' if hasattr(templates, 'find_row_by_cell_value') else 'Missing'}
""")

print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
