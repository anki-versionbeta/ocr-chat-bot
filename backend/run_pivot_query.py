from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://10.242.190.53:7687', auth=('neo4j', 'ocr@4567'))
process_id = '53e654a3-d0ce-47ed-9d7f-d5d676958d80'

cypher = """
MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)
MATCH (t)-[:HAS_CELL]->(r:Cell)
WHERE toLower(coalesce(r.text,'')) CONTAINS 'range'
WITH p, t, collect(DISTINCT r.row_index) AS rangeRows
UNWIND rangeRows AS rr
MATCH (t)-[:HAS_CELL]->(c5:Cell {row_index: rr})
WHERE replace(coalesce(c5.text,''), ' ', '') CONTAINS '5.00'
MATCH (t)-[:HAS_CELL]->(c25:Cell {row_index: rr})
WHERE replace(coalesce(c25.text,''), ' ', '') CONTAINS '25.00'
WITH p, t, rr ORDER BY rr ASC
WITH p, t, collect(rr) AS validRangeRows
WHERE size(validRangeRows) > 0
WITH p, t, validRangeRows[0] AS headerRow
MATCH (t)-[:HAS_CELL]->(lbl:Cell)
WHERE lbl.row_index > headerRow AND lbl.col_index = 1 AND toLower(coalesce(lbl.text,'')) CONTAINS 'concentration'
WITH p, t, headerRow, lbl ORDER BY lbl.row_index ASC
WITH p, t, headerRow, head(collect(lbl.row_index)) AS concRow
WHERE concRow IS NOT NULL
MATCH (t)-[:HAS_CELL]->(h:Cell {row_index: headerRow})
WHERE h.col_index >= 2 AND trim(coalesce(h.text,'')) <> ''
OPTIONAL MATCH (t)-[:HAS_CELL]->(v:Cell {row_index: concRow, col_index: h.col_index})
WITH p, t, collect({header: replace(h.text, ' ', ''), value: v.text}) AS pairs
RETURN p.page_num AS page,
    [x IN pairs WHERE x.header =~ '.*1[.]00.*' | x.value][0] AS c1,
    [x IN pairs WHERE x.header =~ '.*2[.]00.*' | x.value][0] AS c2,
    [x IN pairs WHERE x.header =~ '.*5[.]00.*' AND NOT x.header =~ '.*25.*' AND NOT x.header =~ '.*50.*' | x.value][0] AS c5,
    [x IN pairs WHERE x.header =~ '.*10[.]00.*' | x.value][0] AS c10,
    [x IN pairs WHERE x.header =~ '.*25[.]00.*' | x.value][0] AS c25,
    [x IN pairs WHERE x.header =~ '.*50[.]00.*' | x.value][0] AS c50
ORDER BY p.page_num
"""

with driver.session(database='neo4j') as session:
    result = session.run(cypher, {'process_id': process_id})
    print("page    >=1.00      >=2.00      >=5.00      >=10.00     >=25.00     >=50.00")
    print("-" * 80)
    for rec in result:
        print(f"{rec['page']:<8}{rec['c1'] or '-':<12}{rec['c2'] or '-':<12}{rec['c5'] or '-':<12}{rec['c10'] or '-':<12}{rec['c25'] or '-':<12}{rec['c50'] or '-':<12}")

driver.close()
