"""Upload & Extract: upload files, watch them being processed, correct and save."""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from extractor import categories
from extractor.parser import apply_corrections, process_file
from storage import db
from ui import components

# Fields shown in the editable table (category/currency/payment get dropdowns).
TABLE_FIELDS = {
    "invoice_number": "Invoice number", "invoice_date": "Date (YYYY-MM-DD)",
    "invoice_time": "Time (HH:MM)", "vendor": "Vendor / source", "gstin": "GSTIN",
    "subtotal": "Subtotal", "cgst": "CGST", "sgst": "SGST", "igst": "IGST",
    "total_amount": "Total amount",
}
SCORED = ("invoice_number", "invoice_date", "invoice_time", "vendor", "gstin", "total_amount")
OPTIONAL = ("invoice_time", "gstin")
CURRENCIES = list(components.CURRENCY_SYMBOLS)
PAYMENTS = ["", "UPI", "Card", "Cash", "Net Banking", "Wallet"]


# ----------------------------------------------------------------------
# Processing
# ----------------------------------------------------------------------
def run_pipeline(name: str, data: bytes):
    """Write the upload to a temporary file and run the extractor on it."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / Path(name).name
        path.write_bytes(data)
        return process_file(path, display_name=name)


def process_new(uploads, results: dict) -> None:
    """Extract every new upload, showing live progress in a status box."""
    pending = [u for u in uploads if u.file_id not in results]
    if not pending:
        return
    with st.status(f"Extracting {len(pending)} file(s)...", expanded=True) as status:
        bar = st.progress(0.0)
        for i, upload in enumerate(pending):
            kind = "PDF" if upload.name.lower().endswith(".pdf") else "image (OCR)"
            bar.progress(i / len(pending), text=f"Reading {upload.name} - {kind}")
            data = upload.getvalue()
            invoice = run_pipeline(upload.name, data)
            results[upload.file_id] = {
                "invoice": invoice, "data": data, "name": upload.name,
                "preview": components.preview_bytes(upload.name, data),
                "status": "duplicate" if invoice.file_hash and db.hash_exists(invoice.file_hash) else "pending",
            }
            icon = "⚠️" if invoice.needs_review else "✅"
            st.write(f"{icon} **{upload.name}** → {invoice.vendor or 'unknown vendor'}, "
                     f"{components.money(invoice.total_amount, invoice.currency)}")
        bar.progress(1.0, text="Done")
        status.update(label=f"Extracted {len(pending)} file(s)", state="complete", expanded=False)


def save(result: dict, changes: dict) -> bool:
    """Apply corrections, keep a copy of the file and insert into the database."""
    try:
        invoice = apply_corrections(result["invoice"], changes)
    except ValueError as error:
        st.error(str(error), icon=":material/error:")
        return False
    stored = db.save_original_file(invoice.file_hash, result["name"], result["data"])
    if db.insert_invoice(invoice, file_path=stored):
        result["invoice"], result["status"] = invoice, "saved"
        return True
    result["status"] = "duplicate"
    return False


# ----------------------------------------------------------------------
# One result card
# ----------------------------------------------------------------------
def fields_table(invoice) -> pd.DataFrame:
    rows = []
    for name, label in TABLE_FIELDS.items():
        value = getattr(invoice, name)
        score = invoice.confidence.get(name)
        low = name in SCORED and (score or 0) < config.REVIEW_THRESHOLD and \
            not (name in OPTIONAL and value is None)
        shown = "" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)
        rows.append({"Field": label, "Value": shown, "Confidence": score,
                     "Check": "⚠️ check" if low else "", "key": name})
    return pd.DataFrame(rows)


def result_card(key: str, result: dict) -> None:
    invoice = result["invoice"]
    status = result["status"]
    with st.container(border=True):
        head, badges = st.columns([2, 3])
        head.subheader(invoice.source_file, anchor=False)
        with badges:
            row = st.columns(4)
            row[0].badge(components.METHOD_LABELS.get(invoice.extraction_method, "?"), color="blue")
            overall = invoice.confidence.get("overall", 0)
            row[1].badge(f"{overall:.0%} confident", color=components.confidence_colour(overall))
            if status == "saved":
                row[2].badge("Saved", icon=":material/check_circle:", color="green")
            elif status == "duplicate":
                row[2].badge("Duplicate", icon=":material/content_copy:", color="gray")
            elif status == "skipped":
                row[2].badge("Skipped", color="gray")
            if invoice.needs_review and status == "pending":
                row[3].badge("Needs review", icon=":material/flag:", color="orange")

        preview_col, body = st.columns([1, 2])
        with preview_col:
            if result["preview"]:
                st.image(result["preview"], width="stretch")
            else:
                st.info("No preview available.")

        with body:
            if status == "duplicate":
                st.info("This exact file is already in the database.", icon=":material/content_copy:")
            if invoice.warnings and status == "pending":
                st.warning(" · ".join(invoice.warnings), icon=":material/flag:")

            tab_fields, tab_items, tab_raw = st.tabs(
                [":material/edit: Fields", f":material/list: Line items ({len(invoice.line_items)})",
                 ":material/notes: Raw text"])
            with tab_fields:
                c1, c2, c3 = st.columns(3)
                names = categories.category_names()
                category = c1.selectbox("Category", names, key=f"cat_{key}",
                                        index=names.index(invoice.category) if invoice.category in names else len(names) - 1)
                currency = c2.selectbox("Currency", CURRENCIES, key=f"cur_{key}",
                                        index=CURRENCIES.index(invoice.currency) if invoice.currency in CURRENCIES else 0)
                payment = c3.selectbox("Paid by", PAYMENTS, key=f"pay_{key}",
                                       index=PAYMENTS.index(invoice.payment_method or ""),
                                       format_func=lambda p: p or "Not stated")
                edited = st.data_editor(
                    fields_table(invoice), key=f"editor_{key}", hide_index=True,
                    width="stretch", disabled=["Field", "Confidence", "Check"],
                    column_order=["Field", "Value", "Confidence", "Check"],
                    column_config={
                        "Value": st.column_config.TextColumn("Value (click to edit)"),
                        "Confidence": st.column_config.ProgressColumn(
                            "Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
                        "Check": st.column_config.TextColumn("⚠️", width="small"),
                    })
            with tab_items:
                components.line_items_table(invoice.line_items, invoice.currency)
            with tab_raw:
                st.code(invoice.raw_text or "(no text extracted)", language=None)

            if status == "pending":
                save_col, skip_col, _ = st.columns([2, 1, 3])
                if save_col.button("Save to database", key=f"save_{key}", type="primary",
                                   icon=":material/save:"):
                    changes = dict(zip(edited["key"], edited["Value"]))
                    changes.update(category=category, currency=currency, payment_method=payment)
                    if save(result, changes):
                        components.flash(f"Saved {invoice.source_file}")
                    st.rerun()
                if skip_col.button("Skip", key=f"skip_{key}", icon=":material/close:"):
                    result["status"] = "skipped"
                    st.rerun()


# ----------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------
st.title(":material/upload_file: Upload & Extract")
st.caption("Drop invoices or bill photos (PDF, JPG, PNG). Check the highlighted fields, "
           "fix anything that's wrong, then save.")
components.ocr_warning()

uploads = st.file_uploader("Invoice files", type=["pdf", "jpg", "jpeg", "png"],
                           accept_multiple_files=True, label_visibility="collapsed")
if not uploads:
    st.info("Tip: you can select many files at once. Sample invoices are in tests/samples/.",
            icon=":material/lightbulb:")
    st.stop()

results = st.session_state.setdefault("results", {})
process_new(uploads, results)
current = [(u.file_id, results[u.file_id]) for u in uploads]

# Summary strip + bulk actions
statuses = [r["status"] for _, r in current]
ready = [(k, r) for k, r in current if r["status"] == "pending" and not r["invoice"].needs_review]
pending = [(k, r) for k, r in current if r["status"] == "pending"]
m1, m2, m3, m4, m5 = st.columns([1, 1, 1, 1, 2])
m1.metric("Files", len(current))
m2.metric("Ready to save", len(ready))
m3.metric("Need review", sum(r["invoice"].needs_review for _, r in pending))
m4.metric("Saved", statuses.count("saved"))
with m5:
    if st.button(f"Save all {len(ready)} ready invoice(s)", icon=":material/done_all:",
                 type="primary", disabled=not ready, width="stretch"):
        saved = sum(save(r, {}) for _, r in ready)
        components.flash(f"Saved {saved} invoice(s)")
        st.rerun()
    show = st.segmented_control("Show", ["All", "Needs review", "Ready", "Done"], default="All",
                                key="upload_filter")

for key, result in current:
    needs = result["invoice"].needs_review and result["status"] == "pending"
    done = result["status"] in ("saved", "duplicate", "skipped")
    if show == "Needs review" and not needs:
        continue
    if show == "Ready" and (needs or done):
        continue
    if show == "Done" and not done:
        continue
    result_card(key, result)
