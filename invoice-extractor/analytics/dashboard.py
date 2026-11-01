"""
Spending analytics for the Dashboard page.

The `spend_*` / `summary_*` functions are pure pandas (DataFrame in,
DataFrame or dict out) so they can be tested; the `*_figure` functions
turn those results into Plotly charts.
"""

import pandas as pd
import plotly.graph_objects as go

# Colours: one hue for single-series bars, three distinct hues for GST parts
# (a validated colour-blind-safe set).
BAR_COLOUR = "#2a78d6"
GST_COLOURS = {"CGST": "#2a78d6", "SGST": "#eb6834", "IGST": "#1baf7a"}


# ----------------------------------------------------------------------
# Numbers
# ----------------------------------------------------------------------
def summary_metrics(df: pd.DataFrame) -> dict:
    """Totals for the metric cards."""
    totals = df["total_amount"].dropna() if "total_amount" in df else pd.Series(dtype=float)
    return {
        "total_invoices": int(len(df)),
        "total_spend": float(totals.sum()),
        "average_invoice": float(totals.mean()) if not totals.empty else 0.0,
        "needs_review": int(df["needs_review"].sum()) if "needs_review" in df else 0,
    }


def spend_by_vendor(df: pd.DataFrame, top: int = 10) -> pd.DataFrame:
    """Total spend per vendor, biggest first, top N (unknown vendors grouped)."""
    data = df.assign(vendor=df["vendor"].fillna("Unknown"))
    result = (data.groupby("vendor", as_index=False)["total_amount"].sum()
              .sort_values("total_amount", ascending=False).head(top))
    return result.reset_index(drop=True)


def spend_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Total spend per calendar month (YYYY-MM), in date order. Undated rows are skipped."""
    dates = pd.to_datetime(df["invoice_date"], errors="coerce")
    data = df.assign(month=dates.dt.strftime("%Y-%m")).dropna(subset=["month"])
    result = data.groupby("month", as_index=False)["total_amount"].sum().sort_values("month")
    return result.reset_index(drop=True)


def gst_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Total CGST, SGST and IGST (only the non-zero ones)."""
    rows = [{"tax": name, "amount": float(df[name.lower()].fillna(0).sum())}
            for name in ("CGST", "SGST", "IGST") if name.lower() in df]
    result = pd.DataFrame(rows, columns=["tax", "amount"])
    return result[result["amount"] > 0].reset_index(drop=True)


# ----------------------------------------------------------------------
# Charts
# ----------------------------------------------------------------------
def _style(fig: go.Figure, title: str) -> go.Figure:
    """Shared, quiet chart styling: light grid, no chart junk."""
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50, b=10), bargap=0.35,
                      showlegend=False, hoverlabel=dict(namelength=0))
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


