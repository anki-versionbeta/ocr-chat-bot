"""
Chunk Transformer for Phase 3 - Layout-Aware Chunking

This module transforms parsed Textract blocks into chunks suitable for
Weaviate indexing. It creates two types of chunks:

1. TABLE chunks - with cell_grounding for precise cell-level highlighting
2. TEXT chunks - with line_grounding for line-level highlighting

Each chunk includes:
- content: The actual text content
- cell_grounding or line_grounding: Maps IDs to bbox + text for highlighting
- markdown: HTML-like markup with IDs for Claude to reference
- bbox coordinates: For page-level positioning
- layout_type: Original Textract layout classification
"""

import uuid
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def build_table_chunk(
    table_data: Dict[str, Any],
    document_id: str,
    process_id: str,
    chunk_index: int,
    filename: str = "",
    document_summary: str = "",
    keywords: str = ""
) -> Dict[str, Any]:
    """
    Build a TABLE chunk from parsed table data.

    Args:
        table_data: Parsed table from TextractParser.parse_table_block()
        document_id: UUID of the document
        process_id: UUID of the processing session
        chunk_index: Index of this chunk in the document
        filename: Original PDF filename
        document_summary: Summary of the document
        keywords: Extracted keywords

    Returns:
        Dict matching Weaviate DocumentChunk schema:
        {
            "document_id": str,
            "process_id": str,
            "chunk_id": str,
            "chunk_type": "table",
            "chunk_index": int,
            "page": int,
            "content": str,
            "cell_grounding": Dict[str, Dict],  # {cell_id: {bbox, text, row, col}}
            "line_grounding": None,
            "markdown": str,  # HTML table with cell IDs
            "bbox_left": float,
            "bbox_top": float,
            "bbox_right": float,
            "bbox_bottom": float,
            "layout_type": "TABLE",
            "filename": str,
            "document_summary": str,
            "keywords": str,
            "created_at": str
        }
    """
    chunk_id = f"{document_id}_chunk_{chunk_index}"
    page = table_data.get('page', 1)
    bbox = table_data.get('bbox', {})
    cells = table_data.get('cells', {})
    rows = table_data.get('rows', {})
    content_text = table_data.get('content_text', '')

    # Build cell_grounding map
    cell_grounding = {}
    for cell_id, cell_data in cells.items():
        cell_grounding[cell_id] = {
            'bbox': cell_data['bbox'],
            'text': cell_data['text'],
            'row': cell_data['row'],
            'col': cell_data['col'],
            'row_span': cell_data.get('row_span', 1),
            'col_span': cell_data.get('col_span', 1)
        }

    # Build markdown table with cell IDs
    markdown_lines = [f"<table id='{page}-t{chunk_index}'>"]

    for row_idx in sorted(rows.keys()):
        markdown_lines.append("  <tr>")
        row_cells = rows[row_idx]

        # Sort cells by column
        sorted_cells = sorted(row_cells, key=lambda cid: cells[cid]['col'])

        for cell_id in sorted_cells:
            cell_text = cells[cell_id]['text']
            # Escape HTML in cell text
            cell_text_escaped = cell_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Build span attributes if cell spans multiple rows/cols
            span_attrs = ''
            row_span = cells[cell_id].get('row_span', 1)
            col_span = cells[cell_id].get('col_span', 1)
            if row_span > 1:
                span_attrs += f' rowspan="{row_span}"'
            if col_span > 1:
                span_attrs += f' colspan="{col_span}"'

            markdown_lines.append(f"    <td id='{cell_id}'{span_attrs}>{cell_text_escaped}</td>")

        markdown_lines.append("  </tr>")

    markdown_lines.append("</table>")
    markdown = '\n'.join(markdown_lines)

    # Calculate bbox_right and bbox_bottom
    bbox_left = bbox.get('left', 0)
    bbox_top = bbox.get('top', 0)
    bbox_width = bbox.get('width', 0)
    bbox_height = bbox.get('height', 0)
    bbox_right = bbox_left + bbox_width
    bbox_bottom = bbox_top + bbox_height

    return {
        "document_id": document_id,
        "process_id": process_id,
        "chunk_id": chunk_id,
        "chunk_type": "table",
        "chunk_index": chunk_index,
        "page": page,
        "content": content_text,
        "cell_grounding": json.dumps(cell_grounding),  # Serialize for Weaviate text field
        "line_grounding": None,
        "markdown": markdown,
        "bbox_left": bbox_left,
        "bbox_top": bbox_top,
        "bbox_right": bbox_right,
        "bbox_bottom": bbox_bottom,
        "layout_type": "TABLE",
        "filename": filename,
        "document_summary": document_summary,
        "keywords": keywords,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }


