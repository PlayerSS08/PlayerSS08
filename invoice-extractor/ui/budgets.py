"""Budgets: set a monthly limit per category and watch progress."""

import pandas as pd
import streamlit as st

from analytics import dashboard
from extractor import categories
from storage import db
from ui import components

STATUS = {"ok": ("On track", "green", ":material/check_circle:"),
          "warning": ("Close to limit", "orange", ":material/warning:"),
          "over": ("Over budget", "red", ":material/error:")}

st.title(":material/savings: Budgets")
st.caption("Set how much you want to spend per category each month. "
           "You'll see a warning at 80% and an alert when a budget is exceeded.")

df = db.get_all_invoices()
budgets = db.get_budgets()

months = sorted(set(pd.to_datetime(df["invoice_date"], errors="coerce").dropna().dt.strftime("%Y-%m"))
                | {pd.Timestamp.today().strftime("%Y-%m")}, reverse=True)
latest = dashboard.latest_month(df).strftime("%Y-%m")
month = st.selectbox("Month", months, index=months.index(latest) if latest in months else 0,
                     format_func=lambda m: pd.Period(m).strftime("%B %Y"))

left, right = st.columns([3, 2])
with left:
    status = dashboard.budget_status(df, budgets, month)
    if status.empty:
        st.info("No budgets yet - add some on the right.", icon=":material/savings:")
    for _, row in status.iterrows():
        label, colour, icon = STATUS[row["status"]]
        with st.container(border=True):
            top = st.columns([3, 2])
            top[0].markdown(f"**{row['category']}**")
            top[1].badge(label, icon=icon, color=colour)
            st.progress(min(row["used"], 1.0),
                        text=f"{components.money(row['spent'])} of {components.money(row['limit'])} "
                             f"({row['used']:.0%})")
            remaining = row["limit"] - row["spent"]
            st.caption(f"{components.money(remaining)} left this month" if remaining >= 0
                       else f"{components.money(-remaining)} over the limit")

with right:
    with st.container(border=True):
        st.subheader("Edit budgets", anchor=False)
        table = pd.DataFrame({"category": categories.category_names()})
        table["monthly_limit"] = table["category"].map(budgets).astype(float)
        edited = st.data_editor(table, hide_index=True, width="stretch", key="budget_editor",
                                disabled=["category"], column_config={
                                    "category": "Category",
                                    "monthly_limit": st.column_config.NumberColumn(
                                        "Monthly limit (₹)", min_value=0, step=500, format="₹ %d")})
        if st.button("Save budgets", type="primary", icon=":material/save:"):
            for _, row in edited.iterrows():
                limit = row["monthly_limit"]
                db.set_budget(row["category"], None if pd.isna(limit) else float(limit))
            components.flash("Budgets saved", "💰")
            st.rerun()
