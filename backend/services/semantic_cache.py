"""
Semantic Cache for Phase 4 - Multi-Agent RAG Orchestration

This module provides caching for RAG queries based on semantic similarity.
When a similar query (>95% similarity) is received for the same document,
the cached response is returned instead of re-processing.

Features:
- Per-document (process_id) caching
- TTL-based expiration (30 minutes default)
- Semantic similarity matching using embeddings
- Thread-safe operations
"""

import time
import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from threading import Lock
from datetime import datetime

logger = logging.getLogger("ocr-chatbot.semantic_cache")


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Cosine similarity score (0-1)
    """
    if not vec1 or not vec2:
        return 0.0

    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


class SemanticCache:
    """
    Cache responses based on query semantic similarity.

    Each process_id (document) has its own cache entries.
    Queries are matched by embedding similarity, not exact string match.
    """

    def __init__(
        self,
        ttl_minutes: int = 30,
        similarity_threshold: float = 0.95,
        max_entries_per_document: int = 100
    ):
        """
        Initialize the semantic cache.

        Args:
            ttl_minutes: Time-to-live for cache entries in minutes
            similarity_threshold: Minimum similarity to consider a cache hit (0-1)
            max_entries_per_document: Maximum cache entries per document
        """
        self.ttl = ttl_minutes * 60  # Convert to seconds
        self.threshold = similarity_threshold
        self.max_entries = max_entries_per_document

        # Cache structure: {process_id: [(embedding, response, timestamp, query_text), ...]}
        self._cache: Dict[str, List[Tuple[List[float], Dict, float, str]]] = {}
        self._lock = Lock()

        logger.info(f"SemanticCache initialized: TTL={ttl_minutes}min, threshold={similarity_threshold}")

    def get(
        self,
        process_id: str,
        query_embedding: List[float],
        query_text: str = None
    ) -> Optional[Dict]:
        """
        Check if a similar query exists in cache.

        Args:
            process_id: Document identifier for filtering
            query_embedding: Embedding vector of the query
            query_text: Original query text (for logging)

        Returns:
            Cached response dict if found, None otherwise
        """
        with self._lock:
            if process_id not in self._cache:
                return None

            current_time = time.time()
            valid_entries = []
            best_match = None
            best_similarity = 0.0

            for entry in self._cache[process_id]:
                embedding, response, timestamp, cached_query = entry

                # Check TTL
                if current_time - timestamp > self.ttl:
                    logger.debug(f"Cache entry expired: '{cached_query[:50]}...'")
                    continue

                valid_entries.append(entry)

                # Check similarity
                similarity = cosine_similarity(query_embedding, embedding)

                if similarity >= self.threshold and similarity > best_similarity:
                    best_similarity = similarity
                    best_match = response
                    logger.info(
                        f"Cache HIT: '{query_text[:50] if query_text else 'query'}...' "
                        f"matched '{cached_query[:50]}...' (similarity={similarity:.3f})"
                    )

            # Update cache with only valid entries
            self._cache[process_id] = valid_entries

            if best_match:
                # Add cache hit metadata
                best_match = best_match.copy()
                best_match['_cache_hit'] = True
                best_match['_cache_similarity'] = best_similarity

            return best_match

    def set(
        self,
        process_id: str,
        query_embedding: List[float],
        response: Dict,
        query_text: str = ""
    ) -> None:
        """
        Store a response in the cache.

        Args:
            process_id: Document identifier
            query_embedding: Embedding vector of the query
            response: The response to cache
            query_text: Original query text (for logging/debugging)
        """
        with self._lock:
            if process_id not in self._cache:
                self._cache[process_id] = []

            # Check if very similar query already exists
            for i, (embedding, _, _, _) in enumerate(self._cache[process_id]):
                similarity = cosine_similarity(query_embedding, embedding)
                if similarity >= 0.99:  # Almost identical query
                    # Update existing entry instead of adding new
                    self._cache[process_id][i] = (
                        query_embedding,
                        response,
                        time.time(),
                        query_text
                    )
                    logger.debug(f"Cache UPDATE: '{query_text[:50]}...'")
                    return

            # Add new entry
            self._cache[process_id].append((
                query_embedding,
                response,
                time.time(),
                query_text
            ))

            # Enforce max entries limit (remove oldest)
            if len(self._cache[process_id]) > self.max_entries:
                self._cache[process_id] = self._cache[process_id][-self.max_entries:]
                logger.debug(f"Cache trimmed for process_id={process_id}")

            logger.debug(f"Cache SET: '{query_text[:50]}...' for process_id={process_id}")

    def invalidate(self, process_id: str) -> int:
        """
        Invalidate all cache entries for a document.

        Args:
            process_id: Document identifier

        Returns:
            Number of entries removed
        """
        with self._lock:
            if process_id in self._cache:
                count = len(self._cache[process_id])
                del self._cache[process_id]
                logger.info(f"Cache invalidated: {count} entries for process_id={process_id}")
                return count
            return 0

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Total number of entries removed
        """
        with self._lock:
            total = sum(len(entries) for entries in self._cache.values())
            self._cache.clear()
            logger.info(f"Cache cleared: {total} total entries")
            return total

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        with self._lock:
            current_time = time.time()
            removed = 0

            for process_id in list(self._cache.keys()):
                original_count = len(self._cache[process_id])
                self._cache[process_id] = [
                    entry for entry in self._cache[process_id]
                    if current_time - entry[2] <= self.ttl
                ]
                removed += original_count - len(self._cache[process_id])

                # Remove empty process_id entries
                if not self._cache[process_id]:
                    del self._cache[process_id]

            if removed > 0:
                logger.info(f"Cache cleanup: {removed} expired entries removed")

            return removed

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        with self._lock:
            total_entries = sum(len(entries) for entries in self._cache.values())
            documents = len(self._cache)

            # Calculate oldest and newest entry timestamps
            oldest = float('inf')
            newest = 0

            for entries in self._cache.values():
                for _, _, timestamp, _ in entries:
                    oldest = min(oldest, timestamp)
                    newest = max(newest, timestamp)

            return {
                'total_entries': total_entries,
                'documents_cached': documents,
                'ttl_minutes': self.ttl // 60,
                'similarity_threshold': self.threshold,
                'oldest_entry_age_seconds': time.time() - oldest if oldest != float('inf') else 0,
                'newest_entry_age_seconds': time.time() - newest if newest != 0 else 0
            }


# Global cache instance
_cache_instance: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """Get or create the global semantic cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance


def reset_semantic_cache() -> None:
    """Reset the global cache instance (for testing)."""
    global _cache_instance
    if _cache_instance:
        _cache_instance.clear()
    _cache_instance = None
