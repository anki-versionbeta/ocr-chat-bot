"""
Extract & Verify Engine — Standalone module for document extraction and verification.
Uses Gemini Vision to process 100+ page PDFs without OCR/chunking dependencies.
"""
from .engine import ExtractVerifyEngine
from .models import (
    ExtractionTask, VerificationTask, ExtractVerifyRequest,
    ExtractionResult, VerificationResult, ExtractVerifyResponse,
)

__all__ = [
    "ExtractVerifyEngine",
    "ExtractionTask", "VerificationTask", "ExtractVerifyRequest",
    "ExtractionResult", "VerificationResult", "ExtractVerifyResponse",
]
