"""
Step-by-step simulation of Dynamic Cypher Generation
Query: "Find the row containing 3 Minor defect with all column values"
"""

import sys
sys.path.insert(0, '.')
import json

print('='*80)
print('COMPLETE STEP-BY-STEP SIMULATION')
print('Query: "Find the row containing 3 Minor defect with all column values"')
print('='*80)

process_id = '3cf79126-10d2-44e9-ac91-edebc376bb90'
user_query = 'Find the row that contains 3 Minor defect - show all column names with values'

# ============================================================================
# STEP 1: WEAVIATE SEMANTIC SEARCH (Simulated context)
# ============================================================================
print('\n' + '-'*80)
print('STEP 1: WEAVIATE SEMANTIC SEARCH')
print('-'*80)

print(f'\nUser Query: "{user_query}"')
print(f'Process ID: {process_id}')

# Simulate Weaviate context (in real flow, this comes from Weaviate search)
weaviate_context = """Column headers found: Defect Class, Count, Percentage
Sample content: Table with defect classifications including Critical, Major A, Major B, Minor
User is looking for the ENTIRE ROW where "3 Minor defect" appears"""

print(f'\nWeaviate Context extracted:')
print(weaviate_context)

# ============================================================================
# STEP 2: NEO4J SCHEMA DISCOVERY
# ============================================================================
print('\n' + '-'*80)
print('STEP 2: NEO4J SCHEMA DISCOVERY')
print('-'*80)

from services.langchain_neo4j_service import get_langchain_neo4j_service
service = get_langchain_neo4j_service()

print(f'\nLangChain Neo4j Connected: {service.is_connected}')
print(f'\nNeo4j Schema (what LLM sees):')
print('-'*40)
# Show relevant parts of schema
schema_preview = service.schema[:1000]
print(schema_preview)
print('...[truncated]...')

# ============================================================================
# STEP 3: DYNAMIC CYPHER GENERATION
# ============================================================================
print('\n' + '-'*80)
print('STEP 3: DYNAMIC CYPHER GENERATION (LLM generates query)')
print('-'*80)

print(f'\nSending to Claude Haiku:')
print(f'   - Schema: [Neo4j graph structure]')
print(f'   - Question: "{user_query}"')
print(f'   - Context: "{weaviate_context.strip()}"')

print('\nGenerating Cypher query dynamically...')
cypher, params = service.generate_cypher(user_query, process_id, weaviate_context)

print(f'\nGENERATED CYPHER QUERY:')
print('='*60)
print(cypher)
print('='*60)
print(f'\nParameters: {params}')

# ============================================================================
# STEP 4: NEO4J DATA INSPECTION
# ============================================================================
print('\n' + '-'*80)
print('STEP 4: NEO4J DATA INSPECTION (What data exists)')
print('-'*80)

from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://10.242.190.53:7687', auth=('neo4j', 'ocr@4567'))

with driver.session(database='neo4j') as session:
    # Show table structure
    result = session.run("""
        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
        WHERE c.is_header = true
        RETURN DISTINCT c.text as header, c.col as col_num
        ORDER BY c.col
    """, pid=process_id)

    print('\nTable Headers in Neo4j:')
    headers = []
    for r in result:
        headers.append((r['col_num'], r['header']))
        print(f'   Column {r["col_num"]}: {r["header"]}')

    # Show the row we are looking for
    result2 = session.run("""
        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
        WHERE toLower(c.text) CONTAINS 'minor'
        RETURN c.text as text, c.row as row, c.col as col
    """, pid=process_id)

    print('\nCells containing "minor":')
    for r in result2:
        print(f'   Row {r["row"]}, Col {r["col"]}: "{r["text"]}"')

driver.close()

# ============================================================================
# STEP 5: EXECUTE CYPHER QUERY
# ============================================================================
print('\n' + '-'*80)
print('STEP 5: EXECUTING GENERATED CYPHER QUERY')
print('-'*80)

print('\nRunning the generated Cypher query on Neo4j...')

try:
    results = service.graph.query(cypher, params=params)
    print(f'\nQuery executed successfully!')
    print(f'Results count: {len(results)} rows')

    print('\n' + '='*60)
    print('RESULTS FROM DYNAMIC CYPHER:')
    print('='*60)

    if results:
        for i, row in enumerate(results, 1):
            print(f'\nResult {i}:')
            for key, value in row.items():
                print(f'   {key}: {value}')
    else:
        print('\nNo results from generated query.')

except Exception as e:
    print(f'\nQuery execution error: {e}')

# ============================================================================
# STEP 6: MANUAL VERIFICATION (Get exact row data)
# ============================================================================
print('\n' + '-'*80)
print('STEP 6: MANUAL VERIFICATION - Get exact row with all columns')
print('-'*80)

driver = GraphDatabase.driver('bolt://10.242.190.53:7687', auth=('neo4j', 'ocr@4567'))

with driver.session(database='neo4j') as session:
    # First find the row number of "3 Minor defect"
    result = session.run("""
        MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(target:Cell)
        WHERE target.text CONTAINS 'Minor' OR target.text CONTAINS 'minor'
        RETURN target.row as target_row, target.text as target_text, t.table_index as table_idx
    """, pid=process_id)

    target_rows = list(result)
    print(f'\nFound cells with "Minor":')
    for r in target_rows:
        print(f'   Table {r["table_idx"]}, Row {r["target_row"]}: "{r["target_text"]}"')

    if target_rows:
        target_row = target_rows[0]['target_row']
        table_idx = target_rows[0]['table_idx']

        print(f'\nFetching ALL cells from Row {target_row} in Table {table_idx}...')

        # Get all cells in that row
        result3 = session.run("""
            MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE t.table_index = $table_idx AND c.row = $row_num
            RETURN c.text as value, c.col as col_num
            ORDER BY c.col
        """, pid=process_id, table_idx=table_idx, row_num=target_row)

        row_cells = list(result3)

        # Get headers
        result4 = session.run("""
            MATCH (d:Document {process_id: $pid})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE t.table_index = $table_idx AND c.is_header = true
            RETURN c.text as header, c.col as col_num
            ORDER BY c.col
        """, pid=process_id, table_idx=table_idx)

        headers = {r['col_num']: r['header'] for r in result4}

        print('\n' + '='*60)
        print(f'COMPLETE ROW DATA (Row {target_row} - "3 Minor defect" row)')
        print('='*60)

        print('\n+' + '-'*30 + '+' + '-'*30 + '+')
        print('| {:^28} | {:^28} |'.format('COLUMN NAME', 'VALUE'))
        print('+' + '-'*30 + '+' + '-'*30 + '+')

        for cell in row_cells:
            col_num = cell['col_num']
            col_name = headers.get(col_num, f'Column {col_num}')[:28]
            value = str(cell['value'])[:28] if cell['value'] else 'N/A'
            print('| {:28} | {:28} |'.format(col_name, value))

        print('+' + '-'*30 + '+' + '-'*30 + '+')

driver.close()

print('\n' + '='*80)
print('SIMULATION COMPLETE')
print('='*80)
