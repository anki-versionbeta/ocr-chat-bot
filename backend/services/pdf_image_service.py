"""
PDF Image Service - Phase 5 PDF Viewer Support

Converts PDF pages to WebP images on-demand with caching.
Uses PyMuPDF (fitz) for rendering.

Created: February 2026
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import fitz  # PyMuPDF

from services.database import cache_pdf_page, get_cached_pdf_page

logger = logging.getLogger("ocr-chatbot.pdf_image_service")


class PDFImageService:
    """Service for converting PDF pages to images with caching."""

    def __init__(self, static_dir: str = None, dpi: int = 150):
        """
        Initialize PDF image service.

        Args:
            static_dir: Directory to store generated images
            dpi: Resolution for rendering (150 = good quality, reasonable size)
        """
        if static_dir is None:
            backend_dir = Path(__file__).parent.parent
            static_dir = backend_dir / "static" / "pdf_pages"

        self.static_dir = Path(static_dir)
        self.static_dir.mkdir(parents=True, exist_ok=True)
        self.dpi = dpi
        self.zoom = dpi / 72  # PDF default is 72 DPI

        logger.info(f"PDF Image Service initialized: static_dir={self.static_dir}, dpi={dpi}")

    def get_pdf_path(self, process_id: str, document_name: str = None) -> Optional[str]:
        """
        Get the PDF file path for a given process_id.

        The PDF is stored in backend/temp/{document_name}.pdf
        We need to look up document_name from chat_documents table.

        Args:
            process_id: The Weaviate process_id
            document_name: Optional document name if already known

        Returns:
            Full path to the PDF file, or None if not found
        """
        from services.database import get_db_cursor

        # If document_name not provided, look it up
        if document_name is None:
            with get_db_cursor(commit=False) as cursor:
                cursor.execute("""
                    SELECT document_name, file_path
                    FROM chat_documents
                    WHERE process_id = %s
                    LIMIT 1
                """, [process_id])
                row = cursor.fetchone()

                if row:
                    # Try file_path first if stored
                    if row.get('file_path') and os.path.exists(row['file_path']):
                        return row['file_path']
                    document_name = row.get('document_name')

        if not document_name:
            logger.warning(f"No document found for process_id: {process_id}")
            return None

        # Construct path in temp directory
        backend_dir = Path(__file__).parent.parent
        temp_dir = backend_dir / "temp"

        # Try with .pdf extension first
        pdf_path = temp_dir / f"{document_name}.pdf"
        if pdf_path.exists():
            return str(pdf_path)

        # Try without extension if name already has .pdf
        if document_name.lower().endswith('.pdf'):
            pdf_path = temp_dir / document_name
            if pdf_path.exists():
                return str(pdf_path)

        # Try just the document name without extension
        base_name = document_name.rsplit('.', 1)[0] if '.' in document_name else document_name
        pdf_path = temp_dir / f"{base_name}.pdf"
        if pdf_path.exists():
            return str(pdf_path)

        logger.warning(f"PDF file not found for document: {document_name}")
        return None

    def get_page_image(
        self,
        process_id: str,
        page_num: int,
        document_name: str = None
    ) -> Dict[str, Any]:
        """
        Get a PDF page as a WebP image.

        - Checks cache first (database + file system)
        - Generates on-demand if not cached
        - Returns URL path for frontend to fetch

        Args:
            process_id: The document process_id (Weaviate filter key)
            page_num: Page number (1-indexed)
            document_name: Optional document name if known

        Returns:
            Dict with imageUrl, width, height, cached

        Raises:
            FileNotFoundError: If PDF not found
            ValueError: If page_num invalid
        """
        # Check database cache first
        cached = get_cached_pdf_page(process_id, page_num)

        if cached and cached.get('image_path'):
            image_path = Path(cached['image_path'])
            if image_path.exists():
                logger.debug(f"Cache HIT: {process_id} page {page_num}")
                return {
                    "imageUrl": f"/static/pdf_pages/{process_id}/page_{page_num}.webp",
                    "width": cached.get('width', 0),
                    "height": cached.get('height', 0),
                    "cached": True
                }

        # Cache miss - generate image
        logger.info(f"Cache MISS: {process_id} page {page_num} - generating...")

        # Get PDF path
        pdf_path = self.get_pdf_path(process_id, document_name)

        if not pdf_path or not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found for process_id: {process_id}")

        # Open PDF
        doc = fitz.open(pdf_path)

        try:
            # Validate page number (1-indexed input, 0-indexed internally)
            if page_num < 1 or page_num > len(doc):
                raise ValueError(f"Invalid page number: {page_num}. Document has {len(doc)} pages.")

            page = doc[page_num - 1]  # 0-indexed

            # Render at configured DPI
            matrix = fitz.Matrix(self.zoom, self.zoom)
            pixmap = page.get_pixmap(matrix=matrix)

            # Ensure output directory exists
            doc_dir = self.static_dir / process_id
            doc_dir.mkdir(parents=True, exist_ok=True)

            # Save as WebP
            image_filename = f"page_{page_num}.webp"
            image_path = doc_dir / image_filename
            pixmap.save(str(image_path))

            width = pixmap.width
            height = pixmap.height
            file_size = image_path.stat().st_size

            # Cache in database
            cache_pdf_page(
                document_id=process_id,
                page_num=page_num,
                image_path=str(image_path),
                width=width,
                height=height,
                file_size=file_size
            )

            logger.info(f"Generated page image: {image_path} ({width}x{height}, {file_size} bytes)")

            return {
                "imageUrl": f"/static/pdf_pages/{process_id}/page_{page_num}.webp",
                "width": width,
                "height": height,
                "cached": False
            }

        finally:
            doc.close()

    def get_document_metadata(self, process_id: str, document_name: str = None) -> Dict[str, Any]:
        """
        Get document metadata including page count.

        Args:
            process_id: The document process_id
            document_name: Optional document name if known

        Returns:
            Dict with documentId, documentName, pageCount
        """
        from services.database import get_db_cursor

        # Get document info from database
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT document_id, document_name, page_count, file_path, created_at
                FROM chat_documents
                WHERE process_id = %s
                LIMIT 1
            """, [process_id])
            row = cursor.fetchone()

        if not row:
            raise FileNotFoundError(f"Document not found for process_id: {process_id}")

        doc_name = row.get('document_name', 'Unknown')
        page_count = row.get('page_count')

        # If page_count not stored, get from PDF
        if not page_count:
            pdf_path = self.get_pdf_path(process_id, doc_name)
            if pdf_path and os.path.exists(pdf_path):
                doc = fitz.open(pdf_path)
                page_count = len(doc)
                doc.close()

                # Update database with page count
                with get_db_cursor() as cursor:
                    cursor.execute("""
                        UPDATE chat_documents
                        SET page_count = %s
                        WHERE process_id = %s
                    """, [page_count, process_id])

        return {
            "documentId": row.get('document_id', process_id),
            "documentName": doc_name,
            "pageCount": page_count or 0,
            "processId": process_id,
            "createdAt": row.get('created_at').isoformat() if row.get('created_at') else None
        }

    def preload_pages(
        self,
        process_id: str,
        pages: list,
        document_name: str = None
    ) -> int:
        """
        Preload multiple pages in background.

        Args:
            process_id: The document process_id
            pages: List of page numbers to preload
            document_name: Optional document name if known

        Returns:
            Number of pages successfully preloaded
        """
        success_count = 0

        for page_num in pages:
            try:
                self.get_page_image(process_id, page_num, document_name)
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to preload page {page_num}: {e}")

        return success_count

    def clear_cache(self, process_id: str) -> int:
        """
        Clear cached images for a document.

        Args:
            process_id: The document process_id

        Returns:
            Number of files deleted
        """
        import shutil
        from services.database import get_db_cursor

        doc_dir = self.static_dir / process_id
        deleted = 0

        if doc_dir.exists():
            for f in doc_dir.iterdir():
                f.unlink()
                deleted += 1
            doc_dir.rmdir()

        # Clear database cache
        with get_db_cursor() as cursor:
            cursor.execute("""
                DELETE FROM pdf_page_cache
                WHERE document_id = %s
            """, [process_id])

        logger.info(f"Cleared cache for {process_id}: {deleted} files deleted")
        return deleted


# Singleton instance
_pdf_image_service: Optional[PDFImageService] = None


def get_pdf_image_service() -> PDFImageService:
    """Get the singleton PDF image service instance."""
    global _pdf_image_service

    if _pdf_image_service is None:
        _pdf_image_service = PDFImageService()

    return _pdf_image_service
