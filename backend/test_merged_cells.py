"""
Deep dive into merged cells in Textract output.
Analyze how "Dates" column with sub-columns (Exp., DoM) is structured.
"""
import json
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load the SAF blocks
data = json.load(open('temp/SAF_HL4689_blocks.json', encoding='utf-8'))

# Flatten all blocks
all_blocks = []
for page in data:
    if 'Blocks' in page:
        all_blocks.extend(page['Blocks'])

blocks_map = {b.get('Id'): b for b in all_blocks}

# Find all TABLE blocks on page 1
tables_page1 = [b for b in all_blocks if b.get('BlockType') == 'TABLE' and b.get('Page') == 1]

print('=' * 80)
print('ANALYZING MERGED CELLS IN TEXTRACT OUTPUT')
print('=' * 80)

# Find the "Product Name Material Batch" table (3rd table on page 1)
for i, table in enumerate(tables_page1):
    # Get all cells
    cells = []
    merged_cells = []

    for rel in table.get('Relationships', []):
        if rel.get('Type') == 'CHILD':
            for child_id in rel.get('Ids', []):
                child = blocks_map.get(child_id)
                if child and child.get('BlockType') == 'CELL':
                    cells.append(child)
        elif rel.get('Type') == 'MERGED_CELL':
            for mc_id in rel.get('Ids', []):
                mc = blocks_map.get(mc_id)
                if mc:
                    merged_cells.append(mc)

    # Get text from first cell to identify the table
    if cells:
        first_cell = cells[0]
        first_text = ''
        for rel in first_cell.get('Relationships', []):
            if rel.get('Type') == 'CHILD':
                for word_id in rel.get('Ids', []):
                    word = blocks_map.get(word_id)
                    if word and 'Text' in word:
                        first_text += word.get('Text', '') + ' '

        if 'product name' in first_text.lower():
            print(f'\nFOUND: Table {i+1} - "Product Name Material Batch" table')
            print(f'Total CELL blocks: {len(cells)}')
            print(f'Total MERGED_CELL blocks: {len(merged_cells)}')

            print('\n' + '-' * 80)
            print('CELL STRUCTURE (Row x Column with spans)')
            print('-' * 80)

            # Analyze each cell
            cell_data = []
            for cell in cells:
                row = cell.get('RowIndex', 0)
                col = cell.get('ColumnIndex', 0)
                row_span = cell.get('RowSpan', 1)
                col_span = cell.get('ColumnSpan', 1)

                # Get text
                text = ''
                for rel in cell.get('Relationships', []):
                    if rel.get('Type') == 'CHILD':
                        for word_id in rel.get('Ids', []):
                            word = blocks_map.get(word_id)
                            if word and 'Text' in word:
                                text += word.get('Text', '') + ' '
                text = text.strip()

                cell_data.append({
                    'row': row,
                    'col': col,
                    'row_span': row_span,
                    'col_span': col_span,
                    'text': text
                })

            # Sort by row then column
            cell_data.sort(key=lambda c: (c['row'], c['col']))

            # Print cell structure
            current_row = 0
            for cell in cell_data:
                if cell['row'] != current_row:
                    print(f'\n--- ROW {cell["row"]} ---')
                    current_row = cell['row']

                span_info = ''
                if cell['row_span'] > 1:
                    span_info += f' [rowspan={cell["row_span"]}]'
                if cell['col_span'] > 1:
                    span_info += f' [colspan={cell["col_span"]}]'

                print(f'  Col {cell["col"]}: "{cell["text"][:40]}"{span_info}')

            print('\n' + '-' * 80)
            print('MERGED_CELL BLOCKS (if any)')
            print('-' * 80)

            if merged_cells:
                for mc in merged_cells:
                    mc_id = mc.get('Id', '')[:20]
                    # Get child cell IDs
                    child_ids = []
                    for rel in mc.get('Relationships', []):
                        if rel.get('Type') == 'CHILD':
                            child_ids = rel.get('Ids', [])
                    print(f'  MERGED_CELL: {mc_id}...')
                    print(f'    Contains {len(child_ids)} child cells')
            else:
                print('  No MERGED_CELL blocks found')

            print('\n' + '-' * 80)
            print('TABLE VISUALIZATION')
            print('-' * 80)

            # Build a grid
            max_row = max(c['row'] for c in cell_data)
            max_col = max(c['col'] for c in cell_data)

            # Create grid with spans
            grid = {}
            for cell in cell_data:
                r, c = cell['row'], cell['col']
                grid[(r, c)] = cell['text'][:15] if cell['text'] else '(empty)'

                # Mark spanned cells
                for dr in range(cell['row_span']):
                    for dc in range(cell['col_span']):
                        if dr > 0 or dc > 0:
                            grid[(r + dr, c + dc)] = f'↑←({r},{c})'

            # Print grid
            for r in range(1, max_row + 1):
                row_str = f'R{r}: '
                for c in range(1, max_col + 1):
                    cell_val = grid.get((r, c), '???')
                    row_str += f'| {cell_val:15} '
                row_str += '|'
                print(row_str)

            print('\n' + '-' * 80)
            print('CURRENT MARKDOWN OUTPUT')
            print('-' * 80)

            # Build current markdown (pipe-separated)
            for r in range(1, max_row + 1):
                row_texts = []
                for c in range(1, max_col + 1):
                    for cell in cell_data:
                        if cell['row'] == r and cell['col'] == c:
                            row_texts.append(cell['text'])
                            break
                print(' | '.join(row_texts))

            print('\n' + '-' * 80)
            print('PROPOSED HTML TABLE OUTPUT')
            print('-' * 80)

            # Build HTML table with proper spans
            html = '<table border="1">\n'
            for r in range(1, max_row + 1):
                html += '  <tr>\n'
                for c in range(1, max_col + 1):
                    # Find cell at this position
                    for cell in cell_data:
                        if cell['row'] == r and cell['col'] == c:
                            attrs = ''
                            if cell['row_span'] > 1:
                                attrs += f' rowspan="{cell["row_span"]}"'
                            if cell['col_span'] > 1:
                                attrs += f' colspan="{cell["col_span"]}"'
                            html += f'    <td{attrs}>{cell["text"]}</td>\n'
                            break
                html += '  </tr>\n'
            html += '</table>'

            print(html)

            break

print('\n' + '=' * 80)
print('RECOMMENDATIONS')
print('=' * 80)
print('''
OPTIONS FOR HANDLING MERGED CELLS:

1. ADD HTML FIELD TO CHUNK SCHEMA
   - Add "html" or "table_html" field to DocumentChunk
   - Store HTML table with proper rowspan/colspan
   - Frontend can render HTML for accurate display
   - Pros: Accurate visual representation
   - Cons: Additional storage, more complex rendering

2. IMPROVE MARKDOWN FORMAT
   - Use extended markdown table syntax (some renderers support spans)
   - Or use custom markers like: "Dates [spans: Exp., DoM]"
   - Pros: Simpler, text-based
   - Cons: Not universally supported

3. STRUCTURED JSON FOR TABLES
   - Store table as JSON with cell metadata
   - Include row/col spans in cell_grounding
   - Frontend builds the table from JSON
   - Pros: Most flexible, already have cell_grounding
   - Cons: Requires custom table renderer

4. KEEP CURRENT + ENHANCE cell_grounding
   - Current cell_grounding already has row/col info
   - Just need to add row_span/col_span to each cell
   - Then frontend can reconstruct proper table
   - Pros: Minimal schema change, backward compatible
''')
