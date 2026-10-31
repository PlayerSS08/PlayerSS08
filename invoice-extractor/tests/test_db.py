"""Tests for storage/db.py using a temporary database file."""

import pytest

from extractor.models import InvoiceData
from storage import db


@pytest.fixture
def db_path(tmp_path):
    """A fresh, initialised database for every test."""
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


def make_invoice(file_hash="hash1", vendor="Amazon", number="INV-0001", total=100.0):
    return InvoiceData(
        source_file=f"{file_hash}.pdf", file_hash=file_hash,
        extraction_method="pdf_text", vendor=vendor, invoice_number=number,
        invoice_date="2026-10-01", total_amount=total,
        confidence={"total_amount": 0.9},
    )


def test_init_db_is_idempotent(db_path):
    db.init_db(db_path)  # second call must not fail
    assert db.get_all_invoices(db_path).empty


def test_insert_and_read_back(db_path):
    assert db.insert_invoice(make_invoice(), db_path) is True
    df = db.get_all_invoices(db_path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["vendor"] == "Amazon"
    assert row["total_amount"] == 100.0
    assert row["scanned_at"]          # scan time is filled automatically
    assert row["invoice_date"] == "2026-10-01"


def test_same_file_hash_is_rejected(db_path):
    assert db.insert_invoice(make_invoice(), db_path) is True
    assert db.insert_invoice(make_invoice(), db_path) is False
    assert len(db.get_all_invoices(db_path)) == 1
    assert db.hash_exists("hash1", db_path)
    assert not db.hash_exists("other", db_path)


def test_same_number_different_vendor_does_not_collide(db_path):
    # The old schema made invoice_number UNIQUE, so this used to fail.
    assert db.insert_invoice(make_invoice("h1", vendor="Amazon", number="0001"), db_path)
    assert db.insert_invoice(make_invoice("h2", vendor="Swiggy", number="0001"), db_path)
    assert len(db.get_all_invoices(db_path)) == 2


def test_same_vendor_and_number_warns_but_saves(db_path):
    db.insert_invoice(make_invoice("h1"), db_path)
    second = make_invoice("h2")
    assert db.insert_invoice(second, db_path) is True
    assert second.needs_review
    assert any("Possible duplicate" in w for w in second.warnings)


def test_update_invoice(db_path):
    db.insert_invoice(make_invoice(), db_path)
    row_id = int(db.get_all_invoices(db_path).iloc[0]["id"])
    assert db.update_invoice(row_id, {"vendor": "Flipkart", "total_amount": 55.5,
                                      "file_hash": "hacked"}, db_path)
    row = db.get_all_invoices(db_path).iloc[0]
    assert row["vendor"] == "Flipkart"
    assert row["total_amount"] == 55.5
    assert row["file_hash"] == "hash1"   # not editable


def test_update_with_no_valid_fields_returns_false(db_path):
    db.insert_invoice(make_invoice(), db_path)
    assert db.update_invoice(1, {"not_a_column": 1}, db_path) is False


def test_delete_invoice(db_path):
    db.insert_invoice(make_invoice(), db_path)
    row_id = int(db.get_all_invoices(db_path).iloc[0]["id"])
    assert db.delete_invoice(row_id, db_path) is True
    assert db.delete_invoice(row_id, db_path) is False
    assert db.get_all_invoices(db_path).empty


def test_find_possible_duplicates(db_path):
    db.insert_invoice(make_invoice("h1", total=100.0), db_path)
    db.insert_invoice(make_invoice("h2", total=100.0), db_path)
    db.insert_invoice(make_invoice("h3", vendor="Zomato", number="Z1"), db_path)
    dupes = db.find_possible_duplicates(db_path)
    assert sorted(dupes["id"].tolist()) == [1, 2]


def test_no_connection_at_import_time(tmp_path, monkeypatch):
    # Importing the module must not create the real database file.
    import importlib
    import config
    fake = tmp_path / "nothing" / "x.db"
    monkeypatch.setattr(config, "DATABASE_FILE", fake)
    importlib.reload(db)
    assert not fake.exists()
