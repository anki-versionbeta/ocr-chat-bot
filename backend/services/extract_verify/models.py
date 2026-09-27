"""
Pydantic models for Extract & Verify engine inputs and outputs.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── INPUTS ─────────────────────────────────────────────────────────────────

class ExtractionTask(BaseModel):
    """Defines what structured data to extract from the document."""
    name: str = Field(..., description="Task name, e.g. 'Charges', 'Samples'")
    columns: List[str] = Field(..., description="Column headers for the extracted table")
    description: str = Field("", description="Natural language hint for the AI")
    pages: Optional[List[int]] = Field(None, description="Specific pages to search, or None for all")


class VerificationTask(BaseModel):
    """Defines a rule to verify across the document."""
    name: str = Field(..., description="Task name, e.g. 'Batch Number Consistency'")
    check_type: str = Field(
        "custom",
        description="Type: consistency | cross_reference | format | completeness | custom"
    )
    instruction: str = Field(..., description="Natural language rule to check")
    pages: Optional[List[int]] = Field(None, description="Specific pages, or None for all")


class ExtractVerifyRequest(BaseModel):
    """Complete request to the Extract & Verify engine."""
    pdf_path: str
    extraction_tasks: List[ExtractionTask] = Field(default_factory=list)
    verification_tasks: List[VerificationTask] = Field(default_factory=list)
    page_range: Optional[List[int]] = Field(None, description="Override: only process these pages")


# ─── OUTPUTS ────────────────────────────────────────────────────────────────

class ExtractionRow(BaseModel):
    """A single extracted row with its source page."""
    data: Dict[str, Any] = Field(..., description="Column name → value mapping")
    page: int = Field(..., description="Page number where this row was found")


class ExtractionResult(BaseModel):
    """Results for one extraction task."""
    task_name: str
    columns: List[str]
    rows: List[ExtractionRow] = Field(default_factory=list)
    row_count: int = 0


class VerificationFinding(BaseModel):
    """A single finding from a verification check."""
    issue: str
    page: Optional[int] = None
    details: str = ""


class VerificationResult(BaseModel):
    """Results for one verification task."""
    task_name: str
    status: str = Field("pass", description="pass | fail | warning")
    findings: List[VerificationFinding] = Field(default_factory=list)


class ExtractVerifyResponse(BaseModel):
    """Complete response from the engine."""
    extraction_results: List[ExtractionResult] = Field(default_factory=list)
    verification_results: List[VerificationResult] = Field(default_factory=list)
    pages_analyzed: int = 0
    total_pages: int = 0
    model_used: str = ""
    batches_used: int = 0
    errors: List[str] = Field(default_factory=list)
