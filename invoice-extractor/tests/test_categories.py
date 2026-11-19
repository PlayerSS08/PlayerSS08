"""Tests for extractor/categories.py."""

import pytest

from extractor.categories import OTHER, categorize, category_names


@pytest.mark.parametrize("vendor, text, expected", [
    ("Swiggy", "", ("Food & Dining", 0.9)),
    ("BESCOM", "", ("Utilities", 0.9)),
    ("Hotel Annapoorna", "Masala Dosa 90.00\nFilter Coffee 50", ("Food & Dining", 0.6)),
    ("City Fuels", "Product: Petrol\nVolume 18 L", ("Fuel", 0.6)),
    ("Sri Sai Medicals", "Chemist\nCough syrup", ("Health", 0.6)),
    ("Acme Pvt Ltd", "Consulting services", (OTHER, 0.3)),
    (None, "", (OTHER, 0.3)),
])
def test_categorize(vendor, text, expected):
    assert categorize(vendor, text) == expected


def test_category_names_end_with_other():
    names = category_names()
    assert names[-1] == OTHER and "Groceries" in names
