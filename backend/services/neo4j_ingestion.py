"""
Neo4j Ingestion Service - BATCH UNWIND approach for fast indexing

Uses batch UNWIND queries instead of individual node creation.
This is 100x faster for large documents.

Created: February 11, 2026
"""

import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

from .neo4j_service import get_neo4j_service, Neo4jService

logger = logging.getLogger("ocr-chatbot.neo4j_ingestion")

# Batch sizes
BATCH_SIZE = 2000


class Neo4jIngestionService:
    """
    Fast Neo4j ingestion using batch UNWIND queries.
    """

    def __init__(self, neo4j_service: Optional[Neo4jService] = None):
        self.neo4j = neo4j_service or get_neo4j_service()

    def index_document(
        self,
        process_id: str,
        blocks: List[Dict],
        filename: str,
        document_type: str = "COA",
        username: str = "system"
    ) -> Dict[str, Any]:
        """
        Index a complete Textract document into Neo4j using batch queries.
        """
        if not self.neo4j.is_connected:
            logger.warning("Neo4j not connected, skipping ingestion")
            return {"success": False, "error": "Neo4j not connected"}

        logger.info(f"[Neo4j] Starting BATCH ingestion for {filename} (process_id: {process_id})")
        start_time = datetime.now()

        try:
            # Build block lookup
            block_by_id = {b.get('Id'): b for b in blocks if b.get('Id')}

            # Detect pages
            pages = set()
            for b in blocks:
                pn = b.get('Page')
                if pn is not None:
                    pages.add(int(pn))
            if not pages:
                pages = {1}
            page_count = max(pages)

            logger.info(f"[Neo4j] Document has {page_count} pages, {len(blocks)} blocks")

            # Prepare all data rows
            page_rows = [{"docId": process_id, "pageNumber": pn} for pn in sorted(pages)]

            # Tables and Cells
            cell_to_table = {}
            for t in blocks:
                if t.get('BlockType') == 'TABLE' and t.get('Id'):
                    tid = t['Id']
                    for rel in t.get('Relationships', []):
                        if rel.get('Type') == 'CHILD':
                            for cid in rel.get('Ids', []):
                                cb = block_by_id.get(cid)
                                if cb and cb.get('BlockType') == 'CELL':
                                    cell_to_table[cid] = tid

            table_rows = []
            for t in blocks:
                if t.get('BlockType') == 'TABLE' and t.get('Id'):
                    pn = int(t.get('Page', 1) or 1)
                    bbox = t.get('Geometry', {}).get('BoundingBox', {})
                    table_rows.append({
                        "docId": process_id,
                        "tableId": t['Id'],
                        "pageNumber": pn,
                        "bboxLeft": float(bbox.get('Left', 0)),
                        "bboxTop": float(bbox.get('Top', 0)),
                        "bboxWidth": float(bbox.get('Width', 0)),
                        "bboxHeight": float(bbox.get('Height', 0)),
                    })

            cell_rows = []
            for c in blocks:
                if c.get('BlockType') == 'CELL' and c.get('Id'):
                    cid = c['Id']
                    tid = cell_to_table.get(cid)
                    if not tid:
                        continue
                    pn = int(c.get('Page', 1) or 1)
                    text = self._get_text_from_children(c, block_by_id)
                    bbox = c.get('Geometry', {}).get('BoundingBox', {})
                    cell_rows.append({
                        "docId": process_id,
                        "tableId": tid,
                        "cellId": cid,
                        "pageNumber": pn,
                        "row": int(c.get('RowIndex', 0) or 0),
                        "col": int(c.get('ColumnIndex', 0) or 0),
                        "rowSpan": int(c.get('RowSpan', 1) or 1),
                        "colSpan": int(c.get('ColumnSpan', 1) or 1),
                        "text": text,
                        "bboxLeft": float(bbox.get('Left', 0)),
                        "bboxTop": float(bbox.get('Top', 0)),
                        "bboxWidth": float(bbox.get('Width', 0)),
                        "bboxHeight": float(bbox.get('Height', 0)),
                    })

            # Lines/Spans
            line_rows = []
            for b in blocks:
                if b.get('BlockType') == 'LINE' and b.get('Id'):
                    pn = int(b.get('Page', 1) or 1)
                    bbox = b.get('Geometry', {}).get('BoundingBox', {})
                    line_rows.append({
                        "docId": process_id,
                        "lineId": b['Id'],
                        "pageNumber": pn,
                        "text": b.get('Text', ''),
                        "bboxLeft": float(bbox.get('Left', 0)),
                        "bboxTop": float(bbox.get('Top', 0)),
                        "bboxWidth": float(bbox.get('Width', 0)),
                        "bboxHeight": float(bbox.get('Height', 0)),
                    })

            # Execute batch queries
            logger.info(f"[Neo4j] Inserting: {len(page_rows)} pages, {len(table_rows)} tables, {len(cell_rows)} cells, {len(line_rows)} lines")

            # 1. Create Document
            self.neo4j.query("""
                MERGE (d:Document {process_id: $docId})
                SET d.filename = $filename,
                    d.document_type = $docType,
                    d.username = $username,
                    d.page_count = $pageCount,
                    d.created_at = datetime()
            """, {
                "docId": process_id,
                "filename": filename,
                "docType": document_type,
                "username": username,
                "pageCount": page_count
            })

            # 2. Batch create Pages
            self._batch_query("""
                UNWIND $rows AS r
                MERGE (p:Page {doc_id: r.docId, page_num: r.pageNumber})
                WITH p, r
                MATCH (d:Document {process_id: r.docId})
                MERGE (d)-[:HAS_PAGE]->(p)
            """, page_rows)
            logger.info(f"[Neo4j] ✓ Pages: {len(page_rows)}")

            # 3. Batch create Tables
            self._batch_query("""
                UNWIND $rows AS r
                MATCH (p:Page {doc_id: r.docId, page_num: r.pageNumber})
                MERGE (t:Table {doc_id: r.docId, table_id: r.tableId})
                SET t.page_num = r.pageNumber,
                    t.bbox_left = r.bboxLeft,
                    t.bbox_top = r.bboxTop,
                    t.bbox_width = r.bboxWidth,
                    t.bbox_height = r.bboxHeight
                MERGE (p)-[:CONTAINS_TABLE]->(t)
            """, table_rows)
            logger.info(f"[Neo4j] ✓ Tables: {len(table_rows)}")

            # 4. Batch create Cells
            self._batch_query("""
                UNWIND $rows AS r
                MATCH (t:Table {doc_id: r.docId, table_id: r.tableId})
                MERGE (c:Cell {doc_id: r.docId, cell_id: r.cellId})
                SET c.page_num = r.pageNumber,
                    c.row_index = r.row,
                    c.col_index = r.col,
                    c.row_span = r.rowSpan,
                    c.col_span = r.colSpan,
                    c.text = r.text,
                    c.bbox_left = r.bboxLeft,
                    c.bbox_top = r.bboxTop,
                    c.bbox_width = r.bboxWidth,
                    c.bbox_height = r.bboxHeight
                MERGE (t)-[:HAS_CELL]->(c)
            """, cell_rows)
            logger.info(f"[Neo4j] ✓ Cells: {len(cell_rows)}")

            # 5. Batch create Lines
            self._batch_query("""
                UNWIND $rows AS r
                MATCH (p:Page {doc_id: r.docId, page_num: r.pageNumber})
                MERGE (l:Line {doc_id: r.docId, line_id: r.lineId})
                SET l.page_num = r.pageNumber,
                    l.text = r.text,
                    l.bbox_left = r.bboxLeft,
                    l.bbox_top = r.bboxTop,
                    l.bbox_width = r.bboxWidth,
                    l.bbox_height = r.bboxHeight
                MERGE (p)-[:CONTAINS_LINE]->(l)
            """, line_rows)
            logger.info(f"[Neo4j] ✓ Lines: {len(line_rows)}")

            # 6. Create SAME_ROW relationships (batch)
            self.neo4j.query("""
                MATCH (t:Table {doc_id: $docId})-[:HAS_CELL]->(c1:Cell)
                MATCH (t)-[:HAS_CELL]->(c2:Cell)
                WHERE c1.row_index = c2.row_index AND c1.col_index < c2.col_index
                MERGE (c1)-[:SAME_ROW]->(c2)
            """, {"docId": process_id})

            # 7. Create SAME_COL relationships (batch)
            self.neo4j.query("""
                MATCH (t:Table {doc_id: $docId})-[:HAS_CELL]->(c1:Cell)
                MATCH (t)-[:HAS_CELL]->(c2:Cell)
                WHERE c1.col_index = c2.col_index AND c1.row_index < c2.row_index
                MERGE (c1)-[:SAME_COL]->(c2)
            """, {"docId": process_id})
            logger.info(f"[Neo4j] ✓ SAME_ROW/SAME_COL relationships created")

            elapsed = (datetime.now() - start_time).total_seconds()
            stats = {
                "pages": len(page_rows),
                "tables": len(table_rows),
                "cells": len(cell_rows),
                "lines": len(line_rows),
            }

            logger.info(f"[Neo4j] ✅ BATCH ingestion complete in {elapsed:.2f}s")
            logger.info(f"[Neo4j] Stats: {stats}")

            return {
                "success": True,
                "process_id": process_id,
                "filename": filename,
                "stats": stats,
                "elapsed_seconds": elapsed
            }

        except Exception as e:
            logger.error(f"[Neo4j] ❌ Ingestion failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "process_id": process_id
            }

    def _batch_query(self, query: str, rows: List[Dict], batch_size: int = BATCH_SIZE):
        """Execute query in batches using UNWIND."""
        if not rows:
            return
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            self.neo4j.query(query, {"rows": batch})

    def _get_text_from_children(self, block: Dict, block_by_id: Dict) -> str:
        """Extract text from WORD children of a block."""
        words = []
        for rel in block.get('Relationships', []):
            if rel.get('Type') == 'CHILD':
                for cid in rel.get('Ids', []):
                    cb = block_by_id.get(cid)
                    if not cb:
                        continue
                    bt = cb.get('BlockType')
                    if bt == 'WORD':
                        t = cb.get('Text')
                        if t:
                            words.append(t)
                    elif bt == 'SELECTION_ELEMENT':
                        status = cb.get('SelectionStatus')
                        if status:
                            words.append(f"[{status}]")
        return ' '.join(words).strip()

    def delete_document(self, process_id: str) -> bool:
        """Delete a document and all its related nodes from Neo4j."""
        try:
            self.neo4j.query("""
                MATCH (d:Document {process_id: $process_id})
                OPTIONAL MATCH (d)-[*]->(n)
                DETACH DELETE d, n
            """, {"process_id": process_id})
            logger.info(f"[Neo4j] Deleted document: {process_id}")
            return True
        except Exception as e:
            logger.error(f"[Neo4j] Failed to delete document {process_id}: {e}")
            return False


