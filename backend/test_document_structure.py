"""
Document Structure Explorer for Neo4j - Complete Analysis
Explores the document structure for process_id: f96d6d53-8257-4d3c-86b1-279f0e3ad069
"""

from neo4j import GraphDatabase
import json

# Neo4j connection settings
URI = "bolt://10.242.190.53:7687"
USER = "neo4j"
PASSWORD = REDACTED

PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"

def explore_document_structure():
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    results = {}

    with driver.session() as session:
        # 1. Get Document node and find its doc_id by traversing relationships
        print("=" * 80)
        print("1. DOCUMENT NODE - Finding doc_id via relationships")
        print("=" * 80)

        # Find doc_id via Page relationship
        doc_query = """
        MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
        RETURN p.doc_id as doc_id, d.filename as filename, d.page_count as page_count
        LIMIT 1
        """
        doc_result = session.run(doc_query, process_id=PROCESS_ID).single()

        if doc_result:
            doc_id = doc_result['doc_id']
            print(f"Document found via HAS_PAGE relationship!")
            print(f"  doc_id: {doc_id}")
            print(f"  filename: {doc_result.get('filename')}")
            print(f"  page_count: {doc_result.get('page_count')}")
            results['doc_id'] = doc_id
        else:
            # Try alternative method - search for any node with text containing document info
            print("Could not find doc_id via HAS_PAGE. Trying alternative methods...")

            # Search for cells that have Ges.-Mittel. text and get their doc_id
            alt_query = """
            MATCH (c:Cell)
            WHERE c.text CONTAINS 'Ges' AND c.text CONTAINS 'Mittel'
            RETURN DISTINCT c.doc_id as doc_id LIMIT 10
            """
            alt_results = session.run(alt_query).data()
            print(f"Found doc_ids from Ges-Mittel cells: {[r['doc_id'] for r in alt_results]}")

            # Get doc_id from cells containing SA00
            alt_query2 = """
            MATCH (c:Cell)
            WHERE c.text CONTAINS 'SA00'
            RETURN DISTINCT c.doc_id as doc_id LIMIT 10
            """
            alt_results2 = session.run(alt_query2).data()
            print(f"Found doc_ids from SA00 cells: {[r['doc_id'] for r in alt_results2]}")

            # Try to match by filename
            filename_query = """
            MATCH (d:Document {process_id: $process_id})
            RETURN d.filename as filename
            """
            fname_result = session.run(filename_query, process_id=PROCESS_ID).single()
            if fname_result:
                filename = fname_result['filename']
                print(f"Looking for doc_id matching filename: {filename}")

                # Find a cell from a document that might match
                match_query = """
                MATCH (d:Document)
                WHERE d.filename = $filename
                MATCH (d)-[:HAS_PAGE]->(p:Page)
                RETURN p.doc_id as doc_id LIMIT 1
                """
                match_result = session.run(match_query, filename=filename).single()
                if match_result:
                    doc_id = match_result['doc_id']
                    print(f"Found doc_id from filename match: {doc_id}")
                    results['doc_id'] = doc_id

        # If we still don't have doc_id, get all unique doc_ids
        if 'doc_id' not in results or not results['doc_id']:
            print("\nListing all unique doc_ids in database:")
            all_docs_query = """
            MATCH (c:Cell)
            RETURN DISTINCT c.doc_id as doc_id LIMIT 20
            """
            all_docs = session.run(all_docs_query).data()
            print(f"Available doc_ids: {[d['doc_id'] for d in all_docs]}")

            # Try each doc_id and find one with SA00 data
            for doc_data in all_docs:
                test_doc_id = doc_data['doc_id']
                test_query = """
                MATCH (c:Cell {doc_id: $doc_id})
                WHERE c.text CONTAINS 'SA00'
                RETURN count(c) as count
                """
                test_result = session.run(test_query, doc_id=test_doc_id).single()
                if test_result and test_result['count'] > 0:
                    print(f"  doc_id {test_doc_id} has {test_result['count']} cells with SA00")
                    doc_id = test_doc_id
                    results['doc_id'] = doc_id
                    break

        if 'doc_id' not in results or not results['doc_id']:
            print("ERROR: Could not find doc_id!")
            driver.close()
            return results

        doc_id = results['doc_id']
        print(f"\nUsing doc_id: {doc_id}")

        # 2. Get all Page nodes
        print("\n" + "=" * 80)
        print("2. PAGE NODES")
        print("=" * 80)

        page_query = """
        MATCH (p:Page {doc_id: $doc_id})
        RETURN p.page_num as page_num, p.doc_id as doc_id
        ORDER BY p.page_num
        """
        pages = session.run(page_query, doc_id=doc_id).data()
        print(f"Pages found: {len(pages)}")
        for page in pages:
            print(f"  Page {page['page_num']}")
        results['pages'] = pages

        # 3. Get all Table nodes
        print("\n" + "=" * 80)
        print("3. TABLE NODES")
        print("=" * 80)

        table_query = """
        MATCH (t:Table {doc_id: $doc_id})
        RETURN t.table_id as table_id, t.page_num as page_num,
               t.row_count as row_count, t.col_count as col_count
        ORDER BY t.page_num, t.table_id
        """
        tables = session.run(table_query, doc_id=doc_id).data()
        print(f"Tables found: {len(tables)}")
        for table in tables:
            print(f"  Table {table['table_id']} on Page {table['page_num']}: "
                  f"rows={table['row_count']}, cols={table['col_count']}")
        results['tables'] = tables

        # 4. Find "Ges.-Mittel." or variations in Cell nodes
        print("\n" + "=" * 80)
        print("4. SEARCHING FOR 'Ges.-Mittel.' VARIATIONS IN CELLS")
        print("=" * 80)

        ges_query = """
        MATCH (c:Cell {doc_id: $doc_id})
        WHERE c.text CONTAINS 'Ges' AND c.text CONTAINS 'Mittel'
        RETURN c.text as text, c.row_index as row_idx, c.col_index as col_idx,
               c.page_num as page_num, c.cell_id as cell_id
        ORDER BY c.page_num, c.row_index, c.col_index
        """
        ges_cells = session.run(ges_query, doc_id=doc_id).data()
        print(f"Found 'Ges...Mittel' cells: {len(ges_cells)}")
        for cell in ges_cells:
            print(f"  Page {cell['page_num']}, Row {cell['row_idx']}, Col {cell['col_idx']}: '{cell['text']}'")
        results['ges_mittel_cells'] = ges_cells

        # 5. Find threshold columns (µm values)
        print("\n" + "=" * 80)
        print("5. SEARCHING FOR THRESHOLD COLUMNS (µm values)")
        print("=" * 80)

        threshold_query = """
        MATCH (c:Cell {doc_id: $doc_id})
        WHERE c.text CONTAINS 'µm' OR c.text CONTAINS 'μm'
        RETURN c.text as text, c.row_index as row_idx, c.col_index as col_idx,
               c.page_num as page_num, c.cell_id as cell_id
        ORDER BY c.page_num, c.row_index, c.col_index
        """
        threshold_cells = session.run(threshold_query, doc_id=doc_id).data()
        print(f"Found threshold header cells: {len(threshold_cells)}")
        for cell in threshold_cells:
            print(f"  Page {cell['page_num']}, Row {cell['row_idx']}, Col {cell['col_idx']}: '{cell['text']}'")
        results['threshold_cells'] = threshold_cells

        # 6. Find sample numbers containing "SA00"
        print("\n" + "=" * 80)
        print("6. SEARCHING FOR SAMPLE NUMBERS (SA00*)")
        print("=" * 80)

        sample_query = """
        MATCH (c:Cell {doc_id: $doc_id})
        WHERE c.text CONTAINS 'SA00'
        RETURN c.text as text, c.row_index as row_idx, c.col_index as col_idx,
               c.page_num as page_num, c.cell_id as cell_id
        ORDER BY c.page_num, c.row_index
        """
        sample_cells = session.run(sample_query, doc_id=doc_id).data()
        print(f"Found sample number cells: {len(sample_cells)}")
        for cell in sample_cells:
            print(f"  Page {cell['page_num']}, Row {cell['row_idx']}, Col {cell['col_idx']}: '{cell['text']}'")
        results['sample_cells'] = sample_cells

        # 7. Get complete table structure for each page
        print("\n" + "=" * 80)
        print("7. COMPLETE TABLE STRUCTURES")
        print("=" * 80)

        all_tables_data = {}
        for table in tables:
            table_id = table['table_id']
            page_num = table['page_num']

            cell_query = """
            MATCH (t:Table {doc_id: $doc_id, table_id: $table_id})-[:HAS_CELL]->(c:Cell)
            RETURN c.row_index as row_idx, c.col_index as col_idx, c.text as text
            ORDER BY c.row_index, c.col_index
            """
            cells = session.run(cell_query, doc_id=doc_id, table_id=table_id).data()

            if not cells:
                # Try direct cell query if relationship doesn't work
                cell_query2 = """
                MATCH (c:Cell {doc_id: $doc_id, page_num: $page_num})
                RETURN c.row_index as row_idx, c.col_index as col_idx, c.text as text
                ORDER BY c.row_index, c.col_index
                """
                cells = session.run(cell_query2, doc_id=doc_id, page_num=page_num).data()

            if cells:
                # Organize into rows
                table_data = {}
                max_row = 0
                max_col = 0
                for cell in cells:
                    row = cell['row_idx']
                    col = cell['col_idx']
                    if row not in table_data:
                        table_data[row] = {}
                    table_data[row][col] = cell['text']
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)

                print(f"\nTable {table_id} (Page {page_num}): {max_row + 1} rows x {max_col + 1} cols")
                print("-" * 100)

                # Print first 25 rows
                for row in range(min(25, max_row + 1)):
                    row_content = []
                    for col in range(max_col + 1):
                        content = table_data.get(row, {}).get(col, '')
                        if content:
                            content = content[:12].replace('\n', ' ')
                        row_content.append(f"{content:<12}")
                    print(f"R{row:2d}: {'|'.join(row_content[:10])}")  # First 10 cols

                all_tables_data[table_id] = {
                    'page_num': page_num,
                    'data': table_data,
                    'rows': max_row + 1,
                    'cols': max_col + 1
                }

        results['all_tables_data'] = all_tables_data

        # 8. Map row/col indices for all relevant data
        print("\n" + "=" * 80)
        print("8. ROW/COL INDEX MAPPING FOR RELEVANT DATA")
        print("=" * 80)

        index_mapping = {
            'header_rows_by_page': {},
            'ges_mittel_rows_by_page': {},
            'sample_rows_by_page': {},
            'threshold_columns_by_page': {}
        }

        # Map header rows (with threshold µm values)
        for cell in threshold_cells:
            page = cell['page_num']
            if page not in index_mapping['header_rows_by_page']:
                index_mapping['header_rows_by_page'][page] = set()
            index_mapping['header_rows_by_page'][page].add(cell['row_idx'])

            if page not in index_mapping['threshold_columns_by_page']:
                index_mapping['threshold_columns_by_page'][page] = {}
            index_mapping['threshold_columns_by_page'][page][cell['col_idx']] = cell['text']

        # Map Ges.-Mittel. rows
        for cell in ges_cells:
            page = cell['page_num']
            if page not in index_mapping['ges_mittel_rows_by_page']:
                index_mapping['ges_mittel_rows_by_page'][page] = set()
            index_mapping['ges_mittel_rows_by_page'][page].add(cell['row_idx'])

        # Map sample rows
        for cell in sample_cells:
            page = cell['page_num']
            if page not in index_mapping['sample_rows_by_page']:
                index_mapping['sample_rows_by_page'][page] = set()
            index_mapping['sample_rows_by_page'][page].add(cell['row_idx'])

        # Convert sets to lists for JSON serialization
        for key in ['header_rows_by_page', 'ges_mittel_rows_by_page', 'sample_rows_by_page']:
            for page in index_mapping[key]:
                index_mapping[key][page] = sorted(list(index_mapping[key][page]))

        print("\nHeader rows (with threshold values) by page:")
        for page, rows in index_mapping['header_rows_by_page'].items():
            print(f"  Page {page}: rows {rows}")

        print("\nGes.-Mittel. rows by page:")
        for page, rows in index_mapping['ges_mittel_rows_by_page'].items():
            print(f"  Page {page}: rows {rows}")

        print("\nSample rows (SA00*) by page:")
        for page, rows in index_mapping['sample_rows_by_page'].items():
            print(f"  Page {page}: rows {rows}")

        print("\nThreshold columns by page:")
        for page, cols in index_mapping['threshold_columns_by_page'].items():
            print(f"  Page {page}:")
            for col_idx, text in sorted(cols.items()):
                print(f"    Col {col_idx}: '{text}'")

        results['index_mapping'] = index_mapping

        # 9. Get Line nodes containing SA00
        print("\n" + "=" * 80)
        print("9. LINE NODES CONTAINING SA00")
        print("=" * 80)

        line_query = """
        MATCH (l:Line {doc_id: $doc_id})
        WHERE l.text CONTAINS 'SA00'
        RETURN l.text as text, l.page_num as page_num, l.line_id as line_id
        ORDER BY l.page_num
        """
        lines = session.run(line_query, doc_id=doc_id).data()
        print(f"Lines containing SA00: {len(lines)}")
        for line in lines:
            print(f"  Page {line['page_num']}: '{line['text']}'")
        results['sa00_lines'] = lines

        # 10. Get Section nodes
        print("\n" + "=" * 80)
        print("10. SECTION NODES")
        print("=" * 80)

        section_query = """
        MATCH (s:Section {doc_id: $doc_id})
        RETURN s.section_id as section_id, s.page_num as page_num,
               s.layout_type as layout_type, s.content as content
        ORDER BY s.page_num
        LIMIT 20
        """
        sections = session.run(section_query, doc_id=doc_id).data()
        print(f"Sections found: {len(sections)}")
        for sec in sections[:10]:
            content = sec.get('content', '')
            if content and len(content) > 50:
                content = content[:50] + "..."
            print(f"  Page {sec['page_num']}, Type {sec['layout_type']}: {content}")
        results['sections'] = sections

        # 11. Summary statistics
        print("\n" + "=" * 80)
        print("11. SUMMARY STATISTICS")
        print("=" * 80)

        stats_query = """
        MATCH (c:Cell {doc_id: $doc_id})
        RETURN count(c) as cell_count,
               max(c.row_index) as max_row,
               max(c.col_index) as max_col
        """
        stats = session.run(stats_query, doc_id=doc_id).single()
        print(f"Total cells: {stats['cell_count']}")
        print(f"Max row index: {stats['max_row']}")
        print(f"Max col index: {stats['max_col']}")

        line_count_query = """
        MATCH (l:Line {doc_id: $doc_id})
        RETURN count(l) as line_count
        """
        line_stats = session.run(line_count_query, doc_id=doc_id).single()
        print(f"Total lines: {line_stats['line_count']}")

        section_count_query = """
        MATCH (s:Section {doc_id: $doc_id})
        RETURN count(s) as section_count
        """
        section_stats = session.run(section_count_query, doc_id=doc_id).single()
        print(f"Total sections: {section_stats['section_count']}")

        results['stats'] = {
            'cell_count': stats['cell_count'],
            'max_row': stats['max_row'],
            'max_col': stats['max_col'],
            'line_count': line_stats['line_count'],
            'section_count': section_stats['section_count']
        }

        # 12. Complete row data for Ges.-Mittel. rows
        print("\n" + "=" * 80)
        print("12. COMPLETE DATA FOR Ges.-Mittel. ROWS")
        print("=" * 80)

        if ges_cells:
            for ges_cell in ges_cells:
                page = ges_cell['page_num']
                row = ges_cell['row_idx']

                row_query = """
                MATCH (c:Cell {doc_id: $doc_id, page_num: $page_num, row_index: $row_index})
                RETURN c.col_index as col_idx, c.text as text
                ORDER BY c.col_index
                """
                row_data = session.run(row_query, doc_id=doc_id,
                                       page_num=page, row_index=row).data()

                print(f"\nPage {page}, Row {row} (Ges.-Mittel.):")
                for cell in row_data:
                    text = cell['text'] if cell['text'] else ''
                    print(f"  Col {cell['col_idx']}: '{text}'")

        # 13. All cells in a specific table showing structure
        print("\n" + "=" * 80)
        print("13. DETAILED TABLE CELL STRUCTURE")
        print("=" * 80)

        if tables:
            first_table = tables[0]
            table_id = first_table['table_id']
            page_num = first_table['page_num']

            all_cells_query = """
            MATCH (c:Cell {doc_id: $doc_id, page_num: $page_num})
            RETURN c.row_index as row, c.col_index as col, c.text as text,
                   c.row_span as row_span, c.col_span as col_span
            ORDER BY c.row_index, c.col_index
            """
            all_cells = session.run(all_cells_query, doc_id=doc_id, page_num=page_num).data()

            print(f"\nAll cells on Page {page_num}:")
            current_row = -1
            for cell in all_cells[:100]:  # Limit to first 100
                if cell['row'] != current_row:
                    current_row = cell['row']
                    print(f"\n  Row {current_row}:")
                text = cell['text'][:30] if cell['text'] else ''
                span_info = ""
                if cell.get('row_span', 1) > 1 or cell.get('col_span', 1) > 1:
                    span_info = f" (span:{cell.get('row_span',1)}x{cell.get('col_span',1)})"
                print(f"    [{cell['col']}]: '{text}'{span_info}")

    driver.close()
    return results

if __name__ == "__main__":
    results = explore_document_structure()
    print("\n" + "=" * 80)
    print("EXPLORATION COMPLETE")
    print("=" * 80)
