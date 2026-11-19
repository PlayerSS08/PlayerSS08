"""Dashboard: interactive charts, unusual invoices, recurring vendors and the monthly PDF report."""

import pandas as pd
import streamlit as st

from analytics import dashboard
from analytics.report import monthly_report_pdf
from storage import db
from ui import components

st.title(":material/monitoring: Dashboard")
all_rows = db.get_all_invoices()
if all_rows.empty:
    st.info("No invoices saved yet - load the samples from the Home page to try it out.",
            icon=":material/inbox:")
    st.stop()

# ---------------------------------------------------------------- controls
controls = st.columns([2, 3])
period = controls[0].segmented_control("Period", list(dashboard.PERIODS), default="All",
                                       key="dash_period") or "All"
df = dashboard.filter_period(all_rows, period)
picked = st.session_state.get("dash_category")
with controls[1]:
    if picked:
        st.write("")
        if st.button(f"Showing only **{picked}** - clear filter", icon=":material/filter_alt_off:"):
            st.session_state.pop("dash_category")
            st.session_state.pop("cat_chart", None)      # forget the chart's selection too
            st.rerun()
    else:
        st.caption("Tip: click a bar in **Spend by category** to filter every chart.")
if picked:
    df = df[df["category"].fillna("Other") == picked]

if df.empty:
    st.warning("No invoices in this period.", icon=":material/event_busy:")
    st.stop()

# ---------------------------------------------------------------- metric cards
metrics = dashboard.summary_metrics(df)
mom = dashboard.month_over_month(all_rows)
cards = st.columns(5)
values = [
    ("Invoices", metrics["total_invoices"], None),
    ("Total spend", components.money_short(metrics["total_spend"]), None),
    ("Average invoice", components.money_short(metrics["average_invoice"]), None),
    (mom["month"], components.money_short(mom["this_month"]),
     None if mom["change_pct"] is None else f"{mom['change_pct']:+.0f}% vs {mom['previous']}"),
    ("Need review", metrics["needs_review"], None),
]
for card, (label, value, delta) in zip(cards, values):
    with card.container(border=True):
        st.metric(label, value, delta=delta, delta_color="inverse")

# ---------------------------------------------------------------- charts
left, right = st.columns(2)
with left:
    event = st.plotly_chart(dashboard.category_figure(df), width="stretch",
                            on_select="rerun", selection_mode="points", key="cat_chart")
    points = event.selection.points if event and event.selection else []
    if points and not picked:
        st.session_state["dash_category"] = points[0]["y"]
        st.rerun()
with right:
    st.plotly_chart(dashboard.month_figure(df), width="stretch")

left, right = st.columns(2)
left.plotly_chart(dashboard.vendor_figure(df), width="stretch")
right.plotly_chart(dashboard.trend_figure(df), width="stretch")

left, right = st.columns(2)
left.plotly_chart(dashboard.payment_figure(df), width="stretch")
with right:
    if dashboard.gst_breakdown(df).empty:
        st.info("No GST amounts in these invoices.", icon=":material/receipt_long:")
    else:
        st.plotly_chart(dashboard.gst_figure(df), width="stretch")

# ---------------------------------------------------------------- findings
st.subheader(":material/search_insights: Findings", anchor=False)
tab_unusual, tab_recurring, tab_dupes, tab_data = st.tabs(
    ["Unusual amounts", "Recurring vendors", "Possible duplicates", "Data behind the charts"])
with tab_unusual:
    anomalies = dashboard.find_anomalies(all_rows)
    if anomalies.empty:
        st.success("Nothing unusual - every invoice is in its normal range.", icon=":material/check_circle:")
    else:
        st.dataframe(anomalies, hide_index=True, width="stretch", column_config={
            "total_amount": st.column_config.NumberColumn("Total", format="₹ %.2f"),
            "reason": "Why it stands out"})
with tab_recurring:
    recurring = dashboard.recurring_vendors(all_rows)
    if recurring.empty:
        st.info("No vendor appears in more than one month yet.", icon=":material/info:")
    else:
        st.dataframe(recurring, hide_index=True, width="stretch", column_config={
            "months": "Months billed",
            "average": st.column_config.NumberColumn("Average bill", format="₹ %.2f"),
            "last_date": "Last invoice"})
with tab_dupes:
    duplicates = db.find_possible_duplicates()
    if duplicates.empty:
        st.success("No duplicates found.", icon=":material/check_circle:")
    else:
        st.caption("Same vendor, invoice number and total.")
        st.dataframe(duplicates, hide_index=True, width="stretch")
with tab_data:
    a, b, c = st.columns(3)
    a.dataframe(dashboard.spend_by_category(df), hide_index=True)
    b.dataframe(dashboard.spend_by_month(df), hide_index=True)
    c.dataframe(dashboard.spend_by_vendor(df), hide_index=True)

# ---------------------------------------------------------------- monthly report
st.subheader(":material/picture_as_pdf: Monthly report", anchor=False)
months = sorted(pd.to_datetime(all_rows["invoice_date"], errors="coerce").dropna()
                .dt.strftime("%Y-%m").unique(), reverse=True)
if months:
    pick, button = st.columns([2, 3])
    month = pick.selectbox("Month", months, format_func=lambda m: pd.Period(m).strftime("%B %Y"),
                           label_visibility="collapsed")
    button.download_button("Download PDF summary", monthly_report_pdf(all_rows, month, db.get_budgets()),
                           f"invoice-summary-{month}.pdf", "application/pdf", type="primary",
                           icon=":material/download:")
