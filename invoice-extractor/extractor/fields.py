"""
Rule-based extraction of individual invoice fields from plain text.

Every public `extract_*` function is PURE: it takes text and returns a
`(value, confidence)` tuple. `(None, 0.0)` means "not found".
Confidence is a number from 0.0 to 1.0.

Each function normalises its input first (see `normalize_text`), so it can
be unit tested with raw, messy strings.
"""

import json
import re
import unicodedata
from datetime import date, timedelta
from functools import lru_cache
from typing import Optional

from dateutil import parser as date_parser

import config

# ======================================================================
# 1. TEXT NORMALISATION
# ======================================================================

# Characters OCR often confuses with digits, and what they should be.
OCR_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"})

# A "numeric-looking" token: digits plus the confusable letters, with
# optional separators (as found in amounts, dates and times).
_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])[0-9OolIS]+(?:[.,:/\-][0-9OolIS]+)*(?![A-Za-z0-9])"
)

# Rs / Rs. / INR / unicode rupee variants -> the single symbol "₹".
_CURRENCY_RE = re.compile(r"(?<![A-Za-z])(?:Rs\.?|INR|₨)(?![A-Za-z])\s*", re.IGNORECASE)


def fix_ocr_digits(token: str) -> str:
    """
    Fix O->0, l->1, I->1, S->5 inside a numeric-looking token.

    Only applied when the token already contains at least two real digits
    and at least as many real digits as confusable letters, so words such
    as "SOLD" or "IS" are never changed.
    """
    digits = sum(ch.isdigit() for ch in token)
    letters = sum(ch.isalpha() for ch in token)
    if letters == 0 or digits < 2 or digits < letters:
        return token
    return token.translate(OCR_DIGIT_FIXES)


