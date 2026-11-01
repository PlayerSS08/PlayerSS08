"""
Expense category tagging (Food & Dining, Groceries, Travel, ...).

Rules, in order:
  1. the vendor is a known vendor of a category       -> confidence 0.9
  2. category keywords found in the invoice text       -> confidence 0.6
     (the category with the most keyword hits wins)
  3. nothing matched                                   -> "Other", 0.3

Categories and their words live in categories.json so they are easy to edit.
`categorize()` is pure apart from reading that file once.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

CATEGORIES_FILE = Path(__file__).resolve().parent / "categories.json"
OTHER = "Other"


@lru_cache(maxsize=1)
def load_categories(path: str = str(CATEGORIES_FILE)) -> dict:
    """{category: {"vendors": [...], "keywords": [...]}} from categories.json."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return {name: rules for name, rules in data.items() if not name.startswith("_")}


def category_names() -> list:
    """All category names, plus 'Other' at the end."""
    return list(load_categories()) + [OTHER]


def categorize(vendor: Optional[str], text: str = "", categories: Optional[dict] = None) -> tuple:
    """Return (category, confidence) for an invoice."""
    categories = load_categories() if categories is None else categories
    if vendor:
        for name, rules in categories.items():
            if any(v.lower() == vendor.lower() or v.lower() in vendor.lower()
                   for v in rules.get("vendors", [])):
                return name, 0.9
    haystack = f"{vendor or ''}\n{text}".lower()
    scores = {}
    for name, rules in categories.items():
        hits = sum(1 for word in rules.get("keywords", [])
                   if re.search(r"(?<![a-z])" + re.escape(word.lower()) + r"(?![a-z])", haystack))
        if hits:
            scores[name] = hits
    if scores:
        return max(scores, key=scores.get), 0.6
    return OTHER, 0.3
