"""
Gemini Vision API client with retry, exponential backoff, model fallback, and batch processing.
Communicates via Iliad LiteLLM proxy (OpenAI-compatible format).
"""
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger("extract_verify.gemini_client")

ILIAD_URL = os.getenv("ILIAD_URL", "https://api-epic.ir-gateway.abbvienet.com/iliad")
ILIAD_API_KEY = REDACTED

# Model preference order: stable GA first, fast fallback second
MODELS = [
    "gemini-2.5-pro",       # Stable GA, high RPM, excellent vision
    "gemini-2.5-flash",     # Fastest, highest RPM, good quality
]

MAX_PAGES_PER_CALL = 30    # ~9MB payload at 300KB/page, well within limits
MAX_RETRIES = 3
BACKOFF_BASE = 2           # Exponential backoff: 2s, 4s, 8s
BACKOFF_MAX = 16
COOLDOWN_BETWEEN_BATCHES = 2  # seconds between batch calls
REQUEST_TIMEOUT = 180      # 3 minutes per call (large multi-image requests)


class GeminiClient:
    """
    Gemini Vision client for multi-page document processing.

    Sends multiple page images + prompt in a single API call.
    Handles retries, exponential backoff, and model fallback.
    """

    def __init__(
        self,
        models: Optional[List[str]] = None,
        max_pages_per_call: int = MAX_PAGES_PER_CALL,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.models = models or MODELS
        self.max_pages_per_call = max_pages_per_call
        self.api_url = api_url or ILIAD_URL
        self.api_key = api_key or ILIAD_API_KEY
        self._last_model_used = ""

    @property
    def last_model_used(self) -> str:
        return self._last_model_used

    def call_with_images(
        self,
        images: Dict[int, str],
        prompt: str,
        max_tokens: int = 8000,
        temperature: float = 0,
    ) -> str:
        """
        Send multiple page images + prompt to Gemini in a single call.

        Args:
            images: Dict of page_number → base64 JPEG string.
            prompt: The instruction prompt.
            max_tokens: Maximum response tokens.
            temperature: Model temperature (0 = deterministic).

        Returns:
            Raw text response from Gemini.

        Raises:
            RuntimeError: If all models and retries are exhausted.
        """
        # Build multi-image message content
        content_parts = []
        for page_num in sorted(images.keys()):
            content_parts.append({
                "type": "text",
                "text": f"[Page {page_num}]"
            })
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{images[page_num]}"}
            })
        content_parts.append({"type": "text", "text": prompt})

        messages = [{"role": "user", "content": content_parts}]

        # Try each model with retries
        for model in self.models:
            for attempt in range(MAX_RETRIES):
                try:
                    logger.info(
                        f"Gemini call: model={model}, pages={len(images)}, "
                        f"attempt={attempt+1}/{MAX_RETRIES}"
                    )
                    response = requests.post(
                        f"{self.api_url}/api/llm/v1/chat/completions",
                        headers={
                            "X-API-Key": self.api_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "max_tokens": max_tokens,
                            "temperature": temperature,
                        },
                        timeout=REQUEST_TIMEOUT,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        self._last_model_used = model
                        logger.info(
                            f"Gemini success: model={model}, "
                            f"response_len={len(content)} chars"
                        )
                        return content

                    elif response.status_code in (429, 500, 502, 503):
                        wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                        logger.warning(
                            f"Gemini {response.status_code} on {model}, "
                            f"retrying in {wait}s (attempt {attempt+1})"
                        )
                        time.sleep(wait)
                        continue

                    else:
                        logger.error(
                            f"Gemini error {response.status_code} on {model}: "
                            f"{response.text[:300]}"
                        )
                        break  # Non-retryable error, try next model

                except requests.exceptions.Timeout:
                    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_MAX)
                    logger.warning(f"Gemini timeout on {model}, retrying in {wait}s")
                    time.sleep(wait)
                    continue

                except Exception as e:
                    logger.error(f"Gemini unexpected error on {model}: {e}")
                    break  # Try next model

            logger.warning(f"Model {model} exhausted all retries, trying next model")

        raise RuntimeError("All Gemini models failed after retries")

    def call_batched(
        self,
        all_images: Dict[int, str],
        prompt: str,
        max_tokens: int = 8000,
        progress_cb: Optional[Callable] = None,
        context_pages: Optional[List[int]] = None,
    ) -> List[str]:
        """
        Process 100+ pages by splitting into batches of max_pages_per_call.
        Calls sequentially with cooldown between batches to avoid rate limits.

        Args:
            all_images: Dict of all page_number → base64 JPEG strings.
            prompt: The instruction prompt (applied to each batch).
            max_tokens: Max tokens per batch response.
            progress_cb: Optional callback(batch_num, total_batches, pages_done, total_pages).
            context_pages: Pages to prepend to EVERY batch (e.g., materials/equipment tables).
                           These are included for context but marked as reference-only.

        Returns:
            List of raw text responses, one per batch.
        """
        sorted_pages = sorted(all_images.keys())
        batches = []
        for i in range(0, len(sorted_pages), self.max_pages_per_call):
            batch_pages = sorted_pages[i:i + self.max_pages_per_call]
            batches.append(batch_pages)

        total_batches = len(batches)
        responses = []
        pages_done = 0

        logger.info(
            f"Batched processing: {len(sorted_pages)} pages in "
            f"{total_batches} batches (max {self.max_pages_per_call}/batch)"
        )

        for batch_idx, batch_pages in enumerate(batches):
            batch_images = {p: all_images[p] for p in batch_pages}

            # Prepend context pages (e.g., materials table) to every batch
            if context_pages:
                for cp in context_pages:
                    if cp in all_images and cp not in batch_images:
                        batch_images[cp] = all_images[cp]

            page_range = f"{batch_pages[0]}-{batch_pages[-1]}"
            ctx_note = ""
            if context_pages:
                ctx_note = (
                    f"\nPages {','.join(str(p) for p in context_pages)} are included as "
                    f"REFERENCE CONTEXT (Materials/Equipment tables). "
                    f"Focus your analysis on pages {page_range}.\n"
                )

            batch_prompt = (
                f"These are pages {page_range} of the document.{ctx_note}\n\n{prompt}"
            )

            try:
                response = self.call_with_images(
                    batch_images, batch_prompt, max_tokens=max_tokens
                )
                responses.append(response)
                pages_done += len(batch_pages)

                if progress_cb:
                    progress_cb(batch_idx + 1, total_batches, pages_done, len(sorted_pages))

                logger.info(
                    f"Batch {batch_idx+1}/{total_batches} complete "
                    f"(pages {page_range}, {pages_done}/{len(sorted_pages)} total)"
                )

            except RuntimeError as e:
                logger.error(f"Batch {batch_idx+1} failed: {e}")
                responses.append("")  # Empty response for failed batch
                pages_done += len(batch_pages)

            # Cooldown between batches (skip after last batch)
            if batch_idx < total_batches - 1:
                time.sleep(COOLDOWN_BETWEEN_BATCHES)

        return responses
