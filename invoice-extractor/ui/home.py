"""
Home ("Overview"): read top to bottom in three tiers.

    1. Header       - page title, the month shown, one primary action
    2. Key figures  - one hero card (this month's spend) + three supporting cards
    3. Attention    - ONE strip listing what needs action (or "All caught up")
    4. Detail       - spend by category and recent invoices, side by side

Colour is reserved for meaning: blue = something you can click,
amber/green/red badges = status (always with a word, never colour alone).
"""

import pandas as pd
import streamlit as st

from analytics import dashboard
from storage import db
from ui import components

df = db.get_all_invoices()

# ---------------------------------------------------------------- 1. header
month_label = dashboard.latest_month(df).strftime("%B %Y") if not df.empty else \
    pd.Timestamp.today().strftime("%B %Y")
title_col, action_col = st.columns([3, 1], vertical_alignment="bottom")
with title_col:
    st.title("Overview", anchor=False)
    st.caption(f"{month_label} · latest month with invoices" if not df.empty else "No invoices yet")
with action_col:
    if st.button("Upload invoices", type="primary", icon=":material/upload_file:", width="stretch"):
        st.switch_page("ui/upload.py")

# ---------------------------------------------------------------- empty state
if df.empty:
    with st.container(border=True):
        st.subheader("Start with your first invoices", anchor=False)
        st.write("Upload PDFs or bill photos, or load the 19 sample invoices to see every "
                 "feature with realistic data.")
        if st.button("Load sample invoices", icon=":material/download:"):
            components.load_demo_data()
            st.rerun()
    st.stop()

# ---------------------------------------------------------------- 2. key figures
mom = dashboard.month_over_month(df)
budgets = db.get_budgets()
budget_rows = dashboard.budget_status(df, budgets, dashboard.latest_month(df))
at_risk = budget_rows[budget_rows["status"] != "ok"]
review_count = int(df["needs_review"].sum())

hero, invoices_card, review_card, budget_card = st.columns([2, 1, 1, 1])
with hero.container(border=True, height="stretch"):
    st.metric(f"Spend in {mom['month']}", components.money_short(mom["this_month"]),
              delta=None if mom["change_pct"] is None else f"{mom['change_pct']:+.0f}% vs {mom['previous']}",
              delta_color="inverse")
with invoices_card.container(border=True, height="stretch"):
    st.caption("Invoices")
    st.subheader(str(len(df)), anchor=False)
    st.caption(f"avg {components.money_short(df['total_amount'].mean())}")
with review_card.container(border=True, height="stretch"):
    st.caption("To review")
    st.subheader(str(review_count), anchor=False)
    if review_count:
        st.badge("Action needed", icon=":material/flag:", color="orange")
    else:
        st.badge("All checked", icon=":material/check_circle:", color="green")
with budget_card.container(border=True, height="stretch"):
    st.caption("Budgets")
    if not budgets:
        st.subheader("Not set", anchor=False)
        st.page_link("ui/budgets.py", label="Set budgets")
    elif at_risk.empty:
        st.subheader("On track", anchor=False)
        st.badge(f"{len(budgets)} watched", color="green")
    else:
        st.subheader(f"{len(at_risk)} at risk", anchor=False)
        over = int((at_risk["status"] == "over").sum())
        st.badge(f"{over} over limit" if over else "Close to limit", icon=":material/warning:",
                 color="red" if over else "orange")

# ---------------------------------------------------------------- 3. attention strip
items = []
if review_count:
    items.append(f"{review_count} invoice(s) to review")
for _, row in at_risk.iterrows():
    items.append(f"{row['category']} at {row['used']:.0%} of budget")
unusual = dashboard.find_anomalies(df)
if not unusual.empty:
    items.append(f"{len(unusual)} unusually large invoice(s)")

with st.container(border=True):
    badge_col, text_col, link_col = st.columns([1.4, 7, 1], vertical_alignment="center")
    if items:
        badge_col.badge("Needs attention", icon=":material/priority_high:", color="orange")
        text_col.markdown(" · ".join(items))
        link_col.page_link("ui/records.py", label="Review", icon=":material/arrow_forward:")
    else:
        badge_col.badge("All caught up", icon=":material/check_circle:", color="green")
        text_col.markdown("Nothing needs your attention right now.")

# ---------------------------------------------------------------- 4. detail row
DETAIL_HEIGHT = 440
left, right = st.columns(2)
with left.container(border=True, height=DETAIL_HEIGHT):
    st.subheader("Spend by category", anchor=False)
    figure = dashboard.category_figure(df)
    figure.update_layout(title=None, height=340, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(figure, width="stretch")
with right.container(border=True, height=DETAIL_HEIGHT):
    st.subheader("Recent invoices", anchor=False)
    recent = df.sort_values("scanned_at", ascending=False).head(7).copy()
    recent["status"] = recent["needs_review"].map({True: "🟠 Review", False: "🟢 OK"})
    recent["amount"] = recent["total_amount"].map(
        lambda v: "-" if pd.isna(v) else components.money(v))
    st.dataframe(
        recent[["invoice_date", "vendor", "amount", "status"]],
        hide_index=True, width="stretch",
        column_config={
            "invoice_date": st.column_config.TextColumn("Date", width="small"),
            "vendor": "Vendor",
            "amount": st.column_config.TextColumn("Amount", alignment="right"),
            "status": st.column_config.TextColumn("Status", width="small"),
        })
    st.page_link("ui/records.py", label="All records", icon=":material/arrow_forward:")
