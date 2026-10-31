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
