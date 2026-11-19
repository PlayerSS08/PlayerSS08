"""Tests for extractor/text_extraction.py (digital PDF path)."""

import pymupdf

from extractor import text_extraction as te


def make_pdf(path, text):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=11)
    doc.save(path)
    doc.close()


def test_hash_is_stable_and_distinct():
    assert te.compute_file_hash(b"abc") == te.compute_file_hash(b"abc")
    assert te.compute_file_hash(b"abc") != te.compute_file_hash(b"abd")
    assert len(te.compute_file_hash(b"")) == 64


def test_digital_pdf_returns_pdf_text(tmp_path):
    pdf = tmp_path / "a.pdf"
    make_pdf(pdf, "TAX INVOICE\nInvoice No: INV-2026-001\nGrand Total: Rs. 1,250.00\n"
                  "Thank you for shopping with us today")
    text, method = te.get_text(pdf)
    assert method == "pdf_text"
    assert "INV-2026-001" in text


def test_unsupported_file_fails_gracefully(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert te.get_text(f) == ("", "failed")


def test_corrupt_pdf_fails_gracefully(tmp_path):
    f = tmp_path / "broken.pdf"
    f.write_bytes(b"this is not a pdf")
    text, method = te.get_text(f)
    assert method == "failed" and text == ""


def test_count_meaningful_chars():
    assert te.count_meaningful_chars("  a b\n\tc ") == 3
