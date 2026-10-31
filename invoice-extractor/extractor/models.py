"""
Data model for one extracted invoice.

Every stage of the pipeline (text extraction -> parsing -> validation ->
storage) passes this single dataclass around, so the shape of the data
is defined in exactly one place.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class InvoiceData:
    """All information extracted from a single invoice file."""

    source_file: str
    file_hash: str                       # SHA-256 of file bytes
    extraction_method: str               # "pdf_text" | "ocr" | "pdf_ocr"
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None   # ISO "YYYY-MM-DD"
    invoice_time: Optional[str] = None   # 24h "HH:MM" or "HH:MM:SS"
    vendor: Optional[str] = None
    gstin: Optional[str] = None
    subtotal: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    total_amount: Optional[float] = None
    currency: str = "INR"
    confidence: dict = field(default_factory=dict)  # {"invoice_date": 0.9, ...}
    needs_review: bool = False
    warnings: list = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        """Return the invoice as a plain dictionary (handy for tables)."""
        return asdict(self)

    def add_warning(self, message: str) -> None:
        """Add a warning once (duplicates are ignored)."""
        if message not in self.warnings:
            self.warnings.append(message)