# Singleton instance
_ingestion_service: Optional[Neo4jIngestionService] = None


def get_neo4j_ingestion_service() -> Neo4jIngestionService:
    """Get or create the Neo4j ingestion service singleton."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = Neo4jIngestionService()
    return _ingestion_service


async def index_document_to_neo4j(
    process_id: str,
    blocks_json_path: str,
    filename: str,
    document_type: str = "COA",
    username: str = "system"
) -> Dict[str, Any]:
    """
    Async wrapper to index a document to Neo4j.
    """
    try:
        # Load blocks from file
        with open(blocks_json_path, 'r', encoding='utf-8') as f:
            blocks_data = json.load(f)

        # Handle ALL possible formats
        blocks = []
        if isinstance(blocks_data, dict) and 'Blocks' in blocks_data:
            blocks = blocks_data['Blocks']
        elif isinstance(blocks_data, list):
            if len(blocks_data) > 0 and isinstance(blocks_data[0], dict) and 'Blocks' in blocks_data[0]:
                # List of page objects - MERGE ALL
                for page_obj in blocks_data:
                    blocks.extend(page_obj.get('Blocks', []))
                logger.info(f"[Neo4j] Merged blocks from {len(blocks_data)} page objects, total: {len(blocks)} blocks")
            else:
                blocks = blocks_data

        if not blocks:
            logger.warning(f"[Neo4j] No blocks found in {blocks_json_path}")
            return {"success": False, "error": "No blocks found in file"}

        logger.info(f"[Neo4j] Loaded {len(blocks)} blocks from {blocks_json_path}")

        # Index to Neo4j
        service = get_neo4j_ingestion_service()
        result = service.index_document(
            process_id=process_id,
            blocks=blocks,
            filename=filename,
            document_type=document_type,
            username=username
        )

        return result

    except FileNotFoundError:
        logger.error(f"[Neo4j] Blocks file not found: {blocks_json_path}")
        return {"success": False, "error": f"File not found: {blocks_json_path}"}
    except json.JSONDecodeError as e:
        logger.error(f"[Neo4j] Invalid JSON in blocks file: {e}")
        return {"success": False, "error": f"Invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"[Neo4j] Indexing error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
