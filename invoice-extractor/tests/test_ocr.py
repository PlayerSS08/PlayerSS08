"""Tests for extractor/ocr.py. OCR tests are skipped if Tesseract is missing."""

import cv2
import numpy as np
import pymupdf
import pytest

from extractor import ocr, text_extraction
from extractor.parser import process_file

needs_ocr = pytest.mark.skipif(not ocr.ocr_available(), reason="no OCR engine installed")

LINES = ["HOTEL ROYAL TREAT", "Bill No: 4521", "Date: 14/10/2026",
         "Sub Total 200.00", "Grand Total 210.00"]


def text_image(lines=LINES, width=900):
    img = np.full((80 + 60 * len(lines), width), 255, np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (30, 60 + i * 60), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 0, 2)
    return img


def test_grayscale_and_upscale():
    colour = np.full((100, 200, 3), 255, np.uint8)
    gray = ocr.to_grayscale(colour)
    assert gray.ndim == 2
    assert ocr.upscale_if_small(gray).shape[1] == 1000
    wide = np.full((10, 1500), 255, np.uint8)
    assert ocr.upscale_if_small(wide).shape == wide.shape


@pytest.mark.parametrize("angle", [-6, -3, 3, 6])
def test_deskew_straightens_rotated_text(angle):
    rotated = ocr.rotate(text_image(), angle)
    assert abs(ocr.estimate_skew_angle(rotated) + angle) < 1.0
    assert abs(ocr.estimate_skew_angle(ocr.deskew(rotated))) < 1.0


def test_preprocess_returns_binary_image():
    out = ocr.preprocess_image(cv2.cvtColor(text_image(), cv2.COLOR_GRAY2BGR))
    assert set(np.unique(out)).issubset({0, 255})


def test_missing_engine_raises_clear_error(monkeypatch):
    monkeypatch.setattr(ocr, "active_engine", lambda: "none")
    with pytest.raises(ocr.OCRUnavailableError, match="Tesseract"):
        ocr.ocr_image(text_image())


def test_missing_engine_does_not_crash_pipeline(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "active_engine", lambda: "none")
    path = tmp_path / "photo.png"
    cv2.imwrite(str(path), text_image())
    invoice = process_file(path)
    assert invoice.extraction_method == "failed"
    assert invoice.needs_review
    assert any("OCR engine not available" in w for w in invoice.warnings)


@needs_ocr
def test_image_file_is_ocrd(tmp_path):
    path = tmp_path / "bill.png"
    cv2.imwrite(str(path), ocr.rotate(text_image(), 3))
    text, method = text_extraction.get_text(path)
    assert method == "ocr"
    assert "4521" in text and "210.00" in text


@needs_ocr
def test_scanned_pdf_falls_back_to_ocr(tmp_path):
    # A PDF that only contains a picture of text (no text layer).
    png = tmp_path / "page.png"
    cv2.imwrite(str(png), text_image())
    pdf = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, filename=str(png))
    doc.save(pdf)
    doc.close()
    text, method = text_extraction.get_text(pdf)
    assert method == "pdf_ocr"
    assert "4521" in text
