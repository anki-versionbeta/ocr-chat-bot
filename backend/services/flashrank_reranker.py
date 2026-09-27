"""
FlashRank Reranker Service for RAG Pipeline

Cross-encoder reranking using FlashRank to improve retrieval precision.
- CPU only, ~4MB model, no GPU/Torch needed
- Model: ms-marco-TinyBERT-L-2-v2
- Latency: ~10-50ms for 50-100 passages

Usage:
    from services.flashrank_reranker import get_reranker

    reranker = get_reranker()
    reranked = reranker.rerank(query, results, top_k=5)
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("ocr-chatbot.flashrank_reranker")

# Configuration
@dataclass
class FlashRankConfig:
    MODEL_NAME: str = "ms-marco-MiniLM-L-12-v2"  # ~120MB, 12 layers, production-grade accuracy
    CACHE_DIR: str = "/tmp/flashrank_cache"
    BODY_LIMIT: int = 2048  # chars sent to cross-encoder (512 was too small for large table chunks)
    MAX_PASSAGES: int = 100  # max passages to rerank


CONFIG = FlashRankConfig()

# Try to import FlashRank
try:
    from flashrank import Ranker, RerankRequest
    FLASHRANK_AVAILABLE = True
except ImportError:
    FLASHRANK_AVAILABLE = False
    logger.warning("FlashRank not installed. Install with: pip install flashrank")


class FlashRankReranker:
    """
    Cross-encoder reranker using FlashRank.

    Improves retrieval precision by reranking results using a cross-encoder
    that considers both query and passage together.
    """

    def __init__(self):
        self.ranker = None
        self.is_available = False

        if FLASHRANK_AVAILABLE:
            try:
                logger.info(f"Loading FlashRank model: {CONFIG.MODEL_NAME}")
                # Disable SSL verification for model download behind corporate proxy
                import os
                os.environ.setdefault('CURL_CA_BUNDLE', '')
                self.ranker = Ranker(
                    model_name=CONFIG.MODEL_NAME,
                    cache_dir=CONFIG.CACHE_DIR,
                )
                self.is_available = True
                logger.info("FlashRank reranker initialized successfully")
            except Exception as e:
                logger.error(f"FlashRank initialization failed: {e}")
                self.is_available = False

    def _pack_passage(self, result: Dict) -> str:
        """
        Pack metadata + content for cross-encoder.

        Format: "Page: X | Type: Y\n<content>"
        """
        page = result.get('page', result.get('page_num', 0))
        chunk_type = result.get('chunk_type', 'text')

        header = f"Page: {page} | Type: {chunk_type}"

        # Get content from various possible keys
        content = (
            result.get('content') or
            result.get('text') or
            result.get('chunk_text') or
            ''
        )
        body = content[:CONFIG.BODY_LIMIT]

        return f"{header}\n{body}"

    def rerank(
        self,
        query: str,
        results: List[Dict],
        top_k: int = 5
    ) -> List[Dict]:
        """
        Rerank results using FlashRank cross-encoder.

        Args:
            query: The search query
            results: List of search results to rerank
            top_k: Number of results to return after reranking

        Returns:
            Reranked results with flashrank_score added
        """
        if not self.is_available or not self.ranker:
            logger.debug("FlashRank not available, returning original results")
            return results[:top_k]

        if not results or top_k <= 0:
            return []

        # Limit passages to rerank
        to_rerank = results[:CONFIG.MAX_PASSAGES]

        try:
            # Prepare passages for FlashRank
            passages = [
                {
                    "id": i,
                    "text": self._pack_passage(r),
                    "meta": {
                        "chunk_id": r.get('chunk_id', ''),
                        "page": r.get('page', r.get('page_num', 0))
                    },
                }
                for i, r in enumerate(to_rerank)
            ]

            # Rerank
            reranked = self.ranker.rerank(
                RerankRequest(query=query, passages=passages)
            )

            # Build final results with flashrank scores
            final = []
            for item in reranked[:top_k]:
                idx = int(item["id"])
                original = to_rerank[idx].copy()
                original["flashrank_score"] = float(item["score"])
                final.append(original)

            logger.debug(f"Reranked {len(to_rerank)} results, returning top {len(final)}")
            return final

        except Exception as e:
            logger.error(f"FlashRank rerank error: {e}")
            return results[:top_k]


# Global instance
_reranker_instance: Optional[FlashRankReranker] = None


def get_reranker() -> FlashRankReranker:
    """Get or create the global FlashRank reranker instance."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = FlashRankReranker()
    return _reranker_instance
