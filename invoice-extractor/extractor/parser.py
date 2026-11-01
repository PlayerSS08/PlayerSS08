"""
Turn raw invoice text into an InvoiceData object.

`parse_invoice(text)` is pure (text in, data out) so it can be tested
without any files.
"""

from datetime import date
from typing import Optional

import config
from extractor import categories, fields, validators
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
    invoice.currency, invoice.confidence["currency"] = fields.extract_currency(clean)
    invoice.payment_method, _ = fields.extract_payment_method(clean)
    invoice.line_items, _ = fields.extract_line_items(clean)
    invoice.category, invoice.confidence["category"] = categories.categorize(invoice.vendor, clean)

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


# Fields a user can correct on the "Upload and Extract" page.
EDITABLE_FIELDS = ("invoice_number", "invoice_date", "invoice_time", "vendor", "gstin",
                   "subtotal", "cgst", "sgst", "igst", "total_amount",
                   "currency", "category", "payment_method")
AMOUNT_FIELDS = ("subtotal", "cgst", "sgst", "igst", "total_amount")
# Warnings produced by the validators / guesses; recomputed after an edit.
DERIVED_WARNINGS = ("GST arithmetic mismatch", "invalid GSTIN", "total amount out of range",
                    "invoice date is in the future", "total guessed")


def convert_field(name: str, value):
    """
    Turn a value typed by the user into the stored type.
    Amounts -> float, dates -> ISO string, blanks -> None.
    Raises ValueError with a friendly message if it cannot be understood.
    """
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return None
    text = str(value).strip()
    if not text:
        return None
    if name in AMOUNT_FIELDS:
        amount = fields.parse_amount(text)
        if amount is None:
            raise ValueError(f"'{text}' is not a valid amount for {name}")
        return amount
    if name == "invoice_date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            iso, _conf = fields.extract_date(text, today=date.max.replace(year=9998))
            if iso is None:
                raise ValueError(f"'{text}' is not a valid date (use YYYY-MM-DD)") from None
            return iso
    if name in ("gstin", "currency"):
        return text.upper()
    return text


def apply_corrections(invoice: InvoiceData, changes: dict,
                      today: Optional[date] = None) -> InvoiceData:
    """
    Return a copy of `invoice` with user-corrected values.
    Corrected fields get confidence 1.0 (a human checked them) and the
    validators are run again so needs_review reflects the new values.
    """
    from dataclasses import replace
    fixed = replace(invoice, confidence=dict(invoice.confidence),
                    warnings=[w for w in invoice.warnings if w not in DERIVED_WARNINGS])
    for name, raw in changes.items():
        if name not in EDITABLE_FIELDS:
            continue
        value = convert_field(name, raw)
        if value != getattr(invoice, name):
            setattr(fixed, name, value)
            fixed.confidence[name] = 1.0 if value is not None else 0.0
    if invoice.confidence.get("total_amount") == fields.TOTAL_GUESS_CONFIDENCE \
            and fixed.confidence.get("total_amount") != 1.0:
        fixed.add_warning("total guessed")
    return validators.validate_invoice(fixed, today)
