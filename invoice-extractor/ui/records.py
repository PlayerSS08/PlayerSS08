"""Records: search and filter saved invoices, open one to view/edit/delete, bulk edit, export."""

import pandas as pd
import streamlit as st

from analytics import dashboard
from extractor import categories
from extractor.parser import EDITABLE_FIELDS, convert_field
from storage import db, export
from ui import components

TABLE_COLUMNS = ["id", "invoice_date", "vendor", "category", "invoice_number", "total_amount",
                 "payment_method", "needs_review"]
BULK_COLUMNS = ["id", "invoice_date", "invoice_time", "vendor", "category", "invoice_number",
                "total_amount", "subtotal", "cgst", "sgst", "igst", "gstin", "payment_method",
                "needs_review", "warnings", "source_file", "scanned_at"]
BULK_EDITABLE = ["invoice_date", "invoice_time", "vendor", "category", "invoice_number",
                 "total_amount", "subtotal", "cgst", "sgst", "igst", "gstin", "payment_method",
                 "needs_review"]
COLUMN_CONFIG = {
    "id": st.column_config.NumberColumn("ID", width="small"),
    "invoice_date": "Date", "invoice_time": "Time", "vendor": "Vendor", "category": "Category",
    "invoice_number": "Invoice no.", "gstin": "GSTIN", "warnings": "Warnings",
    "payment_method": "Paid by", "source_file": "File", "scanned_at": "Scanned at",
    "total_amount": st.column_config.NumberColumn("Total", format="₹ %.2f"),
    "subtotal": st.column_config.NumberColumn("Subtotal", format="%.2f"),
    "cgst": st.column_config.NumberColumn("CGST", format="%.2f"),
    "sgst": st.column_config.NumberColumn("SGST", format="%.2f"),
    "igst": st.column_config.NumberColumn("IGST", format="%.2f"),
    "needs_review": st.column_config.CheckboxColumn("Review?"),
}


# ----------------------------------------------------------------------
# Dialogs
# ----------------------------------------------------------------------
@st.dialog("Delete invoice?")
def confirm_delete(ids: list):
    st.write(f"This permanently removes **{len(ids)}** invoice(s): IDs {', '.join(map(str, ids))}.")
    left, right = st.columns(2)
    if left.button("Delete", type="primary", icon=":material/delete:", width="stretch"):
        removed = sum(db.delete_invoice(i) for i in ids)
        st.session_state.pop("records_table", None)
        components.flash(f"Deleted {removed} invoice(s)", "🗑️")
        st.rerun()
    if right.button("Cancel", width="stretch"):
        st.rerun()


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------
def filters(df: pd.DataFrame) -> pd.DataFrame:
    with st.container(border=True):
        top = st.columns([3, 2, 1])
        search = top[0].text_input("Search", placeholder="Vendor or invoice number",
                                   icon=":material/search:", label_visibility="collapsed")
        period = top[1].segmented_control("Period", list(dashboard.PERIODS), default="All",
                                          key="records_period", label_visibility="collapsed")
        review_only = top[2].toggle("Needs review only")

        cats = st.pills("Category", categories.category_names(), selection_mode="multi",
                        key="records_categories")
        low = st.columns([2, 2])
        vendors = low[0].multiselect("Vendor", sorted(df["vendor"].dropna().unique()),
                                     placeholder="All vendors")
        amounts = df["total_amount"].dropna()
        top_amount = float(amounts.max()) if not amounts.empty else 0.0
        amount_range = (0.0, top_amount)
        if top_amount > 0:
            amount_range = low[1].slider("Amount range (₹)", 0.0, top_amount, (0.0, top_amount),
                                         step=float(max(1, round(top_amount / 100))))

    data = dashboard.filter_period(df, period or "All")
    return db.filter_invoices(
        data, search=search, vendors=vendors, review_only=review_only, categories=cats,
        min_amount=amount_range[0] or None,
        max_amount=amount_range[1] if amount_range[1] < top_amount else None)


# ----------------------------------------------------------------------
# Detail panel for one invoice
# ----------------------------------------------------------------------
def detail(invoice_id: int) -> None:
    record = db.get_invoice(invoice_id)
    if record is None:
        return
    with st.container(border=True):
        st.subheader(f"{record.get('vendor') or 'Unknown vendor'} · "
                     f"{components.money(record.get('total_amount'), record.get('currency'))}", anchor=False)
        components.badges_for(record)
        if record.get("warnings"):
            st.warning(record["warnings"], icon=":material/flag:")
        left, right = st.columns([1, 2])
        with left:
            preview = components.preview_from_record(record)
            if preview:
                st.image(preview, width="stretch")
                st.caption(record["source_file"])
            else:
                st.info("Original file not stored (saved before this feature existed).")
        with right:
            tab_edit, tab_items, tab_raw = st.tabs([":material/edit: Edit", ":material/list: Line items",
                                                    ":material/notes: Raw text"])
            with tab_edit:
                edit_form(record)
            with tab_items:
                components.line_items_table(record["line_items"], record.get("currency"))
            with tab_raw:
                st.code(record.get("raw_text") or "", language=None)


