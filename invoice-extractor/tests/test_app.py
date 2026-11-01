"""Smoke tests: every Streamlit page renders without errors (empty and with data)."""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
from extractor.models import InvoiceData
from storage import db

APP = str(config.BASE_DIR / "app.py")
PAGES = ["ui/home.py", "ui/upload.py", "ui/records.py", "ui/dashboard.py",
         "ui/budgets.py", "ui/batch.py", "ui/settings.py"]


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_FILE", tmp_path / "app.db")
    monkeypatch.setattr(config, "INVOICE_FOLDER", tmp_path / "invoices")
    monkeypatch.setattr(config, "FILES_DIR", tmp_path / "files")
    db.init_db()


def add_rows():
    """Three invoices: two this month, one last month (dates relative to today)."""
    this_month = pd.Timestamp.today().replace(day=1)
    last_month = (this_month - pd.Timedelta(days=1)).replace(day=12)
    for i, (vendor, cat, day, total) in enumerate([
            ("Amazon", "Shopping", this_month, 1180.0), ("Swiggy", "Food & Dining", last_month, 450.0),
            ("Swiggy", "Food & Dining", this_month, 520.0)]):
        date = day.strftime("%Y-%m-%d")
        db.insert_invoice(InvoiceData(
            source_file=f"{i}.pdf", file_hash=f"h{i}", extraction_method="pdf_text", vendor=vendor,
            category=cat, invoice_number=f"N{i}", invoice_date=date, total_amount=total,
            subtotal=1000.0 if i == 0 else None, cgst=90.0 if i == 0 else None, sgst=90.0 if i == 0 else None,
            line_items=[{"description": "Item", "quantity": 1.0, "rate": total, "amount": total}]))
    db.set_budget("Food & Dining", 500)


def open_page(page):
    app = AppTest.from_file(APP, default_timeout=60).run()
    if page != PAGES[0]:
        app.switch_page(page).run()
    return app


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_when_empty(page):
    assert not open_page(page).exception


@pytest.mark.parametrize("page", PAGES)
def test_pages_render_with_data(page):
    add_rows()
    app = open_page(page)
    assert not app.exception, app.exception


def test_home_shows_budget_warning():
    add_rows()
    app = open_page("ui/home.py")
    assert any("budget" in w.value for w in app.warning)


def test_records_filters_by_search():
    add_rows()
    app = open_page("ui/records.py")
    app.text_input[0].set_value("swig").run()
    assert not app.exception
    assert "**2** of 3 invoices" in app.markdown[0].value


def test_settings_are_saved():
    app = open_page("ui/settings.py")
    app.selectbox[0].set_value("tesseract")
    next(b for b in app.button if b.label == "Save settings").click().run()
    assert db.get_setting("ocr_engine") == "tesseract"