def normalize_text(text: str) -> str:
    """
    Clean raw extracted text before parsing:
    * unicode normalisation (NFKC) and non-breaking spaces -> spaces
    * Rs. / INR -> ₹
    * collapse repeated spaces and tabs, strip each line
    * fix common OCR letter/digit mix-ups inside amounts and dates
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("–", "-").replace("—", "-")   # en/em dash
    text = _CURRENCY_RE.sub("₹ ", text)
    text = _NUMERIC_TOKEN_RE.sub(lambda m: fix_ocr_digits(m.group(0)), text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines)


def _lines(text: str) -> list:
    """Non-empty lines of the text."""
    return [line for line in text.split("\n") if line.strip()]


# ======================================================================
# 2. AMOUNTS (shared helpers)
# ======================================================================

# A money value: Indian/Western comma grouping or plain digits, optional
# 1-2 decimals. It must not be part of a date, time, percentage or word.
AMOUNT_RE = re.compile(
    r"(?<![\w.,/])(?<!\d:)"
    r"(\d{1,3}(?:,\d{2,3})+(?:[.,]\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"(?![\w]|/\d|[.,]\d|:\d|\s*%)"
)


def parse_amount(raw: str) -> Optional[float]:
    """
    Convert an amount string to float.
    Handles ₹, commas, Indian lakh grouping (1,23,456.78) and the OCR
    habit of printing the decimal point as a comma (1,250,00).
    """
    if raw is None:
        return None
    s = fix_ocr_digits(str(raw)).replace("₹", "").replace(" ", "").strip()
    s = s.rstrip("/-")
    # "1,250,00" -> the last comma is really a decimal point
    if re.fullmatch(r"\d{1,3}(?:,\d{3})*,\d{2}", s):
        s = s[:-3].replace(",", "") + "." + s[-2:]
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def find_amounts(segment: str) -> list:
    """All money values in a piece of text, in order of appearance."""
    values = []
    for match in AMOUNT_RE.finditer(segment):
        value = parse_amount(match.group(1))
        if value is not None:
            values.append(value)
    return values


def _amount_after_label(lines: list, index: int, label_start: int,
                        label_end: int) -> Optional[float]:
    """
    The money value that belongs to a label found on lines[index].

    1. Text after the label on the same line, cut at the next word
       (another label) - take the last number in that piece.
    2. If nothing there, the last number in the rest of the line.
    3. If the label is alone on its line, the first number on the next line.
    """
    rest = lines[index][label_end:]
    piece = re.split(r"[A-Za-z]{3,}", rest, maxsplit=1)[0]
    amounts = find_amounts(piece) or find_amounts(rest)
    if amounts:
        return amounts[-1]
    # "alone" = nothing else on the line, so it is not a table header row
    before = lines[index][:label_start]
    label_alone = len(re.sub(r"[\s:₹\-.()]", "", before + rest)) == 0
    if label_alone and index + 1 < len(lines):
        next_amounts = find_amounts(lines[index + 1])
        if next_amounts:
            return next_amounts[0]
    return None


def _label_regex(label: str) -> str:
    """'Grand Total' -> regex tolerant of missing/extra spaces: Grand\\s*Total."""
    return r"\s*".join(re.escape(word) for word in label.split())


def extract_labeled_amount(text: str, labels: list,
                           exclude_after: str = "", exclude_before: tuple = ()) -> Optional[float]:
    """
    Find the amount next to any of `labels` (tried in priority order).
    The LAST occurrence of a label wins, since summaries are at the bottom.
    """
    lines = _lines(text)
    for label in labels:
        pattern = r"\b" + _label_regex(label) + r"\b"
        for before in exclude_before:
            pattern = rf"(?<!{before})" + pattern
        if exclude_after:
            pattern += rf"(?!\s*(?:{exclude_after}))"
        regex = re.compile(pattern, re.IGNORECASE)
        found = None
        for i, line in enumerate(lines):
            for match in regex.finditer(line):
                value = _amount_after_label(lines, i, match.start(), match.end())
                if value is not None:
                    found = value
        if found is not None:
            return found
    return None


# ======================================================================
# 3. INVOICE NUMBER
# ======================================================================

# Extends the regex from the original Scanner.py with more labels.
# Groups are tried in priority order (real invoice numbers first).
INVOICE_NUMBER_PATTERNS = [
    r"\b(?:Tax\s*)?Invoice\s*(?:Number|No\.?|#|Num\.?)",
    r"\bInv\.?\s*(?:No\.?|Number|#)",
    r"\b(?:Bill|Receipt)\s*(?:Number|No\.?|#)",
    r"\bOrder\s*(?:ID|No\.?|Number|#)",
]
_INVOICE_VALUE = r"\s*#?\s*[:\-.]?\s*#?\s*([A-Z0-9][A-Z0-9/\-]*)"


def extract_invoice_number(text: str) -> tuple:
    """Invoice / bill / receipt / order number. Confidence 0.9 if a label matched."""
    text = normalize_text(text)
    for label in INVOICE_NUMBER_PATTERNS:
        regex = re.compile(label + _INVOICE_VALUE, re.IGNORECASE)
        for match in regex.finditer(text):
            value = match.group(1).strip("-/")
            if any(ch.isdigit() for ch in value):
                return value, 0.9
    return None, 0.0


# ======================================================================
# 4. DATE
# ======================================================================

_MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
           r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")

DATE_PATTERNS = [
    # 2026-10-31
    ("ymd", re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")),
    # 31/10/2026, 31-10-2026, 31.10.2026, 31/10/26
    ("dmy", re.compile(r"(?<![\d.,])(\d{1,2})\s?[/\-.]\s?(\d{1,2})\s?[/\-.]\s?(\d{4}|\d{2})(?![\d,]|\.\d)")),
    # 31 Oct 2026, 31 October 2026, 31-Oct-26, 31st Oct, 2026
    ("text", re.compile(r"(?<!\d)\d{1,2}(?:st|nd|rd|th)?[\s\-/.,]*" + _MONTHS
                        + r"(?![a-z])\.?[\s\-/.,']*(?:\d{4}|\d{2})(?!\d)", re.IGNORECASE)),
    # Oct 31, 2026, October 31 2026
    ("text", re.compile(r"\b" + _MONTHS + r"(?![a-z])\.?[\s\-/.]*\d{1,2}(?:st|nd|rd|th)?,?"
                        r"[\s\-/.]*\d{4}(?!\d)", re.IGNORECASE)),
]

# Keywords that introduce the invoice date, in priority order.
DATE_KEYWORDS = [
    r"invoice\s*date", r"bill\s*date", r"date\s*of\s*invoice", r"dated",
    r"order\s*date", r"(?<!due )(?<!due)(?<!delivery )(?<!expiry )\bdate\b",
]


def _full_year(year: int) -> int:
    """Two-digit years are taken as 20xx."""
    return year + 2000 if year < 100 else year


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(_full_year(year), month, day)
    except ValueError:
        return None


def _interpret(kind: str, match) -> tuple:
    """Turn one regex match into (date, confidence_penalty) or (None, 0)."""
    if kind == "ymd":
        y, m, d = (int(g) for g in match.groups())
        return _safe_date(y, m, d), 0.0
    if kind == "dmy":
        a, b, y = (int(g) for g in match.groups())
        if a > 12 and b <= 12:              # unambiguous day-first
            return _safe_date(y, b, a), 0.0
        if a <= 12 and b > 12:              # must be month-first (US style)
            return _safe_date(y, a, b), 0.1
        penalty = 0.0 if a == b else 0.05   # ambiguous: assume DD/MM (India)
        return _safe_date(y, b, a), penalty
    # textual month: let python-dateutil read it
    try:
        cleaned = re.sub(r"(\d)(st|nd|rd|th)", r"\1", match.group(0), flags=re.IGNORECASE)
        parsed = date_parser.parse(cleaned, dayfirst=True, fuzzy=True).date()
        two_digit = re.search(r"\d{4}", cleaned) is None
        if two_digit and parsed.year < 2000:
            parsed = parsed.replace(year=parsed.year + 100)
        return parsed, 0.0
    except (ValueError, OverflowError):
        return None, 0.0


def _is_plausible(d: date, today: date) -> bool:
    """Reject dates before 2000 or more than one day in the future."""
    return date(2000, 1, 1) <= d <= today + timedelta(days=1)


def find_date_candidates(text: str, today: Optional[date] = None) -> list:
    """
    Every valid date in the text as (start, end, iso_string, penalty),
    sorted by position, without overlaps.
    """
    today = today or date.today()
    found = []
    for kind, regex in DATE_PATTERNS:
        for match in regex.finditer(text):
            if any(s < match.end() and match.start() < e for s, e, _, _ in found):
                continue  # overlaps a date already found
            value, penalty = _interpret(kind, match)
            if value and _is_plausible(value, today):
                found.append((match.start(), match.end(), value.isoformat(), penalty))
    return sorted(found)


def extract_date(text: str, today: Optional[date] = None) -> tuple:
    """
    Invoice date as ISO 'YYYY-MM-DD'.
    Dates right after a keyword (Invoice Date, Date, Dated...) win with
    confidence 0.9; otherwise the first date in the text gets 0.6.
    Ambiguous day/month order lowers the confidence slightly.
    """
    text = normalize_text(text)
    candidates = find_date_candidates(text, today)
    if not candidates:
        return None, 0.0
    for keyword in DATE_KEYWORDS:
        for kw in re.finditer(keyword, text, re.IGNORECASE):
            for start, _end, iso, penalty in candidates:
                if kw.end() <= start <= kw.end() + 40:
                    return iso, round(0.9 - penalty, 2)
    _start, _end, iso, penalty = candidates[0]
    return iso, round(0.6 - penalty, 2)


# ======================================================================
# 5. TIME
# ======================================================================

TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\s*(AM|PM|am|pm)?\b")
TIME_LABEL_RE = re.compile(r"\b(?:order\s*)?time\b", re.IGNORECASE)


def _to_24h(hour: int, minute: str, second: Optional[str], meridiem: Optional[str]) -> Optional[str]:
    """Convert a matched time to 'HH:MM' or 'HH:MM:SS' (24 hour)."""
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        meridiem = meridiem.upper()
        if meridiem == "AM":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    result = f"{hour:02d}:{minute}"
    return f"{result}:{second}" if second else result


def extract_time(text: str, today: Optional[date] = None) -> tuple:
    """
    Time printed on the bill, 24h format. Many invoices have none -> (None, 0.0).
    A time within 30 characters of a date or a 'Time' label gets 0.8, else 0.5.
    """
    text = normalize_text(text)
    dates = find_date_candidates(text, today)
    labels = [m.end() for m in TIME_LABEL_RE.finditer(text)]
    first = None
    for match in TIME_RE.finditer(text):
        hour, minute, second, meridiem = match.groups()
        value = _to_24h(int(hour), minute, second, meridiem)
        if value is None:
            continue
        start, end = match.start(), match.end()
        near_date = any(0 <= start - d_end <= 30 or 0 <= d_start - end <= 30
                        for d_start, d_end, _, _ in dates)
        near_label = any(0 <= start - label_end <= 30 for label_end in labels)
        if near_date or near_label:
            return value, 0.8
        first = first or value
    return (first, 0.5) if first else (None, 0.0)


# ======================================================================
# 6. TOTAL AMOUNT (the most important field)
# ======================================================================

TOTAL_LABELS = [
    "Grand Total", "Total Amount", "Amount Payable", "Net Payable", "Net Amount",
    "Amount Due", "Balance Due", "Total", "Invoice Total", "Bill Amount",
]
# A "Total" label followed by one of these is NOT the final total.
TOTAL_EXCLUDE_AFTER = (r"tax\b|gst\b|qty|quantity|items?\b|discount|savings?|saved|"
                       r"taxable|weight|units?\b|mrp")
# ... nor when preceded by these (Sub Total, Item Total).
TOTAL_EXCLUDE_BEFORE = ("sub ", "sub", "sub-", "item ", "items ")
# Lines with these words are ignored entirely for the final total.
TOTAL_SKIP_LINE_RE = re.compile(r"\bdiscount\b", re.IGNORECASE)

TOTAL_LABEL_CONFIDENCE = 0.9
TOTAL_GUESS_CONFIDENCE = 0.4   # fallback: largest amount in the document


def guess_largest_amount(text: str) -> Optional[float]:
    """
    Fallback: the largest *monetary-looking* value (has ₹ in front or two
    decimals) below the sanity limit. Phone numbers etc. are ignored.
    """
    best = None
    for match in AMOUNT_RE.finditer(text):
        raw = match.group(1)
        before = text[max(0, match.start() - 3):match.start()]
        looks_monetary = "₹" in before or re.search(r"[.,]\d{2}$", raw)
        value = parse_amount(raw)
        if looks_monetary and value and value < config.MAX_REASONABLE_TOTAL:
            best = value if best is None else max(best, value)
    return best


def extract_total(text: str) -> tuple:
    """
    Total payable. Labels are tried in priority order (Grand Total first).
    Confidence 0.9 for a label match; 0.4 if we had to guess the largest
    amount (the parser adds a 'total guessed' warning in that case).
    """
    text = normalize_text(text)
    usable = "\n".join(line for line in _lines(text) if not TOTAL_SKIP_LINE_RE.search(line))
    value = extract_labeled_amount(usable, TOTAL_LABELS,
                                   exclude_after=TOTAL_EXCLUDE_AFTER,
                                   exclude_before=TOTAL_EXCLUDE_BEFORE)
    if value is not None and value > 0:
        return value, TOTAL_LABEL_CONFIDENCE
    guess = guess_largest_amount(text)
    if guess is not None:
        return guess, TOTAL_GUESS_CONFIDENCE
    return None, 0.0


# ======================================================================
# 7. GST FIELDS
# ======================================================================

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")

SUBTOTAL_LABELS = ["Sub Total", "Subtotal", "Sub-Total", "Taxable Value",
                   "Taxable Amount", "Item Total"]


def extract_gstin(text: str) -> tuple:
    """First GSTIN-shaped code in the text (structure checked by validators)."""
    match = GSTIN_RE.search(normalize_text(text).upper())
    return (match.group(0), 0.9) if match else (None, 0.0)


def _tax_amount(text: str, label: str) -> tuple:
    """Amount on the last line labelled CGST / SGST / IGST (percentages ignored)."""
    value = extract_labeled_amount(normalize_text(text), [label])
    return (value, 0.8) if value is not None else (None, 0.0)


def extract_cgst(text: str) -> tuple:
    """Central GST amount."""
    return _tax_amount(text, "CGST")


def extract_sgst(text: str) -> tuple:
    """State GST amount (UTGST is treated the same way)."""
    value, conf = _tax_amount(text, "SGST")
    return (value, conf) if value is not None else _tax_amount(text, "UTGST")


def extract_igst(text: str) -> tuple:
    """Integrated GST amount."""
    return _tax_amount(text, "IGST")


def extract_subtotal(text: str) -> tuple:
    """Amount before tax."""
    value = extract_labeled_amount(normalize_text(text), SUBTOTAL_LABELS)
    return (value, 0.8) if value is not None else (None, 0.0)


# ======================================================================
# 8. VENDOR / SOURCE
# ======================================================================

VENDOR_LABEL_RE = re.compile(
    r"^\s*(?:sold\s*by|seller|billed\s*by|from|supplier|merchant)"
    r"(?:\s*(?:name|details))?\s*[:\-]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Where a vendor name on a line stops (another field begins).
_VENDOR_CUT_RE = re.compile(
    r"\s*(?:,|\||;|\bGSTIN\b|\bGST\b|\bPAN\b|\bAddress\b|\bBilling\b|\bShipping\b|"
    r"\bInvoice\b|\bDate\b|\bPhone\b|\bPh\b|\bMob(?:ile)?\b|\bTel\b|\bEmail\b|\bFSSAI\b)",
    re.IGNORECASE,
)
GENERIC_WORDS = {
    "invoice", "tax", "bill", "receipt", "original", "duplicate", "triplicate",
    "copy", "for", "recipient", "cash", "memo", "of", "supply", "retail", "gst",
    "estimate", "sales", "customer", "transporter", "the", "page", "1", "statement",
}
# Lines that are clearly fields, not names.
_NOT_A_NAME_RE = re.compile(
    r"@|www\.|https?:|\b(?:phone|email|e-mail|address|tel|mob|mobile|gstin|pan|invoice|"
    r"date|bill to|ship to|page|cin|fssai|order|customer|qty|total)\b",
    re.IGNORECASE,
)
_STOP_FIRST_WORDS = {"gstin", "gst", "pan", "registration", "address", "details",
                     "state", "code", "no", "number", "date", "to"}


def clean_vendor(name: str) -> str:
    """Strip, title-case if ALL CAPS, remove trailing punctuation."""
    name = re.sub(r"\s+", " ", name or "").strip(" :-\t")
    name = name.rstrip(".,;:-*|").strip()
    if name.isupper():
        name = name.title()
    return name


def _is_generic(line: str) -> bool:
    words = re.findall(r"[a-z0-9]+", line.lower())
    return not words or all(word in GENERIC_WORDS for word in words)


def _looks_like_name(line: str) -> bool:
    """A rough test for 'this line is a business name'."""
    line = line.strip()
    letters = sum(ch.isalpha() for ch in line)
    if letters < 3 or len(line) > 60 or letters / max(len(line), 1) < 0.5:
        return False
    if _NOT_A_NAME_RE.search(line) or _is_generic(line):
        return False
    first_word = re.findall(r"[a-z]+", line.lower())[:1]
    return not (first_word and first_word[0] in _STOP_FIRST_WORDS)


def _vendor_from_label(lines: list) -> Optional[str]:
    """Rule 1: text after 'Sold By', 'Seller', 'From' ..."""
    for i, line in enumerate(lines):
        match = VENDOR_LABEL_RE.match(line)
        if not match:
            continue
        candidate = match.group(1).strip()
        if not candidate and i + 1 < len(lines):
            candidate = lines[i + 1]
        candidate = _VENDOR_CUT_RE.split(candidate, maxsplit=1)[0]
        if _looks_like_name(candidate):
            return clean_vendor(candidate)
    return None


def _vendor_near_gstin(lines: list) -> Optional[str]:
    """Rule 2: the line just above (or below) the first GSTIN."""
    for i, line in enumerate(lines):
        if GSTIN_RE.search(line.upper()):
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and _looks_like_name(lines[j]):
                    return clean_vendor(lines[j])
            return None
    return None


@lru_cache(maxsize=1)
def load_known_vendors(path: str = str(config.VENDORS_FILE)) -> tuple:
    """Read vendors.json -> tuple of (canonical_name, (aliases...))."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return ()
    return tuple((name, tuple(aliases)) for name, aliases in data.items()
                 if not name.startswith("_"))


