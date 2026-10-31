"""Tests for analytics/dashboard.py."""

import pandas as pd

from analytics import dashboard

DF = pd.DataFrame([
    {"vendor": "Amazon", "invoice_date": "2026-09-05", "total_amount": 100.0,
     "cgst": 9.0, "sgst": 9.0, "igst": None, "needs_review": False},
    {"vendor": "Amazon", "invoice_date": "2026-10-01", "total_amount": 300.0,
     "cgst": None, "sgst": None, "igst": 54.0, "needs_review": True},
    {"vendor": "Swiggy", "invoice_date": "2026-10-20", "total_amount": 250.0,
     "cgst": None, "sgst": None, "igst": None, "needs_review": False},
    {"vendor": None, "invoice_date": None, "total_amount": 50.0,
     "cgst": None, "sgst": None, "igst": None, "needs_review": True},
])


def test_summary_metrics():
    m = dashboard.summary_metrics(DF)
    assert m == {"total_invoices": 4, "total_spend": 700.0,
                 "average_invoice": 175.0, "needs_review": 2}


def test_spend_by_vendor():
    result = dashboard.spend_by_vendor(DF)
    assert result["vendor"].tolist() == ["Amazon", "Swiggy", "Unknown"]
    assert result["total_amount"].tolist() == [400.0, 250.0, 50.0]
    assert len(dashboard.spend_by_vendor(DF, top=1)) == 1


def test_spend_by_month_skips_undated():
    result = dashboard.spend_by_month(DF)
    assert result["month"].tolist() == ["2026-09", "2026-10"]
    assert result["total_amount"].tolist() == [100.0, 550.0]


def test_gst_breakdown():
    result = dashboard.gst_breakdown(DF)
    assert dict(zip(result["tax"], result["amount"])) == {"CGST": 9.0, "SGST": 9.0, "IGST": 54.0}


def test_figures_build():
    for make in (dashboard.vendor_figure, dashboard.month_figure, dashboard.gst_figure):
        assert make(DF).data
