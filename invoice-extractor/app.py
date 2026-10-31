"""
Invoice Extractor - Streamlit user interface (pure Python, no HTML/CSS/JS).

Run with:  streamlit run app.py

Pages (chosen in the sidebar):
    1. Upload and Extract  - upload files, check/correct fields, save
    2. Invoice Records     - filter, edit, delete, download CSV/Excel
    3. Dashboard           - spending charts and possible duplicates
    4. Batch Scan          - process every file in the invoices/ folder
"""

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from extractor import ocr
from extractor.parser import EDITABLE_FIELDS, apply_corrections, convert_field, process_file
from storage import db, export

FIELD_LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date (YYYY-MM-DD)",
    "invoice_time": "Time (HH:MM)",
    "vendor": "Vendor / source",
    "gstin": "GSTIN",
    "subtotal": "Subtotal",
    "cgst": "CGST",
    "sgst": "SGST",
    "igst": "IGST",
    "total_amount": "Total amount",
}
# Fields whose low confidence is worth a warning icon.
SCORED_FIELDS = ("invoice_number", "invoice_date", "invoice_time", "vendor",
                 "gstin", "total_amount")


# ======================================================================
# Helpers
# ======================================================================
def render_preview(name: str, data: bytes):
    """Image bytes for the preview: the image itself, or page 1 of a PDF."""
    if Path(name).suffix.lower() != ".pdf":
        return data
    try:
        import pymupdf
        with pymupdf.open(stream=data, filetype="pdf") as document:
            return document[0].get_pixmap(dpi=100).tobytes("png")
    except Exception:
        return None


def run_pipeline(name: str, data: bytes):
    """Save uploaded bytes to a temporary file and run the extractor on it."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / Path(name).name
        path.write_bytes(data)
        return process_file(path, display_name=name)


def fields_table(invoice) -> pd.DataFrame:
    """One row per field: value (editable), confidence and a warning flag."""
    rows = []
    for name in EDITABLE_FIELDS:
        value = getattr(invoice, name)
        score = invoice.confidence.get(name)
        low = name in SCORED_FIELDS and (score or 0) < config.REVIEW_THRESHOLD
        optional_missing = name in ("invoice_time", "gstin") and value is None
        rows.append({
            "Field": FIELD_LABELS[name],
            "Value": "" if value is None else str(value),
            "Confidence": score,
            "Check": "⚠️ check" if low and not optional_missing else "",
            "key": name,
        })
    return pd.DataFrame(rows)


def flash(message: str, kind: str = "success"):
    """Remember a message to show after st.rerun()."""
    st.session_state["flash"] = (kind, message)


def show_flash():
    """Show (once) a message stored with flash()."""
    if "flash" in st.session_state:
        kind, message = st.session_state.pop("flash")
        getattr(st, kind)(message)


def ocr_banner():
    """Tell the user up front if images / scanned PDFs cannot be read."""
    if not ocr.ocr_available():
        st.warning(ocr.INSTALL_HELP, icon="⚠️")


# ======================================================================
# Page 1: Upload and Extract
# ======================================================================
def page_upload():
    st.header("Upload and Extract")
    st.caption("Upload invoices or bills as PDF or images. Check the extracted fields, "
               "correct anything that is wrong, then save.")
    ocr_banner()

    uploads = st.file_uploader("Invoice files", type=["pdf", "jpg", "jpeg", "png"],
                               accept_multiple_files=True)
    if not uploads:
        st.info("No files uploaded yet.")
        return

    results = st.session_state.setdefault("results", {})
    pending = [u for u in uploads if u.file_id not in results]
    if pending:
        progress = st.progress(0.0, text="Extracting...")
        for i, upload in enumerate(pending, start=1):
            progress.progress((i - 1) / len(pending), text=f"Reading {upload.name} ({i}/{len(pending)})")
            data = upload.getvalue()
            invoice = run_pipeline(upload.name, data)
            results[upload.file_id] = {
                "invoice": invoice,
                "preview": render_preview(upload.name, data),
                "status": "pending",
            }
        progress.progress(1.0, text="Done")

    for upload in uploads:
        show_result_card(upload.file_id, results[upload.file_id])


def show_result_card(key: str, result: dict):
    """Preview + editable fields + Save/Skip for one uploaded file."""
    invoice = result["invoice"]
    with st.container(border=True):
        st.subheader(invoice.source_file)
        left, right = st.columns([1, 2])

        with left:
            if result["preview"]:
                st.image(result["preview"], use_container_width=True)
            else:
                st.write("No preview available.")
            st.caption(f"Method: {invoice.extraction_method} · "
                       f"overall confidence {invoice.confidence.get('overall', 0):.0%}")

        with right:
            duplicate = bool(invoice.file_hash) and db.hash_exists(invoice.file_hash)
            if result["status"] == "saved":
                st.success("Saved to the database.")
            elif result["status"] == "skipped":
                st.info("Skipped (not saved).")
            elif duplicate:
                st.info("Duplicate: this exact file is already in the database.")

            if invoice.needs_review:
                st.warning("Needs review: " + ("; ".join(invoice.warnings)
                                               or "some fields are missing or uncertain"))

            edited = st.data_editor(
                fields_table(invoice), key=f"editor_{key}", hide_index=True,
                use_container_width=True, disabled=["Field", "Confidence", "Check"],
                column_order=["Field", "Value", "Confidence", "Check"],
                column_config={
                    "Value": st.column_config.TextColumn("Value (editable)"),
                    "Confidence": st.column_config.ProgressColumn(
                        "Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                    "Check": st.column_config.TextColumn("⚠️"),
                },
            )

            can_act = result["status"] == "pending" and not duplicate
            save_col, skip_col, _ = st.columns([1, 1, 3])
            if save_col.button("Save to database", key=f"save_{key}", type="primary",
                               disabled=not can_act):
                save_edited(key, result, edited)
            if skip_col.button("Skip", key=f"skip_{key}", disabled=not can_act):
                result["status"] = "skipped"
                st.rerun()

        with st.expander("Show raw extracted text"):
            st.text(invoice.raw_text or "(no text extracted)")


def save_edited(key: str, result: dict, edited: pd.DataFrame):
    """Apply the user's corrections and insert into the database."""
    changes = dict(zip(edited["key"], edited["Value"]))
    try:
        invoice = apply_corrections(result["invoice"], changes)
    except ValueError as error:
        st.error(str(error))
        return
    if db.insert_invoice(invoice):
        result["invoice"], result["status"] = invoice, "saved"
        st.rerun()
    else:
        st.info("Duplicate: this exact file is already in the database.")


