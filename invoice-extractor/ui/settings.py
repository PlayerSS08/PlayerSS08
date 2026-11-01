"""Settings: OCR engine, review threshold, data management and about."""

import streamlit as st

import config
from extractor import ocr
from storage import db, export
from ui import components

st.title(":material/settings: Settings")

# ---------------------------------------------------------------- OCR
with st.container(border=True):
    st.subheader(":material/document_scanner: OCR engine", anchor=False)
    status = ocr.engine_status()
    cols = st.columns(3)
    for col, (engine, available) in zip(cols, status.items()):
        label = components.ENGINE_LABELS[engine]
        if available:
            col.badge(f"{label}: available", icon=":material/check_circle:", color="green")
        elif available is None:
            col.badge(f"{label}: optional (pip install easyocr)", color="gray")
        else:
            col.badge(f"{label}: not found", icon=":material/cancel:", color="red")
    options = ["auto", "bundled", "tesseract", "easyocr"]
    choice = st.selectbox("Preferred engine", options, index=options.index(config.OCR_ENGINE)
                          if config.OCR_ENGINE in options else 0,
                          format_func=lambda o: "Automatic (recommended)" if o == "auto"
                          else components.ENGINE_LABELS[o])
    st.caption(f"Currently using: **{components.ENGINE_LABELS[ocr.active_engine()]}**. "
               "If the preferred engine is missing, the next available one is used.")

# ---------------------------------------------------------------- review
with st.container(border=True):
    st.subheader(":material/rule: Review", anchor=False)
    threshold = st.slider("Flag fields for review below this confidence", 0.3, 0.9,
                          float(config.REVIEW_THRESHOLD), 0.05)
    st.caption("Higher = stricter (more invoices flagged). Applies to newly extracted invoices.")

if st.button("Save settings", type="primary", icon=":material/save:"):
    db.set_setting("ocr_engine", choice)
    db.set_setting("review_threshold", threshold)
    components.flash("Settings saved", "⚙️")
    st.rerun()

# ---------------------------------------------------------------- data
with st.container(border=True):
    st.subheader(":material/database: Data", anchor=False)
    df = db.get_all_invoices()
    st.write(f"Database: `{config.DATABASE_FILE}` · {len(df)} invoices")
    a, b, c = st.columns(3)
    a.download_button("Backup (CSV, with raw text)", export.to_csv(df, include_raw_text=True),
                      "invoices-backup.csv", "text/csv", icon=":material/backup:", width="stretch")
    if b.button("Load sample invoices", icon=":material/download:", width="stretch"):
        components.load_demo_data()
        st.rerun()

    @st.dialog("Delete ALL invoices?")
    def confirm_reset():
        st.warning("This removes every saved invoice. Budgets and settings are kept. "
                   "This cannot be undone.", icon=":material/warning:")
        typed = st.text_input("Type DELETE to confirm")
        if st.button("Delete everything", type="primary", disabled=typed != "DELETE"):
            removed = db.clear_all()
            st.session_state.pop("results", None)
            components.flash(f"Deleted {removed} invoice(s)", "🗑️")
            st.rerun()

    if c.button("Delete all invoices", icon=":material/delete_forever:", width="stretch",
                disabled=df.empty):
        confirm_reset()

# ---------------------------------------------------------------- about
with st.expander("About this app"):
    st.markdown(
        "**Invoice Extractor** reads invoices (digital PDFs, scanned PDFs, photos) and extracts the "
        "date, time, vendor, invoice number, total, GST details, line items, category and payment "
        "method with a confidence score for each field.\n\n"
        "Built with Python only: pymupdf · pdfplumber · Tesseract (tesserocr / pytesseract) · "
        "OpenCV · pandas · SQLite · Streamlit · Plotly.")
