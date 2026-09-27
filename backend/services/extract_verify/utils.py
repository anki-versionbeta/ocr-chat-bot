"""
PDF to JPEG page rendering utility.
Uses PyMuPDF (fitz) for fast, high-quality page rendering.
"""
import base64
import logging
from typing import Dict, List, Optional

import fitz  # PyMuPDF

logger = logging.getLogger("extract_verify.utils")


def get_pdf_page_count(pdf_path: str) -> int:
    """Get total page count of a PDF."""
    doc = fitz.open(pdf_path)
    count = doc.page_count
    doc.close()
    return count


def pdf_to_jpeg_pages(
    pdf_path: str,
    pages: Optional[List[int]] = None,
    zoom: float = 1.5,
    quality: int = 85,
) -> Dict[int, str]:
    """
    Render PDF pages as base64 JPEG strings.

    Args:
        pdf_path: Path to the PDF file.
        pages: List of 1-indexed page numbers to render. None = all pages.
        zoom: Zoom factor (1.5 = 918x1188px for letter-size, ~150-300KB JPEG).
        quality: JPEG quality (1-100). 85 is visually identical for text.

    Returns:
        Dict mapping page_number (1-indexed) → base64 JPEG string.
    """
    doc = fitz.open(pdf_path)
    total = doc.page_count
    matrix = fitz.Matrix(zoom, zoom)

    if pages is None:
        pages = list(range(1, total + 1))

    result = {}
    for page_num in pages:
        if page_num < 1 or page_num > total:
            logger.warning(f"Skipping invalid page {page_num} (document has {total} pages)")
            continue
        try:
            page = doc[page_num - 1]  # fitz uses 0-indexed
            pix = page.get_pixmap(matrix=matrix)
            img_bytes = pix.tobytes("jpeg", jpg_quality=quality)
            result[page_num] = base64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to render page {page_num}: {e}")

    doc.close()
    logger.info(f"Rendered {len(result)}/{len(pages)} pages as JPEG (zoom={zoom}, quality={quality})")
    return result


def estimate_payload_size(images: Dict[int, str]) -> int:
    """Estimate total base64 payload size in bytes."""
    return sum(len(v) for v in images.values())
