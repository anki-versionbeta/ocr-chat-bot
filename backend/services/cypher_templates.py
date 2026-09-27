"""
Cypher Query Templates for Phase 6 - Neo4j Structural Queries

This module provides reusable Cypher query templates for:
1. Structural queries (page finding, table discovery)
2. Extraction queries (column data, row traversal)
3. Hybrid queries (used with Weaviate chunk_index)

Each template is a function that returns formatted Cypher with parameters.

Created: February 11, 2026
Phase: 6 - Neo4j Structural Integration
"""

from typing import Dict, List, Tuple, Any


class CypherTemplates:
    """
    Collection of reusable Cypher query templates.

    Usage:
        templates = CypherTemplates()
        cypher, params = templates.find_pages_with_tables(process_id)
        results = neo4j_service.query(cypher, params)
    """

    # =========================================================================
    # STRUCTURAL QUERIES
    # =========================================================================

    @staticmethod
    def find_pages_with_tables(process_id: str) -> Tuple[str, Dict]:
        """Find all pages that contain tables"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            RETURN p.page_num AS page_num,
                   count(t) AS table_count,
                   collect(t.chunk_index) AS chunk_indices
            ORDER BY p.page_num
        """
        return cypher, {"process_id": process_id}

    @staticmethod
    def find_pages_with_content(process_id: str, search_pattern: str) -> Tuple[str, Dict]:
        """Find pages containing specific text in cells or sections"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE toLower(coalesce(c.text, '')) CONTAINS toLower($pattern)
            WITH p, count(c) AS cell_matches
            WHERE cell_matches > 0
            RETURN p.page_num AS page_num,
                   cell_matches AS matches
            ORDER BY cell_matches DESC
        """
        return cypher, {
            "process_id": process_id,
            "pattern": search_pattern  # Now using CONTAINS instead of regex
        }

    @staticmethod
    def get_document_structure(process_id: str) -> Tuple[str, Dict]:
        """Get complete document structure overview"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})
            OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
            WITH d, p,
                 count(DISTINCT t) AS tables_on_page,
                 count(DISTINCT s) AS sections_on_page
            RETURN d.filename AS filename,
                   d.page_count AS page_count,
                   collect({
                       page: p.page_num,
                       tables: tables_on_page,
                       sections: sections_on_page
                   }) AS pages
        """
        return cypher, {"process_id": process_id}

    @staticmethod
    def find_tables_by_header(process_id: str, header_pattern: str) -> Tuple[str, Dict]:
        """Find tables that have a specific column header"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0 OR header.row_index = 1)
              AND toLower(coalesce(header.text, '')) CONTAINS toLower($pattern)
            RETURN DISTINCT t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   p.page_num AS page_num,
                   header.text AS matched_header,
                   t.row_count AS row_count,
                   t.col_count AS col_count
            ORDER BY p.page_num
        """
        return cypher, {
            "process_id": process_id,
            "pattern": header_pattern  # Now using CONTAINS instead of regex
        }

    # =========================================================================
    # EXTRACTION QUERIES (Column/Row Data)
    # =========================================================================

    @staticmethod
    def extract_column_by_header(process_id: str, header_pattern: str) -> Tuple[str, Dict]:
        """
        Extract ALL data from columns matching a header pattern.
        This is THE POWER QUERY for hybrid extraction.

        Returns data from ALL pages, ALL tables where column header matches.
        """
        cypher = """
            // Find header cells matching the pattern
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0 OR header.row_index = 1)
              AND toLower(coalesce(header.text, '')) CONTAINS toLower($pattern)

            // Get the column index where the match is
            WITH t, p, header.col_index AS target_col, header.text AS column_header

            // Get ALL data cells in that column
            MATCH (t)-[:HAS_CELL]->(data_cell:Cell)
            WHERE data_cell.col_index = target_col
              AND data_cell.row_index > 1  // Skip header rows

            // Get the full row for context (first column usually has the label)
            OPTIONAL MATCH (t)-[:HAS_CELL]->(label_cell:Cell)
            WHERE label_cell.row_index = data_cell.row_index AND label_cell.col_index = 0

            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   data_cell.row_index AS row_index,
                   column_header,
                   coalesce(label_cell.text, '') AS row_label,
                   data_cell.text AS value,
                   data_cell.cell_key AS cell_key,
                   {
                       left: data_cell.bbox_left,
                       top: data_cell.bbox_top,
                       right: data_cell.bbox_right,
                       bottom: data_cell.bbox_bottom
                   } AS bbox
            ORDER BY p.page_num, t.bbox_top, data_cell.row_index
        """
        return cypher, {
            "process_id": process_id,
            "pattern": header_pattern  # Now using CONTAINS instead of regex
        }

    @staticmethod
    def find_row_by_cell_value(process_id: str, search_text: str) -> Tuple[str, Dict]:
        """
        Find and extract ALL cells in a row that contains specific text in ANY cell.
        Example: "Find row containing '3 Minor defect' with all column values"

        This is for queries like:
        - "Find the row that contains 'Critical' with all column values"
        - "Get the row where Minor defect appears"
        """
        cypher = """
            // Find the target cell containing the search text
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(target:Cell)
            WHERE toLower(target.text) CONTAINS toLower($search_text)

            // Get the row number of the target cell
            WITH t, p, target.row_index AS target_row, target.text AS matched_text

            // Get ALL cells in that row
            MATCH (t)-[:HAS_CELL]->(row_cell:Cell)
            WHERE row_cell.row_index = target_row

            // Get column headers for context
            OPTIONAL MATCH (t)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0 OR header.row_index = 1)
              AND header.col_index = row_cell.col_index

            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   target_row AS row,
                   matched_text AS matched_cell,
                   row_cell.col_index AS col,
                   coalesce(header.text, 'Column ' + toString(row_cell.col_index)) AS column_header,
                   row_cell.text AS value,
                   row_cell.cell_key AS cell_key,
                   {
                       left: row_cell.bbox_left,
                       top: row_cell.bbox_top,
                       right: row_cell.bbox_right,
                       bottom: row_cell.bbox_bottom
                   } AS bbox
            ORDER BY row_cell.col_index
        """
        return cypher, {
            "process_id": process_id,
            "search_text": search_text
        }

    @staticmethod
    def extract_row_by_label(process_id: str, label_pattern: str) -> Tuple[str, Dict]:
        """
        Extract full row data where first column matches a label pattern.
        Example: "Get row where first column is 'pH'"
        """
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(label:Cell)
            WHERE label.col_index = 0
              AND label.text =~ $pattern

            // Get all cells in the same row
            MATCH (t)-[:HAS_CELL]->(row_cell:Cell)
            WHERE row_cell.row_index = label.row_index

            // Get header for each column
            OPTIONAL MATCH (t)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0 OR header.row_index = 1)
              AND header.col_index = row_cell.col_index

            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   label.row_index AS row_index,
                   label.text AS row_label,
                   collect({
                       col_index: row_cell.col_index,
                       header: coalesce(header.text, 'Column ' + toString(row_cell.col_index)),
                       value: row_cell.text,
                       cell_key: row_cell.cell_key,
                       bbox: {
                           left: row_cell.bbox_left,
                           top: row_cell.bbox_top,
                           right: row_cell.bbox_right,
                           bottom: row_cell.bbox_bottom
                       }
                   }) AS row_data
            ORDER BY p.page_num, t.bbox_top
        """
        return cypher, {
            "process_id": process_id,
            "pattern": f"(?i).*{label_pattern}.*"
        }

    @staticmethod
    def extract_full_table_by_chunk_index(process_id: str, chunk_index: int) -> Tuple[str, Dict]:
        """
        Extract complete table data by chunk_index.
        This is the BRIDGE query - Weaviate finds chunk_index, Neo4j extracts all data.
        """
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table {chunk_index: $chunk_index})
            MATCH (t)-[:HAS_CELL]->(c:Cell)

            WITH t, p, c
            ORDER BY c.row_index, c.col_index

            WITH t, p,
                 c.row_index AS row,
                 collect({
                     col: c.col_index,
                     text: c.text,
                     cell_key: c.cell_key,
                     is_header: c.is_header,
                     bbox: {
                         left: c.bbox_left,
                         top: c.bbox_top,
                         right: c.bbox_right,
                         bottom: c.bbox_bottom
                     }
                 }) AS row_cells

            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   t.row_count AS row_count,
                   t.col_count AS col_count,
                   collect({
                       row_index: row,
                       cells: row_cells
                   }) AS rows,
                   {
                       left: t.bbox_left,
                       top: t.bbox_top,
                       right: t.bbox_right,
                       bottom: t.bbox_bottom
                   } AS table_bbox
        """
        return cypher, {
            "process_id": process_id,
            "chunk_index": chunk_index
        }

    # =========================================================================
    # VALIDATION QUERIES
    # =========================================================================

    @staticmethod
    def find_values_in_range(
        process_id: str,
        header_pattern: str,
        min_value: float = None,
        max_value: float = None
    ) -> Tuple[str, Dict]:
        """
        Find values in a column that are within or outside a range.
        Useful for validation checks.
        """
        # Build WHERE clause based on provided values
        range_conditions = []
        if min_value is not None:
            range_conditions.append("toFloat(data_cell.text) >= $min_value")
        if max_value is not None:
            range_conditions.append("toFloat(data_cell.text) <= $max_value")

        range_clause = " AND ".join(range_conditions) if range_conditions else "true"

        cypher = f"""
            MATCH (d:Document {{process_id: $process_id}})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0)
              AND header.text =~ $pattern

            WITH t, p, header.col_index AS target_col, header.text AS column_header

            MATCH (t)-[:HAS_CELL]->(data_cell:Cell)
            WHERE data_cell.col_index = target_col
              AND data_cell.row_index > 0
              AND data_cell.text =~ '^[0-9.]+$'  // Numeric values only
              AND {range_clause}

            OPTIONAL MATCH (t)-[:HAS_CELL]->(label:Cell)
            WHERE label.row_index = data_cell.row_index AND label.col_index = 0

            RETURN p.page_num AS page,
                   column_header,
                   label.text AS row_label,
                   data_cell.text AS value,
                   toFloat(data_cell.text) AS numeric_value,
                   data_cell.cell_key AS cell_key
            ORDER BY p.page_num, data_cell.row_index
        """
        params = {
            "process_id": process_id,
            "pattern": header_pattern  # Now using CONTAINS instead of regex
        }
        if min_value is not None:
            params["min_value"] = min_value
        if max_value is not None:
            params["max_value"] = max_value

        return cypher, params

    # =========================================================================
    # ECD/MFI SPECIALIZED QUERIES (Particle counting / concentration tables)
    # =========================================================================

    @staticmethod
    def extract_ecd_concentration_data(process_id: str) -> Tuple[str, Dict]:
        """
        Extract concentration data from ECD/MFI tables across ALL pages.

        Logic:
        1. Find tables with "Range" rows
        2. Identify the SECOND Range row (the one with 5.00/25.00/50.00 threshold markers)
        3. Find the first "Concentration" row AFTER that header row
        4. Extract all values aligned to threshold columns (≥1.00, ≥2.00, ≥5.00, etc.)

        This is a SPECIALIZED query for MFI stability sample documents.
        Returns: page, header row values, concentration values for each threshold.
        """
        cypher = """
            // Find tables with Range rows
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)

            // Identify all Range rows in each table
            MATCH (t)-[:HAS_CELL]->(r:Cell)
            WHERE toLower(coalesce(r.text,'')) CONTAINS 'range'
            WITH p, t, collect(DISTINCT r.row_index) AS rangeRows

            // Find the Range row with threshold markers (5.00, 25.00, etc.)
            UNWIND rangeRows AS rr
            MATCH (t)-[:HAS_CELL]->(c5:Cell {row_index: rr})
            WHERE replace(coalesce(c5.text,''), ' ', '') CONTAINS '5.00'
            MATCH (t)-[:HAS_CELL]->(c25:Cell {row_index: rr})
            WHERE replace(coalesce(c25.text,''), ' ', '') CONTAINS '25.00'

            WITH p, t, rr
            ORDER BY rr ASC
            WITH p, t, collect(rr) AS validRangeRows
            WHERE size(validRangeRows) > 0

            // Take the first valid range row (with thresholds)
            WITH p, t, validRangeRows[0] AS headerRow

            // Find the first Concentration row AFTER headerRow
            MATCH (t)-[:HAS_CELL]->(lbl:Cell)
            WHERE lbl.row_index > headerRow
              AND lbl.col_index = 1
              AND toLower(coalesce(lbl.text,'')) CONTAINS 'concentration'
            WITH p, t, headerRow, lbl
            ORDER BY lbl.row_index ASC
            WITH p, t, headerRow, head(collect(lbl.row_index)) AS concRow
            WHERE concRow IS NOT NULL

            // Get header row cells (threshold values) and concentration row cells
            MATCH (t)-[:HAS_CELL]->(h:Cell {row_index: headerRow})
            WHERE h.col_index >= 2 AND trim(coalesce(h.text,'')) <> ''
            OPTIONAL MATCH (t)-[:HAS_CELL]->(v:Cell {row_index: concRow, col_index: h.col_index})

            RETURN
                p.page_num AS page,
                t.table_id AS table_id,
                headerRow AS header_row,
                concRow AS concentration_row,
                h.col_index AS col,
                h.text AS threshold_header,
                v.text AS concentration_value,
                {
                    left: v.bbox_left,
                    top: v.bbox_top,
                    width: v.bbox_width,
                    height: v.bbox_height
                } AS bbox
            ORDER BY p.page_num, h.col_index
        """
        return cypher, {"process_id": process_id}

    @staticmethod
    def extract_ecd_concentration_pivoted(process_id: str) -> Tuple[str, Dict]:
        """
        Extract ECD concentration data in PIVOTED format (one row per page).

        Returns columns: page, >=1.00, >=2.00, >=5.00, >=10.00, >=25.00, >=50.00
        """
        cypher = """
            // Find tables with Range rows
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)

            MATCH (t)-[:HAS_CELL]->(r:Cell)
            WHERE toLower(coalesce(r.text,'')) CONTAINS 'range'
            WITH p, t, collect(DISTINCT r.row_index) AS rangeRows

            UNWIND rangeRows AS rr
            MATCH (t)-[:HAS_CELL]->(c5:Cell {row_index: rr})
            WHERE replace(coalesce(c5.text,''), ' ', '') CONTAINS '5.00'
            MATCH (t)-[:HAS_CELL]->(c25:Cell {row_index: rr})
            WHERE replace(coalesce(c25.text,''), ' ', '') CONTAINS '25.00'

            WITH p, t, rr
            ORDER BY rr ASC
            WITH p, t, collect(rr) AS validRangeRows
            WHERE size(validRangeRows) > 0
            WITH p, t, validRangeRows[0] AS headerRow

            MATCH (t)-[:HAS_CELL]->(lbl:Cell)
            WHERE lbl.row_index > headerRow
              AND lbl.col_index = 1
              AND toLower(coalesce(lbl.text,'')) CONTAINS 'concentration'
            WITH p, t, headerRow, lbl
            ORDER BY lbl.row_index ASC
            WITH p, t, headerRow, head(collect(lbl.row_index)) AS concRow
            WHERE concRow IS NOT NULL

            // Get all header/value pairs
            MATCH (t)-[:HAS_CELL]->(h:Cell {row_index: headerRow})
            WHERE h.col_index >= 2 AND trim(coalesce(h.text,'')) <> ''
            OPTIONAL MATCH (t)-[:HAS_CELL]->(v:Cell {row_index: concRow, col_index: h.col_index})

            WITH p, t,
                 collect({header: replace(h.text, ' ', ''), value: v.text}) AS pairs

            // Pivot to columns - normalize header text for matching
            RETURN
                p.page_num AS page,
                [x IN pairs WHERE x.header =~ '.*1\\\\.00.*' | x.value][0] AS `>=1.00`,
                [x IN pairs WHERE x.header =~ '.*2\\\\.00.*' | x.value][0] AS `>=2.00`,
                [x IN pairs WHERE x.header =~ '.*5\\\\.00.*' AND NOT x.header =~ '.*25.*' AND NOT x.header =~ '.*50.*' | x.value][0] AS `>=5.00`,
                [x IN pairs WHERE x.header =~ '.*10\\\\.00.*' | x.value][0] AS `>=10.00`,
                [x IN pairs WHERE x.header =~ '.*25\\\\.00.*' | x.value][0] AS `>=25.00`,
                [x IN pairs WHERE x.header =~ '.*50\\\\.00.*' | x.value][0] AS `>=50.00`
            ORDER BY p.page_num
        """
        return cypher, {"process_id": process_id}

    # =========================================================================
    # ANALYTICS QUERIES
    # =========================================================================

    @staticmethod
    def count_tables_per_page(process_id: str) -> Tuple[str, Dict]:
        """Count tables on each page"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            RETURN p.page_num AS page_num,
                   count(t) AS table_count
            ORDER BY p.page_num
        """
        return cypher, {"process_id": process_id}

    @staticmethod
    def get_column_headers_from_all_tables(process_id: str) -> Tuple[str, Dict]:
        """Get all unique column headers across all tables"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE c.is_header = true OR c.row_index = 0 OR c.row_index = 1
            RETURN DISTINCT c.text AS header,
                   count(*) AS occurrence_count
            ORDER BY occurrence_count DESC
        """
        return cypher, {"process_id": process_id}

    @staticmethod
    def get_document_statistics(process_id: str) -> Tuple[str, Dict]:
        """Get comprehensive document statistics"""
        cypher = """
            MATCH (d:Document {process_id: $process_id})
            OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_CELL]->(c:Cell)
            OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
            OPTIONAL MATCH (p)-[:CONTAINS_LINE]->(l:Line)

            RETURN d.filename AS filename,
                   d.document_type AS document_type,
                   count(DISTINCT p) AS page_count,
                   count(DISTINCT t) AS table_count,
                   count(DISTINCT c) AS cell_count,
                   count(DISTINCT s) AS section_count,
                   count(DISTINCT l) AS line_count
        """
        return cypher, {"process_id": process_id}

    # =========================================================================
    # PROVENANCE QUERIES
    # =========================================================================

    @staticmethod
    def get_cell_provenance(cell_key: str) -> Tuple[str, Dict]:
        """Get full hierarchy path to a cell"""
        cypher = """
            MATCH (c:Cell {cell_key: $cell_key})
            MATCH (t:Table)-[:HAS_CELL]->(c)
            MATCH (p:Page)-[:CONTAINS_TABLE]->(t)
            MATCH (d:Document)-[:HAS_PAGE]->(p)

            RETURN {
                document: {
                    id: d.process_id,
                    filename: d.filename
                },
                page: {
                    num: p.page_num
                },
                table: {
                    key: t.table_key,
                    chunk_index: t.chunk_index,
                    bbox: {
                        left: t.bbox_left,
                        top: t.bbox_top,
                        right: t.bbox_right,
                        bottom: t.bbox_bottom
                    }
                },
                cell: {
                    key: c.cell_key,
                    text: c.text,
                    row: c.row_index,
                    col: c.col_index,
                    bbox: {
                        left: c.bbox_left,
                        top: c.bbox_top,
                        right: c.bbox_right,
                        bottom: c.bbox_bottom
                    }
                }
            } AS provenance
        """
        return cypher, {"cell_key": cell_key}

    @staticmethod
    def get_row_context(cell_key: str) -> Tuple[str, Dict]:
        """Get all cells in the same row as a given cell"""
        cypher = """
            MATCH (c:Cell {cell_key: $cell_key})
            MATCH (t:Table)-[:HAS_CELL]->(c)
            MATCH (t)-[:HAS_CELL]->(row_cell:Cell)
            WHERE row_cell.row_index = c.row_index

            // Get headers for context
            OPTIONAL MATCH (t)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0)
              AND header.col_index = row_cell.col_index

            RETURN c.cell_key AS target_cell,
                   c.row_index AS row_index,
                   t.table_key AS table_key,
                   collect({
                       col_index: row_cell.col_index,
                       text: row_cell.text,
                       cell_key: row_cell.cell_key,
                       header: header.text,
                       is_target: row_cell.cell_key = $cell_key
                   }) AS row_cells
            ORDER BY row_cell.col_index
        """
        return cypher, {"cell_key": cell_key}


# Singleton instance
_cypher_templates = None


def get_cypher_templates() -> CypherTemplates:
    """Get CypherTemplates singleton"""
    global _cypher_templates
    if _cypher_templates is None:
        _cypher_templates = CypherTemplates()
    return _cypher_templates
