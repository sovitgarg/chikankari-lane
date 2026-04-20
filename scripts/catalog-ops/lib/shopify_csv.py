"""Shopify product CSV helpers.

The Shopify product export/import CSV has a wide, stable schema. Many columns
are only populated on the FIRST row of a given handle (the "product row");
subsequent rows for the same handle are image-extension rows and leave the
product-level columns blank. This module preserves that shape when reading and
writing so the output round-trips back into Shopify cleanly.
"""
from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, List, Optional


# Canonical column order matches a real Shopify export (2026-era admin).
# Any other columns found in an input CSV are passed through untouched.
CANONICAL_FIELDS: List[str] = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Product Category",
    "Type",
    "Tags",
    "Published",
    "Option1 Name", "Option1 Value", "Option1 Linked To",
    "Option2 Name", "Option2 Value", "Option2 Linked To",
    "Option3 Name", "Option3 Value", "Option3 Linked To",
    "Variant SKU",
    "Variant Grams",
    "Variant Inventory Tracker",
    "Variant Inventory Qty",
    "Variant Inventory Policy",
    "Variant Fulfillment Service",
    "Variant Price",
    "Variant Compare At Price",
    "Variant Requires Shipping",
    "Variant Taxable",
    "Unit Price Total Measure", "Unit Price Total Measure Unit",
    "Unit Price Base Measure", "Unit Price Base Measure Unit",
    "Variant Barcode",
    "Image Src",
    "Image Position",
    "Image Alt Text",
    "Gift Card",
    "SEO Title",
    "SEO Description",
    "Variant Image",
    "Variant Weight Unit",
    "Variant Tax Code",
    "Cost per item",
    "Status",
]


def read_rows(path: Path) -> tuple[List[OrderedDict], List[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = [OrderedDict((fn, r.get(fn, "")) for fn in fieldnames) for r in reader]
    return rows, fieldnames


def write_rows(path: Path, rows: Iterable[OrderedDict], fieldnames: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def is_product_row(row: OrderedDict) -> bool:
    """First row of a handle has product-level fields populated."""
    return bool(row.get("Title", "").strip())


def iter_handles(rows: Iterable[OrderedDict]) -> Iterable[str]:
    seen = set()
    for r in rows:
        h = r.get("Handle", "")
        if h and h not in seen:
            seen.add(h)
            yield h


def normalize_tags(tag_csv: str, add: Optional[Iterable[str]] = None,
                   remove: Optional[Iterable[str]] = None) -> str:
    tags = [t.strip() for t in tag_csv.split(",") if t.strip()]
    if remove:
        lowered_remove = {r.lower() for r in remove}
        tags = [t for t in tags if t.lower() not in lowered_remove]
    if add:
        existing_lower = {t.lower() for t in tags}
        for a in add:
            if a.lower() not in existing_lower:
                tags.append(a)
                existing_lower.add(a.lower())
    return ", ".join(sorted(set(tags), key=str.lower))


def empty_row(fieldnames: List[str]) -> OrderedDict:
    return OrderedDict((fn, "") for fn in fieldnames)


def format_price(rupees: float) -> str:
    """Shopify expects '12345.00' — two decimals, no thousands separator."""
    return f"{float(rupees):.2f}"
