"""
Validation and confidence scoring for a parsed invoice.

Checks (from the spec):
1. GST arithmetic: subtotal + CGST + SGST + IGST == total (within ₹1).
2. GSTIN: valid 15-character structure and state code 01-38.
3. Sanity: total positive and under ₹1 crore, date not in the future.
4. needs_review if anything important is missing, uncertain or warned about.
5. overall confidence = weighted average of the main fields.

All functions are pure apart from `validate_invoice`, which updates the
InvoiceData it is given (and also returns it for convenience).
"""

import re
from datetime import date, timedelta
from typing import Optional

import config
from extractor.models import InvoiceData

GSTIN_STRUCTURE_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Fields that every invoice should have; missing ones need review.
CORE_FIELDS = ("total_amount", "invoice_date", "vendor", "invoice_number")
# Helpful extras that never trigger a review on their own.
INFO_FIELDS = ("overall", "currency", "category")


# ----------------------------------------------------------------------
# Individual checks
# ----------------------------------------------------------------------
def is_valid_gstin(gstin: Optional[str]) -> bool:
    """True if the GSTIN has the right shape and a real state code (01-38)."""
    if not gstin or not GSTIN_STRUCTURE_RE.match(gstin):
        return False
    return 1 <= int(gstin[:2]) <= 38


def gst_arithmetic_ok(subtotal, cgst, sgst, igst, total,
                      tolerance: float = config.GST_TOLERANCE) -> Optional[bool]:
    """
    True/False if the GST sum can be checked, None if values are missing.
    Needs subtotal, total and at least one tax amount.
    """
    taxes = [t for t in (cgst, sgst, igst) if t is not None]
    if subtotal is None or total is None or not taxes:
        return None
    return abs(subtotal + sum(taxes) - total) <= tolerance


def total_is_sane(total: Optional[float]) -> bool:
    """Total must be positive and below the 1 crore limit."""
    return total is not None and 0 < total < config.MAX_REASONABLE_TOTAL


def date_is_sane(iso_date: Optional[str], today: Optional[date] = None) -> bool:
    """Date must parse and must not be more than a day in the future."""
    if not iso_date:
        return False
    try:
        value = date.fromisoformat(iso_date)
    except ValueError:
        return False
    return value <= (today or date.today()) + timedelta(days=1)


def overall_confidence(confidence: dict) -> float:
    """Weighted average: total 0.35, date 0.25, vendor 0.2, invoice number 0.2."""
    weights = config.CONFIDENCE_WEIGHTS
    score = sum(confidence.get(name, 0.0) * weight for name, weight in weights.items())
    return round(score / sum(weights.values()), 3)


def low_confidence_fields(invoice: InvoiceData, threshold: Optional[float] = None) -> list:
    """
    Names of fields whose confidence is under the threshold.
    Core fields count even when missing; optional ones (time, GSTIN) only
    when they were actually found.
    """
    threshold = config.REVIEW_THRESHOLD if threshold is None else threshold
    low = []
    for name, score in invoice.confidence.items():
        if name in INFO_FIELDS:
            continue
        found = getattr(invoice, name, None) is not None
        if (name in CORE_FIELDS or found) and score < threshold:
            low.append(name)
    return low


# ----------------------------------------------------------------------
# Run everything
# ----------------------------------------------------------------------
def validate_invoice(invoice: InvoiceData, today: Optional[date] = None) -> InvoiceData:
    """Apply all checks, add warnings, compute overall confidence and needs_review."""
    conf = invoice.confidence

    # 1. GST arithmetic
    gst_ok = gst_arithmetic_ok(invoice.subtotal, invoice.cgst, invoice.sgst,
                               invoice.igst, invoice.total_amount)
    if gst_ok is False:
        invoice.add_warning("GST arithmetic mismatch")
        conf["total_amount"] = round(max(0.0, conf.get("total_amount", 0.0) - 0.3), 2)

    # 2. GSTIN
    if invoice.gstin and not is_valid_gstin(invoice.gstin):
        invoice.add_warning("invalid GSTIN")
        conf["gstin"] = min(conf.get("gstin", 0.0), 0.3)

    # 3. Sanity checks
    if invoice.total_amount is not None and not total_is_sane(invoice.total_amount):
        invoice.add_warning("total amount out of range")
        conf["total_amount"] = min(conf.get("total_amount", 0.0), 0.2)
    if invoice.invoice_date and not date_is_sane(invoice.invoice_date, today):
        invoice.add_warning("invoice date is in the future")
        conf["invoice_date"] = min(conf.get("invoice_date", 0.0), 0.2)

    # 4. Overall score and the review flag
    for name in CORE_FIELDS:
        conf.setdefault(name, 0.0)
    conf["overall"] = overall_confidence(conf)

    missing = [name for name in ("total_amount", "invoice_date", "vendor")
               if getattr(invoice, name) is None]
    invoice.needs_review = bool(missing or low_confidence_fields(invoice) or invoice.warnings)
    return invoice
