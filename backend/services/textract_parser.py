"""
Textract Parser for Phase 3 - Layout-Aware Chunking

This module parses AWS Textract output (blocks.json) and extracts:
1. TABLE blocks with cell relationships and geometry
2. LAYOUT blocks with line relationships and geometry

The parsed data is used by chunk_transformer.py to build grounded chunks.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class TextractParser:
    """
    Parses Textract blocks.json output to extract TABLE and LAYOUT blocks
    with their relationships and geometry information.
    """

    def __init__(self, blocks_json_path: str = None, blocks_data: List[Dict] = None):
        """
        Initialize parser with either a file path or raw blocks data.

        Args:
            blocks_json_path: Path to the _blocks.json file
            blocks_data: Raw list of Textract response pages
        """
        self.blocks_map: Dict[str, Dict] = {}
        self.table_blocks: List[Dict] = []
        self.layout_blocks: List[Dict] = []
        self.line_blocks: List[Dict] = []
        self.cell_blocks: List[Dict] = []
        self.word_blocks: List[Dict] = []

        if blocks_json_path:
            self._load_from_file(blocks_json_path)
        elif blocks_data:
            self._load_from_data(blocks_data)

    def _load_from_file(self, blocks_json_path: str) -> None:
        """Load and parse blocks from a JSON file."""
        logger.info(f"Loading Textract blocks from: {blocks_json_path}")

        with open(blocks_json_path, 'r', encoding='utf-8') as f:
            pages = json.load(f)

        self._load_from_data(pages)

    def _load_from_data(self, pages: List[Dict]) -> None:
        """Load and parse blocks from raw Textract response pages."""
        all_blocks = []
        for page in pages:
            if 'Blocks' in page:
                all_blocks.extend(page['Blocks'])

        logger.info(f"Total blocks loaded: {len(all_blocks)}")

        # Build blocks map and categorize blocks
        for block in all_blocks:
            block_id = block.get('Id')
            block_type = block.get('BlockType', '')

            self.blocks_map[block_id] = block

            if block_type == 'TABLE':
                self.table_blocks.append(block)
            elif block_type.startswith('LAYOUT_'):
                self.layout_blocks.append(block)
            elif block_type == 'LINE':
                self.line_blocks.append(block)
            elif block_type == 'CELL':
                self.cell_blocks.append(block)
            elif block_type == 'WORD':
                self.word_blocks.append(block)

        logger.info(f"Parsed: {len(self.table_blocks)} tables, {len(self.layout_blocks)} layout blocks, "
                   f"{len(self.line_blocks)} lines, {len(self.cell_blocks)} cells")

    def get_block_by_id(self, block_id: str) -> Optional[Dict]:
        """Get a block by its ID."""
        return self.blocks_map.get(block_id)

    def get_child_ids(self, block: Dict) -> List[str]:
        """Get all child IDs from a block's relationships."""
        child_ids = []
        for relationship in block.get('Relationships', []):
            if relationship.get('Type') == 'CHILD':
                child_ids.extend(relationship.get('Ids', []))
        return child_ids

    def get_text_from_block(self, block: Dict) -> str:
        """
        Extract text from a block, recursively getting text from children.
        """
        # If block has direct text, return it
        if 'Text' in block:
            return block['Text']

        # Otherwise, get text from children
        child_ids = self.get_child_ids(block)
        texts = []
        for child_id in child_ids:
            child_block = self.get_block_by_id(child_id)
            if child_block:
                child_text = self.get_text_from_block(child_block)
                if child_text:
                    texts.append(child_text)

        return ' '.join(texts)

    def get_bbox(self, block: Dict) -> Dict[str, float]:
        """
        Extract bounding box from block geometry.
        Returns normalized coordinates (0-1 range): left, top, width, height.

        For Phase 5 highlighting, use directly with canvas:
          ctx.fillRect(left * pageWidth, top * pageHeight, width * pageWidth, height * pageHeight)
        """
        geometry = block.get('Geometry', {})
        bbox = geometry.get('BoundingBox', {})

        return {
            'left': bbox.get('Left', 0),
            'top': bbox.get('Top', 0),
            'width': bbox.get('Width', 0),
            'height': bbox.get('Height', 0)
        }

    def parse_table_block(self, table_block: Dict) -> Dict[str, Any]:
        """
        Parse a TABLE block and extract all cells with their relationships.

        Returns:
            Dict with table metadata and cells:
            {
                'block_id': str,
                'page': int,
                'bbox': {left, top, width, height},
                'cells': {
                    '{page}-{sequence}': {
                        'bbox': {left, top, width, height},
                        'text': str,
                        'row': int,
                        'col': int,
                        'row_span': int,
                        'col_span': int
                    }
                },
                'rows': Dict[int, List[cell_ids]],
                'content_text': str (all cell text joined)
            }
        """
        table_id = table_block.get('Id')
        page = table_block.get('Page', 1)
        bbox = self.get_bbox(table_block)

        cells = {}
        rows = defaultdict(list)
        cell_sequence = 0

        # First, build a map of cell block IDs to their merged cell span info
        # MERGED_CELL blocks contain the actual row_span/col_span for merged cells
        merged_cell_spans = {}  # cell_block_id -> {'row_span': x, 'col_span': y}

        for relationship in table_block.get('Relationships', []):
            if relationship.get('Type') == 'MERGED_CELL':
                for merged_cell_id in relationship.get('Ids', []):
                    merged_block = self.get_block_by_id(merged_cell_id)
                    if merged_block:
                        mc_row_span = merged_block.get('RowSpan', 1)
                        mc_col_span = merged_block.get('ColumnSpan', 1)

                        # Get child cells of this merged cell
                        for mc_rel in merged_block.get('Relationships', []):
                            if mc_rel.get('Type') == 'CHILD':
                                child_cell_ids = mc_rel.get('Ids', [])
                                # Apply span to the first (anchor) cell only
                                if child_cell_ids:
                                    # Find the cell with smallest row/col (anchor cell)
                                    anchor_cell_id = None
                                    anchor_row = float('inf')
                                    anchor_col = float('inf')
                                    for cc_id in child_cell_ids:
                                        cc = self.get_block_by_id(cc_id)
                                        if cc:
                                            cc_row = cc.get('RowIndex', 0)
                                            cc_col = cc.get('ColumnIndex', 0)
                                            if cc_row < anchor_row or (cc_row == anchor_row and cc_col < anchor_col):
                                                anchor_row = cc_row
                                                anchor_col = cc_col
                                                anchor_cell_id = cc_id

                                    if anchor_cell_id:
                                        merged_cell_spans[anchor_cell_id] = {
                                            'row_span': mc_row_span,
                                            'col_span': mc_col_span
                                        }

        # Get all CELL children
        child_ids = self.get_child_ids(table_block)

        for child_id in child_ids:
            child_block = self.get_block_by_id(child_id)
            if child_block and child_block.get('BlockType') == 'CELL':
                cell_sequence += 1
                cell_id = f"{page}-{cell_sequence}"

                row_idx = child_block.get('RowIndex', 0)
                col_idx = child_block.get('ColumnIndex', 0)

                # Check if this cell has merged span info from MERGED_CELL blocks
                if child_id in merged_cell_spans:
                    row_span = merged_cell_spans[child_id]['row_span']
                    col_span = merged_cell_spans[child_id]['col_span']
                else:
                    row_span = child_block.get('RowSpan', 1)
                    col_span = child_block.get('ColumnSpan', 1)

                cell_text = self.get_text_from_block(child_block)
                cell_bbox = self.get_bbox(child_block)

                cells[cell_id] = {
                    'bbox': cell_bbox,
                    'text': cell_text,
                    'row': row_idx,
                    'col': col_idx,
                    'row_span': row_span,
                    'col_span': col_span
                }

                rows[row_idx].append(cell_id)

        # Build content text from all cells (row by row)
        content_lines = []
        for row_idx in sorted(rows.keys()):
            row_cells = rows[row_idx]
            row_texts = []
            for cell_id in sorted(row_cells, key=lambda cid: cells[cid]['col']):
                row_texts.append(cells[cell_id]['text'])
            content_lines.append(' | '.join(row_texts))

        content_text = '\n'.join(content_lines)

        return {
            'block_id': table_id,
            'page': page,
            'bbox': bbox,
            'cells': cells,
            'rows': dict(rows),
            'content_text': content_text
        }

    def parse_layout_block(self, layout_block: Dict) -> Dict[str, Any]:
        """
        Parse a LAYOUT block and extract all LINE children with their geometry.

        Returns:
            Dict with layout metadata and lines:
            {
                'block_id': str,
                'page': int,
                'layout_type': str (e.g., 'LAYOUT_TEXT', 'LAYOUT_TITLE'),
                'bbox': {left, top, width, height},
                'lines': {
                    '{line_block_id}': {
                        'bbox': {left, top, width, height},
                        'text': str
                    }
                },
                'content_text': str (all line text joined)
            }
        """
        block_id = layout_block.get('Id')
        page = layout_block.get('Page', 1)
        layout_type = layout_block.get('BlockType', 'LAYOUT_TEXT')
        bbox = self.get_bbox(layout_block)

        lines = {}
        line_texts = []

        # Get all children and find LINE blocks
        child_ids = self.get_child_ids(layout_block)

        for child_id in child_ids:
            child_block = self.get_block_by_id(child_id)
            if child_block and child_block.get('BlockType') == 'LINE':
                line_text = child_block.get('Text', '')
                line_bbox = self.get_bbox(child_block)

                lines[child_id] = {
                    'bbox': line_bbox,
                    'text': line_text
                }

                if line_text:
                    line_texts.append(line_text)

        # If no LINE children found, try to get text directly
        if not lines:
            direct_text = self.get_text_from_block(layout_block)
            if direct_text:
                line_texts = [direct_text]

        content_text = '\n'.join(line_texts)

        return {
            'block_id': block_id,
            'page': page,
            'layout_type': layout_type,
            'bbox': bbox,
            'lines': lines,
            'content_text': content_text
        }

    def get_all_tables(self) -> List[Dict[str, Any]]:
        """Parse all TABLE blocks and return structured data."""
        tables = []
        for table_block in self.table_blocks:
            parsed = self.parse_table_block(table_block)
            tables.append(parsed)
        return tables

    def _bbox_overlap_ratio(self, bbox1: Dict[str, float], bbox2: Dict[str, float]) -> float:
        """
        Calculate the overlap ratio between two bounding boxes.
        Returns the overlap area divided by the smaller box's area.

        This is used to detect if a LAYOUT_TABLE overlaps with a TABLE block
        (they represent the same content but with different structure).
        """
        # Calculate intersection
        x1 = max(bbox1.get('left', 0), bbox2.get('left', 0))
        y1 = max(bbox1.get('top', 0), bbox2.get('top', 0))
        x2 = min(bbox1.get('left', 0) + bbox1.get('width', 0),
                 bbox2.get('left', 0) + bbox2.get('width', 0))
        y2 = min(bbox1.get('top', 0) + bbox1.get('height', 0),
                 bbox2.get('top', 0) + bbox2.get('height', 0))

        # No overlap
        if x2 <= x1 or y2 <= y1:
            return 0.0

        overlap_area = (x2 - x1) * (y2 - y1)

        # Calculate areas
        area1 = bbox1.get('width', 0) * bbox1.get('height', 0)
        area2 = bbox2.get('width', 0) * bbox2.get('height', 0)

        if area1 == 0 or area2 == 0:
            return 0.0

        # Return overlap relative to smaller bbox
        min_area = min(area1, area2)
        return overlap_area / min_area

    def get_all_layouts(self, skip_duplicate_tables: bool = True) -> List[Dict[str, Any]]:
        """
        Parse all LAYOUT blocks and return structured data.

        Args:
            skip_duplicate_tables: If True, skip LAYOUT_TABLE blocks that overlap
                                   significantly (>80%) with existing TABLE blocks.
                                   This prevents duplicate chunking of tables.
        """
        layouts = []

        # If we need to filter duplicates, first collect all TABLE bboxes by page
        table_bboxes_by_page = defaultdict(list)
        if skip_duplicate_tables:
            for table_block in self.table_blocks:
                page = table_block.get('Page', 1)
                bbox = self.get_bbox(table_block)
                table_bboxes_by_page[page].append(bbox)

        for layout_block in self.layout_blocks:
            layout_type = layout_block.get('BlockType', '')

            # Check if this is a LAYOUT_TABLE that might duplicate a TABLE block
            if skip_duplicate_tables and layout_type == 'LAYOUT_TABLE':
                page = layout_block.get('Page', 1)
                layout_bbox = self.get_bbox(layout_block)

                # Check overlap with all TABLE blocks on the same page
                is_duplicate = False
                for table_bbox in table_bboxes_by_page.get(page, []):
                    overlap = self._bbox_overlap_ratio(layout_bbox, table_bbox)
                    if overlap > 0.8:  # 80% overlap threshold
                        logger.debug(f"Skipping LAYOUT_TABLE (page {page}) - "
                                    f"overlaps {overlap:.1%} with existing TABLE block")
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue  # Skip this LAYOUT_TABLE

            parsed = self.parse_layout_block(layout_block)
            layouts.append(parsed)

        return layouts

    def get_blocks_by_page(self, skip_duplicate_tables: bool = True) -> Dict[int, Dict[str, List]]:
        """
        Organize all parsed blocks by page.

        Args:
            skip_duplicate_tables: If True, skip LAYOUT_TABLE blocks that overlap
                                   significantly (>80%) with existing TABLE blocks.

        Returns:
            {
                page_number: {
                    'tables': [parsed_table_data],
                    'layouts': [parsed_layout_data]
                }
            }
        """
        pages = defaultdict(lambda: {'tables': [], 'layouts': []})

        # First, collect all TABLE bboxes by page for duplicate detection
        table_bboxes_by_page = defaultdict(list)

        for table_block in self.table_blocks:
            page = table_block.get('Page', 1)
            parsed = self.parse_table_block(table_block)
            pages[page]['tables'].append(parsed)

            # Store bbox for duplicate detection
            if skip_duplicate_tables:
                table_bboxes_by_page[page].append(parsed['bbox'])

        for layout_block in self.layout_blocks:
            page = layout_block.get('Page', 1)
            layout_type = layout_block.get('BlockType', '')

            # Check if this is a LAYOUT_TABLE that might duplicate a TABLE block
            if skip_duplicate_tables and layout_type == 'LAYOUT_TABLE':
                layout_bbox = self.get_bbox(layout_block)

                # Check overlap with all TABLE blocks on the same page
                is_duplicate = False
                for table_bbox in table_bboxes_by_page.get(page, []):
                    overlap = self._bbox_overlap_ratio(layout_bbox, table_bbox)
                    if overlap > 0.8:  # 80% overlap threshold
                        logger.debug(f"Skipping LAYOUT_TABLE (page {page}) - "
                                    f"overlaps {overlap:.1%} with existing TABLE block")
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue  # Skip this LAYOUT_TABLE

            parsed = self.parse_layout_block(layout_block)
            pages[page]['layouts'].append(parsed)

        return dict(pages)

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about the parsed blocks."""
        layout_types = defaultdict(int)
        for layout in self.layout_blocks:
            layout_types[layout.get('BlockType', 'UNKNOWN')] += 1

        return {
            'total_blocks': len(self.blocks_map),
            'tables': len(self.table_blocks),
            'layouts': len(self.layout_blocks),
            'lines': len(self.line_blocks),
            'cells': len(self.cell_blocks),
            'words': len(self.word_blocks),
            'layout_types': dict(layout_types)
        }


def parse_textract_output(blocks_json_path: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Convenience function to parse Textract output and return tables and layouts.

    Args:
        blocks_json_path: Path to the _blocks.json file

    Returns:
        Tuple of (tables, layouts) where each is a list of parsed block data
    """
    parser = TextractParser(blocks_json_path=blocks_json_path)

    stats = parser.get_statistics()
    logger.info(f"Textract parsing stats: {stats}")

    tables = parser.get_all_tables()
    layouts = parser.get_all_layouts()

    return tables, layouts


if __name__ == '__main__':
    # Test with a sample blocks.json file
    import sys

    if len(sys.argv) > 1:
        blocks_path = sys.argv[1]
        parser = TextractParser(blocks_json_path=blocks_path)

        print("\n=== Statistics ===")
        stats = parser.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n=== Tables ===")
        tables = parser.get_all_tables()
        for i, table in enumerate(tables):
            print(f"\nTable {i+1} (Page {table['page']}):")
            print(f"  Cells: {len(table['cells'])}")
            print(f"  Preview: {table['content_text'][:200]}...")

        print("\n=== Layouts ===")
        layouts = parser.get_all_layouts()
        for i, layout in enumerate(layouts[:5]):  # First 5 only
            print(f"\nLayout {i+1} ({layout['layout_type']}, Page {layout['page']}):")
            print(f"  Lines: {len(layout['lines'])}")
            print(f"  Preview: {layout['content_text'][:100]}...")
    else:
        print("Usage: python textract_parser.py <path_to_blocks.json>")
