#!/usr/bin/env python3
"""Regenerate PRODUCT.md inside each product folder, matching the current CSV."""
import csv
from pathlib import Path

CSV_PATH = Path("/Users/sovitgarg/Downloads/Chikankari Lane/chikankari-lane-products.csv")
ROOT = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/products")

with CSV_PATH.open() as f:
    rows = list(csv.DictReader(f))

for row in rows:
    handle = row["Handle"]
    folder = ROOT / handle
    if not folder.exists():
        print(f"WARN: missing {folder}")
        continue
    images = sorted(folder.glob("*.jpg"))
    md = [
        f"# {row['Title']}",
        "",
        f"**Type:** {row['Type']}",
        f"**Tags:** {row['Tags']}",
        f"**Price:** ₹{row['Variant Price'].split('.')[0]}",
        f"**SKU:** {row['Variant SKU']}",
        f"**Inventory:** {row['Variant Inventory Qty']}",
        "",
        "## Description (rendered HTML)",
        "",
        row["Body (HTML)"],
        "",
        "## Images (drag these into Shopify Media in order)",
        "",
    ] + [f"- `{img.name}`" for img in images]
    (folder / "PRODUCT.md").write_text("\n".join(md))
    print(f"Wrote {folder.name}/PRODUCT.md ({len(images)} images)")
