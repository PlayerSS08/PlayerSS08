"""
Unit tests for extractor/fields.py.
At least five cases per field: good, messy, missing and OCR-noisy text.
"""

from datetime import date

import pytest

from extractor import fields

TODAY = date(2026, 10, 31)   # fixed "today" so the tests never go stale


# ----------------------------------------------------------------------
# normalisation helpers
# ----------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("1,25O.OO", "1,250.00"),
    ("3l/1O/2026", "31/10/2026"),
    ("SOLD", "SOLD"),           # a word, not a number
    ("IS", "IS"),
    ("12:3O", "12:30"),
])
def test_fix_ocr_digits(raw, expected):
    assert fields.fix_ocr_digits(raw) == expected


def test_normalize_text_currency_and_spaces():
    text = fields.normalize_text("Grand   Total :\tRs. 1,250.00\nAmount INR 50")
    assert "Grand Total : ₹ 1,250.00" in text
    assert "₹ 50" in text


@pytest.mark.parametrize("raw, expected", [
    ("1,23,456.78", 123456.78),
    ("₹ 1,250", 1250.0),
    ("1,250,00", 1250.0),       # OCR comma instead of decimal point
    ("500/-", 500.0),
    ("abc", None),
])
def test_parse_amount(raw, expected):
    assert fields.parse_amount(raw) == expected


# ----------------------------------------------------------------------
# invoice number
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Invoice Number: INV-2026-0042", "INV-2026-0042"),        # good
    ("TAX INVOICE NO.  KA/2026/1187\nDate: 12/10/2026", "KA/2026/1187"),
    ("Inv No # 77821", "77821"),
    ("Bill No: 45\nTable 3", "45"),                              # short receipt number
    ("Receipt No.- R9081", "R9081"),
    ("Order ID: 405-1234567-7654321", "405-1234567-7654321"),
    ("Invoice No: lNV2O26OO1", "lNV2O26OO1"),                   # noisy but kept
])
def test_invoice_number_found(text, expected):
    value, conf = fields.extract_invoice_number(text)
    assert value == expected
    assert conf == 0.9


def test_invoice_number_prefers_invoice_over_order():
    text = "Order Number: 403-111-222\nInvoice Number: IN-998877"
    assert fields.extract_invoice_number(text)[0] == "IN-998877"


@pytest.mark.parametrize("text", [
    "Thank you for shopping",          # missing
    "Invoice Number: pending",         # label without a number
    "",
])
def test_invoice_number_missing(text):
    assert fields.extract_invoice_number(text) == (None, 0.0)


# ----------------------------------------------------------------------
# date
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Invoice Date: 31/10/2026", "2026-10-31"),
    ("Invoice Date: 31-10-2026", "2026-10-31"),
    ("Date: 31.10.2026", "2026-10-31"),
    ("Dated 31 Oct 2026", "2026-10-31"),
    ("Bill Date: 31 October 2026", "2026-10-31"),
    ("Order Date: Oct 31, 2026", "2026-10-31"),
    ("Date : 2026-10-31", "2026-10-31"),
    ("Date: 31/10/26", "2026-10-31"),
    ("Date: 3l/1O/2O26", "2026-10-31"),          # OCR noise
    ("Invoice Date: 5th Sept, 2026", "2026-09-05"),
])
def test_date_formats(text, expected):
    value, conf = fields.extract_date(text, today=TODAY)
    assert value == expected
    assert conf >= 0.85


def test_date_is_day_first_with_lower_confidence_when_ambiguous():
    value, conf = fields.extract_date("Invoice Date: 05/10/2026", today=TODAY)
    assert value == "2026-10-05"         # 5 October, not May 10
    assert 0.8 <= conf < 0.9


def test_date_without_keyword_has_lower_confidence():
    value, conf = fields.extract_date("Swiggy order\n25/09/2026 8:15 PM", today=TODAY)
    assert value == "2026-09-25"
    assert conf == 0.6


def test_date_keyword_beats_earlier_date():
    text = "Printed 01/01/2025\nInvoice Date: 15/08/2026"
    assert fields.extract_date(text, today=TODAY)[0] == "2026-08-15"


def test_due_date_is_not_the_invoice_date():
    text = "Due Date: 20/11/2026\nBill Date: 20/10/2026"
    assert fields.extract_date(text, today=date(2026, 12, 1))[0] == "2026-10-20"