def build_text_chunk(
    layout_data: Dict[str, Any],
    document_id: str,
    process_id: str,
    chunk_index: int,
    filename: str = "",
    document_summary: str = "",
    keywords: str = ""
) -> Dict[str, Any]:
    """
    Build a TEXT chunk from parsed layout data.

    Args:
        layout_data: Parsed layout from TextractParser.parse_layout_block()
        document_id: UUID of the document
        process_id: UUID of the processing session
        chunk_index: Index of this chunk in the document
        filename: Original PDF filename
        document_summary: Summary of the document
        keywords: Extracted keywords

    Returns:
        Dict matching Weaviate DocumentChunk schema:
        {
            "document_id": str,
            "process_id": str,
            "chunk_id": str,
            "chunk_type": "text",
            "chunk_index": int,
            "page": int,
            "content": str,
            "cell_grounding": None,
            "line_grounding": Dict[str, Dict],  # {line_id: {bbox, text}}
            "markdown": str,  # Spans with line IDs
            "bbox_left": float,
            "bbox_top": float,
            "bbox_right": float,
            "bbox_bottom": float,
            "layout_type": str,  # e.g., "LAYOUT_TEXT", "LAYOUT_TITLE"
            "filename": str,
            "document_summary": str,
            "keywords": str,
            "created_at": str
        }
    """
    chunk_id = f"{document_id}_chunk_{chunk_index}"
    page = layout_data.get('page', 1)
    layout_type = layout_data.get('layout_type', 'LAYOUT_TEXT')
    bbox = layout_data.get('bbox', {})
    lines = layout_data.get('lines', {})
    content_text = layout_data.get('content_text', '')

    # Build line_grounding map
    line_grounding = {}
    for line_id, line_data in lines.items():
        line_grounding[line_id] = {
            'bbox': line_data['bbox'],
            'text': line_data['text']
        }

    # Build markdown with line IDs
    markdown_lines = []
    for line_id, line_data in lines.items():
        line_text = line_data['text']
        # Escape HTML in line text
        line_text_escaped = line_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        markdown_lines.append(f"<span id='{line_id}'>{line_text_escaped}</span>")

    # If no lines were found, use content_text directly
    if not markdown_lines and content_text:
        content_escaped = content_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        markdown_lines.append(f"<p>{content_escaped}</p>")

    markdown = '\n'.join(markdown_lines)

    # Calculate bbox_right and bbox_bottom
    bbox_left = bbox.get('left', 0)
    bbox_top = bbox.get('top', 0)
    bbox_width = bbox.get('width', 0)
    bbox_height = bbox.get('height', 0)
    bbox_right = bbox_left + bbox_width
    bbox_bottom = bbox_top + bbox_height

    # Clean layout_type (remove LAYOUT_ prefix for storage)
    clean_layout_type = layout_type.replace('LAYOUT_', '') if layout_type.startswith('LAYOUT_') else layout_type

    return {
        "document_id": document_id,
        "process_id": process_id,
        "chunk_id": chunk_id,
        "chunk_type": "text",
        "chunk_index": chunk_index,
        "page": page,
        "content": content_text,
        "cell_grounding": None,
        "line_grounding": json.dumps(line_grounding),  # Serialize for Weaviate text field
        "markdown": markdown,
        "bbox_left": bbox_left,
        "bbox_top": bbox_top,
        "bbox_right": bbox_right,
        "bbox_bottom": bbox_bottom,
        "layout_type": clean_layout_type,
        "filename": filename,
        "document_summary": document_summary,
        "keywords": keywords,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }


