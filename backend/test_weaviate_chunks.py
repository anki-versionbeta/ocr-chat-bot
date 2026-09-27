"""
Weaviate Chunk Analyzer for Process ID: f96d6d53-8257-4d3c-86b1-279f0e3ad069

This script analyzes what Weaviate knows about a specific document by:
1. Connecting to Weaviate at http://10.242.190.53:8080
2. Searching for chunks related to the process_id
3. Finding chunks containing "Ges.-Mittel." or similar
4. Finding chunks with threshold headers (2,0 um, 5,0 um, etc.)
5. Checking the cell_grounding data in chunks
6. Analyzing chunk_type distribution (table vs text)
7. Finding sample numbers (SA00...)
"""

import requests
import json
from collections import Counter
import re

# Configuration
WEAVIATE_URL = "http://10.242.190.53:8080"
PROCESS_ID = "f96d6d53-8257-4d3c-86b1-279f0e3ad069"
COLLECTION_NAME = "DocumentChunk"


def check_connection():
    """Check if Weaviate is reachable."""
    try:
        response = requests.get(f"{WEAVIATE_URL}/v1/.well-known/ready", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Connection error: {e}")
        return False


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
                document_type
                _additional {{
                    id
                }}
            }}
        }}
    }}
    '''

    try:
        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": graphql_query},
            headers={"Content-Type": "application/json"},
            timeout=60
        )

        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                print(f"GraphQL errors: {data['errors']}")
                return []
            return data.get("data", {}).get("Get", {}).get(COLLECTION_NAME, [])
        else:
            print(f"Query failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Query error: {e}")
        return []


def get_chunk_count(process_id: str = None):
    """Get count of chunks."""
    where_filter = ""
    if process_id:
        where_filter = f'''
            where: {{
                path: ["process_id"],
                operator: Equal,
                valueText: "{process_id}"
            }}
        '''

    graphql_query = f'''
    {{
        Aggregate {{
            {COLLECTION_NAME}(
                {where_filter}
            ) {{
                meta {{
                    count
                }}
            }}
        }}
    }}
    '''

    try:
        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": graphql_query},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("Aggregate", {}).get(COLLECTION_NAME, [{}])[0].get("meta", {}).get("count", 0)
        return 0
    except Exception as e:
        print(f"Count error: {e}")
        return 0


def analyze_chunks(chunks):
    """Analyze the chunks for various patterns and data."""

    print("\n" + "=" * 80)
    print("CHUNK ANALYSIS RESULTS")
    print("=" * 80)

    # 1. Basic stats
    print(f"\n[1] BASIC STATISTICS")
    print("-" * 40)
    print(f"Total chunks: {len(chunks)}")

    if not chunks:
        print("No chunks found for this process_id!")
        return

    # 2. Chunk type distribution
    print(f"\n[2] CHUNK TYPE DISTRIBUTION")
    print("-" * 40)
    chunk_types = Counter(c.get('chunk_type', 'unknown') for c in chunks)
    for ct, count in chunk_types.most_common():
        print(f"  {ct}: {count}")

    # 3. Layout type distribution
    print(f"\n[3] LAYOUT TYPE DISTRIBUTION")
    print("-" * 40)
    layout_types = Counter(c.get('layout_type', 'unknown') for c in chunks)
    for lt, count in layout_types.most_common():
        print(f"  {lt}: {count}")

    # 4. Page distribution
    print(f"\n[4] PAGE DISTRIBUTION")
    print("-" * 40)
    pages = Counter(c.get('page', 0) for c in chunks)
    for page, count in sorted(pages.items()):
        print(f"  Page {page}: {count} chunks")

    # 5. Search for "Ges.-Mittel." or similar
    print(f"\n[5] CHUNKS CONTAINING 'Ges.-Mittel.' OR SIMILAR")
    print("-" * 40)
    ges_mittel_patterns = ['ges.-mittel', 'ges-mittel', 'ges mittel', 'gesamtmittel', 'ges.-mitt']
    ges_chunks = []
    for c in chunks:
        content = (c.get('content', '') or '').lower()
        markdown = (c.get('markdown', '') or '').lower()
        for pattern in ges_mittel_patterns:
            if pattern in content or pattern in markdown:
                ges_chunks.append(c)
                break

    if ges_chunks:
        print(f"Found {len(ges_chunks)} chunks with 'Ges.-Mittel.' or similar:")
        for i, c in enumerate(ges_chunks[:5], 1):
            print(f"\n  Chunk {i}:")
            print(f"    Page: {c.get('page')}")
            print(f"    Type: {c.get('chunk_type')}")
            print(f"    Layout: {c.get('layout_type')}")
            content_preview = (c.get('content', '') or '')[:300].replace('\n', ' ')
            print(f"    Content preview: {content_preview}...")

            # Check cell_grounding
            cell_grounding = c.get('cell_grounding')
            if cell_grounding:
                try:
                    cg = json.loads(cell_grounding) if isinstance(cell_grounding, str) else cell_grounding
                    print(f"    Cell grounding entries: {len(cg)}")
                    # Find cells with Ges.-Mittel
                    for cell_id, cell_data in list(cg.items())[:3]:
                        cell_text = cell_data.get('text', '') if isinstance(cell_data, dict) else ''
                        if 'ges' in cell_text.lower():
                            print(f"      Cell {cell_id}: {cell_text[:50]}")
                except:
                    print(f"    Cell grounding: (parse error)")
    else:
        print("No chunks found with 'Ges.-Mittel.' patterns")

    # 6. Search for threshold headers (2,0 um, 5,0 um, etc.)
    print(f"\n[6] CHUNKS WITH THRESHOLD HEADERS (2,0 um, 5,0 um, etc.)")
    print("-" * 40)
    threshold_patterns = [
        r'2[,.]0\s*[uµ]m', r'5[,.]0\s*[uµ]m', r'10[,.]0\s*[uµ]m',
        r'25[,.]0\s*[uµ]m', r'\d+[,.]0\s*[uµ]m'
    ]
    threshold_chunks = []
    for c in chunks:
        content = c.get('content', '') or ''
        markdown = c.get('markdown', '') or ''
        combined = content + ' ' + markdown
        for pattern in threshold_patterns:
            if re.search(pattern, combined, re.IGNORECASE):
                threshold_chunks.append(c)
                break

    if threshold_chunks:
        print(f"Found {len(threshold_chunks)} chunks with threshold headers:")
        for i, c in enumerate(threshold_chunks[:5], 1):
            print(f"\n  Chunk {i}:")
            print(f"    Page: {c.get('page')}")
            print(f"    Type: {c.get('chunk_type')}")
            content_preview = (c.get('content', '') or '')[:300].replace('\n', ' ')
            print(f"    Content: {content_preview}...")
    else:
        print("No chunks found with threshold patterns")

    # 7. Check cell_grounding data in TABLE chunks
    print(f"\n[7] CELL_GROUNDING ANALYSIS FOR TABLE CHUNKS")
    print("-" * 40)
    table_chunks = [c for c in chunks if c.get('chunk_type') == 'table']
    chunks_with_grounding = 0
    total_cells = 0

    for c in table_chunks:
        cell_grounding = c.get('cell_grounding')
        if cell_grounding:
            chunks_with_grounding += 1
            try:
                cg = json.loads(cell_grounding) if isinstance(cell_grounding, str) else cell_grounding
                total_cells += len(cg)
            except:
                pass

    print(f"Table chunks: {len(table_chunks)}")
    print(f"Tables with cell_grounding: {chunks_with_grounding}")
    print(f"Total cell entries: {total_cells}")

    # Show sample cell_grounding structure
    if table_chunks:
        sample_table = table_chunks[0]
        cell_grounding = sample_table.get('cell_grounding')
        if cell_grounding:
            print(f"\nSample cell_grounding structure (first table chunk):")
            try:
                cg = json.loads(cell_grounding) if isinstance(cell_grounding, str) else cell_grounding
                for cell_id, cell_data in list(cg.items())[:5]:
                    print(f"  {cell_id}: {json.dumps(cell_data)[:100]}...")
            except Exception as e:
                print(f"  Parse error: {e}")

    # 8. Find sample numbers (SA00...)
    print(f"\n[8] SAMPLE NUMBERS (SA00... patterns)")
    print("-" * 40)
    sample_pattern = r'SA\d{2,}'
    sample_numbers = set()
    chunks_with_samples = []

    for c in chunks:
        content = c.get('content', '') or ''
        markdown = c.get('markdown', '') or ''
        combined = content + ' ' + markdown
        matches = re.findall(sample_pattern, combined, re.IGNORECASE)
        if matches:
            chunks_with_samples.append(c)
            sample_numbers.update(matches)

    if sample_numbers:
        print(f"Found {len(sample_numbers)} unique sample numbers in {len(chunks_with_samples)} chunks:")
        for sn in sorted(sample_numbers)[:20]:
            print(f"  - {sn}")
        if len(sample_numbers) > 20:
            print(f"  ... and {len(sample_numbers) - 20} more")
    else:
        print("No SA00... sample numbers found")

    # 9. Search for specific terms related to particle counts
    print(f"\n[9] PARTICLE COUNT RELATED CONTENT")
    print("-" * 40)
    particle_terms = ['particle', 'partikel', 'count', 'anzahl', 'kum', 'cumulative']
    particle_chunks = []
    for c in chunks:
        content = (c.get('content', '') or '').lower()
        for term in particle_terms:
            if term in content:
                particle_chunks.append(c)
                break

    if particle_chunks:
        print(f"Found {len(particle_chunks)} chunks with particle-related content:")
        for i, c in enumerate(particle_chunks[:3], 1):
            print(f"\n  Chunk {i}: Page {c.get('page')}, Type: {c.get('chunk_type')}")
            content_preview = (c.get('content', '') or '')[:400].replace('\n', ' ')
            print(f"    {content_preview}...")
    else:
        print("No particle-related chunks found")

    # 10. Full content dump of all table chunks
    print(f"\n[10] ALL TABLE CHUNKS CONTENT")
    print("-" * 40)
    for i, c in enumerate(table_chunks[:10], 1):
        print(f"\n  TABLE CHUNK {i}:")
        print(f"    Page: {c.get('page')}")
        print(f"    Chunk Index: {c.get('chunk_index')}")
        print(f"    Layout Type: {c.get('layout_type')}")
        content = c.get('content', '') or ''
        print(f"    Content ({len(content)} chars):")
        # Print first 600 chars of content
        for line in content[:600].split('\n')[:15]:
            print(f"      {line[:100]}")
        if len(content) > 600:
            print(f"      ... ({len(content) - 600} more chars)")

    if len(table_chunks) > 10:
        print(f"\n  ... and {len(table_chunks) - 10} more table chunks")


def main():
    print("=" * 80)
    print("WEAVIATE CHUNK ANALYZER")
    print(f"Process ID: {PROCESS_ID}")
    print(f"Weaviate URL: {WEAVIATE_URL}")
    print("=" * 80)

    # Check connection
    print("\n[Connection Check]")
    if not check_connection():
        print("ERROR: Cannot connect to Weaviate!")
        return
    print("Connected to Weaviate successfully")

    # Get counts
    print("\n[Chunk Counts]")
    total_count = get_chunk_count()
    process_count = get_chunk_count(PROCESS_ID)
    print(f"Total chunks in collection: {total_count}")
    print(f"Chunks for process_id: {process_count}")

    if process_count == 0:
        print(f"\nWARNING: No chunks found for process_id: {PROCESS_ID}")
        print("The document may not have been indexed yet.")
        return

    # Get all chunks
    print(f"\n[Fetching all chunks for process_id...]")
    chunks = get_all_chunks_for_process(PROCESS_ID)
    print(f"Retrieved {len(chunks)} chunks")

    # Analyze
    analyze_chunks(chunks)

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
