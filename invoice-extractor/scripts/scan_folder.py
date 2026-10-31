import re
import sqlite3
from pathlib import Path
from datetime import datetime

import pymupdf

# ==============================
# CONFIGURATION
# ==============================

INVOICE_FOLDER = Path("invoices")
DATABASE_FILE = "Manager"

# Create invoices folder if it doesn't exist
INVOICE_FOLDER.mkdir(exist_ok=True)

# ==============================
# DATABASE SETUP
# ==============================

conn = sqlite3.connect(DATABASE_FILE)

conn.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        serial_no INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT NOT NULL UNIQUE,
        source_file TEXT NOT NULL,
        date_added TEXT NOT NULL
    )
""")
conn.commit()


# ==============================
# EXTRACT INVOICE NUMBERS
# ==============================

def extract_invoice_numbers(pdf_path):
    """Extract all invoice numbers from a text-based PDF."""

    try:
        with pymupdf.open(pdf_path) as document:
            text = "\n".join(
                page.get_text() for page in document
            )

        pattern = (
            r"\bInvoice\s*(?:Number|No\.?)\s*#?\s*"
            r"[:\-]?\s*([A-Z0-9][A-Z0-9/-]{4,})"
        )

        return list(dict.fromkeys(
            match.group(1).strip()
            for match in re.finditer(
                pattern, text, re.IGNORECASE
            )
        ))

    except Exception as error:
        print(f"ERROR reading {pdf_path.name}: {error}")
        return []


# ==============================
# SCAN AND SAVE INVOICES
# ==============================

def scan_invoices():
    """Scan PDFs and append new invoice records."""

    pdf_files = sorted(INVOICE_FOLDER.glob("*.pdf"))

    total_found = 0
    total_added = 0

    if not pdf_files:
        print("No PDF invoices found in the invoices folder.")

    for pdf_path in pdf_files:
        invoice_numbers = extract_invoice_numbers(pdf_path)

        if not invoice_numbers:
            print(f"REVIEW: No invoice number found in {pdf_path.name}")
            continue

        for invoice_number in invoice_numbers:
            total_found += 1

            # Generate local timezone-aware timestamp
            date_added = datetime.now().astimezone().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO invoices
                    (invoice_number, source_file, date_added)
                VALUES (?, ?, ?)
                """,
                (invoice_number, pdf_path.name, date_added),
            )

            if cursor.rowcount == 1:
                total_added += 1
                print(f"ADDED: {invoice_number} | {date_added}")
            else:
                print(f"EXISTS: {invoice_number}")

    conn.commit()

    print("\n========== SCAN SUMMARY ==========")
    print(f"PDF files scanned: {len(pdf_files)}")
    print(f"Invoice numbers found: {total_found}")
    print(f"New records added: {total_added}")
    print(f"Database file: {DATABASE_FILE}")


# ==============================
# DISPLAY DATABASE TABLE
# ==============================

def show_database():
    """Display all saved invoice records."""

    rows = conn.execute("""
        SELECT serial_no, invoice_number, source_file, date_added
        FROM invoices
        ORDER BY serial_no
    """).fetchall()

    print("\n================ MANAGER DATABASE ================")
    print(
        f"{'S.No.':<8}"
        f"{'Invoice Number':<26}"
        f"{'Source File':<32}"
        f"{'Date Added':<20}"
    )
    print("-" * 86)

    for serial_no, invoice_number, source_file, date_added in rows:
        print(
            f"{serial_no:<8}"
            f"{invoice_number:<26}"
            f"{source_file:<32}"
            f"{date_added:<20}"
        )

    print("-" * 86)
    print(f"Total unique invoices: {len(rows)}")


# ==============================
# MAIN PROGRAM
# ==============================

if __name__ == "__main__":
    try:
        scan_invoices()
        show_database()
    finally:
        conn.close()
