"""
Quick script to trigger Neo4j indexing for an existing process_id + blocks file.
"""

import asyncio
import os
import sys
import logging

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from dotenv import load_dotenv
load_dotenv()

# Configuration
PROCESS_ID = "cc766a16-377e-415f-bbfd-958890a33df9"
BLOCKS_PATH = "temp/MFI_stabilitysamples_104pages_blocks.json"
FILENAME = "MFI_stabilitysamples_104pages.pdf"
DOCUMENT_TYPE = "COA"
USERNAME = "bapatar"

async def main():
    print("=" * 80)
    print("TRIGGER NEO4J INDEXING")
    print("=" * 80)
    print(f"Process ID: {PROCESS_ID}")
    print(f"Blocks Path: {BLOCKS_PATH}")
    print(f"Filename: {FILENAME}")
    print()

    # Check if blocks file exists
    if not os.path.exists(BLOCKS_PATH):
        print(f"ERROR: Blocks file not found: {BLOCKS_PATH}")
        return

    print("Importing Neo4j ingestion service...")
    from services.neo4j_ingestion import index_document_to_neo4j

    print("Starting Neo4j indexing...")
    print("-" * 40)

    result = await index_document_to_neo4j(
        process_id=PROCESS_ID,
        blocks_json_path=BLOCKS_PATH,
        filename=FILENAME,
        document_type=DOCUMENT_TYPE,
        username=USERNAME
    )

    print("-" * 40)
    print()
    print("=" * 80)
    print("RESULT")
    print("=" * 80)

    if result.get("success"):
        print("✅ SUCCESS!")
        print(f"Stats: {result.get('stats', {})}")
        print(f"Time: {result.get('elapsed_seconds', 0):.2f}s")
    else:
        print("❌ FAILED!")
        print(f"Error: {result.get('error', 'Unknown')}")

if __name__ == "__main__":
    asyncio.run(main())
