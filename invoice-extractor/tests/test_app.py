"""Smoke tests: every Streamlit page renders without errors."""

import pytest
from streamlit.testing.v1 import AppTest

import config
from extractor.models import InvoiceData
from storage import db

APP = str(config.BASE_DIR / "app.py")


@pytest.fixture(autouse=True)
def temp_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_FILE", tmp_path / "app.db")
    monkeypatch.setattr(config, "INVOICE_FOLDER", tmp_path / "invoices")
    db.init_db()
    db.insert_invoice(InvoiceData(source_file="a.pdf", file_hash="h1", extraction_method="pdf_text",
                                  vendor="Amazon", invoice_number="A1", invoice_date="2026-10-01",
                                  total_amount=1180.0, subtotal=1000.0, cgst=90.0, sgst=90.0))


def run_page(name):
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.sidebar.radio[0].set_value(name).run()
    return app


def test_upload_page_renders():
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception
    assert app.header[0].value == "Upload and Extract"


def test_records_page_renders():
    app = run_page("Invoice Records")
    assert not app.exception
    assert "Showing 1 of 1" in app.caption[0].value


def test_dashboard_page_renders():
    app = run_page("Dashboard")
    assert not app.exception
    assert app.metric[0].value == "1"


def test_batch_page_renders():
    app = run_page("Batch Scan")
    assert not app.exception
