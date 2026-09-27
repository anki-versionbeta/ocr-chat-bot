"""
Detailed Weaviate Chunk Analysis - Focus on Ges.-Mittel. cell grounding
"""

import requests
import json
import re

WEAVIATE_URL = "http://10.242.190.53:8080"
PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"
COLLECTION_NAME = "DocumentChunk"


def get_all_chunks_for_process(process_id: str, limit: int = 1000):
    """Get all chunks for a specific process_id."""
    graphql_query = f'''
    {{
        Get {{
            {COLLECTION_NAME}(
                where: {{
                    path: ["process_id"],
                    operator: Equal,
                    valueText: "{process_id}"
                }}
                limit: {limit}
            ) {{
                document_id
                process_id
                chunk_id
                chunk_index
                page
                chunk_type
                layout_type
                content
                cell_grounding
                line_grounding
                markdown
                bbox_left
                bbox_top
                bbox_right
                bbox_bottom
                filename
                _additional {{
                    id
                }}
            }}
        }}
    }}
    '''

    response = requests.post(
        f"{WEAVIATE_URL}/v1/graphql",
        json={"query": graphql_query},
        headers={"Content-Type": "application/json"},
        timeout=60
    )

    if response.status_code == 200:
        data = response.json()
        return data.get("data", {}).get("Get", {}).get(COLLECTION_NAME, [])
    return []


def main():
    print("=" * 80)
    print("DETAILED CELL_GROUNDING ANALYSIS FOR Ges.-Mittel.")
    print("=" * 80)

    chunks = get_all_chunks_for_process(PROCESS_ID)
    print(f"Retrieved {len(chunks)} chunks\n")

    # Find chunks with Ges.-Mittel.
    ges_chunks = []
    for c in chunks:
        content = (c.get('content', '') or '').lower()
        if 'ges.-mittel' in content or 'ges-mittel' in content:
            ges_chunks.append(c)

    print(f"Found {len(ges_chunks)} chunks containing 'Ges.-Mittel.'\n")

    for i, chunk in enumerate(ges_chunks, 1):
        print(f"\n{'='*60}")
        print(f"CHUNK {i}: Page {chunk.get('page')}, Index {chunk.get('chunk_index')}")
        print(f"{'='*60}")

        # Show full content
        content = chunk.get('content', '') or ''
        print(f"\nCONTENT:\n{content}")

        # Parse cell_grounding
        cell_grounding = chunk.get('cell_grounding')
        if cell_grounding:
            print(f"\n{'~'*40}")
            print("CELL_GROUNDING DETAILS:")
            print(f"{'~'*40}")
            try:
                cg = json.loads(cell_grounding) if isinstance(cell_grounding, str) else cell_grounding
                print(f"Total cells: {len(cg)}")

                # Find cells with Ges.-Mittel.
                print("\nCells containing 'Ges.-Mittel.':")
                for cell_id, cell_data in cg.items():
                    cell_text = cell_data.get('text', '') if isinstance(cell_data, dict) else ''
                    if 'ges' in cell_text.lower():
                        bbox = cell_data.get('bbox', {})
                        print(f"\n  Cell ID: {cell_id}")
                        print(f"    Text: {cell_text}")
                        print(f"    BBox: left={bbox.get('left', 0):.4f}, top={bbox.get('top', 0):.4f}, "
                              f"width={bbox.get('width', 0):.4f}, height={bbox.get('height', 0):.4f}")

                # Find cells with threshold values (numeric data in same row)
                print("\nAll cells with numeric values (potential data cells):")
                for cell_id, cell_data in cg.items():
                    cell_text = cell_data.get('text', '') if isinstance(cell_data, dict) else ''
                    # Check if it's a numeric value like "133,7" or "0,0"
                    if re.match(r'^\d+[,.]?\d*$', cell_text.strip()):
                        bbox = cell_data.get('bbox', {})
                        # Only show first 20
                        print(f"    {cell_id}: '{cell_text}' @ ({bbox.get('left', 0):.3f}, {bbox.get('top', 0):.3f})")

            except Exception as e:
                print(f"  Parse error: {e}")

        # Show markdown if available
        markdown = chunk.get('markdown', '')
        if markdown:
            print(f"\n{'~'*40}")
            print("MARKDOWN (first 500 chars):")
            print(f"{'~'*40}")
            print(markdown[:500])

    # Summary of sample numbers per page
    print(f"\n\n{'='*80}")
    print("SAMPLE NUMBERS BY PAGE")
    print("=" * 80)

    sample_pattern = r'SA\d{5,}'
    page_samples = {}

    for c in chunks:
        page = c.get('page', 0)
        content = c.get('content', '') or ''
        matches = re.findall(sample_pattern, content, re.IGNORECASE)
        if matches:
            if page not in page_samples:
                page_samples[page] = set()
            page_samples[page].update(matches)

    for page in sorted(page_samples.keys()):
        samples = sorted(page_samples[page])
        print(f"Page {page}: {', '.join(samples)}")

    # Show relationship between sample numbers and Ges.-Mittel. values
    print(f"\n\n{'='*80}")
    print("DATA STRUCTURE PER PAGE (Sample + Ges.-Mittel. values)")
    print("=" * 80)

    for c in ges_chunks:
        page = c.get('page', 0)
        content = c.get('content', '') or ''

        # Find sample in same page
        samples_on_page = page_samples.get(page, set())

        # Extract Ges.-Mittel. row values
        lines = content.split('\n')
        ges_line = None
        for line in lines:
            if 'ges.-mittel' in line.lower():
                ges_line = line
                break

        print(f"\nPage {page}:")
        print(f"  Samples: {', '.join(sorted(samples_on_page)) if samples_on_page else 'None found'}")
        if ges_line:
            print(f"  Ges.-Mittel. row: {ges_line}")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
