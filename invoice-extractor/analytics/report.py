"""
Monthly spending summary as a PDF (built with pymupdf, already a dependency).

`monthly_report_pdf(df, month, budgets)` returns the PDF as bytes so the
Streamlit page can offer it with st.download_button.
"""

from datetime import datetime

import pandas as pd
import pymupdf

from analytics import dashboard

PAGE_W, PAGE_H = 595, 842          # A4 in points
MARGIN = 45
BLUE = (0.165, 0.471, 0.839)       # same blue as the charts
GREY = (0.45, 0.45, 0.45)
LIGHT = (0.93, 0.94, 0.96)
RED = (0.80, 0.20, 0.20)


def _money(value) -> str:
    """Rs. 1,234.50 (the base PDF fonts have no ₹ glyph)."""
    return "-" if value is None or pd.isna(value) else f"Rs. {value:,.2f}"


class _Writer:
    """Tiny helper that writes lines top-to-bottom and adds pages when full."""

    def __init__(self, title: str):
        self.doc = pymupdf.open()
        self.title = title
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN
        self.page.insert_text((MARGIN, PAGE_H - 25), self.title, fontsize=8, color=GREY)

    def need(self, height: float):
        if self.y + height > PAGE_H - 50:
            self._new_page()

    def text(self, value: str, size=10, bold=False, color=(0, 0, 0), x=MARGIN, gap=1.5):
        self.need(size * gap)
        self.page.insert_text((x, self.y + size), value, fontsize=size,
                              fontname="hebo" if bold else "helv", color=color)
        self.y += size * gap

    def heading(self, value: str):
        self.y += 8
        self.text(value, size=13, bold=True, color=BLUE)
        self.page.draw_line((MARGIN, self.y), (PAGE_W - MARGIN, self.y), color=LIGHT, width=1)
        self.y += 6

    def table(self, headers: list, rows: list, widths: list):
        """Simple table; the last column is right-aligned (amounts)."""
        self.need(18)
        self.page.draw_rect(pymupdf.Rect(MARGIN, self.y, PAGE_W - MARGIN, self.y + 16), color=None, fill=LIGHT)
        self._row(headers, widths, bold=True)
        for row in rows:
            self._row(row, widths)

    def _row(self, cells, widths, bold=False):
        self.need(16)
        x = MARGIN + 4
        for i, (cell, width) in enumerate(zip(cells, widths)):
            value = str(cell)[: int(width / 5)]
            font = "hebo" if bold else "helv"
            if i == len(cells) - 1:          # right-align the last column
                length = pymupdf.get_text_length(value, fontname=font, fontsize=9)
                self.page.insert_text((x + width - length - 8, self.y + 11.5), value, fontsize=9, fontname=font)
            else:
                self.page.insert_text((x, self.y + 11.5), value, fontsize=9, fontname=font)
            x += width
        self.y += 16

    def bar(self, label: str, value: float, maximum: float, note: str, color=BLUE):
        """Labelled horizontal bar (used for categories and budgets)."""
        self.need(20)
        self.page.insert_text((MARGIN, self.y + 11), label[:28], fontsize=9)
        left, width = MARGIN + 150, 230
        self.page.draw_rect(pymupdf.Rect(left, self.y + 3, left + width, self.y + 13), color=None, fill=LIGHT)
        share = 0 if not maximum else min(value / maximum, 1.0)
        if share > 0:
            self.page.draw_rect(pymupdf.Rect(left, self.y + 3, left + width * share, self.y + 13),
                                color=None, fill=color)
        self.page.insert_text((left + width + 10, self.y + 11), note, fontsize=9)
        self.y += 18


def monthly_report_pdf(df: pd.DataFrame, month: str, budgets: dict = None) -> bytes:
    """PDF summary of one month ('YYYY-MM'): totals, categories, budgets, vendors, invoices."""
    period = pd.Period(month, freq="M")
    data = df[pd.to_datetime(df["invoice_date"], errors="coerce").dt.to_period("M") == period]
    writer = _Writer(f"Invoice Extractor - monthly summary {period.strftime('%B %Y')}")

    writer.text("Monthly Spending Summary", size=22, bold=True)
    writer.text(period.strftime("%B %Y"), size=13, color=BLUE)
    writer.text(f"Generated {datetime.now():%d %b %Y %H:%M}", size=8, color=GREY)

    metrics = dashboard.summary_metrics(data)
    writer.heading("Overview")
    writer.text(f"Invoices: {metrics['total_invoices']}      Total spend: {_money(metrics['total_spend'])}"
                f"      Average invoice: {_money(metrics['average_invoice'])}"
                f"      Need review: {metrics['needs_review']}")
    if data.empty:
        writer.text("No invoices are dated in this month.", color=GREY)
        return writer.doc.tobytes()

    writer.heading("Spend by category")
    categories = dashboard.spend_by_category(data)
    top = categories["total_amount"].max()
    for _, row in categories.iterrows():
        writer.bar(row["category"], row["total_amount"], top,
                   f"{_money(row['total_amount'])} ({row['invoices']})")

    status = dashboard.budget_status(data, budgets or {}, month)
    if not status.empty:
        writer.heading("Budgets")
        for _, row in status.iterrows():
            colour = RED if row["status"] == "over" else BLUE
            writer.bar(row["category"], row["spent"], row["limit"],
                       f"{row['used']:.0%} of {_money(row['limit'])}", color=colour)

    writer.heading("Top vendors")
    vendors = dashboard.spend_by_vendor(data)
    writer.table(["Vendor", "Amount"], [[r["vendor"], _money(r["total_amount"])] for _, r in vendors.iterrows()],
                 [380, 125])

    writer.heading("All invoices")
    rows = [[r["invoice_date"], r.get("vendor") or "-", r.get("category") or "-",
             r.get("invoice_number") or "-", _money(r["total_amount"])]
            for _, r in data.sort_values("invoice_date").iterrows()]
    writer.table(["Date", "Vendor", "Category", "Invoice no.", "Amount"], rows, [70, 150, 110, 95, 80])
    return writer.doc.tobytes()
