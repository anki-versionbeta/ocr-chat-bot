"""
Neo4j Service for Phase 6 - Structural Query Support

This service provides:
1. Connection management to Neo4j database
2. Query execution with parameterization
3. Common structural query methods
4. Bridge methods for Weaviate chunk_index linking

Connection: bolt://10.242.190.53:7687
User: neo4j
Password: ocr@4567

Created: February 11, 2026
Phase: 6 - Neo4j Structural Integration
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

try:
    from neo4j import GraphDatabase, Driver
    from neo4j.exceptions import ServiceUnavailable, AuthError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None
    Driver = None

logger = logging.getLogger("ocr-chatbot.neo4j_service")

# Neo4j Connection Configuration
NEO4J_URI = "bolt://10.242.190.53:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = REDACTED


class Neo4jService:
    """
    Neo4j Service for structural queries in RAG system.

    Provides methods for:
    - Document structure queries (pages, sections, tables)
    - Cell/row traversal using SAME_ROW, SAME_COL relationships
    - Chunk index bridge to Weaviate
    - Provenance path queries
    """

    _instance = None
    _driver: Optional[Driver] = None

    def __new__(cls):
        """Singleton pattern for connection reuse"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize Neo4j driver (lazy connection)"""
        if not NEO4J_AVAILABLE:
            logger.warning("neo4j package not installed. Run: pip install neo4j")
            return

        if self._driver is None:
            try:
                self._driver = GraphDatabase.driver(
                    NEO4J_URI,
                    auth=(NEO4J_USER, NEO4J_PASSWORD),
                    max_connection_lifetime=3600,  # 1 hour
                    max_connection_pool_size=50,
                    connection_acquisition_timeout=30
                )
                # Verify connection
                self._driver.verify_connectivity()
                logger.info(f"✅ Neo4j connected to {NEO4J_URI}")
            except AuthError as e:
                logger.error(f"❌ Neo4j authentication failed: {e}")
                self._driver = None
            except ServiceUnavailable as e:
                logger.error(f"❌ Neo4j service unavailable: {e}")
                self._driver = None
            except Exception as e:
                logger.error(f"❌ Neo4j connection error: {e}")
                self._driver = None

    @property
    def is_connected(self) -> bool:
        """Check if Neo4j is connected"""
        return self._driver is not None

    def close(self):
        """Close the Neo4j driver"""
        if self._driver:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @contextmanager
    def get_session(self):
        """Get a Neo4j session with automatic cleanup"""
        if not self._driver:
            raise ConnectionError("Neo4j driver not initialized")

        session = self._driver.session()
        try:
            yield session
        finally:
            session.close()

    def query(self, cypher: str, params: Dict = None) -> List[Dict]:
        """
        Execute a Cypher query and return results as list of dicts.

        Args:
            cypher: Cypher query string
            params: Query parameters (optional)

        Returns:
            List of result records as dictionaries
        """
        if not self._driver:
            logger.warning("Neo4j not connected, returning empty results")
            return []

        try:
            with self.get_session() as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except Exception as e:
            logger.error(f"Neo4j query error: {e}\nQuery: {cypher[:200]}...")
            return []

    def query_single(self, cypher: str, params: Dict = None) -> Optional[Dict]:
        """Execute query and return single result or None"""
        results = self.query(cypher, params)
        return results[0] if results else None

    # =========================================================================
    # DOCUMENT STRUCTURE QUERIES
    # =========================================================================

    def get_document_by_process_id(self, process_id: str) -> Optional[Dict]:
        """Get document node by process_id"""
        return self.query_single("""
            MATCH (d:Document {process_id: $process_id})
            RETURN d.doc_id AS doc_id,
                   d.filename AS filename,
                   d.page_count AS page_count,
                   d.document_type AS document_type,
                   d.created_at AS created_at
        """, {"process_id": process_id})

    def get_document_pages(self, process_id: str) -> List[Dict]:
        """Get all pages for a document"""
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            RETURN p.page_key AS page_key,
                   p.page_num AS page_num,
                   p.width AS width,
                   p.height AS height
            ORDER BY p.page_num
        """, {"process_id": process_id})

    def get_tables_on_page(self, process_id: str, page_num: int) -> List[Dict]:
        """Get all tables on a specific page"""
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page {page_num: $page_num})
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            RETURN t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   t.row_count AS row_count,
                   t.col_count AS col_count,
                   t.bbox_left AS bbox_left,
                   t.bbox_top AS bbox_top,
                   t.bbox_right AS bbox_right,
                   t.bbox_bottom AS bbox_bottom
            ORDER BY t.bbox_top
        """, {"process_id": process_id, "page_num": page_num})

    def get_sections_on_page(self, process_id: str, page_num: int) -> List[Dict]:
        """Get all sections on a specific page"""
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page {page_num: $page_num})
            MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
            RETURN s.section_key AS section_key,
                   s.layout_type AS layout_type,
                   s.content AS content,
                   s.chunk_index AS chunk_index,
                   s.bbox_left AS bbox_left,
                   s.bbox_top AS bbox_top
            ORDER BY s.bbox_top
        """, {"process_id": process_id, "page_num": page_num})

    # =========================================================================
    # TABLE CELL QUERIES (SAME_ROW, SAME_COL)
    # =========================================================================

    def get_table_cells(self, table_key: str) -> List[Dict]:
        """Get all cells in a table ordered by row and column"""
        return self.query("""
            MATCH (t:Table {table_key: $table_key})-[:HAS_CELL]->(c:Cell)
            RETURN c.cell_key AS cell_key,
                   c.row_index AS row_index,
                   c.col_index AS col_index,
                   c.text AS text,
                   c.is_header AS is_header,
                   c.bbox_left AS bbox_left,
                   c.bbox_top AS bbox_top,
                   c.bbox_right AS bbox_right,
                   c.bbox_bottom AS bbox_bottom
            ORDER BY c.row_index, c.col_index
        """, {"table_key": table_key})

    def get_row_cells(self, table_key: str, row_index: int) -> List[Dict]:
        """Get all cells in a specific row using SAME_ROW relationship"""
        return self.query("""
            MATCH (t:Table {table_key: $table_key})-[:HAS_CELL]->(c:Cell {row_index: $row_index})
            RETURN c.cell_key AS cell_key,
                   c.col_index AS col_index,
                   c.text AS text,
                   c.bbox_left AS bbox_left,
                   c.bbox_top AS bbox_top,
                   c.bbox_right AS bbox_right,
                   c.bbox_bottom AS bbox_bottom
            ORDER BY c.col_index
        """, {"table_key": table_key, "row_index": row_index})

    def get_column_cells(self, table_key: str, col_index: int) -> List[Dict]:
        """Get all cells in a specific column using SAME_COL relationship"""
        return self.query("""
            MATCH (t:Table {table_key: $table_key})-[:HAS_CELL]->(c:Cell {col_index: $col_index})
            RETURN c.cell_key AS cell_key,
                   c.row_index AS row_index,
                   c.text AS text,
                   c.is_header AS is_header,
                   c.bbox_left AS bbox_left,
                   c.bbox_top AS bbox_top,
                   c.bbox_right AS bbox_right,
                   c.bbox_bottom AS bbox_bottom
            ORDER BY c.row_index
        """, {"table_key": table_key, "col_index": col_index})

    def get_cell_with_row_context(self, cell_key: str) -> Dict:
        """Get a cell along with all cells in its row"""
        result = self.query("""
            MATCH (c:Cell {cell_key: $cell_key})
            MATCH (t:Table)-[:HAS_CELL]->(c)
            MATCH (t)-[:HAS_CELL]->(row_cell:Cell {row_index: c.row_index})
            RETURN c.cell_key AS target_cell,
                   c.text AS target_text,
                   c.row_index AS row_index,
                   t.table_key AS table_key,
                   t.page_num AS page_num,
                   collect({
                       col_index: row_cell.col_index,
                       text: row_cell.text,
                       cell_key: row_cell.cell_key
                   }) AS row_cells
            ORDER BY row_cell.col_index
        """, {"cell_key": cell_key})
        return result[0] if result else {}

    # =========================================================================
    # CHUNK INDEX BRIDGE (Weaviate <-> Neo4j)
    # =========================================================================

    def get_table_by_chunk_index(self, process_id: str, chunk_index: int) -> Optional[Dict]:
        """
        Get table structure by chunk_index (bridge from Weaviate).

        This is the KEY method for Weaviate -> Neo4j hybrid queries.
        Weaviate returns chunk_index, Neo4j returns full structure.
        """
        return self.query_single("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table {chunk_index: $chunk_index})
            RETURN t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   t.row_count AS row_count,
                   t.col_count AS col_count,
                   p.page_num AS page_num,
                   t.bbox_left AS bbox_left,
                   t.bbox_top AS bbox_top,
                   t.bbox_right AS bbox_right,
                   t.bbox_bottom AS bbox_bottom
        """, {"process_id": process_id, "chunk_index": chunk_index})

    def get_full_table_data_by_chunk_index(self, process_id: str, chunk_index: int) -> Dict:
        """
        Get complete table data (all rows, all columns) by chunk_index.

        This is used for extraction queries where Weaviate finds the table
        and Neo4j extracts all the data.

        Returns:
            {
                "table_key": "...",
                "page_num": 1,
                "headers": ["Col1", "Col2", ...],
                "rows": [
                    {"row_index": 1, "cells": [{"col_index": 0, "text": "..."}]}
                ]
            }
        """
        # Get table info
        table = self.get_table_by_chunk_index(process_id, chunk_index)
        if not table:
            return {}

        # Get all cells
        cells = self.get_table_cells(table["table_key"])

        # Organize into rows
        headers = []
        rows = {}

        for cell in cells:
            row_idx = cell["row_index"]

            if cell.get("is_header") or row_idx == 0:
                headers.append({
                    "col_index": cell["col_index"],
                    "text": cell["text"]
                })
            else:
                if row_idx not in rows:
                    rows[row_idx] = []
                rows[row_idx].append({
                    "col_index": cell["col_index"],
                    "text": cell["text"],
                    "cell_key": cell["cell_key"],
                    "bbox": {
                        "left": cell["bbox_left"],
                        "top": cell["bbox_top"],
                        "right": cell["bbox_right"],
                        "bottom": cell["bbox_bottom"]
                    }
                })

        # Sort headers and rows by column index
        headers.sort(key=lambda x: x["col_index"])

        return {
            "table_key": table["table_key"],
            "chunk_index": chunk_index,
            "page_num": table["page_num"],
            "row_count": table.get("row_count", len(rows)),
            "col_count": table.get("col_count", len(headers)),
            "headers": [h["text"] for h in headers],
            "rows": [
                {
                    "row_index": row_idx,
                    "cells": sorted(row_cells, key=lambda x: x["col_index"])
                }
                for row_idx, row_cells in sorted(rows.items())
            ],
            "bbox": {
                "left": table["bbox_left"],
                "top": table["bbox_top"],
                "right": table["bbox_right"],
                "bottom": table["bbox_bottom"]
            }
        }

    # =========================================================================
    # COLUMN-BASED EXTRACTION (for queries like "get all concentration values")
    # =========================================================================

    def find_column_by_header(self, process_id: str, header_pattern: str) -> List[Dict]:
        """
        Find all columns across all tables that match a header pattern.

        Args:
            process_id: Document process ID
            header_pattern: Pattern to match (e.g., "Concentration", "Result")

        Returns:
            List of matching columns with their table info
        """
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0)
              AND header.text =~ $pattern
            RETURN t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   p.page_num AS page_num,
                   header.col_index AS col_index,
                   header.text AS header_text
            ORDER BY p.page_num, t.bbox_top
        """, {"process_id": process_id, "pattern": f"(?i).*{header_pattern}.*"})

    def extract_column_data(self, process_id: str, header_pattern: str) -> List[Dict]:
        """
        Extract all data from columns matching a header pattern across all pages.

        This is the POWER query for hybrid semantic-structural extraction.
        Weaviate finds "concentration" → Neo4j extracts ALL concentration values.

        Returns:
            List of {page, table, row_index, column_header, value, bbox}
        """
        return self.query("""
            // Find all header cells matching the pattern
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(header:Cell)
            WHERE (header.is_header = true OR header.row_index = 0)
              AND header.text =~ $pattern

            // Get the column index
            WITH t, p, header.col_index AS target_col, header.text AS column_header

            // Get all data cells in that column (row_index > 0)
            MATCH (t)-[:HAS_CELL]->(data_cell:Cell)
            WHERE data_cell.col_index = target_col AND data_cell.row_index > 0

            // Get the full row for context
            MATCH (t)-[:HAS_CELL]->(row_cell:Cell {row_index: data_cell.row_index})

            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   data_cell.row_index AS row_index,
                   column_header,
                   data_cell.text AS value,
                   data_cell.cell_key AS cell_key,
                   data_cell.bbox_left AS bbox_left,
                   data_cell.bbox_top AS bbox_top,
                   data_cell.bbox_right AS bbox_right,
                   data_cell.bbox_bottom AS bbox_bottom,
                   collect({col: row_cell.col_index, text: row_cell.text}) AS full_row
            ORDER BY p.page_num, t.bbox_top, data_cell.row_index
        """, {"process_id": process_id, "pattern": f"(?i).*{header_pattern}.*"})

    # =========================================================================
    # PROVENANCE PATH QUERIES
    # =========================================================================

    def get_provenance_path(self, cell_key: str) -> List[Dict]:
        """
        Get the full hierarchical path from document to cell.

        Returns:
            List of path nodes: [Document, Page, Table, Cell]
        """
        return self.query("""
            MATCH (c:Cell {cell_key: $cell_key})
            MATCH (t:Table)-[:HAS_CELL]->(c)
            MATCH (p:Page)-[:CONTAINS_TABLE]->(t)
            MATCH (d:Document)-[:HAS_PAGE]->(p)

            RETURN [
                {type: 'Document', id: d.doc_id, name: d.filename},
                {type: 'Page', id: p.page_key, name: 'Page ' + toString(p.page_num)},
                {type: 'Table', id: t.table_key, name: 'Table (chunk ' + toString(t.chunk_index) + ')'},
                {type: 'Cell', id: c.cell_key, name: c.text, row: c.row_index, col: c.col_index}
            ] AS hierarchy
        """, {"cell_key": cell_key})

    # =========================================================================
    # STRUCTURAL SEARCH QUERIES
    # =========================================================================

    def find_text_in_cells(self, process_id: str, search_text: str, limit: int = 20) -> List[Dict]:
        """
        Find cells containing specific text across all tables.
        """
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE c.text =~ $pattern
            RETURN p.page_num AS page,
                   t.table_key AS table_key,
                   t.chunk_index AS chunk_index,
                   c.cell_key AS cell_key,
                   c.row_index AS row_index,
                   c.col_index AS col_index,
                   c.text AS text,
                   c.bbox_left AS bbox_left,
                   c.bbox_top AS bbox_top,
                   c.bbox_right AS bbox_right,
                   c.bbox_bottom AS bbox_bottom
            ORDER BY p.page_num, t.bbox_top, c.row_index
            LIMIT $limit
        """, {"process_id": process_id, "pattern": f"(?i).*{search_text}.*", "limit": limit})

    def find_pages_with_content(self, process_id: str, content_pattern: str) -> List[Dict]:
        """
        Find pages that contain specific content in cells or sections.
        """
        return self.query("""
            MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
            WHERE c.text =~ $pattern
            OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
            WHERE s.content =~ $pattern
            WITH p, count(DISTINCT c) AS cell_matches, count(DISTINCT s) AS section_matches
            WHERE cell_matches > 0 OR section_matches > 0
            RETURN p.page_num AS page_num,
                   cell_matches,
                   section_matches,
                   cell_matches + section_matches AS total_matches
            ORDER BY total_matches DESC
        """, {"process_id": process_id, "pattern": f"(?i).*{content_pattern}.*"})

    # =========================================================================
    # ANALYTICS QUERIES
    # =========================================================================

    def get_document_statistics(self, process_id: str) -> Dict:
        """Get statistics about a document's structure"""
        result = self.query_single("""
            MATCH (d:Document {process_id: $process_id})
            OPTIONAL MATCH (d)-[:HAS_PAGE]->(p:Page)
            OPTIONAL MATCH (p)-[:CONTAINS_TABLE]->(t:Table)
            OPTIONAL MATCH (t)-[:HAS_CELL]->(c:Cell)
            OPTIONAL MATCH (p)-[:CONTAINS_SECTION]->(s:Section)
            RETURN d.filename AS filename,
                   count(DISTINCT p) AS page_count,
                   count(DISTINCT t) AS table_count,
                   count(DISTINCT c) AS cell_count,
                   count(DISTINCT s) AS section_count
        """, {"process_id": process_id})
        return result or {}


# Singleton instance
_neo4j_service: Optional[Neo4jService] = None


def get_neo4j_service() -> Neo4jService:
    """Get or create the Neo4j service singleton"""
    global _neo4j_service
    if _neo4j_service is None:
        _neo4j_service = Neo4jService()
    return _neo4j_service


# For backward compatibility
def get_neo4j_connection() -> Neo4jService:
    """Alias for get_neo4j_service()"""
    return get_neo4j_service()
