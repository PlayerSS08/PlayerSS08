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


ADV = pd.DataFrame([
    {"id": 1, "vendor": "Swiggy", "category": "Food & Dining", "payment_method": "UPI",
     "invoice_date": "2026-09-10", "total_amount": 400.0, "needs_review": False},
    {"id": 2, "vendor": "Swiggy", "category": "Food & Dining", "payment_method": "UPI",
     "invoice_date": "2026-10-02", "total_amount": 500.0, "needs_review": False},
    {"id": 3, "vendor": "Swiggy", "category": "Food & Dining", "payment_method": None,
     "invoice_date": "2026-10-15", "total_amount": 450.0, "needs_review": True},
    {"id": 4, "vendor": "Swiggy", "category": "Food & Dining", "payment_method": "Card",
     "invoice_date": "2026-10-20", "total_amount": 2500.0, "needs_review": False},
    {"id": 5, "vendor": "BESCOM", "category": "Utilities", "payment_method": "UPI",
     "invoice_date": "2026-08-05", "total_amount": 1800.0, "needs_review": False},
])
TODAY = "2026-10-31"


def test_filter_period():
    assert len(dashboard.filter_period(ADV, "1M", TODAY)) == 3
    assert len(dashboard.filter_period(ADV, "3M", TODAY)) == 5
    assert len(dashboard.filter_period(ADV, "All", TODAY)) == 5


def test_spend_by_category_and_payment():
    cats = dashboard.spend_by_category(ADV)
    assert cats.iloc[0].to_dict() == {"category": "Food & Dining", "total_amount": 3850.0, "invoices": 4}
    pay = dashboard.spend_by_payment_method(ADV)
    assert dict(zip(pay["payment_method"], pay["total_amount"]))["Not stated"] == 450.0


def test_month_over_month():
    mom = dashboard.month_over_month(ADV, TODAY)
    assert mom == {"this_month": 3450.0, "last_month": 400.0, "change_pct": 762.5, "month": "October 2026",
                   "previous": "Sep"}
    assert dashboard.month_over_month(ADV)["month"] == "October 2026"     # latest month with data
    assert dashboard.month_over_month(ADV, "2026-08-15")["change_pct"] is None


def test_budget_status():
    status = dashboard.budget_status(ADV, {"Food & Dining": 3000, "Utilities": 2000, "Fuel": 1000},
                                     month="2026-10")
    rows = {r["category"]: r["status"] for _, r in status.iterrows()}
    assert rows == {"Food & Dining": "over", "Utilities": "ok", "Fuel": "ok"}
    near = dashboard.budget_status(ADV, {"Food & Dining": 4000}, month="2026-10")
    assert near.iloc[0]["status"] == "warning"           # 3450 / 4000 = 86 %


def test_find_anomalies():
    result = dashboard.find_anomalies(ADV)
    assert result["id"].tolist() == [4]
    assert "usual for this vendor" in result.iloc[0]["reason"]


def test_recurring_vendors():
    result = dashboard.recurring_vendors(ADV)
    assert result["vendor"].tolist() == ["Swiggy"] and result.iloc[0]["months"] == 2


def test_insights_mention_budget_and_change():
    notes = dashboard.insights(ADV, {"Food & Dining": 3000}, TODAY)
    text = " ".join(notes)
    assert "more in October 2026" in text and "over its budget" in text and "need your review" in text


def test_advanced_figures_build():
    for make in (dashboard.category_figure, dashboard.trend_figure, dashboard.payment_figure):
        assert make(ADV).data
