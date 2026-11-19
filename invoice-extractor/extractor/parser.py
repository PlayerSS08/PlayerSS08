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


PAGE_SEPARATOR = "\f"     # what text_extraction puts between PDF pages


def split_documents(text: str) -> list:
    """
    Split a file's text into separate invoices.

    Some PDFs hold more than one invoice - e.g. an Amazon order prints the
    seller's invoice on page 1 and Amazon's own cash-on-delivery fee invoice
    on page 2, each with its own invoice number, seller and total. A page
    starts a new invoice when it shows an invoice number different from the
    one before; a page with no number, or the same number, continues it.
    """
    pages = [page for page in (text or "").split(PAGE_SEPARATOR) if page.strip()]
    documents, current, current_number = [], [], None
    for page in pages:
        number, _ = fields.extract_invoice_number(page)
        if current and number and current_number and number != current_number:
            documents.append("\n".join(current))
            current, current_number = [], None
        current.append(page)
        current_number = current_number or number
    if current:
        documents.append("\n".join(current))
    return documents or [text or ""]


def _extract_fields(text: str, today: Optional[date] = None) -> InvoiceData:
    """Run every field extractor over ONE invoice's text (no validation)."""
    clean = fields.normalize_text(text)
    invoice = InvoiceData(source_file="", file_hash="", extraction_method="",
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
    return invoice


def _add_up(values: list) -> Optional[float]:
    """Sum of the values that were found (None if none were)."""
    found = [v for v in values if v is not None]
    return round(sum(found), 2) if found else None


def combine_documents(parts: list) -> InvoiceData:
    """
    Merge several invoices from one file into one record:
    * identity (number, date, vendor, GSTIN, category) = the FIRST invoice,
      which is the main purchase (e.g. the product, not the delivery fee)
    * total amount = the sum of every invoice's total = what was paid
    * CGST / SGST / IGST = summed per tax type across the invoices
    * line items are joined; each invoice is listed in `documents`
    """
    from dataclasses import replace
    main = parts[0]
    merged = replace(main, confidence=dict(main.confidence), warnings=list(main.warnings),
                     line_items=[item for part in parts for item in part.line_items])
    totals = [part.total_amount for part in parts]
    merged.total_amount = _add_up(totals)
    if None in totals and merged.total_amount is not None:
        merged.add_warning("total missing for one of the invoices in this file")
    merged.confidence["total_amount"] = min(p.confidence.get("total_amount", 0.0) for p in parts)
    for tax in ("cgst", "sgst", "igst"):
        setattr(merged, tax, _add_up([getattr(part, tax) for part in parts]))
    subtotals = [part.subtotal for part in parts]
    merged.subtotal = None if None in subtotals else _add_up(subtotals)
    merged.payment_method = next((p.payment_method for p in parts if p.payment_method), None)
    merged.invoice_date = merged.invoice_date or next((p.invoice_date for p in parts if p.invoice_date), None)
    for part in parts[1:]:
        for warning in part.warnings:
            merged.add_warning(warning)
    merged.documents = [{"invoice_number": p.invoice_number, "vendor": p.vendor,
                         "invoice_date": p.invoice_date, "total_amount": p.total_amount,
                         "gst": p.gst_total()} for p in parts]
    return merged


def parse_invoice(text: str, source_file: str = "", file_hash: str = "",
                  extraction_method: str = "pdf_text",
                  today: Optional[date] = None) -> InvoiceData:
    """
    Turn a file's text into one validated InvoiceData.
    A file holding several invoices is read invoice by invoice and combined.
    """
    documents = split_documents(text)
    parts = [_extract_fields(doc, today) for doc in documents]
    invoice = parts[0] if len(parts) == 1 else combine_documents(parts)
    invoice.source_file, invoice.file_hash = source_file, file_hash
    invoice.extraction_method, invoice.raw_text = extraction_method, text or ""
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
