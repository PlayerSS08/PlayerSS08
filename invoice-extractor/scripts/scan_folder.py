"""
Batch scanner: process every invoice in the invoices/ folder.

This is the descendant of the original Scanner.py. Its ideas are kept:
* the invoice-number regex now lives (extended) in extractor/fields.py
* INSERT OR IGNORE de-duplication now lives in storage/db.py, keyed on
  the file hash instead of the invoice number
* the "REVIEW" message is still printed - but the file is now saved and
  flagged needs_review instead of being skipped
* the summary and the database table are printed at the end, as before

Usage (from the project folder):
    python scripts/scan_folder.py            # scan ./invoices
    python scripts/scan_folder.py some/dir   # scan another folder
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

import config  # noqa: E402
from extractor.parser import process_file  # noqa: E402
from extractor.text_extraction import hash_file  # noqa: E402
from storage import db  # noqa: E402


def list_invoice_files(folder: Path) -> list:
    """All supported files (PDF and images) in the folder, sorted by name."""
    return sorted(p for p in folder.glob("*")
                  if p.is_file() and p.suffix.lower() in config.SUPPORTED_EXTENSIONS)


def scan_folder(folder=None, db_path=None) -> list:
    """
    Process every file in `folder` and save new ones to the database.
    Returns one dict per file: file, status (ADDED / EXISTS / REVIEW),
    vendor, invoice_number, invoice_date, total_amount, warnings.
    """
    folder = Path(folder or config.INVOICE_FOLDER)
    folder.mkdir(parents=True, exist_ok=True)
    db.init_db(db_path)

    results = []
    for path in list_invoice_files(folder):
        if db.hash_exists(hash_file(path), db_path):
            results.append({"file": path.name, "status": "EXISTS"})
            continue
        invoice = process_file(path)
        db.insert_invoice(invoice, db_path)
        results.append({
            "file": path.name,
            "status": "REVIEW" if invoice.needs_review else "ADDED",
            "vendor": invoice.vendor,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "total_amount": invoice.total_amount,
            "warnings": "; ".join(invoice.warnings),
        })
    return results


def print_summary(results: list) -> None:
    """Console output in the style of the original Scanner.py."""
    for r in results:
        if r["status"] == "EXISTS":
            print(f"EXISTS: {r['file']}")
        else:
            print(f"{r['status']}: {r['file']} | {r['vendor']} | {r['invoice_number']} | "
                  f"{r['invoice_date']} | {r['total_amount']}")
            if r["status"] == "REVIEW":
                print(f"        needs review: {r['warnings'] or 'low confidence fields'}")

    print("\n========== SCAN SUMMARY ==========")
    print(f"Files scanned: {len(results)}")
    print(f"New records added: {sum(r['status'] != 'EXISTS' for r in results)}")
    print(f"Flagged for review: {sum(r['status'] == 'REVIEW' for r in results)}")
    print(f"Database file: {config.DATABASE_FILE}")


def show_database(db_path=None) -> None:
    """Print all saved invoices as a table (like the old show_database)."""
    df = db.get_all_invoices(db_path)
    print("\n================ INVOICE DATABASE ================")
    print(f"{'ID':<5}{'Date':<12}{'Vendor':<28}{'Invoice No.':<22}{'Total':>12}  Review")
    print("-" * 88)
    for _, row in df.sort_values("id").iterrows():
        total = f"{row['total_amount']:,.2f}" if row["total_amount"] == row["total_amount"] else "-"
        print(f"{row['id']:<5}{str(row['invoice_date'] or '-'):<12}"
              f"{str(row['vendor'] or '-')[:26]:<28}{str(row['invoice_number'] or '-')[:20]:<22}"
              f"{total:>12}  {'yes' if row['needs_review'] else ''}")
    print("-" * 88)
    print(f"Total invoices: {len(df)}")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    folder = Path(argv[0]) if argv else config.INVOICE_FOLDER
    if not folder.exists() or not list_invoice_files(folder):
        print(f"No invoices found in {folder}.")
    print_summary(scan_folder(folder))
    show_database()


if __name__ == "__main__":
    main()
