"""
Test script to re-index from existing blocks.json

This script:
1. Deletes existing chunks in Weaviate for the process_id
2. Reads the existing blocks.json
3. Creates chunks and indexes to Weaviate
4. Shows real-time progress logs

Usage: python test_reindex_from_blocks.py
"""

import os
import sys
import json
import time
import logging

# Setup UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging to see all messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

from dotenv import load_dotenv
load_dotenv()

# =====================================================
# CONFIGURATION - Change these values
# =====================================================
PROCESS_ID = "661976a2-3d65-4893-815e-26fe779b6765"  # Your MFI PDF process_id
FILENAME = "MFI_stabilitysamples_104pages"
USERNAME = "bapatar"

# Path to blocks.json (adjust if different)
BLOCKS_JSON_PATH = f"temp/{FILENAME}_blocks.json"

print("=" * 80)
print("RE-INDEX FROM EXISTING BLOCKS.JSON")
print("=" * 80)
print(f"Process ID: {PROCESS_ID}")
print(f"Filename: {FILENAME}")
print(f"Blocks path: {BLOCKS_JSON_PATH}")
print()

# =====================================================
# Step 1: Delete existing chunks from Weaviate
# =====================================================
print("=" * 80)
print("STEP 1: Delete existing chunks from Weaviate")
print("=" * 80)

from services.weaviate_indexer import WeaviateIndexer

indexer = WeaviateIndexer()

if not indexer.check_connection():
    print("ERROR: Cannot connect to Weaviate!")
    sys.exit(1)

print(f"Connected to Weaviate: {indexer.weaviate_url}")

# Check how many chunks exist
existing_count = indexer.get_chunk_count(process_id=PROCESS_ID)
print(f"Existing chunks for process_id: {existing_count}")

if existing_count > 0:
    print(f"Deleting {existing_count} existing chunks...")
    deleted = indexer.delete_by_process_id(PROCESS_ID)
    print(f"Deleted: {deleted} chunks")

    # Verify deletion
    remaining = indexer.get_chunk_count(process_id=PROCESS_ID)
    print(f"Remaining chunks: {remaining}")
else:
    print("No existing chunks to delete")

print()

# =====================================================
# Step 2: Load blocks.json
# =====================================================
print("=" * 80)
print("STEP 2: Load blocks.json")
print("=" * 80)

if not os.path.exists(BLOCKS_JSON_PATH):
    print(f"ERROR: Blocks file not found: {BLOCKS_JSON_PATH}")
    print("Available files in temp/:")
    if os.path.exists("temp"):
        for f in os.listdir("temp"):
            if f.endswith("_blocks.json"):
                print(f"  - {f}")
    sys.exit(1)

with open(BLOCKS_JSON_PATH, 'r', encoding='utf-8') as f:
    blocks_data = json.load(f)

# Handle different formats
if isinstance(blocks_data, list) and len(blocks_data) > 0:
    if 'Blocks' in blocks_data[0]:
        blocks = blocks_data[0]['Blocks']
    else:
        blocks = blocks_data
elif isinstance(blocks_data, dict) and 'Blocks' in blocks_data:
    blocks = blocks_data['Blocks']
else:
    blocks = blocks_data if isinstance(blocks_data, list) else []

print(f"Loaded {len(blocks)} blocks from {BLOCKS_JSON_PATH}")

# Count block types
block_types = {}
for b in blocks:
    bt = b.get('BlockType', 'UNKNOWN')
    block_types[bt] = block_types.get(bt, 0) + 1

print("Block types:")
for bt, count in sorted(block_types.items()):
    print(f"  - {bt}: {count}")

print()

# =====================================================
# Step 3: Parse blocks and create chunks
# =====================================================
print("=" * 80)
print("STEP 3: Parse blocks and create chunks")
print("=" * 80)

from services.textract_parser import parse_textract_output
from services.chunk_transformer import chunk_textract_blocks

# Parse blocks using file path (parse_textract_output takes file path, not blocks list)
tables, layouts = parse_textract_output(BLOCKS_JSON_PATH)
print(f"Parsed: {len(tables)} tables, {len(layouts)} text blocks")

# Create document_id
import uuid
document_id = str(uuid.uuid4())

# Create chunks
start_time = time.time()

chunks = chunk_textract_blocks(
    tables=tables,
    layouts=layouts,
    document_id=document_id,
    process_id=PROCESS_ID,
    filename=f"{FILENAME}.pdf",
    document_summary=f"Certificate of Analysis: {FILENAME}",
    keywords="COA, certificate, analysis, test, specification, result"
)

chunk_time = time.time() - start_time
print(f"Created {len(chunks)} chunks in {chunk_time:.2f}s")

# Count chunk types
chunk_types = {}
for c in chunks:
    ct = c.get('chunk_type', 'unknown')
    chunk_types[ct] = chunk_types.get(ct, 0) + 1

print("Chunk types:")
for ct, count in sorted(chunk_types.items()):
    print(f"  - {ct}: {count}")

print()

# =====================================================
# Step 4: Index chunks to Weaviate
# =====================================================
print("=" * 80)
print("STEP 4: Index chunks to Weaviate (with parallel processing)")
print("=" * 80)

print(f"Starting indexing of {len(chunks)} chunks...")
print("Watch for progress logs below:")
print("-" * 40)

start_time = time.time()

result = indexer.index_chunks_batch(
    chunks=chunks,
    username=USERNAME,
    document_type="COA",
    source=f"coa_{USERNAME.lower()}"
)

total_time = time.time() - start_time

print("-" * 40)
print()
print("=" * 80)
print("RESULTS")
print("=" * 80)
print(f"Success: {result['success']}")
print(f"Failed: {result['failed']}")
print(f"Total time: {total_time:.2f}s")
print(f"Chunks per second: {len(chunks)/total_time:.1f}")

if result['errors']:
    print(f"\nErrors ({len(result['errors'])}):")
    for err in result['errors'][:5]:
        print(f"  - {err}")

# Verify in Weaviate
final_count = indexer.get_chunk_count(process_id=PROCESS_ID)
print(f"\nFinal chunk count in Weaviate: {final_count}")

print()
print("=" * 80)
print("DONE! You can now test RAG queries with this process_id:")
print(f"  Process ID: {PROCESS_ID}")
print("=" * 80)