def vendor_figure(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of spend by vendor (top 10)."""
    data = spend_by_vendor(df).iloc[::-1]          # biggest at the top
    fig = go.Figure(go.Bar(
        x=data["total_amount"], y=data["vendor"], orientation="h",
        marker=dict(color=BAR_COLOUR, cornerradius=4),
        hovertemplate="%{y}<br>₹ %{x:,.2f}<extra></extra>"))
    fig = _style(fig, "Spend by vendor (top 10)")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)", tickprefix="₹ ")
    fig.update_yaxes(showgrid=False)
    return fig


def month_figure(df: pd.DataFrame) -> go.Figure:
    """Bar chart of spend per month."""
    data = spend_by_month(df)
    fig = go.Figure(go.Bar(
        x=data["month"], y=data["total_amount"],
        marker=dict(color=BAR_COLOUR, cornerradius=4),
        hovertemplate="%{x}<br>₹ %{y:,.2f}<extra></extra>"))
    fig = _style(fig, "Spend by month")
    fig.update_xaxes(type="category")
    fig.update_yaxes(tickprefix="₹ ")
    return fig


def gst_figure(df: pd.DataFrame) -> go.Figure:
    """Donut chart of CGST / SGST / IGST totals, labelled directly."""
    data = gst_breakdown(df)
    fig = go.Figure(go.Pie(
        labels=data["tax"], values=data["amount"], hole=0.55, sort=False,
        marker=dict(colors=[GST_COLOURS[t] for t in data["tax"]],
                    line=dict(color="white", width=2)),
        textinfo="label+percent",
        hovertemplate="%{label}<br>₹ %{value:,.2f}<extra></extra>"))
    fig = _style(fig, "GST breakdown")
    fig.update_layout(showlegend=True)
    return fig


# ======================================================================
# Advanced analytics
# ======================================================================
PERIODS = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "All": None}
BUDGET_WARNING = 0.8          # 80 % of a budget used -> warning


def _dates(df: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(df["invoice_date"], errors="coerce")


def filter_period(df: pd.DataFrame, period: str = "All", today=None) -> pd.DataFrame:
    """
    Keep invoices dated within the last N months (by calendar month, so
    "1M" = the current month). "All" keeps everything, including undated rows.
    """
    months = PERIODS.get(period)
    if months is None:
        return df
    today = pd.Timestamp(today or pd.Timestamp.today()).normalize()
    start = (today.to_period("M") - (months - 1)).to_timestamp()
    dates = _dates(df)
    return df[(dates >= start) & (dates <= today + pd.Timedelta(days=1))]


def spend_by_category(df: pd.DataFrame) -> pd.DataFrame:
    """Total spend and invoice count per category, biggest first."""
    data = df.assign(category=df["category"].fillna("Other") if "category" in df else "Other")
    result = (data.groupby("category", as_index=False)
              .agg(total_amount=("total_amount", "sum"), invoices=("total_amount", "size"))
              .sort_values("total_amount", ascending=False))
    return result.reset_index(drop=True)


def spend_by_payment_method(df: pd.DataFrame) -> pd.DataFrame:
    """Total spend per payment method (unknown ones grouped as 'Not stated')."""
    data = df.assign(payment_method=df["payment_method"].fillna("Not stated"))
    result = (data.groupby("payment_method", as_index=False)["total_amount"].sum()
              .sort_values("total_amount", ascending=False))
    return result.reset_index(drop=True)


def month_over_month(df: pd.DataFrame, today=None) -> dict:
    """Spend this calendar month vs last month, with the % change (None if no base)."""
    today = pd.Timestamp(today or pd.Timestamp.today())
    months = _dates(df).dt.to_period("M")
    this_month = today.to_period("M")
    current = float(df.loc[months == this_month, "total_amount"].sum())
    previous = float(df.loc[months == this_month - 1, "total_amount"].sum())
    change = None if previous == 0 else round(100 * (current - previous) / previous, 1)
    return {"this_month": current, "last_month": previous, "change_pct": change}


def budget_status(df: pd.DataFrame, budgets: dict, month=None) -> pd.DataFrame:
    """
    For each budgeted category: limit, amount spent in `month` (default: the
    current month), share used and a status of "ok", "warning" or "over".
    """
    columns = ["category", "limit", "spent", "used", "status"]
    if not budgets:
        return pd.DataFrame(columns=columns)
    month = pd.Period(month or pd.Timestamp.today(), freq="M")
    in_month = df[_dates(df).dt.to_period("M") == month]
    spent = in_month.groupby(in_month["category"].fillna("Other"))["total_amount"].sum()
    rows = []
    for category, limit in budgets.items():
        used_amount = float(spent.get(category, 0.0))
        share = used_amount / limit if limit else 0.0
        status = "over" if share > 1 else "warning" if share >= BUDGET_WARNING else "ok"
        rows.append({"category": category, "limit": float(limit), "spent": used_amount,
                     "used": round(share, 3), "status": status})
    return pd.DataFrame(rows, columns=columns).sort_values("used", ascending=False).reset_index(drop=True)


def find_anomalies(df: pd.DataFrame, factor: float = 2.0, min_history: int = 3) -> pd.DataFrame:
    """
    Invoices whose total is unusually high:
    * more than `factor` x the median of the same vendor (needs `min_history`
      invoices from that vendor), or
    * more than 4 x the median of all invoices (needs 5+ invoices).
    """
    data = df.dropna(subset=["total_amount"]).copy()
    if data.empty:
        return data.assign(reason=pd.Series(dtype=str))
    reasons = []
    overall_median = data["total_amount"].median()
    vendor_stats = data.groupby("vendor")["total_amount"].agg(["median", "count"])
    for _, row in data.iterrows():
        reason = ""
        stats = vendor_stats.loc[row["vendor"]] if row["vendor"] in vendor_stats.index else None
        if stats is not None and stats["count"] >= min_history and row["total_amount"] > factor * stats["median"]:
            reason = f"{row['total_amount'] / stats['median']:.1f}x usual for this vendor"
        elif len(data) >= 5 and row["total_amount"] > 4 * overall_median:
            reason = f"{row['total_amount'] / overall_median:.1f}x your typical invoice"
        reasons.append(reason)
    data["reason"] = reasons
    keep = ["id", "invoice_date", "vendor", "total_amount", "reason"]
    return data[data["reason"] != ""][[c for c in keep if c in data.columns]].reset_index(drop=True)


def recurring_vendors(df: pd.DataFrame, min_months: int = 2) -> pd.DataFrame:
    """Vendors billed in at least `min_months` different months (subscriptions, bills)."""
    data = df.dropna(subset=["vendor"]).assign(month=_dates(df).dt.to_period("M")).dropna(subset=["month"])
    result = (data.groupby("vendor")
              .agg(months=("month", "nunique"), average=("total_amount", "mean"),
                   last_date=("invoice_date", "max"))
              .reset_index())
    result = result[result["months"] >= min_months].sort_values("months", ascending=False)
    return result.reset_index(drop=True)


def insights(df: pd.DataFrame, budgets: dict = None, today=None) -> list:
    """Short plain-English observations for the Home page (most useful first)."""
    if df.empty:
        return []
    notes = []
    mom = month_over_month(df, today)
    if mom["change_pct"] is not None:
        direction = "more" if mom["change_pct"] > 0 else "less"
        notes.append(f"You spent {abs(mom['change_pct']):.0f}% {direction} this month "
                     f"(₹ {mom['this_month']:,.0f}) than last month (₹ {mom['last_month']:,.0f}).")
    categories = spend_by_category(df)
    if not categories.empty and categories["total_amount"].sum() > 0:
        top = categories.iloc[0]
        share = 100 * top["total_amount"] / categories["total_amount"].sum()
        notes.append(f"{top['category']} is your biggest category: {share:.0f}% of all spending.")
    vendors = spend_by_vendor(df, top=1)
    if not vendors.empty:
        notes.append(f"Top vendor: {vendors.iloc[0]['vendor']} (₹ {vendors.iloc[0]['total_amount']:,.0f}).")
    status = budget_status(df, budgets or {}, today)
    for _, row in status[status["status"] != "ok"].iterrows():
        word = "over" if row["status"] == "over" else "close to"
        notes.append(f"⚠️ {row['category']} is {word} its budget: ₹ {row['spent']:,.0f} of ₹ {row['limit']:,.0f}.")
    anomalies = find_anomalies(df)
    if not anomalies.empty:
        notes.append(f"{len(anomalies)} invoice(s) look unusually large - see the Dashboard.")
    review = int(df["needs_review"].sum())
    if review:
        notes.append(f"{review} invoice(s) still need your review.")
    return notes


# ----------------------------------------------------------------------
# More charts
# ----------------------------------------------------------------------
def category_figure(df: pd.DataFrame) -> go.Figure:
    """Horizontal bars: spend per category (click a bar to filter)."""
    data = spend_by_category(df).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=data["total_amount"], y=data["category"], orientation="h",
        customdata=data["invoices"],
        marker=dict(color=BAR_COLOUR, cornerradius=4),
        hovertemplate="%{y}<br>₹ %{x:,.2f} · %{customdata} invoice(s)<extra></extra>"))
    fig = _style(fig, "Spend by category")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.2)", tickprefix="₹ ")
    fig.update_yaxes(showgrid=False)
    return fig


def trend_figure(df: pd.DataFrame) -> go.Figure:
    """Cumulative spend over time, one point per invoice date."""
    dates = _dates(df)
    data = (df.assign(day=dates).dropna(subset=["day"]).groupby("day")["total_amount"].sum()
            .sort_index().cumsum().reset_index())
    fig = go.Figure(go.Scatter(
        x=data["day"], y=data["total_amount"], mode="lines+markers",
        line=dict(color=BAR_COLOUR, width=2), marker=dict(size=8),
        hovertemplate="%{x|%d %b %Y}<br>₹ %{y:,.2f} so far<extra></extra>"))
    fig = _style(fig, "Cumulative spend")
    fig.update_yaxes(tickprefix="₹ ")
    fig.update_layout(hovermode="x unified")
    return fig


def payment_figure(df: pd.DataFrame) -> go.Figure:
    """Bars: spend per payment method."""
    data = spend_by_payment_method(df)
    fig = go.Figure(go.Bar(
        x=data["payment_method"], y=data["total_amount"],
        marker=dict(color=BAR_COLOUR, cornerradius=4),
        hovertemplate="%{x}<br>₹ %{y:,.2f}<extra></extra>"))
    fig = _style(fig, "Spend by payment method")
    fig.update_yaxes(tickprefix="₹ ")
    return fig
