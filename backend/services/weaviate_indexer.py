"""
Weaviate Indexer for Phase 3 - Document Chunk Storage

This module handles indexing document chunks to Weaviate with:
1. Schema creation/verification for DocumentChunk collection
2. Embedding generation using text-embedding-3-large
3. Batch upload of chunks with vectors

Uses the Weaviate Python client v4 API.
"""

import os
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# Weaviate configuration
WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://10.242.190.53:8080")

# Iliad API configuration (for embeddings)
ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072  # text-embedding-3-large has 3072 dimensions


class WeaviateIndexer:
    """
    Indexes document chunks to Weaviate with embeddings.
    """

    def __init__(self, weaviate_url: str = None):
        """
        Initialize the indexer.

        Args:
            weaviate_url: Weaviate server URL (defaults to WEAVIATE_URL env var)
        """
        self.weaviate_url = weaviate_url or WEAVIATE_URL
        self.collection_name = "DocumentChunk"

        logger.info(f"WeaviateIndexer initialized with URL: {self.weaviate_url}")

    def check_connection(self) -> bool:
        """Check if Weaviate is reachable."""
        try:
            response = requests.get(f"{self.weaviate_url}/v1/.well-known/ready", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Weaviate connection check failed: {e}")
            return False

    def schema_exists(self) -> bool:
        """Check if DocumentChunk schema exists."""
        try:
            response = requests.get(
                f"{self.weaviate_url}/v1/schema/{self.collection_name}",
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Schema check failed: {e}")
            return False

    def create_schema(self) -> bool:
        """
        Create the DocumentChunk schema if it doesn't exist.

        Returns:
            True if schema exists or was created successfully
        """
        if self.schema_exists():
            logger.info("DocumentChunk schema already exists")
            return True

        logger.info("Creating DocumentChunk schema...")

        schema = {
            "class": self.collection_name,
            "description": "Stores document chunks with embeddings and grounding data for RAG",
            "vectorizer": "none",
            "vectorIndexType": "hnsw",
            "vectorIndexConfig": {
                "distance": "cosine",
                "efConstruction": 128,
                "maxConnections": 64
            },
            "invertedIndexConfig": {
                "bm25": {
                    "b": 0.75,
                    "k1": 1.2
                },
                "stopwords": {
                    "preset": "en"
                }
            },
            "properties": [
                # Identification fields
                {"name": "document_id", "dataType": ["text"], "description": "Links to PostgreSQL chat_documents"},
                {"name": "process_id", "dataType": ["text"], "description": "Unique UUID for session isolation"},
                {"name": "chunk_id", "dataType": ["text"], "description": "Unique chunk identifier"},
                {"name": "page", "dataType": ["int"], "description": "Page number (1-indexed)"},
                {"name": "chunk_index", "dataType": ["int"], "description": "Reading order (0, 1, 2...)"},

                # Chunk type fields
                {"name": "chunk_type", "dataType": ["text"], "description": "Type: 'text' or 'table'"},
                {"name": "layout_type", "dataType": ["text"], "description": "AWS LAYOUT type"},

                # Search field
                {"name": "content", "dataType": ["text"], "description": "Plain text for BM25 keyword search"},

                # Bounding box fields
                {"name": "bbox_left", "dataType": ["number"], "description": "Normalized left coordinate (0-1)"},
                {"name": "bbox_top", "dataType": ["number"], "description": "Normalized top coordinate (0-1)"},
                {"name": "bbox_right", "dataType": ["number"], "description": "Normalized right coordinate (0-1)"},
                {"name": "bbox_bottom", "dataType": ["number"], "description": "Normalized bottom coordinate (0-1)"},

                # Grounding maps
                {"name": "line_grounding", "dataType": ["text"], "description": "JSON: Line-level bboxes for TEXT chunks"},
                {"name": "cell_grounding", "dataType": ["text"], "description": "JSON: Cell-level bboxes for TABLE chunks"},

                # Markdown
                {"name": "markdown", "dataType": ["text"], "description": "HTML with cell IDs for Claude parsing"},

                # Metadata fields
                {"name": "filename", "dataType": ["text"], "description": "Original filename"},
                {"name": "document_type", "dataType": ["text"], "description": "Document type: COA, HBR, etc."},
                {"name": "document_summary", "dataType": ["text"], "description": "AI-generated summary"},
                {"name": "keywords", "dataType": ["text"], "description": "Comma-separated keywords"},
                {"name": "source", "dataType": ["text"], "description": "Source identifier"},
                {"name": "username", "dataType": ["text"], "description": "Username who uploaded"},
                {"name": "created_at", "dataType": ["date"], "description": "Index timestamp"}
            ]
        }

        try:
            response = requests.post(
                f"{self.weaviate_url}/v1/schema",
                json=schema,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                logger.info("DocumentChunk schema created successfully")
                return True
            else:
                logger.error(f"Schema creation failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Schema creation error: {e}")
            return False

    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text using Iliad API.

        Args:
            text: Text to embed

        Returns:
            List of floats (1536 dimensions) or None on error
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None

        try:
            # Use the correct Iliad embed endpoint format: /api/v1/embed/{model}
            response = requests.post(
                f"{ILIAD_URL}/api/v1/embed/{EMBEDDING_MODEL}",
                headers={
                    "x-api-key": ILIAD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "input": [text[:8000]]  # Truncate to avoid token limits, must be a list
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                # Response format: {"embeddings": [[...], [...], ...]}
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
                else:
                    logger.error(f"No embeddings in response: {data}")
                    return None
            else:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Embedding generation error: {e}")
            return None

    def generate_embeddings_batch_api(self, texts: List[str], retry_with_smaller: bool = True) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in a SINGLE API call (true batch).

        The Iliad API supports multiple inputs in one call - much faster than 1-by-1.
        If batch fails and retry_with_smaller=True, automatically retries with smaller batches.

        Args:
            texts: List of texts to embed (max 2048 per Iliad docs)
            retry_with_smaller: If True, retry with smaller batches on failure

        Returns:
            List of embeddings (or None for failed items)
        """
        if not texts:
            return []

        # Truncate texts to avoid token limits
        truncated_texts = [text[:8000] if text else "" for text in texts]

        try:
            response = requests.post(
                f"{ILIAD_URL}/api/v1/embed/{EMBEDDING_MODEL}",
                headers={
                    "x-api-key": ILIAD_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "input": truncated_texts  # Send ALL texts in one call
                },
                timeout=180  # Longer timeout for large batches
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                return embeddings if embeddings else [None] * len(texts)
            else:
                logger.warning(f"Batch embedding API error: {response.status_code} - {response.text[:200]}")

                # Fallback: retry with smaller batches
                if retry_with_smaller and len(texts) > 10:
                    logger.info(f"Retrying with smaller batches (splitting {len(texts)} texts in half)...")
                    mid = len(texts) // 2
                    first_half = self.generate_embeddings_batch_api(texts[:mid], retry_with_smaller=True)
                    second_half = self.generate_embeddings_batch_api(texts[mid:], retry_with_smaller=True)
                    return first_half + second_half

                return [None] * len(texts)

        except requests.exceptions.Timeout:
            logger.warning(f"Batch embedding timeout for {len(texts)} texts")

            # Fallback: retry with smaller batches on timeout
            if retry_with_smaller and len(texts) > 10:
                logger.info(f"Timeout - retrying with smaller batches (splitting {len(texts)} texts in half)...")
                mid = len(texts) // 2
                first_half = self.generate_embeddings_batch_api(texts[:mid], retry_with_smaller=True)
                second_half = self.generate_embeddings_batch_api(texts[mid:], retry_with_smaller=True)
                return first_half + second_half

            return [None] * len(texts)

        except Exception as e:
            logger.error(f"Batch embedding error: {e}")

            # Fallback: retry with smaller batches on any error
            if retry_with_smaller and len(texts) > 10:
                logger.info(f"Error - retrying with smaller batches (splitting {len(texts)} texts in half)...")
                mid = len(texts) // 2
                first_half = self.generate_embeddings_batch_api(texts[:mid], retry_with_smaller=True)
                second_half = self.generate_embeddings_batch_api(texts[mid:], retry_with_smaller=True)
                return first_half + second_half

            return [None] * len(texts)

    def generate_embeddings_batch(self, texts: List[str], batch_size: int = 100, max_workers: int = 10) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts using PARALLEL batch API calls.

        Strategy:
        1. Split texts into batches of `batch_size` (e.g., 20 texts per batch)
        2. Call the batch API for each batch IN PARALLEL using ThreadPoolExecutor
        3. Combine results maintaining original order

        Args:
            texts: List of texts to embed
            batch_size: Number of texts per API call (default 20)
            max_workers: Number of parallel API calls (default 5)

        Returns:
            List of embeddings (or None for failed items)
        """
        if not texts:
            return []

        total = len(texts)
        logger.info(f"Generating {total} embeddings with batch_size={batch_size}, parallel_workers={max_workers}")

        # Split into batches
        batches = []
        for i in range(0, total, batch_size):
            batch_texts = texts[i:i + batch_size]
            batches.append((i, batch_texts))  # (start_index, texts)

        # Results placeholder
        all_embeddings = [None] * total
        completed_count = 0

        def process_batch(batch_info):
            start_idx, batch_texts = batch_info
            return start_idx, self.generate_embeddings_batch_api(batch_texts)

        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_batch, batch): batch for batch in batches}

            for future in as_completed(futures):
                try:
                    start_idx, batch_embeddings = future.result()
                    # Place embeddings in correct positions
                    for j, emb in enumerate(batch_embeddings):
                        all_embeddings[start_idx + j] = emb
                    completed_count += len(batch_embeddings)
                    logger.info(f"Generated {completed_count}/{total} embeddings ({100*completed_count//total}%)")
                except Exception as e:
                    logger.error(f"Batch processing error: {e}")

        return all_embeddings

    def index_chunk(self, chunk: Dict[str, Any], embedding: List[float] = None) -> Optional[str]:
        """
        Index a single chunk to Weaviate.

        Args:
            chunk: Chunk data from chunk_transformer
            embedding: Pre-computed embedding (will generate if None)

        Returns:
            Weaviate object UUID or None on error
        """
        # Generate embedding if not provided
        if embedding is None:
            content_for_embedding = self._prepare_embedding_text(chunk)
            embedding = self.generate_embedding(content_for_embedding)

        if embedding is None:
            logger.error(f"Failed to generate embedding for chunk {chunk.get('chunk_id')}")
            return None

        # Prepare the object data
        object_data = {
            "class": self.collection_name,
            "properties": {
                "document_id": chunk.get("document_id", ""),
                "process_id": chunk.get("process_id", ""),
                "chunk_id": chunk.get("chunk_id", ""),
                "page": chunk.get("page", 1),
                "chunk_index": chunk.get("chunk_index", 0),
                "chunk_type": chunk.get("chunk_type", "text"),
                "layout_type": chunk.get("layout_type", ""),
                "content": chunk.get("content", ""),
                "bbox_left": chunk.get("bbox_left", 0),
                "bbox_top": chunk.get("bbox_top", 0),
                "bbox_right": chunk.get("bbox_right", 0),
                "bbox_bottom": chunk.get("bbox_bottom", 0),
                "line_grounding": chunk.get("line_grounding") or "",
                "cell_grounding": chunk.get("cell_grounding") or "",
                "markdown": chunk.get("markdown", ""),
                "filename": chunk.get("filename", ""),
                "document_type": chunk.get("document_type", "COA"),
                "document_summary": chunk.get("document_summary", ""),
                "keywords": chunk.get("keywords", ""),
                "source": chunk.get("source", ""),
                "username": chunk.get("username", ""),
                "created_at": chunk.get("created_at") or datetime.utcnow().isoformat() + "Z"
            },
            "vector": embedding
        }

        try:
            response = requests.post(
                f"{self.weaviate_url}/v1/objects",
                json=object_data,
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("id")
            else:
                logger.error(f"Indexing failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Indexing error: {e}")
            return None

    def index_chunks_parallel(
        self,
        chunks_with_embeddings: List[tuple],
        max_workers: int = 20
    ) -> Dict[str, Any]:
        """
        Index chunks to Weaviate in PARALLEL using ThreadPoolExecutor.

        Args:
            chunks_with_embeddings: List of (chunk, embedding) tuples
            max_workers: Number of parallel indexing threads

        Returns:
            Dict with results
        """
        results = {
            'success': 0,
            'failed': 0,
            'object_ids': [],
            'errors': []
        }

        total = len(chunks_with_embeddings)
        completed = [0]  # Use list to allow modification in nested function

        def index_single(item):
            chunk, embedding = item
            if embedding is None:
                return None, f"No embedding for chunk {chunk.get('chunk_id')}"
            object_id = self.index_chunk(chunk, embedding)
            return object_id, None if object_id else f"Failed to index chunk {chunk.get('chunk_id')}"

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(index_single, item): item for item in chunks_with_embeddings}

            for future in as_completed(futures):
                try:
                    object_id, error = future.result()
                    if object_id:
                        results['success'] += 1
                        results['object_ids'].append(object_id)
                    else:
                        results['failed'] += 1
                        if error:
                            results['errors'].append(error)
                except Exception as e:
                    results['failed'] += 1
                    results['errors'].append(str(e))

                # Log progress every 50 chunks
                completed[0] += 1
                if completed[0] % 50 == 0 or completed[0] == total:
                    logger.info(f"[Weaviate Indexing] {completed[0]}/{total} chunks indexed ({100*completed[0]//total}%)")

        return results

    def index_chunks_batch(
        self,
        chunks: List[Dict[str, Any]],
        username: str = "",
        document_type: str = "COA",
        source: str = "",
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Index multiple chunks to Weaviate with batch processing.

        OPTIMIZED:
        1. Delete existing chunks for this process_id (avoid duplicates)
        2. Generate embeddings in parallel batches
        3. Index chunks to Weaviate in parallel

        Args:
            chunks: List of chunks from chunk_transformer
            username: Username who uploaded
            document_type: Type of document (COA, HBR, etc.)
            source: Source identifier
            progress_callback: Optional callback(progress, message)

        Returns:
            Dict with indexing results
        """
        results = {
            'success': 0,
            'failed': 0,
            'object_ids': [],
            'errors': []
        }

        if not chunks:
            logger.warning("No chunks to index")
            return results

        # Ensure schema exists
        if not self.create_schema():
            results['errors'].append("Failed to create/verify schema")
            return results

        # Add metadata to all chunks
        for chunk in chunks:
            chunk['username'] = username
            chunk['document_type'] = document_type
            chunk['source'] = source

        total_chunks = len(chunks)
        logger.info(f"Indexing {total_chunks} chunks...")

        # Step 1: Generate embeddings in parallel batches
        if progress_callback:
            progress_callback(0, "Generating embeddings (parallel batch)...")

        import time
        embed_start = time.time()

        texts_for_embedding = [self._prepare_embedding_text(c) for c in chunks]
        embeddings = self.generate_embeddings_batch(texts_for_embedding)

        embed_time = time.time() - embed_start
        logger.info(f"Embedding generation took {embed_time:.1f}s for {total_chunks} chunks")

        if progress_callback:
            progress_callback(50, f"Embeddings done in {embed_time:.1f}s. Indexing to Weaviate...")

        # Step 2: Index chunks to Weaviate in PARALLEL
        index_start = time.time()

        # Pair chunks with their embeddings
        chunks_with_embeddings = list(zip(chunks, embeddings))

        # Use parallel indexing
        parallel_results = self.index_chunks_parallel(chunks_with_embeddings, max_workers=20)

        index_time = time.time() - index_start
        logger.info(f"Weaviate indexing took {index_time:.1f}s for {total_chunks} chunks")

        results['success'] = parallel_results['success']
        results['failed'] = parallel_results['failed']
        results['object_ids'] = parallel_results['object_ids']
        results['errors'] = parallel_results['errors']

        if progress_callback:
            progress_callback(100, f"Indexed {results['success']}/{total_chunks} chunks")

        logger.info(f"Indexing complete: {results['success']} success, {results['failed']} failed")
        logger.info(f"Total time: embeddings={embed_time:.1f}s, indexing={index_time:.1f}s")

        return results

    def _prepare_embedding_text(self, chunk: Dict[str, Any]) -> str:
        """
        Prepare chunk content for embedding generation.

        Args:
            chunk: Chunk data

        Returns:
            Text optimized for embedding
        """
        parts = []

        # Add layout type for context
        layout_type = chunk.get('layout_type', '')
        if layout_type:
            parts.append(f"[{layout_type}]")

        # Add main content
        content = chunk.get('content', '')
        if content:
            parts.append(content)

        # Add filename for context
        filename = chunk.get('filename', '')
        if filename:
            parts.append(f"Source: {filename}")

        return ' '.join(parts)

    def search_chunks(
        self,
        query: str,
        process_id: str = None,
        limit: int = 5,
        alpha: float = 0.7,
        page_filter: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search for chunks using hybrid search.

        Args:
            query: Search query
            process_id: Filter by process_id (optional)
            limit: Maximum results
            alpha: Weight for semantic vs keyword (0=keyword, 1=semantic)
            page_filter: Filter by specific page number (optional)

        Returns:
            List of matching chunks with scores
        """
        # Generate query embedding
        query_embedding = self.generate_embedding(query)

        if query_embedding is None:
            logger.error("Failed to generate query embedding")
            return []

        # Build GraphQL where filter with AND conditions
        where_filter = ""
        if process_id and page_filter:
            # Both process_id AND page filter
            where_filter = f'''
                where: {{
                    operator: And,
                    operands: [
                        {{
                            path: ["process_id"],
                            operator: Equal,
                            valueText: "{process_id}"
                        }},
                        {{
                            path: ["page"],
                            operator: Equal,
                            valueInt: {page_filter}
                        }}
                    ]
                }}
            '''
        elif process_id:
            # Only process_id filter
            where_filter = f'''
                where: {{
                    path: ["process_id"],
                    operator: Equal,
                    valueText: "{process_id}"
                }}
            '''
        elif page_filter:
            # Only page filter
            where_filter = f'''
                where: {{
                    path: ["page"],
                    operator: Equal,
                    valueInt: {page_filter}
                }}
            '''

        # Escape query for GraphQL
        escaped_query = query.replace('"', '\\"')

        graphql_query = f'''
        {{
            Get {{
                {self.collection_name}(
                    hybrid: {{
                        query: "{escaped_query}"
                        alpha: {alpha}
                        fusionType: relativeScoreFusion
                        vector: {json.dumps(query_embedding)}
                    }}
                    {where_filter}
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
                    _additional {{
                        score
                    }}
                }}
            }}
        }}
        '''

        try:
            response = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("data", {}).get("Get", {}).get(self.collection_name, [])
                return results
            else:
                logger.error(f"Search failed: {response.status_code} - {response.text}")
                return []

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    def get_all_chunks_for_page(self, process_id: str, page_num: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get ALL chunks for a specific page without keyword filtering.
        Uses a simple where filter — no hybrid search, no embeddings needed.
        Only used by schema extraction service.
        """
        graphql_query = f'''
        {{
            Get {{
                {self.collection_name}(
                    where: {{
                        operator: And,
                        operands: [
                            {{ path: ["process_id"], operator: Equal, valueText: "{process_id}" }},
                            {{ path: ["page"], operator: Equal, valueInt: {page_num} }}
                        ]
                    }}
                    limit: {limit}
                ) {{
                    document_id process_id chunk_id chunk_index page chunk_type layout_type
                    content cell_grounding line_grounding markdown
                    bbox_left bbox_top bbox_right bbox_bottom
                }}
            }}
        }}
        '''

        try:
            response = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("data", {}).get("Get", {}).get(self.collection_name, []) or []
                results.sort(key=lambda x: x.get("chunk_index", 0))
                return results
            else:
                logger.error(f"Get page chunks failed: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Get page chunks error: {e}")
            return []

    def delete_by_process_id(self, process_id: str) -> int:
        """
        Delete all chunks for a given process_id using batch delete API.

        Args:
            process_id: Process ID to delete

        Returns:
            Number of deleted objects
        """
        try:
            # Use the batch delete endpoint (POST with match/where)
            response = requests.post(
                f"{self.weaviate_url}/v1/batch/objects",
                json={
                    "match": {
                        "class": self.collection_name,
                        "where": {
                            "path": ["process_id"],
                            "operator": "Equal",
                            "valueText": process_id
                        }
                    },
                    "output": "minimal"
                },
                params={"delete": "true"},  # This makes it a delete operation
                headers={"Content-Type": "application/json"},
                timeout=120
            )

            if response.status_code == 200:
                data = response.json()
                deleted = data.get("results", {}).get("successful", 0)
                logger.info(f"Deleted {deleted} objects for process_id {process_id}")
                return deleted
            else:
                # Try alternative: delete objects one by one using GraphQL to find IDs first
                logger.warning(f"Batch delete failed ({response.status_code}), trying alternative method...")
                return self._delete_by_process_id_fallback(process_id)

        except Exception as e:
            logger.error(f"Delete error: {e}")
            return self._delete_by_process_id_fallback(process_id)

    def _delete_by_process_id_fallback(self, process_id: str) -> int:
        """Fallback: Find object IDs via GraphQL and delete one by one."""
        try:
            # First get all object IDs for this process_id
            graphql_query = f'''
            {{
                Get {{
                    {self.collection_name}(
                        where: {{
                            path: ["process_id"],
                            operator: Equal,
                            valueText: "{process_id}"
                        }}
                        limit: 10000
                    ) {{
                        _additional {{
                            id
                        }}
                    }}
                }}
            }}
            '''

            response = requests.post(
                f"{self.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
                headers={"Content-Type": "application/json"},
                timeout=60
            )

            if response.status_code != 200:
                logger.error(f"GraphQL query failed: {response.status_code}")
                return 0

            data = response.json()
            results = data.get("data", {}).get("Get", {}).get(self.collection_name, [])

            if not results:
                logger.info(f"No objects found for process_id {process_id}")
                return 0

            # Delete each object by ID
            deleted_count = 0
            total = len(results)
            logger.info(f"Deleting {total} objects for process_id {process_id}...")

            for i, obj in enumerate(results):
                obj_id = obj.get("_additional", {}).get("id")
                if obj_id:
                    del_response = requests.delete(
                        f"{self.weaviate_url}/v1/objects/{self.collection_name}/{obj_id}",
                        timeout=10
                    )
                    if del_response.status_code in [200, 204]:
                        deleted_count += 1

                # Log progress
                if (i + 1) % 100 == 0 or (i + 1) == total:
                    logger.info(f"Deleted {deleted_count}/{total} objects ({100*(i+1)//total}%)")

            logger.info(f"Deleted {deleted_count} objects for process_id {process_id}")
            return deleted_count

        except Exception as e:
            logger.error(f"Fallback delete error: {e}")
            return 0

    def get_chunk_count(self, process_id: str = None) -> int:
        """
        Get count of chunks, optionally filtered by process_id.

        Args:
            process_id: Optional filter

        Returns:
            Count of matching chunks
        """
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
                {self.collection_name}(
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
                f"{self.weaviate_url}/v1/graphql",
                json={"query": graphql_query},
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                count = data.get("data", {}).get("Aggregate", {}).get(self.collection_name, [{}])[0].get("meta", {}).get("count", 0)
                return count
            else:
                logger.error(f"Count query failed: {response.status_code}")
                return 0

        except Exception as e:
            logger.error(f"Count error: {e}")
            return 0


def index_document_chunks(
    chunks: List[Dict[str, Any]],
    username: str,
    document_type: str = "COA",
    source: str = None,
    progress_callback=None
) -> Dict[str, Any]:
    """
    Convenience function to index document chunks.

    Args:
        chunks: List of chunks from chunk_transformer
        username: Username who uploaded
        document_type: Type of document
        source: Source identifier (defaults to {document_type}_{username})
        progress_callback: Optional callback(progress, message)

    Returns:
        Indexing results dict
    """
    if source is None:
        source = f"{document_type.lower()}_{username}"

    indexer = WeaviateIndexer()
    return indexer.index_chunks_batch(
        chunks=chunks,
        username=username,
        document_type=document_type,
        source=source,
        progress_callback=progress_callback
    )


if __name__ == '__main__':
    # Test connection and schema
    indexer = WeaviateIndexer()

    print(f"Weaviate URL: {indexer.weaviate_url}")
    print(f"Connection OK: {indexer.check_connection()}")
    print(f"Schema exists: {indexer.schema_exists()}")

    if not indexer.schema_exists():
        print(f"Creating schema: {indexer.create_schema()}")

    print(f"Total chunks: {indexer.get_chunk_count()}")
