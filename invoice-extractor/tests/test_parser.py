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


# ----------------------------------------------------------------------
# One PDF, two invoices (Amazon order paid cash-on-delivery).
# Layout copied from a real Amazon invoice; customer name, address and
# order/invoice numbers replaced with placeholders. Pages are separated
# by "\f" exactly as text_extraction.get_text() separates them.
# ----------------------------------------------------------------------
AMAZON_TWO_INVOICES = """Tax Invoice/Bill of Supply/Cash Memo
(Original for Recipient)
Please note that this invoice is not a demand for payment
Page 1 of 1
For Repro Books Limited:
Authorized Signatory
Order Number: 171-0000000-0000001
Invoice Number : XQVZ-100001
Order Date: 06.11.2026
Invoice Details : HR-XQVZ-100001-2627
Invoice Date : 07.11.2026
Sl.
No
Description
Unit
Price
Qty Net
Amount
Tax
Rate
Tax
Type
Tax
Amount
Total
Amount
1
The Iliad | 0140447946 ( RKC0003332955
)
HSN:49011010
₹275.00
1
₹275.00
0%
IGST
₹0.00
₹275.00
0%
IGST
₹0.00
0%
None
₹0.00
Shipping Charges
₹40.00
₹40.00
0%
IGST
₹0.00
₹40.00
0%
IGST
₹0.00
0%
None
₹0.00
TOTAL:
₹0.00
₹315.00
Amount in Words:
Three Hundred Fifteen only
Sold By :
Repro Books Limited
*
Dharuhera, Rewari ,
Haryana - 123110
PAN No: AAECR4557N
GST Registration No: 06AAECR4557N3ZU
Billing Address :
Customer Name
1 Example Street, Bengaluru
BENGALURU, KARNATAKA, 560001
\f
Tax Invoice/Bill of Supply/Cash Memo
(Original for Recipient)
Regd Office: Amazon Seller Services Private Limited
Amazon.in - Amazon Seller Services Private Limited
Page 1 of 1
For Amazon Seller Services Private Limited:
Authorized Signatory
Order Number:171-0000000-0000001
Invoice Number :POD-27-200000001
Order Date:06.11.2026
Invoice Details :HR-XQVZ-1044-2627
Invoice Date :07.11.2026
Sl. No Description
Unit Price
Qty Net Amount
Tax Rate
Tax Type
Tax Amount
Total Amount
1
Cash/Pay on Delivery fee:
₹5.94
₹5.94
9%
CGST
₹0.53
₹7.00
9%
SGST
₹0.53
TOTAL:
₹1.06
₹7.00
Amount in Words:
Seven only
Digitally signed by DS AMAZON SELLER SERVICES PRIVATE LIMITED 6
Date: 2026.11.06 19:42:55 UTC
Sold By :
Amazon Seller Services Private Limited
*
Bangalore, Karnataka – 560064
GST Registration No:29AAICA3918J1ZE
"""


def test_split_documents_finds_both_invoices():
    from extractor.parser import split_documents
    docs = split_documents(AMAZON_TWO_INVOICES)
    assert len(docs) == 2
    assert "XQVZ-100001" in docs[0] and "POD-27-200000001" in docs[1]


def test_split_keeps_a_multi_page_invoice_together():
    from extractor.parser import split_documents
    text = "Invoice No: A-1\nItem 10.00\n\f\nContinued\nGrand Total 10.00"
    assert len(split_documents(text)) == 1
    same_number = "Invoice No: A-1\nPage 1\n\f\nInvoice No: A-1\nPage 2"
    assert len(split_documents(same_number)) == 1


def test_amazon_two_invoices_amount_and_gst():
    inv = parse_invoice(AMAZON_TWO_INVOICES, today=TODAY.replace(month=11, day=19))
    assert inv.total_amount == 322.0                 # 315.00 book + 7.00 COD fee
    assert (inv.cgst, inv.sgst, inv.igst) == (0.53, 0.53, 0.0)
    assert inv.gst_total() == 1.06
    assert inv.invoice_number == "XQVZ-100001"
    assert inv.invoice_date == "2026-11-07"
    assert inv.vendor == "Repro Books Limited"
    assert inv.category == "Shopping"
    assert [(d["invoice_number"], d["total_amount"], d["gst"]) for d in inv.documents] == [
        ("XQVZ-100001", 315.0, 0.0), ("POD-27-200000001", 7.0, 1.06)]
    junk = [i for i in inv.line_items if "Page" in i["description"] or i["amount"] == 123110]
    assert junk == []


def test_amazon_single_invoice_total_under_column_headings():
    first_page = AMAZON_TWO_INVOICES.split("\f")[0]
    inv = parse_invoice(first_page, today=TODAY.replace(month=11, day=19))
    assert inv.total_amount == 315.0                 # not the "1" under "Total Amount"
    assert inv.igst == 0.0 and inv.documents == []
