"""
Generate the synthetic sample invoices in tests/samples/ and the matching
tests/ground_truth.csv.

All names, numbers and addresses are FICTIONAL (no personal data). The set
mixes the document types the spec asks for:
    digital PDFs, scanned (image-only) PDFs, phone photos (tilted, noisy,
    shadowed JPGs), app screenshots, thermal receipts, utility/phone bills
    and a handwritten-style bill.

Replace or extend these with real (blurred) invoices when you have them;
just add a row to ground_truth.csv for every new file.

Run from the project folder:  python tests/samples/make_samples.py
"""

import csv
import random
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

OUT = config.SAMPLES_DIR
FONT_DIR = Path("/usr/share/fonts/truetype")
FOOTER = "SAMPLE - synthetic test document"


def find_font(*names):
    """First available TTF file among the given names (falls back to PIL default)."""
    for name in names:
        hits = list(FONT_DIR.rglob(name)) + list(Path("C:/Windows/Fonts").glob(name))
        if hits:
            return str(hits[0])
    return None


SANS = find_font("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf")
MONO = find_font("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "cour.ttf")
SERIF_ITALIC = find_font("FreeSerifItalic.ttf", "DejaVuSerif-Italic.ttf", "LiberationSerif-Italic.ttf")


def font(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


# ======================================================================
# The samples: (file, kind, lines, truth)
# truth = invoice_number, invoice_date, invoice_time, vendor, total_amount
# ======================================================================
SAMPLES = [
    ("amazon_order.pdf", "pdf", [
        "Tax Invoice/Bill of Supply/Cash Memo",
        "(Original for Recipient)",
        "Sold By :",
        "Sunrise Retail Private Limited",
        "Plot 12, Industrial Area, Bengaluru, Karnataka, 560068",
        "PAN No: AAKCS1234M          GST Registration No: 29AAKCS1234M1Z8",
        "Order Number: 403-5512877-9912345      Order Date: 02.10.2026",
        "Invoice Number : BLR8-778812          Invoice Date : 03.10.2026",
        "Sl. Description               Unit Price  Qty  Net Amount  Tax Rate  Tax Type  Tax Amount  Total Amount",
        "1   Wireless Mouse M221        ₹508.47     1    ₹508.47     18%       IGST      ₹91.53      ₹600.00",
        "2   USB-C Cable 1m             ₹338.98     1    ₹338.98     18%       IGST      ₹61.02      ₹400.00",
        "TOTAL:                                                                         ₹152.55     ₹1,000.00",
        "Amount in Words: One Thousand only",
        "Sold on Amazon.in",
    ], ("BLR8-778812", "2026-10-03", "", "Sunrise Retail Private Limited", 1000.00)),

    ("flipkart_shoes.pdf", "pdf", [
        "Flipkart",
        "Tax Invoice",
        "Order ID: OD329981234567891000      Order Date: 14-09-2026",
        "Invoice No: FAAB2026001234           Invoice Date: 15-09-2026",
        "Seller: Kavya Fashions, Jaipur, Rajasthan",
        "GSTIN: 08ABCPK1234L1ZQ",
        "Product            Qty   Gross Amount   Discount   Taxable Value   IGST   Total",
        "Running Shoes      1     1,899.00       -200.00    1,516.96        182.04  1,699.00",
        "Shipping Charges   1     40.00          0.00       35.71           4.29    40.00",
        "Grand Total                                                               ₹ 1,739.00",
    ], ("FAAB2026001234", "2026-09-15", "", "Kavya Fashions", 1739.00)),

    ("swiggy_dinner.pdf", "pdf", [
        "SWIGGY",
        "Bundl Technologies Private Limited",
        "Order ID: 172233445566",
        "Order placed at 21 Sep 2026, 08:42 PM",
        "Restaurant: Meghana Foods, Koramangala",
        "Chicken Biryani x 1          ₹ 340.00",
        "Paneer Tikka x 1             ₹ 260.00",
        "Item Total                   ₹ 600.00",
        "Delivery partner fee         ₹ 35.00",
        "Platform fee                 ₹ 5.00",
        "Taxes                        ₹ 30.00",
        "Total Discount               -₹ 120.00",
        "Grand Total                  ₹ 550.00",
    ], ("172233445566", "2026-09-21", "20:42", "Swiggy", 550.00)),

    ("zomato_lunch.png", "screenshot", [
        "zomato",
        "Order #7781234560",
        "Delivered from Empire Restaurant",
        "Ordered on Oct 05, 2026 at 1:15 PM",
        "Ghee Rice x 2            Rs 180.00",
        "Kebab x 1                Rs 210.00",
        "Item total               Rs 390.00",
        "Taxes & charges          Rs 39.50",
        "Delivery                 Rs 25.00",
        "Bill Total               Rs 454.50",
        "Paid via UPI",
    ], ("7781234560", "2026-10-05", "13:15", "Zomato", 454.50)),

    ("bescom_electricity.pdf", "pdf", [
        "BANGALORE ELECTRICITY SUPPLY COMPANY LIMITED",
        "BESCOM",
        "Electricity Bill",
        "Bill No: 2610051234            Bill Date: 05/10/2026",
        "Account ID: 9876501234   Tariff: LT2a",
        "Billing Period From: 01/09/2026 To: 30/09/2026",
        "Units Consumed: 214",
        "Energy Charges        1,412.00",
        "Fixed Charges           220.00",
        "Tax                     148.00",
        "Net Amount Payable  Rs. 1,780.00",
        "Due Date: 20/10/2026",
    ], ("2610051234", "2026-10-05", "", "BESCOM", 1780.00)),

    ("airtel_postpaid.pdf", "pdf", [
        "airtel",
        "Bharti Airtel Limited",
        "Postpaid Bill",
        "Invoice No: AP0926778812        Bill Date: 28 September 2026",
        "Bill Period: 28 Aug 2026 to 27 Sep 2026",
        "Plan: Postpaid 499",
        "Monthly Rental              499.00",
        "Usage Charges                 0.00",
        "Sub Total                   499.00",
        "CGST @ 9%                    44.91",
        "SGST @ 9%                    44.91",
        "Amount Payable          Rs. 588.82",
        "Pay by: 15 October 2026",
    ], ("AP0926778812", "2026-09-28", "", "Airtel", 588.82)),

    ("jio_recharge.png", "screenshot", [
        "Jio",
        "Recharge Successful",
        "Transaction ID: JR20261012345",
        "Date: 12/10/2026 Time: 09:05:44",
        "Plan: Rs 299 - 28 days",
        "Amount Paid: Rs. 299.00",
        "Reliance Jio Infocomm Ltd",
    ], ("", "2026-10-12", "09:05:44", "Jio", 299.00)),

    ("annapoorna_photo.jpg", "photo", [
        "HOTEL ANNAPOORNA",
        "Pure Veg Restaurant, Gandhipuram",
        "GSTIN: 33AABFH1234Q1Z2",
        "Bill No: 1187       Table: 4",
        "Date: 30/09/2026    Time: 1:45 PM",
        "Idli (2)          2    60.00",
        "Masala Dosa       1    90.00",
        "Filter Coffee     2    50.00",
        "Sub Total             200.00",
        "CGST 2.5%               5.00",
        "SGST 2.5%               5.00",
        "Total Rs.             210.00",
        "Thank you! Visit again",
    ], ("1187", "2026-09-30", "13:45", "Hotel Annapoorna", 210.00)),

    ("brew_corner_receipt.png", "receipt", [
        "BREW CORNER CAFE",
        "MG Road, Pune",
        "GSTIN 27AAKFB4321C1ZP",
        "Receipt No: BC-20456",
        "18-Oct-2026 17:32",
        "Cappuccino      1  180.00",
        "Croissant       1  120.00",
        "Subtotal           300.00",
        "CGST 2.5%            7.50",
        "SGST 2.5%            7.50",
        "TOTAL           Rs 315.00",
        "Cash            Rs 500.00",
        "Change          Rs 185.00",
    ], ("BC-20456", "2026-10-18", "17:32", "Brew Corner Cafe", 315.00)),

    ("sai_medicals_photo.jpg", "photo", [
        "SRI SAI MEDICALS",
        "Chemist & Druggist, Anna Nagar",
        "D.L. No: TN-02-20B-1234",
        "Bill No. SSM/2611",
        "Date: 07/10/2026",
        "Paracetamol 500 1 strip    30.00",
        "Vitamin C tabs  1 strip    85.00",
        "Cough syrup     1          110.00",
        "Net Amount           225.00",
        "Get well soon",
    ], ("SSM/2611", "2026-10-07", "", "Sri Sai Medicals", 225.00)),

    ("ganesh_hardware_scan.pdf", "scan", [
        "GANESH HARDWARE",
        "Station Road, Nashik",
        "GSTIN: 27AFKPG5678H1ZD",
        "TAX INVOICE",
        "Invoice No: GH-0921        Date: 11/09/2026",
        "PVC Pipe 1 inch    10   45.00    450.00",
        "Elbow joint        20    8.00    160.00",
        "Taxable Value                    610.00",
        "CGST 9%                           54.90",
        "SGST 9%                           54.90",
        "Grand Total                      719.80",
    ], ("GH-0921", "2026-09-11", "", "Ganesh Hardware", 719.80)),

    ("lakshmi_stores_handwritten.jpg", "handwritten", [
        "Lakshmi Stores",
        "Bill No 342",
        "Date 25/09/2026",
        "Rice 5kg       320",
        "Dal 1kg        140",
        "Oil 1L         165",
        "Total          625",
    ], ("342", "2026-09-25", "", "Lakshmi Stores", 625.00)),

    ("uber_trip.pdf", "pdf", [
        "Uber",
        "Thanks for riding, here is your receipt",
        "Trip on 16 October 2026",
        "Pickup 07:48 AM  -  Indiranagar",
        "Drop   08:21 AM  -  Electronic City",
        "Trip fare                 ₹ 412.36",
        "Booking fee               ₹ 20.00",
        "Total                     ₹ 432.36",
        "Invoice No: UBR-IN-55102938",
    ], ("UBR-IN-55102938", "2026-10-16", "07:48", "Uber", 432.36)),

    ("bigbasket_grocery.pdf", "pdf", [
        "bigbasket",
        "Supermarket Grocery Supplies Pvt Ltd",
        "TAX INVOICE",
        "Invoice No: BB/KA/26/0098812",
        "Order No: 1029384756",
        "Invoice Date: 2026-10-09",
        "Tomato 1 kg          1    38.00",
        "Milk 1 L             2   108.00",
        "Atta 5 kg            1   265.00",
        "Total Items: 4",
        "Total Savings: 22.00",
        "Total Amount            ₹ 411.00",
    ], ("BB/KA/26/0098812", "2026-10-09", "", "BigBasket", 411.00)),

    ("city_fuels_receipt.png", "receipt", [
        "CITY FUELS",
        "Indian Oil Dealer",
        "Ring Road, Hyderabad",
        "Receipt No: 558812",
        "Date: 19/10/2026",
        "Time: 18:04",
        "Product: Petrol",
        "Rate: 107.41 Rs/L",
        "Volume: 18.62 L",
        "Amount: Rs. 2000.00",
        "Total Rs. 2000.00",
        "Thank you",
    ], ("558812", "2026-10-19", "18:04", "City Fuels", 2000.00)),

    ("paper_plus_invoice.pdf", "pdf", [
        "PAPER PLUS STATIONERS",
        "12 Brigade Road, Bengaluru 560001",
        "GSTIN: 29AAGFP7788K1ZS",
        "TAX INVOICE",
        "Invoice No: PPS/2026/0457",
        "Dated: 22 Aug 2026",
        "Bill To: Acme College Department of CSE, Chennai",
        "A4 Paper Ream       10    260.00    2,600.00",
        "Whiteboard Markers  24     35.00      840.00",
        "Sub Total                            3,440.00",
        "IGST @ 18%                             619.20",
        "Grand Total                      Rs. 4,059.20",
        "Amount in words: Four Thousand Fifty Nine and Twenty Paise only",
    ], ("PPS/2026/0457", "2026-08-22", "", "Paper Plus Stationers", 4059.20)),

    ("rangoli_textiles_scan.pdf", "scan", [
        "RANGOLI TEXTILES",
        "Chickpet, Bengaluru",
        "GSTIN 29AAHFR3344M1ZT",
        "Tax Invoice No: RT-7781",
        "Invoice Date: 03-08-2026",
        "Cotton Saree     2   1,250.00   2,500.00",
        "Silk Dupatta     1     850.00     850.00",
        "Taxable Amount                   3,350.00",
        "CGST 2.5%                           83.75",
        "SGST 2.5%                           83.75",
        "Amount Payable                Rs 3,517.50",
    ], ("RT-7781", "2026-08-03", "", "Rangoli Textiles", 3517.50)),

    ("zepto_order.pdf", "pdf", [
        "zepto",
        "Kiranakart Technologies Pvt Ltd",
        "Invoice Number: ZP26KA00451122",
        "Order No: 20261020-88123",
        "Order Date: 20/10/2026 10:12 PM",
        "Bananas 6 pcs        1    54.00",
        "Bread                1    45.00",
        "Handling charge           9.00",
        "Total Payable         ₹ 108.00",
    ], ("ZP26KA00451122", "2026-10-20", "22:12", "Zepto", 108.00)),
]


# ======================================================================
# Writers
# ======================================================================
def write_pdf(path, lines):
    """Digital PDF with a real text layer."""
    doc = pymupdf.open()
    page = doc.new_page(width=842 if max(map(len, lines)) > 90 else 595, height=842)
    y = 60
    for line in lines + ["", FOOTER]:
        page.insert_text((40, y), line, fontsize=9.5, fontname="dj", fontfile=SANS)
        y += 17
    doc.subset_fonts()          # keep only the used glyphs -> small files
    doc.save(path, garbage=4, deflate=True)
    doc.close()


def draw_lines(lines, size=28, width=1100, mono=False, padding=50, gap=1.6):
    """Render lines of text onto a white image (PIL)."""
    fnt = font(MONO if mono else SANS, size)
    height = int(padding * 2 + len(lines) * size * gap)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((padding, padding + i * size * gap), line, fill=(20, 20, 20), font=fnt)
    return img


def photo_effects(img, angle, seed):
    """Make a clean render look like a phone photo: tilt, shadow, blur, noise."""
    rng = np.random.default_rng(seed)
    img = img.rotate(angle, expand=True, fillcolor=(235, 230, 220), resample=Image.BICUBIC)
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    shadow = np.linspace(1.0, 0.72, w)[None, :, None] * np.linspace(0.95, 1.0, h)[:, None, None]
    arr = arr * shadow * np.array([1.0, 0.97, 0.9])          # warm indoor light
    arr += rng.normal(0, 9, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return img.filter(ImageFilter.GaussianBlur(0.7))


def handwritten(lines, seed=7):
    """Approximate handwriting: italic serif, jittered size/position/angle, blue ink."""
    rnd = random.Random(seed)
    img = Image.new("RGB", (1000, 120 + 85 * len(lines)), (250, 248, 240))
    for row in range(len(lines) + 1):                           # ruled notebook lines
        ImageDraw.Draw(img).line([(0, 115 + row * 85), (1000, 115 + row * 85)], fill=(190, 205, 230), width=2)
    x0 = 70
    for i, line in enumerate(lines):
        x, y = x0 + rnd.randint(-8, 8), 50 + i * 85
        for ch in line:
            size = rnd.randint(40, 46)
            glyph = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(glyph).text((size // 2, size // 3), ch, font=font(SERIF_ITALIC, size),
                                       fill=(25, 40, 120, 255))
            glyph = glyph.rotate(rnd.uniform(-6, 6), resample=Image.BICUBIC)
            img.paste(glyph, (int(x) - size // 2, y + rnd.randint(-3, 3) - size // 3), glyph)
            x += font(SERIF_ITALIC, size).getlength(ch) + rnd.uniform(-0.5, 1.5)
    return photo_effects(img, 1.5, seed)


def write_scanned_pdf(path, lines, seed):
    """A PDF that only contains a (slightly tilted, noisy) picture of the page."""
    img = draw_lines(lines + ["", FOOTER], size=30, width=1240, padding=80)
    page_img = Image.new("RGB", (1240, 1754), "white")
    page_img.paste(img, (0, 0))
    page_img = photo_effects(page_img, -1.2, seed).convert("L")
    tmp = path.with_suffix(".tmp.jpg")
    page_img.save(tmp, quality=75)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(tmp))
    doc.save(path)
    doc.close()
    tmp.unlink()


def build(file, kind, lines, seed):
    path = OUT / file
    if kind == "pdf":
        write_pdf(path, lines)
    elif kind == "scan":
        write_scanned_pdf(path, lines, seed)
    elif kind == "screenshot":
        draw_lines(lines + ["", FOOTER], size=30, width=900).save(path)
    elif kind == "receipt":
        draw_lines(lines + ["", FOOTER], size=22, width=560, mono=True, padding=30, gap=1.5).save(path)
    elif kind == "photo":
        img = draw_lines(lines + ["", FOOTER], size=30, width=1000)
        photo_effects(img, 3.5 if seed % 2 else -2.5, seed).save(path, quality=80)
    elif kind == "handwritten":
        handwritten(lines + [FOOTER[:6]], seed).save(path, quality=85)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for seed, (file, kind, lines, truth) in enumerate(SAMPLES, start=1):
        build(file, kind, lines, seed)
        number, inv_date, inv_time, vendor, total = truth
        rows.append({"file": file, "invoice_number": number, "invoice_date": inv_date,
                     "invoice_time": inv_time, "vendor": vendor, "total_amount": f"{total:.2f}"})
        print(f"wrote {file} ({kind})")
    with open(config.GROUND_TRUTH_FILE, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {config.GROUND_TRUTH_FILE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