@pytest.mark.parametrize("text", [
    "No date here",
    "Date: 31/12/2030",          # future -> rejected
    "Date: 12/05/1998",          # before 2000 -> rejected
    "Date: 45/45/2026",          # impossible
    "",
])
def test_date_missing_or_rejected(text):
    assert fields.extract_date(text, today=TODAY) == (None, 0.0)


# ----------------------------------------------------------------------
# time
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, expected, conf", [
    ("Date: 12/10/2026 08:15 PM", "20:15", 0.8),
    ("Time: 14:05:33", "14:05:33", 0.8),
    ("Order Time 9:07 am", "09:07", 0.8),
    ("12/10/2026  12:00 AM", "00:00", 0.8),
    ("Thanks! Visit again 18:30", "18:30", 0.5),      # no date / label nearby
    ("Time: 1O:3O PM", "22:30", 0.8),                 # OCR noise
])
def test_time_found(text, expected, conf):
    value, confidence = fields.extract_time(text, today=TODAY)
    assert value == expected
    assert confidence == conf


@pytest.mark.parametrize("text", [
    "Invoice Date: 12/10/2026",   # many bills have no time
    "Ratio 1:2",
    "Time: 25:99",
    "",
    "13:45 PM",                   # invalid 12-hour time
])
def test_time_missing(text):
    assert fields.extract_time(text, today=TODAY) == (None, 0.0)


# ----------------------------------------------------------------------
# total amount
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("Sub Total 1,000.00\nCGST 9% 90.00\nSGST 9% 90.00\nGrand Total ₹ 1,180.00", 1180.0),
    ("Total Amount: Rs. 1,23,456.78", 123456.78),                    # lakh grouping
    ("Amount Payable\n₹ 2,345", 2345.0),                              # value on next line
    ("Total Qty: 3 Total: 450.00", 450.0),
    ("Item Total 400.00\nDelivery 30.00\nTotal 430", 430.0),
    ("Net Payable : INR 999/-", 999.0),
    ("TOTAL Rs 1,25O.OO", 1250.0),                                    # OCR noise
    ("Discount 50.00\nTotal Discount 50.00\nBill Amount 200.00", 200.0),
])
def test_total_with_label(text, expected):
    value, conf = fields.extract_total(text)
    assert value == expected
    assert conf == 0.9


def test_total_priority_grand_total_over_total():
    text = "Grand Total 590.00\nTotal 500.00"
    assert fields.extract_total(text)[0] == 590.0


def test_total_ignores_percentages():
    assert fields.extract_total("Grand Total (incl. 18%) 1,180.00")[0] == 1180.0


def test_total_fallback_guesses_largest_amount():
    value, conf = fields.extract_total("Paneer 250.00\nNaan 60.00\nPh 9876543210")
    assert value == 250.0
    assert conf == fields.TOTAL_GUESS_CONFIDENCE


@pytest.mark.parametrize("text", ["No numbers at all", "", "Call 9876543210"])
def test_total_missing(text):
    assert fields.extract_total(text) == (None, 0.0)


# ----------------------------------------------------------------------
# vendor
# ----------------------------------------------------------------------
KNOWN = (("Amazon", ("Amazon", "Amazon.in")), ("Swiggy", ("Swiggy",)),
         ("BESCOM", ("BESCOM",)))


@pytest.mark.parametrize("text, expected, conf", [
    ("Tax Invoice\nSold By: Appario Retail Private Ltd, Bangalore", "Appario Retail Private Ltd", 0.9),
    ("Seller : CLOUDTAIL INDIA PVT LTD\nGSTIN 29AAACC1234F1Z5", "Cloudtail India Pvt Ltd", 0.9),
    ("TAX INVOICE\nSri Krishna Sweets\nGSTIN: 33ABCDE1234F1Z5", "Sri Krishna Sweets", 0.7),
    ("Order via swiggy\nTotal 300", "Swiggy", 0.85),
    ("ORIGINAL FOR RECIPIENT\nTAX INVOICE\nHOTEL ANNAPOORNA.\nBill No 4", "Hotel Annapoorna", 0.4),
    ("Supplier:\nGreen Leaf Traders\nAddress: MG Road", "Green Leaf Traders", 0.9),
])
def test_vendor_found(text, expected, conf):
    value, confidence = fields.extract_vendor(text, known_vendors=KNOWN)
    assert value == expected
    assert confidence == conf


