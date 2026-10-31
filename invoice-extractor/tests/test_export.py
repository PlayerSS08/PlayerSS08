"""Tests for storage/export.py."""

import io

import pandas as pd

from storage import export

DF = pd.DataFrame([{"id": 1, "vendor": "Amazon", "total_amount": 1499.0,
                    "invoice_date": "2026-10-13", "raw_text": "long text"}])


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "out.csv"
    data = export.to_csv(DF, path)
    back = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")
    assert back.loc[0, "vendor"] == "Amazon"
    assert "raw_text" not in back.columns
    assert path.read_bytes() == data


def test_excel_roundtrip():
    back = pd.read_excel(io.BytesIO(export.to_excel(DF)), sheet_name="Invoices")
    assert back.loc[0, "total_amount"] == 1499.0
    assert list(back.columns) == ["id", "invoice_date", "vendor", "total_amount"]


def test_raw_text_optional():
    back = pd.read_csv(io.BytesIO(export.to_csv(DF, include_raw_text=True)), encoding="utf-8-sig")
    assert "raw_text" in back.columns


def test_empty_dataframe_exports():
    empty = pd.DataFrame(columns=export.EXPORT_COLUMNS)
    assert export.to_csv(empty)
    assert export.to_excel(empty)