def edit_form(record: dict) -> None:
    with st.form(f"edit_{record['id']}", border=False):
        c1, c2 = st.columns(2)
        values = {
            "vendor": c1.text_input("Vendor", record.get("vendor") or ""),
            "invoice_number": c2.text_input("Invoice number", record.get("invoice_number") or ""),
            "invoice_date": c1.text_input("Date (YYYY-MM-DD)", record.get("invoice_date") or ""),
            "invoice_time": c2.text_input("Time", record.get("invoice_time") or ""),
            "total_amount": c1.text_input("Total", "" if record.get("total_amount") is None
                                          else f"{record['total_amount']:.2f}"),
            "gstin": c2.text_input("GSTIN", record.get("gstin") or ""),
        }
        names = categories.category_names()
        values["category"] = c1.selectbox("Category", names, index=names.index(record["category"])
                                          if record.get("category") in names else len(names) - 1)
        values["needs_review"] = c2.checkbox("Needs review", bool(record.get("needs_review")))
        save_col, delete_col = st.columns(2)
        saved = save_col.form_submit_button("Save changes", type="primary", icon=":material/save:",
                                            width="stretch")
        deleted = delete_col.form_submit_button("Delete", icon=":material/delete:", width="stretch")
    if saved:
        try:
            changes = {k: convert_field(k, v) if k in EDITABLE_FIELDS else v for k, v in values.items()}
        except ValueError as error:
            st.error(str(error))
            return
        db.update_invoice(record["id"], changes)
        components.flash("Invoice updated")
        st.rerun()
    if deleted:
        confirm_delete([record["id"]])


# ----------------------------------------------------------------------
# Bulk edit
# ----------------------------------------------------------------------
def bulk_edit(filtered: pd.DataFrame) -> None:
    st.caption("Edit cells directly, tick rows to delete, then press **Apply changes**.")
    table = filtered[BULK_COLUMNS].copy()
    table.insert(0, "Delete", False)
    edited = st.data_editor(
        table, key="records_editor", hide_index=True, width="stretch",
        disabled=[c for c in BULK_COLUMNS if c not in BULK_EDITABLE],
        column_config={**COLUMN_CONFIG, "Delete": st.column_config.CheckboxColumn("🗑️", width="small"),
                       "category": st.column_config.SelectboxColumn("Category",
                                                                    options=categories.category_names())})
    if st.button("Apply changes", type="primary", icon=":material/done:"):
        updated, to_delete = 0, []
        for (_, before), (_, after) in zip(table.iterrows(), edited.iterrows()):
            if after["Delete"]:
                to_delete.append(int(before["id"]))
                continue
            changes = {}
            for column in BULK_EDITABLE:
                old, new = before[column], after[column]
                if not (pd.isna(old) and pd.isna(new)) and old != new:
                    changes[column] = None if pd.isna(new) else new
            try:
                changes = {k: convert_field(k, v) if k in EDITABLE_FIELDS else v for k, v in changes.items()}
            except ValueError as error:
                st.error(f"Row {int(before['id'])}: {error}")
                return
            if changes:
                updated += db.update_invoice(int(before["id"]), changes)
        if updated:
            components.flash(f"Updated {updated} invoice(s)")
        if to_delete:
            confirm_delete(to_delete)
        else:
            st.rerun()


# ----------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------
st.title(":material/table_view: Records")
df = db.get_all_invoices()
if df.empty:
    st.info("No invoices saved yet.", icon=":material/inbox:")
    st.page_link("ui/upload.py", label="Upload invoices", icon=":material/upload_file:")
    st.stop()

filtered = filters(df)
metrics = dashboard.summary_metrics(filtered)
info, d1, d2 = st.columns([3, 1, 1])
info.markdown(f"**{len(filtered)}** of {len(df)} invoices · total "
              f"**{components.money(metrics['total_spend'])}** · "
              f"{metrics['needs_review']} need review")
d1.download_button("CSV", export.to_csv(filtered), "invoices.csv", "text/csv",
                   icon=":material/download:", width="stretch")
d2.download_button("Excel", export.to_excel(filtered), "invoices.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   icon=":material/download:", width="stretch")

browse, bulk = st.tabs([":material/visibility: Browse", ":material/edit_note: Bulk edit"])
with browse:
    st.caption("Click a row to open the invoice.")
    event = st.dataframe(filtered[TABLE_COLUMNS], key="records_table", hide_index=True,
                         width="stretch", on_select="rerun", selection_mode="single-row",
                         column_config=COLUMN_CONFIG)
    rows = event.selection.rows if event else []
    if rows:
        detail(int(filtered.iloc[rows[0]]["id"]))
with bulk:
    bulk_edit(filtered)
