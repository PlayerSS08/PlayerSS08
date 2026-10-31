"""
Accuracy report: run the full pipeline over tests/samples/ and compare
against tests/ground_truth.csv.

Matching rules (from the spec):
* amounts match within ₹0.01
* dates and times compare as strings (ISO date, 24h time)
* vendor matches case-insensitively as a substring (either direction)
* a field with an empty ground-truth value is skipped ("only where present")

Usage (from the project folder):
    python scripts/evaluate.py             # summary table
    python scripts/evaluate.py --details   # also list every mismatch
    python scripts/evaluate.py --markdown  # table in Markdown (for the README)
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

import config  # noqa: E402
from extractor.parser import process_file  # noqa: E402

FIELDS = ["invoice_number", "invoice_date", "invoice_time", "vendor", "total_amount"]


def field_matches(field: str, expected: str, actual) -> bool:
    """Compare one extracted value with the ground truth."""
    if actual is None or actual == "":
        return False
    if field == "total_amount":
        return abs(float(actual) - float(expected)) <= 0.01
    if field == "vendor":
        a, e = str(actual).lower().strip(), expected.lower().strip()
        return e in a or a in e
    if field == "invoice_number":
        return str(actual).strip().upper() == expected.strip().upper()
    return str(actual).strip() == expected.strip()


def load_ground_truth(path=config.GROUND_TRUTH_FILE) -> list:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate(samples_dir=config.SAMPLES_DIR, truth_path=config.GROUND_TRUTH_FILE) -> tuple:
    """Return (scores, mismatches). scores[field] = [correct, total]."""
    scores = {field: [0, 0] for field in FIELDS}
    mismatches = []
    for row in load_ground_truth(truth_path):
        invoice = process_file(Path(samples_dir) / row["file"])
        for field in FIELDS:
            expected = row[field].strip()
            if not expected:
                continue                      # not printed on this invoice
            scores[field][1] += 1
            actual = getattr(invoice, field)
            if field_matches(field, expected, actual):
                scores[field][0] += 1
            else:
                mismatches.append((row["file"], field, expected, actual))
    return scores, mismatches


def format_table(scores: dict, markdown: bool = False) -> str:
    """The accuracy table, plain text or Markdown."""
    note = {"invoice_time": "(only where present)", "invoice_number": "(only where present)"}
    if markdown:
        lines = ["| Field | Correct / Total | Accuracy |", "|---|---|---|"]
        for field, (ok, total) in scores.items():
            pct = 100 * ok / total if total else 0
            lines.append(f"| {field} {note.get(field, '')} | {ok} / {total} | {pct:.1f}% |")
        return "\n".join(lines)
    lines = [f"{'Field':<17}{'Correct / Total':<19}Accuracy"]
    for field, (ok, total) in scores.items():
        pct = 100 * ok / total if total else 0
        lines.append(f"{field:<17}{f'{ok:>2} / {total}':<19}{pct:5.1f}%   {note.get(field, '')}".rstrip())
    return "\n".join(lines)


def main():
    args = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    args.add_argument("--details", action="store_true", help="list every mismatch")
    args.add_argument("--markdown", action="store_true", help="print a Markdown table")
    options = args.parse_args()

    scores, mismatches = evaluate()
    print(format_table(scores, options.markdown))
    if options.details and mismatches:
        print("\nMismatches:")
        for file, field, expected, actual in mismatches:
            print(f"  {file:<34} {field:<15} expected {expected!r:<28} got {actual!r}")


if __name__ == "__main__":
    main()
