"""
Export invoice records to CSV and Excel.

Both functions return bytes so Streamlit's st.download_button can serve
them directly; pass `path` to also write the file to disk.
"""

import io
from pathlib import Path
from typing import Optional

import pandas as pd

# Columns exported by default, in a readable order (raw OCR text is left
# out because it makes spreadsheets huge).
EXPORT_COLUMNS = [
    "id", "invoice_date", "invoice_time", "vendor", "invoice_number",
    "total_amount", "currency", "subtotal", "cgst", "sgst", "igst", "gstin",
    "needs_review", "warnings", "extraction_method", "source_file", "scanned_at",
]


def prepare_for_export(df: pd.DataFrame, include_raw_text: bool = False) -> pd.DataFrame:
    """Keep the useful columns (those that exist) in a fixed order."""
    columns = [c for c in EXPORT_COLUMNS if c in df.columns]
    if include_raw_text and "raw_text" in df.columns:
        columns.append("raw_text")
    return df[columns].copy()


def to_csv(df: pd.DataFrame, path: Optional[Path] = None,
           include_raw_text: bool = False) -> bytes:
    """CSV bytes (UTF-8 with BOM so Excel shows ₹ correctly)."""
    data = prepare_for_export(df, include_raw_text).to_csv(index=False).encode("utf-8-sig")
    if path:
        Path(path).write_bytes(data)
    return data


def to_excel(df: pd.DataFrame, path: Optional[Path] = None,
             include_raw_text: bool = False) -> bytes:
    """Excel (.xlsx) bytes with one sheet called 'Invoices'."""
    buffer = io.BytesIO()
    table = prepare_for_export(df, include_raw_text)
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        table.to_excel(writer, index=False, sheet_name="Invoices")
        sheet = writer.sheets["Invoices"]
        for i, column in enumerate(table.columns, start=1):   # readable column widths
            width = max([len(str(column))] + [len(str(v)) for v in table[column].head(200)])
            sheet.column_dimensions[sheet.cell(row=1, column=i).column_letter].width = min(width + 2, 50)
    data = buffer.getvalue()
    if path:
        Path(path).write_bytes(data)
    return data
