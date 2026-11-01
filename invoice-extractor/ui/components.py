"""
Shared building blocks for the Streamlit pages (pure Python, no HTML/CSS/JS).

Every page script in ui/ imports this module for formatting helpers,
badges, previews, flash messages and the invoice detail view.
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from extractor import ocr
from storage import db

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
ENGINE_LABELS = {"bundled": "Bundled Tesseract", "tesseract": "Installed Tesseract",
                 "easyocr": "EasyOCR", "none": "No OCR engine"}
METHOD_LABELS = {"pdf_text": "Digital PDF", "pdf_ocr": "Scanned PDF (OCR)",
                 "ocr": "Image (OCR)", "failed": "Unreadable"}


# ----------------------------------------------------------------------
# Start-up
# ----------------------------------------------------------------------
def bootstrap() -> None:
    """Create tables and apply saved settings (runs at the start of every page load)."""
    db.init_db()
    config.OCR_ENGINE = db.get_setting("ocr_engine", config.OCR_ENGINE)
    config.REVIEW_THRESHOLD = float(db.get_setting("review_threshold", config.REVIEW_THRESHOLD))


def sidebar_status() -> None:
    """Small status block at the bottom of the sidebar."""
    df = db.get_all_invoices()
    with st.sidebar:
        engine = ocr.active_engine()
        st.caption(f"OCR: **{ENGINE_LABELS[engine]}**" + (" ✅" if engine != "none" else " ⚠️"))
        st.caption(f"{len(df)} invoices saved · {int(df['needs_review'].sum()) if len(df) else 0} to review")


# ----------------------------------------------------------------------
# Formatting
# ----------------------------------------------------------------------
def money(value, currency: str = "INR") -> str:
    """₹ 1,234.50 style text ('-' when missing)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return f"{CURRENCY_SYMBOLS.get(currency or 'INR', (currency or '') + ' ')} {value:,.2f}"


def money_short(value) -> str:
    """Compact amount for metric cards: ₹ 19,034 / ₹ 1.2L / ₹ 2.5Cr."""
    if value is None or pd.isna(value):
        return "-"
    if value >= 1e7:
        return f"₹ {value / 1e7:.1f}Cr"
    if value >= 1e5:
        return f"₹ {value / 1e5:.1f}L"
    return f"₹ {value:,.0f}"


def confidence_colour(score) -> str:
    """Badge colour for a 0-1 confidence score."""
    score = score or 0
    if score >= 0.8:
        return "green"
    return "orange" if score >= config.REVIEW_THRESHOLD else "red"


def flash(message: str, icon: str = "✅") -> None:
    """Remember a toast to show after st.rerun()."""
    st.session_state.setdefault("_flash", []).append((message, icon))


def show_flash() -> None:
    """Show any toasts stored with flash()."""
    for message, icon in st.session_state.pop("_flash", []):
        st.toast(message, icon=icon)


def ocr_warning() -> None:
    """Explain clearly when images cannot be read."""
    if not ocr.ocr_available():
        st.warning(ocr.INSTALL_HELP, icon=":material/warning:")


# ----------------------------------------------------------------------
# Previews
# ----------------------------------------------------------------------
def preview_bytes(name: str, data: bytes, dpi: int = 100):
    """PNG/JPG bytes to show: the image itself, or page 1 of a PDF."""
    if not data:
        return None
    if Path(name).suffix.lower() != ".pdf":
        return data
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as document:
            return document[0].get_pixmap(dpi=dpi).tobytes("png")
    except Exception:
        return None


def preview_from_record(record: dict):
    """Preview of a saved invoice's original file (if a copy was kept)."""
    path = record.get("file_path")
    if not path or not Path(path).exists():
        return None
    return preview_bytes(path, Path(path).read_bytes())


# ----------------------------------------------------------------------
# Invoice detail (used on Records)
# ----------------------------------------------------------------------
def badges_for(record: dict) -> None:
    """A row of status badges for one invoice."""
    confidence = record.get("confidence") or json.loads(record.get("confidence_json") or "{}")
    overall = confidence.get("overall", 0)
    cols = st.columns(5)
    cols[0].badge(METHOD_LABELS.get(record.get("extraction_method"), "Unknown"),
                  icon=":material/description:", color="blue")
    cols[1].badge(f"Confidence {overall:.0%}", icon=":material/verified:", color=confidence_colour(overall))
    cols[2].badge(record.get("category") or "Other", icon=":material/sell:", color="violet")
    if record.get("payment_method"):
        cols[3].badge(record["payment_method"], icon=":material/payments:", color="gray")
    if record.get("needs_review"):
        cols[4].badge("Needs review", icon=":material/flag:", color="orange")


def line_items_table(items: list, currency: str = "INR") -> None:
    """Purchased items, or a hint that none were found."""
    if not items:
        st.caption("No line items were recognised on this invoice.")
        return
    table = pd.DataFrame(items)
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "description": "Item", "quantity": st.column_config.NumberColumn("Qty", format="%g"),
        "rate": st.column_config.NumberColumn("Rate", format="%.2f"),
        "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
    })
    st.caption(f"{len(items)} item(s) · items total {money(table['amount'].sum(), currency)}")


def load_demo_data() -> None:
    """Scan the sample invoices into the database with a live progress display."""
    from scripts.scan_folder import scan_folder

    with st.status("Loading the sample invoices...", expanded=True) as status:
        bar = st.progress(0.0)

        def progress(done, total, name):
            bar.progress(done / total, text=f"Reading {name} ({done + 1}/{total})")

        results = scan_folder(config.SAMPLES_DIR, on_progress=progress)
        bar.progress(1.0, text="Done")
        added = sum(r["status"] != "EXISTS" for r in results)
        status.update(label=f"Sample data loaded: {added} new invoice(s)", state="complete", expanded=False)
    flash(f"Loaded {added} sample invoice(s)", "📦")