def test_vendor_from_dates_is_rejected():
    # "From: 01/09/2026" on a utility bill is a billing period, not a vendor.
    text = "From: 01/09/2026 To: 30/09/2026\nBESCOM\nAmount Payable 1200"
    assert fields.extract_vendor(text, known_vendors=KNOWN) == ("BESCOM", 0.85)


@pytest.mark.parametrize("text", ["", "INVOICE\n12345\n31/10/2026", "Tax Invoice\nReceipt"])
def test_vendor_missing(text):
    assert fields.extract_vendor(text, known_vendors=KNOWN) == (None, 0.0)


def test_vendor_dictionary_file_loads():
    vendors = dict(fields.load_known_vendors())
    assert "Amazon" in vendors and "Zomato" in vendors


@pytest.mark.parametrize("raw, expected", [
    ("  ACME TRADERS.  ", "Acme Traders"),
    ("Big Bazaar,", "Big Bazaar"),
    (": Foo Bar -", "Foo Bar"),
    ("McDonald's", "McDonald's"),
    ("", ""),
])
def test_clean_vendor(raw, expected):
    assert fields.clean_vendor(raw) == expected


# ----------------------------------------------------------------------
# GST fields
# ----------------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("GSTIN: 29AAACC1234F1Z5", "29AAACC1234F1Z5"),
    ("GSTIN/UIN 07aabcu9603r1zx", "07AABCU9603R1ZX"),     # lower case print
    ("Our GST No 33ABCDE1234F1Z5 and PAN ABCDE1234F", "33ABCDE1234F1Z5"),
    ("GSTIN: 29AAACC1234F1Z", None),                      # too short
    ("", None),
])
def test_gstin(text, expected):
    assert fields.extract_gstin(text)[0] == expected


GST_BILL = """Sub Total 1,000.00
CGST @ 9% 90.00
SGST @ 9% 90.00
Grand Total 1,180.00"""


def test_gst_amounts():
    assert fields.extract_subtotal(GST_BILL)[0] == 1000.0
    assert fields.extract_cgst(GST_BILL)[0] == 90.0
    assert fields.extract_sgst(GST_BILL)[0] == 90.0
    assert fields.extract_igst(GST_BILL) == (None, 0.0)


@pytest.mark.parametrize("text, expected", [
    ("IGST 18% 180.00", 180.0),
    ("IGST (18%): ₹ 1,800", 1800.0),
    ("IGST: 18 %  36.00", 36.0),
    ("IGST 0.00", 0.0),
    ("No tax", None),
])
def test_igst(text, expected):
    assert fields.extract_igst(text)[0] == expected


@pytest.mark.parametrize("text, expected", [
    ("Taxable Value 500.00", 500.0),
    ("Subtotal: Rs. 250", 250.0),
    ("Sub-Total 75.50", 75.5),
    ("Item Total ₹ 410", 410.0),
    ("Total 99", None),
])
def test_subtotal(text, expected):
    assert fields.extract_subtotal(text)[0] == expected


def test_vendor_skips_address_between_name_and_gstin():
    text = "PAPER PLUS STATIONERS\n12 Brigade Road, Bengaluru 560001\nGSTIN: 29AAGFP7788K1ZS"
    assert fields.extract_vendor(text, known_vendors=KNOWN) == ("Paper Plus Stationers", 0.7)


def test_vendor_ignores_ocr_noise_and_fixes_exclamation():
    text = "nana\nSRI SA! MEDICALS\nChemist & Druggist, Anna Nagar"
    assert fields.extract_vendor(text, known_vendors=KNOWN)[0] == "Sri Sai Medicals"


@pytest.mark.parametrize("line, is_address", [
    ("12 Brigade Road, Bengaluru 560001", True), ("Station Road", True),
    ("Chickpet, Bengaluru", True), ("Ganesh Hardware", False), ("Hotel Annapoorna", False),
])
def test_looks_like_address(line, is_address):
    assert fields.looks_like_address(line) is is_address


def test_tax_label_inside_item_row_is_ignored():
    text = ("1 Mouse ₹508.47 1 ₹508.47 18% IGST ₹91.53 ₹600.00\n"
            "TOTAL: ₹152.55 ₹1,000.00")
    assert fields.extract_igst(text) == (None, 0.0)
    assert fields.extract_igst(text + "\nIGST @ 18% 152.55")[0] == 152.55
