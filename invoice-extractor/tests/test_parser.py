"""End-to-end tests for parse_invoice() on complete invoice texts."""

from datetime import date

from extractor.parser import parse_invoice

TODAY = date(2026, 10, 31)

AMAZON = """Tax Invoice/Bill of Supply/Cash Memo
(Original for Recipient)
Sold By :
Appario Retail Private Ltd
Bengaluru, Karnataka, 560068
PAN No: AALCA0171E
GST Registration No: 29AALCA0171E1ZK
Order Number: 408-1234567-1234567
Order Date: 12.10.2026
Invoice Number : BLR7-123456
Invoice Date : 13.10.2026
Sl. Description Unit Price Qty Net Amount Tax Rate Tax Type Tax Amount Total Amount
1 Boat Rockerz 450 Headphones 1,270.34 1 ₹1,270.34 18% IGST ₹228.66 ₹1,499.00
TOTAL: ₹228.66 ₹1,499.00
Amount in Words: One Thousand Four Hundred Ninety-nine only
"""

SWIGGY = """SWIGGY
Bundl Technologies Private Limited
Order ID: 168934521098
Order placed at 25 Sep 2026, 08:42 PM
Restaurant: Meghana Foods
Item Total ₹ 520.00
Delivery partner fee ₹ 35.00
Taxes ₹ 26.00
Total Discount -₹ 100.00
Grand Total ₹ 481.00
"""

RESTAURANT_OCR = """HOTEL ANNAPOORNA
GSTIN: 33ABCDE1234F1Z5
Bill No: 1187   Table: 4
Date: 3O/O9/2O26  Time: 1:45 PM
Idli 2 60.OO
Dosa 1 9O.OO
Sub Total 150.OO
CGST 2.5% 3.75
SGST 2.5% 3.75
Total Rs. 157.5O
"""

ELECTRICITY = """BANGALORE ELECTRICITY SUPPLY COMPANY LIMITED
BESCOM
Bill Date: 05/10/2026
Billing Period From: 01/09/2026 To: 30/09/2026
Account ID 1234567890
Units consumed 210
Net Amount Payable Rs. 1,845.00
Due Date: 20/10/2026
"""


def test_amazon_invoice():
    inv = parse_invoice(AMAZON, "amazon.pdf", "h", today=TODAY)
    assert inv.invoice_number == "BLR7-123456"
    assert inv.invoice_date == "2026-10-13"
    assert inv.vendor == "Appario Retail Private Ltd"
    assert inv.total_amount == 1499.0
    assert inv.gstin == "29AALCA0171E1ZK"
    assert inv.invoice_time is None
    assert inv.source_file == "amazon.pdf"


def test_swiggy_order():
    inv = parse_invoice(SWIGGY, today=TODAY)
    assert inv.invoice_number == "168934521098"
    assert inv.invoice_date == "2026-09-25"
    assert inv.invoice_time == "20:42"
    assert inv.vendor == "Swiggy"
    assert inv.total_amount == 481.0


def test_noisy_restaurant_bill():
    inv = parse_invoice(RESTAURANT_OCR, extraction_method="ocr", today=TODAY)
    assert inv.invoice_number == "1187"
    assert inv.invoice_date == "2026-09-30"
    assert inv.invoice_time == "13:45"
    assert inv.vendor == "Hotel Annapoorna"
    assert inv.total_amount == 157.5
    assert inv.subtotal == 150.0
    assert inv.cgst == 3.75 and inv.sgst == 3.75
    assert inv.extraction_method == "ocr"


def test_electricity_bill():
    inv = parse_invoice(ELECTRICITY, today=TODAY)
    assert inv.invoice_date == "2026-10-05"
    assert inv.total_amount == 1845.0
    assert inv.vendor.lower() in ("bescom", "bangalore electricity supply company limited")


def test_confidence_dict_is_filled():
    inv = parse_invoice(AMAZON, today=TODAY)
    for key in ("invoice_number", "invoice_date", "vendor", "total_amount"):
        assert 0.0 <= inv.confidence[key] <= 1.0


def test_empty_text_gives_empty_but_valid_result():
    inv = parse_invoice("", "blank.png", "x", "failed", today=TODAY)
    assert inv.total_amount is None and inv.vendor is None
    assert inv.raw_text == ""
    assert "no text could be extracted" in inv.warnings


def test_guessed_total_adds_warning():
    inv = parse_invoice("Corner Shop\nMilk 30.00\nBread 45.00", today=TODAY)
    assert inv.total_amount == 45.0
    assert "total guessed" in inv.warnings


def test_apply_corrections_marks_fields_verified():
    from extractor.parser import apply_corrections
    inv = parse_invoice("Corner Shop\nMilk 30.00\nBread 45.00", today=TODAY)
    assert inv.needs_review
    fixed = apply_corrections(inv, {"total_amount": "75", "invoice_date": "2026-10-30",
                                    "invoice_number": "CS-1", "vendor": "Corner Shop Ltd"},
                              today=TODAY)
    assert fixed.total_amount == 75.0
    assert fixed.confidence["total_amount"] == 1.0
    assert "total guessed" not in fixed.warnings
    assert not fixed.needs_review
    assert inv.total_amount == 45.0          # original untouched


def test_convert_field():
    import pytest
    from extractor.parser import convert_field
    assert convert_field("total_amount", "₹ 1,234.50") == 1234.5
    assert convert_field("invoice_date", "31/10/2026") == "2026-10-31"
    assert convert_field("vendor", "  ") is None
    assert convert_field("gstin", "29aaacc1234f1z5") == "29AAACC1234F1Z5"
    with pytest.raises(ValueError):
        convert_field("total_amount", "abc")
