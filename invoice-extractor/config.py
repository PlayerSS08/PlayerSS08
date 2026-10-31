"""
Project-wide configuration constants.

Everything that a user might want to tweak (paths, thresholds, OCR engine)
lives here so that no other module needs hard-coded values.
Nothing in this file touches the disk or opens connections: it only
defines constants (no work at import time).
"""

from pathlib import Path

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent          # project root
DATA_DIR = BASE_DIR / "data"                         # database lives here
DATABASE_FILE = DATA_DIR / "invoices.db"             # SQLite database file
INVOICE_FOLDER = BASE_DIR / "invoices"               # drop-in folder for batch scan
VENDORS_FILE = BASE_DIR / "extractor" / "vendors.json"  # known vendor names
SAMPLES_DIR = BASE_DIR / "tests" / "samples"         # sample invoices for evaluation
GROUND_TRUTH_FILE = BASE_DIR / "tests" / "ground_truth.csv"

# ------------------------------------------------------------------
# File types we accept
# ------------------------------------------------------------------
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS

# ------------------------------------------------------------------
# Extraction settings
# ------------------------------------------------------------------
# A PDF page set with fewer non-space characters than this is treated
# as a scanned PDF and sent to OCR.
MIN_TEXT_CHARS = 50

# Resolution used when rendering scanned PDF pages to images for OCR.
PDF_RENDER_DPI = 300

# Images narrower than this are upscaled before OCR.
MIN_IMAGE_WIDTH = 1000

# Which OCR engine to use: "tesseract" (default) or "easyocr".
OCR_ENGINE = "tesseract"

# ------------------------------------------------------------------
# Validation settings
# ------------------------------------------------------------------
# Any field confidence below this marks the invoice as needs_review.
REVIEW_THRESHOLD = 0.6

# Allowed difference (in rupees) for the GST arithmetic check.
GST_TOLERANCE = 1.0

# Totals at or above this (1 crore) are treated as suspicious.
MAX_REASONABLE_TOTAL = 10_000_000

# Weights used for the overall confidence score.
CONFIDENCE_WEIGHTS = {
    "total_amount": 0.35,
    "invoice_date": 0.25,
    "vendor": 0.20,
    "invoice_number": 0.20,
}

DEFAULT_CURRENCY = "INR"
