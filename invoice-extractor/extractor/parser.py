"""
Turn raw invoice text into an InvoiceData object.

`parse_invoice(text)` is pure (text in, data out) so it can be tested
without any files.
"""

from datetime import date
from typing import Optional

import config
from extractor import fields, validators
from extractor.models import InvoiceData


def parse_invoice(text: str, source_file: str = "", file_hash: str = "",
                  extraction_method: str = "pdf_text",
                  today: Optional[date] = None) -> InvoiceData:
    """Run every field extractor over the text, then validate the result."""
    clean = fields.normalize_text(text)
    invoice = InvoiceData(source_file=source_file, file_hash=file_hash,
                          extraction_method=extraction_method, raw_text=text or "",
                          currency=config.DEFAULT_CURRENCY)

    invoice.invoice_number, invoice.confidence["invoice_number"] = fields.extract_invoice_number(clean)
    invoice.invoice_date, invoice.confidence["invoice_date"] = fields.extract_date(clean, today)
    invoice.invoice_time, invoice.confidence["invoice_time"] = fields.extract_time(clean, today)
    invoice.vendor, invoice.confidence["vendor"] = fields.extract_vendor(clean)
    invoice.gstin, invoice.confidence["gstin"] = fields.extract_gstin(clean)
    invoice.total_amount, invoice.confidence["total_amount"] = fields.extract_total(clean)
    invoice.subtotal, _ = fields.extract_subtotal(clean)
    invoice.cgst, _ = fields.extract_cgst(clean)
    invoice.sgst, _ = fields.extract_sgst(clean)
    invoice.igst, _ = fields.extract_igst(clean)

    if invoice.total_amount is not None and \
            invoice.confidence["total_amount"] == fields.TOTAL_GUESS_CONFIDENCE:
        invoice.add_warning("total guessed")
    if not clean.strip():
        invoice.add_warning("no text could be extracted")
    return validators.validate_invoice(invoice, today)


def process_file(path, display_name: Optional[str] = None,
                 today: Optional[date] = None) -> InvoiceData:
    """
    Full pipeline for one file on disk: hash -> text -> parse -> validate.
    Never raises; problems become warnings and needs_review = True.
    """
    from pathlib import Path
    from extractor import ocr, text_extraction

    path = Path(path)
    name = display_name or path.name
    try:
        file_hash = text_extraction.hash_file(path)
    except OSError as error:
        invoice = InvoiceData(source_file=name, file_hash="", extraction_method="failed")
        invoice.add_warning(f"could not read file: {error}")
        invoice.needs_review = True
        return invoice

    text, method = text_extraction.get_text(path)
    invoice = parse_invoice(text, name, file_hash, method, today)
    if method == "failed":
        if path.suffix.lower() not in config.SUPPORTED_EXTENSIONS:
            invoice.add_warning("unsupported file type")
        elif not ocr.ocr_available():
            invoice.add_warning("OCR engine not available - install Tesseract to read "
                                "images and scanned PDFs")
        invoice.needs_review = True
    return invoice
