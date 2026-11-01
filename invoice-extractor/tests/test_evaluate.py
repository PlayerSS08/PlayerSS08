"""Regression guard: accuracy on the sample set must not drop."""

import pytest

from extractor import ocr
from scripts.evaluate import evaluate, field_matches, format_table


@pytest.mark.parametrize("field, expected, actual, ok", [
    ("total_amount", "100.00", 100.004, True),
    ("total_amount", "100.00", 100.02, False),
    ("vendor", "Swiggy", "SWIGGY Bundl", True),
    ("invoice_date", "2026-10-01", "2026-10-01", True),
    ("invoice_number", "abc-1", "ABC-1", True),
    ("vendor", "Swiggy", None, False),
])
def test_field_matches(field, expected, actual, ok):
    assert field_matches(field, expected, actual) is ok


@pytest.mark.skipif(not ocr.ocr_available(), reason="sample set includes images that need OCR")
def test_sample_accuracy():
    scores, _mismatches = evaluate()
    for field, (correct, total) in scores.items():
        assert total > 0
        assert correct / total >= 0.85, format_table(scores)
