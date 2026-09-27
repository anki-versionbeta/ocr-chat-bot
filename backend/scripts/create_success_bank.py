"""
One-time setup script to create CypherSuccessBank collection in Weaviate.

This collection stores successful Cypher queries for few-shot learning,
replacing the hardcoded FEW_SHOT_EXAMPLES with dynamic vector retrieval.

Run this once before using the Success Bank feature:
    python backend/scripts/create_success_bank.py

Created: February 12, 2026
Part of: Phase 2 - Success Bank Implementation
"""

import requests
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://10.242.190.53:8080")


def delete_existing_collection():
    """Delete the CypherSuccessBank collection if it exists."""
    try:
        response = requests.delete(
            f"{WEAVIATE_URL}/v1/schema/CypherSuccessBank",
            timeout=10
        )
        if response.status_code == 200:
            print("[OK] Deleted existing CypherSuccessBank collection")
            return True
        elif response.status_code == 404:
            print("[INFO] CypherSuccessBank collection does not exist (nothing to delete)")
            return True
        else:
            print(f"[WARN] Unexpected response when deleting: {response.status_code}")
            return True
    except Exception as e:
        print(f"[WARN] Error deleting collection: {e}")
        return True


def create_success_bank():
    """Create the CypherSuccessBank collection in Weaviate."""

    # Collection schema
    schema = {
        "class": "CypherSuccessBank",
        "description": "Stores successful Cypher queries for few-shot learning in multi-agent GraphRAG",
        "vectorizer": "none",  # We provide our own vectors via text-embedding-3-large
        "properties": [
            {
                "name": "user_query",
                "dataType": ["text"],
                "description": "Natural language query from user"
            },
            {
                "name": "cypher_query",
                "dataType": ["text"],
                "description": "Generated Cypher query that succeeded"
            },
            {
                "name": "logical_plan",
                "dataType": ["text"],
                "description": "Step-by-step logical plan used"
            },
            {
                "name": "node_types_used",
                "dataType": ["text[]"],
                "description": "Node types used in Cypher (Cell, Line, Section, etc.)"
            },
            {
                "name": "relationship_path",
                "dataType": ["text"],
                "description": "Main relationship chain (e.g., HAS_PAGE->CONTAINS_TABLE->HAS_CELL)"
            },
            {
                "name": "structural_signature",
                "dataType": ["text"],
                "description": "JSON of structural probe results for compatibility matching"
            },
            {
                "name": "chunk_types_seen",
                "dataType": ["text[]"],
                "description": "Chunk types from Weaviate search (table, text, line)"
            },
            {
                "name": "accuracy_score",
                "dataType": ["number"],
                "description": "Success score (0.0 to 1.0) - higher means better quality"
            },
            {
                "name": "process_id",
                "dataType": ["text"],
                "description": "Document UUID this query was run against"
            },
            {
                "name": "result_count",
                "dataType": ["int"],
                "description": "Number of rows returned by the query"
            },
            {
                "name": "iterations_used",
                "dataType": ["int"],
                "description": "Number of retry iterations (1 = first try success)"
            },
            {
                "name": "created_at",
                "dataType": ["date"],
                "description": "Timestamp when this success was recorded"
            }
        ]
    }

    try:
        response = requests.post(
            f"{WEAVIATE_URL}/v1/schema",
            json=schema,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            print("[OK] Successfully created CypherSuccessBank collection!")
            return True
        else:
            print(f"[ERROR] Failed to create collection: {response.status_code}")
            print(f"        Response: {response.text}")
            return False

    except Exception as e:
        print(f"[ERROR] Error creating collection: {e}")
        return False


def verify_collection():
    """Verify the collection was created correctly."""
    try:
        response = requests.get(
            f"{WEAVIATE_URL}/v1/schema/CypherSuccessBank",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            print("\n[OK] Collection verification successful!")
            print("-" * 50)
            print(f"Class name: {data.get('class', 'N/A')}")
            print(f"Properties: {len(data.get('properties', []))}")
            for prop in data.get('properties', []):
                print(f"  - {prop['name']}: {prop['dataType']}")
            print("-" * 50)
            return True
        else:
            print(f"[ERROR] Collection verification failed: {response.status_code}")
            return False

    except Exception as e:
        print(f"[ERROR] Error verifying collection: {e}")
        return False


def count_documents():
    """Count existing documents in the collection."""
    try:
        query = '''
        {
            Aggregate {
                CypherSuccessBank {
                    meta {
                        count
                    }
                }
            }
        }
        '''

        response = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": query},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            count = data.get("data", {}).get("Aggregate", {}).get("CypherSuccessBank", [{}])[0].get("meta", {}).get("count", 0)
            print(f"\n[INFO] Current document count: {count}")
            return count
        else:
            print(f"[WARN] Could not count documents: {response.status_code}")
            return 0

    except Exception as e:
        print(f"[WARN] Error counting documents: {e}")
        return 0


def seed_initial_examples():
    """
    Optionally seed the Success Bank with initial examples.

    These are converted from the existing FEW_SHOT_EXAMPLES to bootstrap
    the system before it learns from actual successes.
    """
    print("\n[INFO] Seeding initial examples...")

    # Import the embedding function
    try:
        from test_multiagent_cypher import WeaviateTools
        weaviate_tools = WeaviateTools()
    except ImportError:
        print("[WARN] Could not import WeaviateTools - skipping seed")
        return False

    # Initial examples (converted from FEW_SHOT_EXAMPLES)
    seed_examples = [
        {
            "user_query": "Find all cells containing a specific term and return values with page numbers",
            "cypher_query": """MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(c:Cell)
WHERE toLower(coalesce(c.text, '')) CONTAINS toLower($search_term)
RETURN p.page_num AS page, c.text AS value, c.row_index AS row, c.col_index AS col
ORDER BY p.page_num, c.row_index""",
            "logical_plan": "1. Search cells where text contains search term\n2. Return text and page number\n3. Order by page",
            "node_types_used": ["Document", "Page", "Table", "Cell"],
            "relationship_path": "HAS_PAGE->CONTAINS_TABLE->HAS_CELL",
            "accuracy_score": 0.9,
            "result_count": 0,
            "iterations_used": 1
        },
        {
            "user_query": "Extract data from Line nodes (text paragraphs, not tables)",
            "cypher_query": """MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_LINE]->(l:Line)
WHERE toLower(coalesce(l.text, '')) CONTAINS toLower($search_term)
RETURN p.page_num AS page, l.text AS line_text
ORDER BY p.page_num""",
            "logical_plan": "1. Search Line nodes for text containing search term\n2. Return line text with page number\n3. Order by page",
            "node_types_used": ["Document", "Page", "Line"],
            "relationship_path": "HAS_PAGE->CONTAINS_LINE",
            "accuracy_score": 0.9,
            "result_count": 0,
            "iterations_used": 1
        },
        {
            "user_query": "Find a row by label and extract all columns from that row",
            "cypher_query": """MATCH (d:Document {process_id: $process_id})-[:HAS_PAGE]->(p:Page)-[:CONTAINS_TABLE]->(t:Table)-[:HAS_CELL]->(label:Cell)
WHERE label.col_index IN [0, 1] AND toLower(coalesce(label.text, '')) CONTAINS toLower($row_label)
WITH t, p, label.row_index AS targetRow, label.text AS rowLabel
MATCH (t)-[:HAS_CELL]->(c:Cell {row_index: targetRow})
WITH p, rowLabel, c ORDER BY c.col_index
RETURN p.page_num AS page, rowLabel AS row_label, collect({col: c.col_index, text: c.text}) AS row_data
ORDER BY p.page_num""",
            "logical_plan": "1. Find cells in col 0/1 containing row label\n2. Get row_index of that cell\n3. Get all cells in same row\n4. Return all column values",
            "node_types_used": ["Document", "Page", "Table", "Cell"],
            "relationship_path": "HAS_PAGE->CONTAINS_TABLE->HAS_CELL",
            "accuracy_score": 0.9,
            "result_count": 0,
            "iterations_used": 1
        }
    ]

    from datetime import datetime

    success_count = 0
    for example in seed_examples:
        try:
            # Generate embedding
            embedding = weaviate_tools.generate_embedding(example["user_query"])
            if not embedding:
                print(f"  [WARN] Failed to generate embedding for: {example['user_query'][:50]}...")
                continue

            # Prepare data
            data = {
                "user_query": example["user_query"],
                "cypher_query": example["cypher_query"],
                "logical_plan": example["logical_plan"],
                "node_types_used": example["node_types_used"],
                "relationship_path": example["relationship_path"],
                "structural_signature": "{}",
                "chunk_types_seen": ["table"] if "Cell" in example["node_types_used"] else ["line"],
                "accuracy_score": example["accuracy_score"],
                "process_id": "seed-example",
                "result_count": example["result_count"],
                "iterations_used": example["iterations_used"],
                "created_at": datetime.now().isoformat()
            }

            # Insert into Weaviate
            response = requests.post(
                f"{WEAVIATE_URL}/v1/objects",
                json={
                    "class": "CypherSuccessBank",
                    "properties": data,
                    "vector": embedding
                },
                timeout=10
            )

            if response.status_code == 200:
                success_count += 1
                print(f"  [OK] Seeded: {example['user_query'][:50]}...")
            else:
                print(f"  [WARN] Failed to seed: {response.status_code}")

        except Exception as e:
            print(f"  [ERROR] Error seeding example: {e}")

    print(f"\n[INFO] Seeded {success_count}/{len(seed_examples)} examples")
    return success_count > 0


def main():
    """Main setup function."""
    print("=" * 60)
    print("CYPHER SUCCESS BANK SETUP")
    print("=" * 60)
    print(f"Weaviate URL: {WEAVIATE_URL}")
    print()

    # Step 1: Delete existing collection (if any)
    print("[STEP 1] Cleaning up existing collection...")
    delete_existing_collection()

    # Step 2: Create new collection
    print("\n[STEP 2] Creating CypherSuccessBank collection...")
    if not create_success_bank():
        print("\n[FATAL] Failed to create collection. Exiting.")
        sys.exit(1)

    # Step 3: Verify collection
    print("\n[STEP 3] Verifying collection...")
    if not verify_collection():
        print("\n[FATAL] Collection verification failed. Exiting.")
        sys.exit(1)

    # Step 4: Seed initial examples (optional)
    print("\n[STEP 4] Seeding initial examples (optional)...")
    try:
        seed_initial_examples()
    except Exception as e:
        print(f"[WARN] Seeding skipped due to error: {e}")

    # Step 5: Count documents
    count_documents()

    print("\n" + "=" * 60)
    print("SETUP COMPLETE!")
    print("=" * 60)
    print("\nThe CypherSuccessBank is ready for use.")
    print("Successful queries will be automatically stored here.")
    print("=" * 60)


if __name__ == "__main__":
    main()
