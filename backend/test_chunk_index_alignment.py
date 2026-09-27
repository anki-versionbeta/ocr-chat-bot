"""
Test Chunk Index Alignment between Weaviate and Neo4j

Process ID: 96799ebd-7848-4099-a6b1-65fcf0760d47
"""

import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

PROCESS_ID = "96799ebd-7848-4099-a6b1-65fcf0760d47"

print("=" * 80)
print("CHUNK INDEX ALIGNMENT TEST")
print("=" * 80)
print(f"Process ID: {PROCESS_ID}")

# =============================================================================
# 1. CHECK WEAVIATE CHUNKS
# =============================================================================
print("\n" + "=" * 80)
print("1. WEAVIATE CHUNKS")
print("=" * 80)

from services.weaviate_indexer import WeaviateIndexer

weaviate = WeaviateIndexer()
results = weaviate.search_chunks(
    query="table data",
    process_id=PROCESS_ID,
    limit=20,
    alpha=0.5
)

print(f"\nFound {len(results)} chunks in Weaviate:")
weaviate_table_indices = []
weaviate_text_indices = []

for chunk in results:
    chunk_type = chunk.get('chunk_type', 'unknown')
    chunk_index = chunk.get('chunk_index')
    page = chunk.get('page', '?')
    content = chunk.get('content', '')[:50]

    print(f"  - chunk_index={chunk_index}, type={chunk_type}, page={page}: {content}...")

    if chunk_type == 'table':
        weaviate_table_indices.append(chunk_index)
    else:
        weaviate_text_indices.append(chunk_index)

print(f"\nWeaviate TABLE chunk_indices: {sorted(set(weaviate_table_indices))}")
print(f"Weaviate TEXT chunk_indices: {sorted(set(weaviate_text_indices))}")

# =============================================================================
# 2. CHECK NEO4J TABLES
# =============================================================================
print("\n" + "=" * 80)
print("2. NEO4J TABLES")
print("=" * 80)

from services.neo4j_service import get_neo4j_service

neo4j = get_neo4j_service()

if neo4j.is_connected:
    tables = neo4j.query("""
        MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
        RETURN t.chunk_index as chunk_index, p.page_num as page,
               t.row_count as rows, t.col_count as cols
        ORDER BY t.chunk_index
    """, {'process_id': PROCESS_ID})

    neo4j_table_indices = []
    print(f"\nFound {len(tables)} tables in Neo4j:")
    for t in tables:
        chunk_idx = t.get('chunk_index')
        neo4j_table_indices.append(chunk_idx)
        print(f"  - chunk_index={chunk_idx}, page={t.get('page')}, rows={t.get('rows')}, cols={t.get('cols')}")

    # Check sections too
    sections = neo4j.query("""
        MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_SECTION]->(s:Section)
        RETURN s.chunk_index as chunk_index, s.layout_type as type, p.page_num as page,
               substring(s.content, 0, 40) as content
        ORDER BY s.chunk_index
        LIMIT 10
    """, {'process_id': PROCESS_ID})

    neo4j_section_indices = []
    print(f"\nFound {len(sections)} sections in Neo4j:")
    for s in sections:
        chunk_idx = s.get('chunk_index')
        neo4j_section_indices.append(chunk_idx)
        print(f"  - chunk_index={chunk_idx}, type={s.get('type')}, page={s.get('page')}: {s.get('content')}...")

    # =============================================================================
    # 3. COMPARE
    # =============================================================================
    print("\n" + "=" * 80)
    print("3. ALIGNMENT CHECK")
    print("=" * 80)

    print(f"\nWeaviate TABLE indices: {sorted(set(weaviate_table_indices))}")
    print(f"Neo4j TABLE indices:    {sorted(set(neo4j_table_indices))}")

    weaviate_set = set(weaviate_table_indices)
    neo4j_set = set(neo4j_table_indices)

    overlap = weaviate_set & neo4j_set
    if overlap:
        print(f"\n[OK] OVERLAP EXISTS: {sorted(overlap)}")
        print("     chunk_index bridge is WORKING!")
    else:
        print(f"\n[!] NO OVERLAP - chunk_index mismatch!")
        print(f"     Weaviate: {sorted(weaviate_set)}")
        print(f"     Neo4j:    {sorted(neo4j_set)}")

else:
    print("Neo4j not connected!")

# =============================================================================
# 4. TEST RAG QUERY
# =============================================================================
print("\n" + "=" * 80)
print("4. TEST RAG QUERY")
print("=" * 80)

from services.rag_orchestrator import get_rag_orchestrator

rag = get_rag_orchestrator()

# Test query
test_query = "Find the row containing defect with all column values"
print(f"\nTest Query: {test_query}")

result = rag.process_query_sync(
    query=test_query,
    process_id=PROCESS_ID,
    filename="neo4j_testng.pdf"
)

print(f"\nResult:")
print(f"  Success: {not result.get('error', False)}")
print(f"  Query Type: {result.get('query_type', 'unknown')}")
print(f"  Confidence: {result.get('confidence', 0)}")
print(f"  Neo4j Rows: {result.get('neo4j_rows_extracted', 'N/A')}")
print(f"  Dynamic Cypher: {result.get('dynamic_cypher', 'N/A')}")
print(f"\nAnswer:")
print(result.get('answer', 'No answer')[:500])

if result.get('references'):
    print(f"\nReferences: {len(result.get('references', []))} found")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
