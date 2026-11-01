"""Home: a quick overview - key numbers, insights, shortcuts and recent invoices."""

import pandas as pd
import streamlit as st

from analytics import dashboard
from storage import db
from ui import components

st.title("🧾 Invoice Extractor")
st.caption("Turn invoice PDFs and bill photos into clean, searchable spending data.")

df = db.get_all_invoices()

# ---------------------------------------------------------------- empty state
if df.empty:
    with st.container(border=True):
        st.subheader("Welcome! 👋")
        st.write("Nothing is saved yet. Upload your own invoices, or load the 18 sample "
                 "invoices to explore every feature straight away.")
        left, right, _ = st.columns([1, 1, 2])
        if left.button("Load sample invoices", icon=":material/download:", type="primary"):
            components.load_demo_data()
            st.rerun()
        right.page_link("ui/upload.py", label="Upload invoices", icon=":material/upload_file:")
    st.stop()

# ---------------------------------------------------------------- key numbers
mom = dashboard.month_over_month(df)
metrics = dashboard.summary_metrics(df)
c1, c2, c3, c4 = st.columns(4)
with c1.container(border=True):
    st.metric(mom["month"], components.money_short(mom["this_month"]),
              delta=None if mom["change_pct"] is None else f"{mom['change_pct']:+.0f}% vs {mom['previous']}",
              delta_color="inverse")
with c2.container(border=True):
    st.metric("All-time spend", components.money_short(metrics["total_spend"]))
with c3.container(border=True):
    st.metric("Invoices", metrics["total_invoices"],
              delta=f"avg {components.money_short(metrics['average_invoice'])}", delta_color="off")
with c4.container(border=True):
    st.metric("Need review", metrics["needs_review"],
              delta="all clear" if metrics["needs_review"] == 0 else "check them",
              delta_color="normal" if metrics["needs_review"] == 0 else "inverse")

# ---------------------------------------------------------------- insights + actions
left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader(":material/lightbulb: Insights")
        notes = dashboard.insights(df, db.get_budgets())
        for note in notes:
            if note.startswith("⚠️"):
                st.warning(note.replace("⚠️ ", ""), icon=":material/warning:")
            else:
                st.markdown(f"- {note}")
with right:
    with st.container(border=True):
        st.subheader(":material/bolt: Quick actions")
        st.page_link("ui/upload.py", label="Upload new invoices", icon=":material/upload_file:")
        st.page_link("ui/records.py", label="Review & edit records", icon=":material/edit_note:")
        st.page_link("ui/dashboard.py", label="Open the dashboard", icon=":material/monitoring:")
        st.page_link("ui/budgets.py", label="Set monthly budgets", icon=":material/savings:")
        st.page_link("ui/batch.py", label="Scan the invoices folder", icon=":material/folder_open:")

# ---------------------------------------------------------------- charts + recent
left, right = st.columns(2)
with left:
    st.plotly_chart(dashboard.category_figure(df), width="stretch")
with right:
    st.subheader(":material/history: Recent invoices")
    recent = df.sort_values("scanned_at", ascending=False).head(6)
    st.dataframe(
        recent[["invoice_date", "vendor", "category", "total_amount", "needs_review"]],
        hide_index=True, width="stretch",
        column_config={
            "invoice_date": "Date", "vendor": "Vendor", "category": "Category",
            "total_amount": st.column_config.NumberColumn("Total", format="₹ %.2f"),
            "needs_review": st.column_config.CheckboxColumn("Review?"),
        })
    review = df[df["needs_review"]]
    if not review.empty:
        st.page_link("ui/records.py", label=f"{len(review)} invoice(s) need review →",
                     icon=":material/flag:")
