"""
Reference Extractor for Phase 4 - Multi-Agent RAG Orchestration

This module extracts bounding box (bbox) references from cell_grounding
data for PDF highlighting. When the answer includes [cell:X-Y] references,
this module looks up the corresponding bbox coordinates.

The extracted references are used by the frontend PDF viewer (Phase 5)
to highlight the relevant cells/lines on the PDF.
"""

import json
import logging
import re
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ocr-chatbot.reference_extractor")


def extract_cell_ids_from_answer(answer: str) -> List[str]:
    """
    Extract all grounding IDs from answer text (both cells and lines).

    Supports formats:
    - Cell references: [cell:CHUNK:CELL_ID] e.g., [cell:23:2-4] -> "23:2-4"
    - Line references: [line:CHUNK:LINE_ID] e.g., [line:5:abc-123] -> "5:abc-123"
    - Old format: [cell:ROW-COL] e.g., [cell:2-4] -> "2-4" (backward compatibility)

    Args:
        answer: Answer text containing [cell:...] or [line:...] references

    Returns:
        List of grounding IDs (e.g., ["23:2-4", "5:abc-123"])
    """
    all_ids = []

    # Extract cell references: [cell:CHUNK:CELL_ID]
    # CELL_ID can be row-col format (2-4) or UUID format
    cell_pattern = r'\[cell:([^\]]+)\]'
    cell_ids = re.findall(cell_pattern, answer)
    all_ids.extend(cell_ids)

    # Extract line references: [line:CHUNK:LINE_ID]
    line_pattern = r'\[line:([^\]]+)\]'
    line_ids = re.findall(line_pattern, answer)
    all_ids.extend(line_ids)

    # Normalize IDs - remove any "line:" or "cell:" prefix that might have been included
    # The grounding map uses format "CHUNK:ID" without the type prefix
    normalized_ids = []
    for id_str in all_ids:
        # Remove "line:" or "cell:" prefix if present
        if id_str.startswith('line:'):
            id_str = id_str[5:]  # Remove "line:"
        elif id_str.startswith('cell:'):
            id_str = id_str[5:]  # Remove "cell:"
        normalized_ids.append(id_str)

    return list(set(normalized_ids))  # Remove duplicates


