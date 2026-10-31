"""
Turn an invoice file (PDF or image) into plain text.

`get_text(path)` returns a `(text, method)` tuple where method is one of:
    "pdf_text"  - digital PDF, text read directly with pymupdf/pdfplumber
    "pdf_ocr"   - scanned PDF, pages rendered to images and OCR'd
    "ocr"       - image file OCR'd
    "failed"    - nothing could be read (the caller flags needs_review)

This module never raises for a bad file; it returns ("", "failed").
The pymupdf logic is ported from the original Scanner.py.
"""

import hashlib
from pathlib import Path

import config


def compute_file_hash(data: bytes) -> str:
    """SHA-256 hex digest of the raw file bytes (used for de-duplication)."""
    return hashlib.sha256(data).hexdigest()


def hash_file(path) -> str:
    """SHA-256 of a file on disk."""
    return compute_file_hash(Path(path).read_bytes())


def count_meaningful_chars(text: str) -> int:
    """Number of non-whitespace characters (used to spot scanned PDFs)."""
    return sum(1 for ch in text if not ch.isspace())


# ------------------------------------------------------------------
# Digital PDF text
# ------------------------------------------------------------------
def pdf_text_pymupdf(path) -> str:
    """Read the text layer of every page with pymupdf (from Scanner.py)."""
    import pymupdf
    with pymupdf.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def pdf_text_pdfplumber(path) -> str:
    """Second option: read the text layer with pdfplumber."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def extract_pdf_text(path) -> str:
    """Try pymupdf first, then pdfplumber; return the longer useful text."""
    best = ""
    for reader in (pdf_text_pymupdf, pdf_text_pdfplumber):
        try:
            text = reader(path)
        except Exception:
            continue
        if count_meaningful_chars(text) > count_meaningful_chars(best):
            best = text
        if count_meaningful_chars(best) > config.MIN_TEXT_CHARS:
            break  # good enough, no need for the second reader
    return best


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------
def get_text(path) -> tuple:
    """
    Extract text from a PDF or image file.

    Order: PDF text layer -> (if almost empty) OCR of rendered pages.
    Images go straight to OCR. Never raises.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix in config.PDF_EXTENSIONS:
            text = extract_pdf_text(path)
            if count_meaningful_chars(text) > config.MIN_TEXT_CHARS:
                return text, "pdf_text"
            # Scanned PDF: render pages and OCR them.
            from extractor import ocr
            text = ocr.ocr_pdf(path)
            return (text, "pdf_ocr") if text.strip() else ("", "failed")

        if suffix in config.IMAGE_EXTENSIONS:
            from extractor import ocr
            text = ocr.ocr_image_file(path)
            return (text, "ocr") if text.strip() else ("", "failed")
    except Exception:
        pass
    return "", "failed"
