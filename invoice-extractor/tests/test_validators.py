"""Tests for extractor/validators.py."""

from datetime import date

import pytest

from extractor import validators
from extractor.models import InvoiceData
from extractor.parser import parse_invoice

TODAY = date(2026, 10, 31)


def make(**kwargs):
    base = dict(source_file="a.pdf", file_hash="h", extraction_method="pdf_text",
                invoice_number="INV-1", invoice_date="2026-10-01", vendor="Acme",
                total_amount=118.0,
                confidence={"invoice_number": 0.9, "invoice_date": 0.9,
                            "vendor": 0.9, "total_amount": 0.9})
    base.update(kwargs)
    return InvoiceData(**base)


@pytest.mark.parametrize("gstin, ok", [
    ("29AAACC1234F1Z5", True),
    ("38AAACC1234F1Z5", True),
    ("00AAACC1234F1Z5", False),   # state code 00 does not exist
    ("39AAACC1234F1Z5", False),   # above 38
    ("29AAACC1234F1X5", False),   # 14th character must be Z
    ("29AAACC1234F0Z5", False),   # 13th character cannot be 0
    ("", False),
    (None, False),
])
def test_is_valid_gstin(gstin, ok):
    assert validators.is_valid_gstin(gstin) is ok


@pytest.mark.parametrize("values, expected", [
    ((100, 9, 9, None, 118), True),
    ((100, None, None, 18, 118.6), True),     # within ₹1 rounding
    ((100, 9, 9, None, 150), False),
    ((None, 9, 9, None, 118), None),          # cannot check
    ((100, None, None, None, 118), None),     # no taxes
])
def test_gst_arithmetic(values, expected):
    assert validators.gst_arithmetic_ok(*values) is expected


def test_gst_mismatch_adds_warning_and_lowers_confidence():
    inv = validators.validate_invoice(make(subtotal=100, cgst=9, sgst=9, total_amount=150),
                                      today=TODAY)
    assert "GST arithmetic mismatch" in inv.warnings
    assert inv.confidence["total_amount"] == pytest.approx(0.6)
    assert inv.needs_review


def test_clean_invoice_does_not_need_review():
    inv = validators.validate_invoice(make(subtotal=100, cgst=9, sgst=9), today=TODAY)
    assert inv.warnings == []
    assert not inv.needs_review
    assert inv.confidence["overall"] == pytest.approx(0.9)


@pytest.mark.parametrize("total, sane", [(100.0, True), (0.0, False), (-5.0, False),
                                         (10_000_000.0, False), (None, False)])
def test_total_is_sane(total, sane):
    assert validators.total_is_sane(total) is sane


def test_future_date_is_flagged():
    inv = validators.validate_invoice(make(invoice_date="2027-05-01"), today=TODAY)
    assert "invoice date is in the future" in inv.warnings
    assert inv.needs_review


def test_tomorrow_is_allowed():
    assert validators.date_is_sane("2026-11-01", today=TODAY)


@pytest.mark.parametrize("missing", ["total_amount", "invoice_date", "vendor"])
def test_missing_core_field_needs_review(missing):
    inv = make(**{missing: None})
    inv.confidence[missing] = 0.0
    assert validators.validate_invoice(inv, today=TODAY).needs_review


def test_missing_invoice_number_needs_review():
    inv = make(invoice_number=None)
    inv.confidence["invoice_number"] = 0.0
    assert validators.validate_invoice(inv, today=TODAY).needs_review


def test_low_confidence_needs_review():
    inv = make()
    inv.confidence["vendor"] = 0.4
    assert validators.validate_invoice(inv, today=TODAY).needs_review


def test_missing_time_alone_is_fine():
    inv = make(invoice_time=None)
    inv.confidence["invoice_time"] = 0.0
    assert not validators.validate_invoice(inv, today=TODAY).needs_review


def test_overall_confidence_weights():
    conf = {"total_amount": 1.0, "invoice_date": 0.0, "vendor": 0.0, "invoice_number": 0.0}
    assert validators.overall_confidence(conf) == pytest.approx(0.35)


def test_invalid_gstin_warns():
    inv = validators.validate_invoice(make(gstin="99AAACC1234F1Z5"), today=TODAY)
    assert "invalid GSTIN" in inv.warnings


def test_parser_runs_validation():
    inv = parse_invoice("Shop\nSub Total 100.00\nCGST 9.00\nSGST 9.00\nGrand Total 200.00",
                        today=TODAY)
    assert "GST arithmetic mismatch" in inv.warnings
    assert "overall" in inv.confidence