def build_grounding_map(chunks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Build a complete map of cell_id -> grounding data from all chunks.

    Uses composite keys (chunk_index:cell_id) for unique identification.
    Also maintains old-format keys for backward compatibility.

    Args:
        chunks: List of chunk dictionaries

    Returns:
        Dict mapping cell_id to {bbox, text, row, col, page, chunk_index}
        Keys are in format "chunk_index:row-col" (e.g., "23:2-4")
    """
    grounding_map = {}

    for chunk in chunks:
        page = chunk.get('page', 1)
        chunk_index = chunk.get('chunk_index', 0)

        # Handle table chunks with cell_grounding
        if chunk.get('cell_grounding'):
            try:
                cell_grounding = (
                    json.loads(chunk['cell_grounding'])
                    if isinstance(chunk['cell_grounding'], str)
                    else chunk['cell_grounding']
                )

                for cell_id, data in cell_grounding.items():
                    # Create composite key: chunk_index:cell_id (e.g., "23:2-4")
                    composite_key = f"{chunk_index}:{cell_id}"

                    grounding_map[composite_key] = {
                        'bbox': data.get('bbox', {}),
                        'text': data.get('text', ''),
                        'row': data.get('row'),
                        'col': data.get('col'),
                        'row_span': data.get('row_span', 1),
                        'col_span': data.get('col_span', 1),
                        'page': page,
                        'chunk_index': chunk_index,
                        'type': 'cell'
                    }

                    # Also add old-format key for backward compatibility
                    # But only if: (1) key doesn't exist, OR (2) new entry has text but old is empty
                    if cell_id not in grounding_map:
                        grounding_map[cell_id] = grounding_map[composite_key]
                    elif data.get('text') and not grounding_map[cell_id].get('text'):
                        # New entry has text but existing one is empty - prefer the one with text
                        grounding_map[cell_id] = grounding_map[composite_key]

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse cell_grounding: {e}")

        # Handle text chunks with line_grounding
        if chunk.get('line_grounding'):
            try:
                line_grounding = (
                    json.loads(chunk['line_grounding'])
                    if isinstance(chunk['line_grounding'], str)
                    else chunk['line_grounding']
                )

                for line_id, data in line_grounding.items():
                    # Create composite key for lines too
                    composite_key = f"{chunk_index}:{line_id}"

                    grounding_map[composite_key] = {
                        'bbox': data.get('bbox', {}),
                        'text': data.get('text', ''),
                        'page': page,
                        'chunk_index': chunk_index,
                        'type': 'line'
                    }

                    # Also add old-format key
                    if line_id not in grounding_map:
                        grounding_map[line_id] = grounding_map[composite_key]

            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse line_grounding: {e}")

    return grounding_map


def extract_references(
    answer_data: Dict[str, Any],
    chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Extract bbox references from cell_ids for PDF highlighting.

    Supports both new format (chunk_index:row-col) and old format (row-col).

    Args:
        answer_data: Answer dict with 'answer' and 'cell_ids' keys
        chunks: List of chunk dictionaries with grounding data

    Returns:
        List of reference dicts with page, bbox, cell_id, text, row, col, chunk_index
    """
    references = []

    # Get cell_ids from answer_data or extract from answer text
    cell_ids = answer_data.get('cell_ids', [])

    if not cell_ids:
        # Try to extract from answer text
        answer_text = answer_data.get('answer', '')
        cell_ids = extract_cell_ids_from_answer(answer_text)

    if not cell_ids:
        logger.debug("No cell_ids found in answer")
        return references

    # Normalize cell_ids - remove "line:" or "cell:" prefix if LLM included it
    # Grounding map uses format "CHUNK:ID" without type prefix
    normalized_ids = []
    for cid in cell_ids:
        if isinstance(cid, str):
            if cid.startswith('line:'):
                cid = cid[5:]
            elif cid.startswith('cell:'):
                cid = cid[5:]
        normalized_ids.append(cid)
    cell_ids = normalized_ids

    # Build complete grounding map (with composite keys)
    grounding_map = build_grounding_map(chunks)

    # Log available chunk indices for debugging
    chunk_indices = set()
    for chunk in chunks:
        chunk_indices.add(chunk.get('chunk_index', 'N/A'))
    logger.info(f"Building grounding map from {len(chunks)} chunks with indices: {sorted(chunk_indices)}")
    logger.info(f"Looking for cell_ids: {cell_ids}")
    logger.info(f"Grounding map has {len(grounding_map)} keys, sample: {list(grounding_map.keys())[:10]}")

    # Look up each cell_id
    for cell_id in cell_ids:
        if cell_id in grounding_map:
            data = grounding_map[cell_id]
            references.append({
                'page': data.get('page', 1),
                'bbox': data.get('bbox', {}),
                'cell_id': cell_id,
                'text': data.get('text', ''),
                'row': data.get('row'),
                'col': data.get('col'),
                'chunk_index': data.get('chunk_index'),
                'type': data.get('type', 'cell')
            })
            logger.info(f"Found reference for cell {cell_id}: page {data.get('page')}, bbox={data.get('bbox')}, text='{data.get('text', '')[:30]}'")
        else:
            logger.warning(f"Cell ID {cell_id} NOT FOUND in grounding map. Available keys sample: {list(grounding_map.keys())[:20]}")

    return references


def lookup_by_row_col(
    row: int,
    col: int,
    chunks: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find a cell by row/column position in cell_grounding.

    Args:
        row: Target row number
        col: Target column number
        chunks: List of chunk dictionaries

    Returns:
        Reference dict if found, None otherwise
    """
    grounding_map = build_grounding_map(chunks)

    for cell_id, data in grounding_map.items():
        if data.get('row') == row and data.get('col') == col:
            return {
                'found': True,
                'page': data.get('page', 1),
                'bbox': data.get('bbox', {}),
                'cell_id': cell_id,
                'text': data.get('text', ''),
                'row': row,
                'col': col
            }

    return {
        'found': False,
        'message': f"No cell found at row {row}, column {col}"
    }


def get_chunk_bbox(chunk: Dict[str, Any]) -> Dict[str, float]:
    """
    Get the bounding box for an entire chunk.

    Args:
        chunk: Chunk dictionary

    Returns:
        Dict with left, top, width, height
    """
    return {
        'left': chunk.get('bbox_left', 0),
        'top': chunk.get('bbox_top', 0),
        'width': chunk.get('bbox_right', 0) - chunk.get('bbox_left', 0),
        'height': chunk.get('bbox_bottom', 0) - chunk.get('bbox_top', 0)
    }


def format_references_for_frontend(references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format references for frontend PDF viewer consumption.

    Ensures all required fields are present and bbox is properly structured.

    Args:
        references: Raw reference list

    Returns:
        Formatted reference list for frontend
    """
    formatted = []

    for ref in references:
        bbox = ref.get('bbox', {})

        # Ensure bbox has all required fields
        formatted_bbox = {
            'left': float(bbox.get('left', 0)),
            'top': float(bbox.get('top', 0)),
            'width': float(bbox.get('width', 0)),
            'height': float(bbox.get('height', 0))
        }

        # Calculate right and bottom for convenience
        formatted_bbox['right'] = formatted_bbox['left'] + formatted_bbox['width']
        formatted_bbox['bottom'] = formatted_bbox['top'] + formatted_bbox['height']

        formatted.append({
            'page': ref.get('page', 1),
            'bbox': formatted_bbox,
            'cell_id': ref.get('cell_id', ''),
            'text': ref.get('text', ''),
            'row': ref.get('row'),
            'col': ref.get('col'),
            'type': ref.get('type', 'cell')
        })

    return formatted


def merge_overlapping_references(
    references: List[Dict[str, Any]],
    overlap_threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Merge references that significantly overlap on the same page.

    This reduces visual clutter when multiple adjacent cells are highlighted.

    Args:
        references: List of references
        overlap_threshold: Minimum overlap ratio to merge (0-1)

    Returns:
        Merged reference list
    """
    if len(references) <= 1:
        return references

    # Group by page
    by_page = {}
    for ref in references:
        page = ref.get('page', 1)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(ref)

    merged = []

    for page, page_refs in by_page.items():
        # For now, just return all references without merging
        # Can implement merging logic later if needed
        merged.extend(page_refs)

    return merged


def build_response_with_references(
    answer_data: Dict[str, Any],
    chunks: List[Dict[str, Any]],
    query_type: str = "vector_only"
) -> Dict[str, Any]:
    """
    Build complete response with answer and formatted references.

    Args:
        answer_data: Answer dict from synthesizer
        chunks: Retrieved chunks
        query_type: Type of query (vector_only, structural, extraction)

    Returns:
        Complete response dict for API
    """
    # Extract references from cell_ids
    references = extract_references(answer_data, chunks)

    # If no cell_ids but we have table chunks, use chunk-level bbox
    # This handles "view table" requests where we show the whole table layout
    cell_ids = answer_data.get('cell_ids', [])
    table_chunk_index = answer_data.get('table_chunk_index')

    if not cell_ids and not references:
        # Check if LLM specified a specific table chunk to reference
        if table_chunk_index is not None:
            # LLM identified a specific table - only use that table's bbox
            for chunk in chunks:
                if chunk.get('chunk_type') == 'table' and chunk.get('chunk_index') == table_chunk_index:
                    chunk_bbox = get_chunk_bbox(chunk)
                    if chunk_bbox.get('width', 0) > 0 and chunk_bbox.get('height', 0) > 0:
                        references.append({
                            'page': chunk.get('page', 1),
                            'bbox': chunk_bbox,
                            'cell_id': f"table_{chunk.get('chunk_index', 0)}",
                            'text': 'Table',
                            'type': 'table_layout'
                        })
                        logger.info(f"Using specific table chunk {table_chunk_index} bbox (LLM specified)")
                    break
        else:
            # No specific table identified - use all table chunks
            # This handles "show all tables" or general requests
            for chunk in chunks:
                if chunk.get('chunk_type') == 'table':
                    chunk_bbox = get_chunk_bbox(chunk)
                    # Only add if bbox has valid dimensions
                    if chunk_bbox.get('width', 0) > 0 and chunk_bbox.get('height', 0) > 0:
                        references.append({
                            'page': chunk.get('page', 1),
                            'bbox': chunk_bbox,
                            'cell_id': f"table_{chunk.get('chunk_index', 0)}",
                            'text': 'Table',
                            'type': 'table_layout'
                        })
            logger.info(f"No cell_ids or specific table, using {len(references)} chunk-level table bbox(es)")

    # Format for frontend
    formatted_refs = format_references_for_frontend(references)

    return {
        'answer': answer_data.get('answer', ''),
        'references': formatted_refs,
        'confidence': answer_data.get('confidence', 0.5),
        'query_type': query_type,
        'cell_ids': answer_data.get('cell_ids', []),
        'low_confidence': answer_data.get('low_confidence', False),
        'error': answer_data.get('error', False)
    }
