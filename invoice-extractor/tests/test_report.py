"""Tests for analytics/report.py."""

import pymupdf

from analytics.report import monthly_report_pdf
from tests.test_dashboard import ADV


def pdf_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def test_monthly_report_contents():
    text = pdf_text(monthly_report_pdf(ADV, "2026-10", {"Food & Dining": 3000}))
    assert "October 2026" in text
    assert "Food & Dining" in text and "Swiggy" in text
    assert "Rs. 3,450.00" in text            # month total
    assert "Budgets" in text


def test_report_for_empty_month():
    text = pdf_text(monthly_report_pdf(ADV, "2025-01"))
    assert "No invoices are dated in this month." in text
