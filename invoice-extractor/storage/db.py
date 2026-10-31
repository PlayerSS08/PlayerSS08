"""
SQLite storage for extracted invoices.

Design rules (from the spec):
* Never connect at import time: every function opens its own connection
  through the `connect()` context manager.
* De-duplicate on the SHA-256 hash of the file (not on invoice number),
  using the same `INSERT OR IGNORE` idea as the original Scanner.py.
* A second, softer duplicate check warns (does not block) when another row
  has the same vendor + invoice number.

Every public function accepts an optional `db_path` so tests can use a
temporary database instead of the real one.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

import config
from extractor.models import InvoiceData

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash       TEXT NOT NULL UNIQUE,      -- prevents re-importing the same file
    source_file     TEXT NOT NULL,
    invoice_number  TEXT,
    invoice_date    TEXT,                      -- ISO date printed on invoice
    invoice_time    TEXT,
    vendor          TEXT,
    gstin           TEXT,
    subtotal        REAL,
    cgst            REAL,
    sgst            REAL,
    igst            REAL,
    total_amount    REAL,
    currency        TEXT DEFAULT 'INR',
    extraction_method TEXT,
    confidence_json TEXT,                      -- JSON string of per-field scores
    needs_review    INTEGER DEFAULT 0,
    warnings        TEXT,
    raw_text        TEXT,
    scanned_at      TEXT NOT NULL              -- when the file was processed
);
CREATE INDEX IF NOT EXISTS idx_vendor ON invoices(vendor);
CREATE INDEX IF NOT EXISTS idx_date   ON invoices(invoice_date);
"""

# Columns a user is allowed to change from the UI.
EDITABLE_COLUMNS = {
    "invoice_number", "invoice_date", "invoice_time", "vendor", "gstin",
    "subtotal", "cgst", "sgst", "igst", "total_amount", "currency",
    "needs_review", "warnings",
}

# Separator used to store the list of warnings as one text column.
WARNING_SEPARATOR = "; "


# ------------------------------------------------------------------
# Connection helpers
# ------------------------------------------------------------------
def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a new SQLite connection (creating the data folder if needed)."""
    path = Path(db_path) if db_path else config.DATABASE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connect(db_path: Optional[Path] = None):
    """Context manager: open, commit on success, always close."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Create the invoices table and indexes if they do not exist."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


# ------------------------------------------------------------------
# Duplicate checks
# ------------------------------------------------------------------
def hash_exists(file_hash: str, db_path: Optional[Path] = None) -> bool:
    """Return True if a file with this hash has already been saved."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM invoices WHERE file_hash = ?", (file_hash,)
        ).fetchone()
    return row is not None


def find_same_vendor_and_number(vendor: Optional[str],
                                invoice_number: Optional[str],
                                exclude_id: Optional[int] = None,
                                db_path: Optional[Path] = None) -> list:
    """Return ids of rows sharing this vendor + invoice number (case-insensitive)."""
    if not vendor or not invoice_number:
        return []
    query = ("SELECT id FROM invoices WHERE LOWER(vendor) = LOWER(?) "
             "AND LOWER(invoice_number) = LOWER(?)")
    params = [vendor, invoice_number]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    with connect(db_path) as conn:
        return [row["id"] for row in conn.execute(query, params)]


# ------------------------------------------------------------------
# Create / update / delete
# ------------------------------------------------------------------
def _now() -> str:
    """Local, human-readable timestamp (kept from the original Scanner.py)."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def insert_invoice(invoice: InvoiceData, db_path: Optional[Path] = None) -> bool:
    """
    Save an invoice. Returns False if the same file (hash) already exists.

    If another row has the same vendor + invoice number, the invoice is
    still saved but gets a warning and is flagged needs_review.
    """
    clashes = find_same_vendor_and_number(
        invoice.vendor, invoice.invoice_number, db_path=db_path)
    if clashes:
        invoice.add_warning(
            f"Possible duplicate of record #{clashes[0]} (same vendor and invoice number)")
        invoice.needs_review = True

    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO invoices (
                file_hash, source_file, invoice_number, invoice_date,
                invoice_time, vendor, gstin, subtotal, cgst, sgst, igst,
                total_amount, currency, extraction_method, confidence_json,
                needs_review, warnings, raw_text, scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice.file_hash, invoice.source_file, invoice.invoice_number,
                invoice.invoice_date, invoice.invoice_time, invoice.vendor,
                invoice.gstin, invoice.subtotal, invoice.cgst, invoice.sgst,
                invoice.igst, invoice.total_amount, invoice.currency,
                invoice.extraction_method, json.dumps(invoice.confidence),
                int(invoice.needs_review),
                WARNING_SEPARATOR.join(invoice.warnings), invoice.raw_text,
                _now(),
            ),
        )
        return cursor.rowcount == 1


def update_invoice(invoice_id: int, fields: dict,
                   db_path: Optional[Path] = None) -> bool:
    """
    Update editable columns of one row. Unknown columns are ignored.
    Returns True if a row was changed.
    """
    changes = {k: v for k, v in fields.items() if k in EDITABLE_COLUMNS}
    if not changes:
        return False
    if "needs_review" in changes:
        changes["needs_review"] = int(bool(changes["needs_review"]))
    if isinstance(changes.get("warnings"), list):
        changes["warnings"] = WARNING_SEPARATOR.join(changes["warnings"])

    # Column names come only from the whitelist above, so this is safe.
    assignments = ", ".join(f"{column} = ?" for column in changes)
    with connect(db_path) as conn:
        cursor = conn.execute(
            f"UPDATE invoices SET {assignments} WHERE id = ?",
            [*changes.values(), invoice_id],
        )
        return cursor.rowcount == 1


def delete_invoice(invoice_id: int, db_path: Optional[Path] = None) -> bool:
    """Delete one row. Returns True if it existed."""
    with connect(db_path) as conn:
        cursor = conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        return cursor.rowcount == 1


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------
def get_all_invoices(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Return every saved invoice as a DataFrame (newest first)."""
    with connect(db_path) as conn:
        df = pd.read_sql_query("SELECT * FROM invoices ORDER BY id DESC", conn)
    df["needs_review"] = df["needs_review"].astype(bool)
    return df


def find_possible_duplicates(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Rows that share vendor + invoice_number + total with another row."""
    query = """
        SELECT a.id, a.source_file, a.vendor, a.invoice_number,
               a.invoice_date, a.total_amount
        FROM invoices a
        JOIN invoices b
          ON a.id != b.id
         AND LOWER(a.vendor) = LOWER(b.vendor)
         AND LOWER(a.invoice_number) = LOWER(b.invoice_number)
         AND ABS(a.total_amount - b.total_amount) < 0.01
        GROUP BY a.id
        ORDER BY a.vendor, a.invoice_number, a.id
    """
    with connect(db_path) as conn:
        return pd.read_sql_query(query, conn)