def _vendor_from_dictionary(text: str, known_vendors) -> Optional[str]:
    """Rule 3: the earliest known vendor name mentioned anywhere."""
    best_pos, best_name = None, None
    for name, aliases in known_vendors:
        for alias in aliases:
            match = re.search(r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])",
                              text, re.IGNORECASE)
            if match and (best_pos is None or match.start() < best_pos):
                best_pos, best_name = match.start(), name
    return best_name


def _vendor_from_first_line(lines: list) -> Optional[str]:
    """Rule 4: the first line that is not a generic heading."""
    for line in lines[:15]:
        if _looks_like_name(line):
            return clean_vendor(line)
    return None


def extract_vendor(text: str, known_vendors=None) -> tuple:
    """
    Who issued the invoice. Rules, first success wins:
      1. labelled ('Sold By: ...')        -> 0.9
      2. line next to the GSTIN            -> 0.7
      3. known name from vendors.json      -> 0.85
      4. first meaningful line             -> 0.4
    """
    text = normalize_text(text)
    lines = _lines(text)
    if known_vendors is None:
        known_vendors = load_known_vendors()

    name = _vendor_from_label(lines)
    if name:
        return name, 0.9
    name = _vendor_near_gstin(lines)
    if name:
        return name, 0.7
    name = _vendor_from_dictionary(text, known_vendors)
    if name:
        return name, 0.85
    name = _vendor_from_first_line(lines)
    if name:
        return name, 0.4
    return None, 0.0