# ======================================================================
# Page 2: Invoice Records
# ======================================================================
RECORD_COLUMNS = ["id", "invoice_date", "invoice_time", "vendor", "invoice_number",
                  "total_amount", "subtotal", "cgst", "sgst", "igst", "gstin",
                  "needs_review", "warnings", "extraction_method", "source_file", "scanned_at"]
EDITABLE_RECORD_COLUMNS = ["invoice_date", "invoice_time", "vendor", "invoice_number",
                           "total_amount", "subtotal", "cgst", "sgst", "igst", "gstin",
                           "needs_review"]


def record_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Draw the filter widgets and return the filtered rows."""
    search = st.text_input("Search vendor or invoice number")
    c1, c2, c3, c4 = st.columns(4)
    dates = pd.to_datetime(df["invoice_date"], errors="coerce").dropna()
    use_dates = c1.checkbox("Filter by date")
    start = end = None
    if use_dates:
        default = (dates.min().date(), dates.max().date()) if not dates.empty else (date.today(), date.today())
        chosen = c1.date_input("Date range", value=default)
        if isinstance(chosen, (list, tuple)) and len(chosen) == 2:
            start, end = chosen
    vendors = c2.multiselect("Vendor", sorted(df["vendor"].dropna().unique()))
    min_amount = c3.number_input("Min amount", min_value=0.0, value=0.0, step=100.0)
    max_value = float(df["total_amount"].max() or 0) if df["total_amount"].notna().any() else 0.0
    max_amount = c3.number_input("Max amount", min_value=0.0, value=max_value, step=100.0)
    review_only = c4.checkbox("Needs review only")
    return db.filter_invoices(df, search=search, start_date=start, end_date=end,
                              vendors=vendors, min_amount=min_amount or None,
                              max_amount=max_amount if max_amount < max_value else None,
                              review_only=review_only)


def page_records():
    st.header("Invoice Records")
    show_flash()
    df = db.get_all_invoices()
    if df.empty:
        st.info("No invoices saved yet. Use 'Upload and Extract' or 'Batch Scan'.")
        return

    filtered = record_filters(df)
    st.caption(f"Showing {len(filtered)} of {len(df)} invoices. Edit cells, tick "
               "'Delete' to remove rows, then press 'Apply changes'.")

    table = filtered[RECORD_COLUMNS].copy()
    table.insert(0, "Delete", False)
    edited = st.data_editor(
        table, key="records_editor", hide_index=True, use_container_width=True,
        disabled=[c for c in RECORD_COLUMNS if c not in EDITABLE_RECORD_COLUMNS],
        column_config={
            "Delete": st.column_config.CheckboxColumn("Delete"),
            "total_amount": st.column_config.NumberColumn("Total", format="₹ %.2f"),
            "needs_review": st.column_config.CheckboxColumn("Needs review"),
        },
    )

    if st.button("Apply changes", type="primary"):
        apply_record_changes(table, edited)

    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download CSV", export.to_csv(filtered), "invoices.csv", "text/csv")
    d2.download_button("Download Excel", export.to_excel(filtered), "invoices.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def apply_record_changes(original: pd.DataFrame, edited: pd.DataFrame):
    """Write edits and deletions from the records table to the database."""
    updated = deleted = 0
    for (_, before), (_, after) in zip(original.iterrows(), edited.iterrows()):
        row_id = int(before["id"])
        if after["Delete"]:
            deleted += db.delete_invoice(row_id)
            continue
        changes = {}
        for column in EDITABLE_RECORD_COLUMNS:
            old, new = before[column], after[column]
            if not (pd.isna(old) and pd.isna(new)) and old != new:
                changes[column] = None if pd.isna(new) else new
        try:   # check typed dates / amounts, same rules as the upload page
            for column in list(changes):
                if column in EDITABLE_FIELDS:
                    changes[column] = convert_field(column, changes[column])
        except ValueError as error:
            st.error(f"Row {row_id}: {error}")
            return
        if changes:
            updated += db.update_invoice(row_id, changes)
    flash(f"Updated {updated} row(s), deleted {deleted} row(s).")
    st.rerun()


# ======================================================================
# Main
# ======================================================================
PAGES = {
    "Upload and Extract": page_upload,
    "Invoice Records": page_records,
}


def main():
    st.set_page_config(page_title="Invoice Extractor", layout="wide")
    db.init_db()
    st.sidebar.title("🧾 Invoice Extractor")
    choice = st.sidebar.radio("Go to", list(PAGES))
    st.sidebar.caption(f"OCR engine: {ocr.active_engine()}")
    PAGES[choice]()


if __name__ == "__main__":
    main()
