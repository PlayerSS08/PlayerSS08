"""Tests for the batch scanner (scripts/scan_folder.py)."""

import pymupdf

from scripts.scan_folder import scan_folder
from storage import db


def make_pdf(path, text):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def test_scan_adds_then_skips_existing(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "FILES_DIR", tmp_path / "files")
    folder, db_path = tmp_path / "invoices", tmp_path / "t.db"
    folder.mkdir()
    make_pdf(folder / "a.pdf", "Sold By: Green Leaf Traders\nInvoice No: GL-1001\n"
                               "Invoice Date: 12/10/2026\nGrand Total Rs. 1,250.00")
    make_pdf(folder / "b.pdf", "Thank you for your visit. Please come again soon to our store.")
    (folder / "notes.txt").write_text("ignored")

    first = {r["file"]: r["status"] for r in scan_folder(folder, db_path)}
    assert first == {"a.pdf": "ADDED", "b.pdf": "REVIEW"}   # b is saved but flagged

    second = {r["file"]: r["status"] for r in scan_folder(folder, db_path)}
    assert second == {"a.pdf": "EXISTS", "b.pdf": "EXISTS"}
    assert len(db.get_all_invoices(db_path)) == 2
    assert len(list((tmp_path / "files").iterdir())) == 2     # originals kept