def chunk_textract_blocks(
    tables: List[Dict[str, Any]],
    layouts: List[Dict[str, Any]],
    document_id: str,
    process_id: str,
    filename: str = "",
    document_summary: str = "",
    keywords: str = ""
) -> List[Dict[str, Any]]:
    """
    Transform parsed Textract blocks into chunks for Weaviate indexing.

    This is the main function that replaces RecursiveCharacterTextSplitter.
    Instead of arbitrary text splitting, it creates layout-aware chunks
    with precise grounding information for PDF highlighting.

    Args:
        tables: List of parsed table data from TextractParser
        layouts: List of parsed layout data from TextractParser
        document_id: UUID of the document
        process_id: UUID of the processing session
        filename: Original PDF filename
        document_summary: Summary of the document
        keywords: Extracted keywords

    Returns:
        List of chunks ready for Weaviate indexing
    """
    chunks = []
    chunk_index = 0

    # Sort all blocks by page and vertical position for proper ordering
    all_blocks = []

    for table in tables:
        all_blocks.append({
            'type': 'table',
            'data': table,
            'page': table.get('page', 1),
            'top': table.get('bbox', {}).get('top', 0)
        })

    for layout in layouts:
        all_blocks.append({
            'type': 'layout',
            'data': layout,
            'page': layout.get('page', 1),
            'top': layout.get('bbox', {}).get('top', 0)
        })

    # Sort by page first, then by vertical position
    all_blocks.sort(key=lambda x: (x['page'], x['top']))

    # Build chunks in order
    for block in all_blocks:
        if block['type'] == 'table':
            chunk = build_table_chunk(
                table_data=block['data'],
                document_id=document_id,
                process_id=process_id,
                chunk_index=chunk_index,
                filename=filename,
                document_summary=document_summary,
                keywords=keywords
            )
        else:
            chunk = build_text_chunk(
                layout_data=block['data'],
                document_id=document_id,
                process_id=process_id,
                chunk_index=chunk_index,
                filename=filename,
                document_summary=document_summary,
                keywords=keywords
            )

        # Only add chunks with content
        if chunk['content'].strip():
            chunks.append(chunk)
            chunk_index += 1

    logger.info(f"Created {len(chunks)} chunks from {len(tables)} tables and {len(layouts)} layouts")

    return chunks


def prepare_chunk_for_embedding(chunk: Dict[str, Any]) -> str:
    """
    Prepare chunk content for embedding generation.

    Creates a text representation suitable for semantic search,
    combining content with metadata for better retrieval.

    Args:
        chunk: A chunk dict from chunk_textract_blocks

    Returns:
        Text string optimized for embedding
    """
    parts = []

    # Add layout type context
    layout_type = chunk.get('layout_type', '')
    if layout_type:
        parts.append(f"[{layout_type}]")

    # Add main content
    content = chunk.get('content', '')
    if content:
        parts.append(content)

    # Add filename context
    filename = chunk.get('filename', '')
    if filename:
        parts.append(f"Source: {filename}")

    return ' '.join(parts)


def get_chunk_statistics(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get statistics about generated chunks.

    Args:
        chunks: List of chunks from chunk_textract_blocks

    Returns:
        Dict with chunk statistics
    """
    stats = {
        'total_chunks': len(chunks),
        'table_chunks': 0,
        'text_chunks': 0,
        'by_page': {},
        'by_layout_type': {},
        'avg_content_length': 0
    }

    total_length = 0

    for chunk in chunks:
        chunk_type = chunk.get('chunk_type', 'unknown')
        page = chunk.get('page', 0)
        layout_type = chunk.get('layout_type', 'unknown')
        content_length = len(chunk.get('content', ''))

        if chunk_type == 'table':
            stats['table_chunks'] += 1
        else:
            stats['text_chunks'] += 1

        stats['by_page'][page] = stats['by_page'].get(page, 0) + 1
        stats['by_layout_type'][layout_type] = stats['by_layout_type'].get(layout_type, 0) + 1

        total_length += content_length

    if chunks:
        stats['avg_content_length'] = total_length // len(chunks)

    return stats


if __name__ == '__main__':
    # Test with sample data
    from textract_parser import TextractParser
    import sys

    if len(sys.argv) > 1:
        blocks_path = sys.argv[1]
        parser = TextractParser(blocks_json_path=blocks_path)

        tables = parser.get_all_tables()
        layouts = parser.get_all_layouts()

        document_id = str(uuid.uuid4())
        process_id = str(uuid.uuid4())

        chunks = chunk_textract_blocks(
            tables=tables,
            layouts=layouts,
            document_id=document_id,
            process_id=process_id,
            filename="test_document.pdf",
            document_summary="Test COA document",
            keywords="COA, test, batch"
        )

        print(f"\n=== Generated {len(chunks)} Chunks ===")

        stats = get_chunk_statistics(chunks)
        print(f"\nStatistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n=== Sample Chunks ===")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\nChunk {i+1}:")
            print(f"  Type: {chunk['chunk_type']}")
            print(f"  Layout: {chunk['layout_type']}")
            print(f"  Page: {chunk['page']}")
            print(f"  Content preview: {chunk['content'][:100]}...")
            if chunk['chunk_type'] == 'table':
                grounding = json.loads(chunk['cell_grounding']) if chunk['cell_grounding'] else {}
                print(f"  Cells with grounding: {len(grounding)}")
            else:
                grounding = json.loads(chunk['line_grounding']) if chunk['line_grounding'] else {}
                print(f"  Lines with grounding: {len(grounding)}")
    else:
        print("Usage: python chunk_transformer.py <path_to_blocks.json>")
