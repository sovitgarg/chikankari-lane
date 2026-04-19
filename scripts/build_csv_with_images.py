#!/usr/bin/env python3
"""Build a Shopify-import-ready CSV that adds image URLs to existing products.

Shopify CSV import rules we rely on:
- First row per Handle carries full product data (title, price, etc.).
- Subsequent rows with the same Handle and only Image Src/Position filled append additional images.
- Importing a CSV where the Handle already exists UPDATES the product (adds images, does not duplicate).
- Skipping product 19 (-ivory-peach-butti-chikankari-suit) since it already has images.
"""
import csv
from pathlib import Path

SRC_CSV = Path("/Users/sovitgarg/Downloads/Chikankari Lane/chikankari-lane-products.csv")
PRODUCTS_DIR = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/products")
OUT_CSV = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/shopify_import_with_images.csv")

RAW_BASE = "https://raw.githubusercontent.com/sovitgarg/chikankari-lane/main/catalog/products"
SKIP_HANDLE = "19-ivory-peach-butti-chikankari-suit"

with SRC_CSV.open(newline='') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    src_rows = list(reader)

# Keep only the first row per handle (product-defining rows have Title set).
first_rows = {}
for r in src_rows:
    h = r.get("Handle", "").strip()
    if h and h not in first_rows and r.get("Title", "").strip():
        first_rows[h] = r

out_rows = []
for handle, prod in first_rows.items():
    folder = PRODUCTS_DIR / handle
    if not folder.is_dir():
        print(f"  [warn] no folder for {handle}")
        out_rows.append(prod)
        continue

    jpgs = sorted(p.name for p in folder.glob("*.jpg"))
    if not jpgs:
        print(f"  [warn] no jpgs for {handle}")
        out_rows.append(prod)
        continue

    if handle == SKIP_HANDLE:
        print(f"  [skip] {handle} already has images in Shopify")
        # Emit the product row but WITHOUT image columns so import doesn't touch its images
        clean = {k: v for k, v in prod.items()}
        clean["Image Src"] = ""
        clean["Image Position"] = ""
        clean["Image Alt Text"] = ""
        out_rows.append(clean)
        continue

    # First row: full product data + image 1
    first = {k: v for k, v in prod.items()}
    first["Image Src"] = f"{RAW_BASE}/{handle}/{jpgs[0]}"
    first["Image Position"] = "1"
    first["Image Alt Text"] = f"{prod.get('Title', '').strip()} — image 1"
    out_rows.append(first)

    # Subsequent rows: just Handle + image columns
    for idx, name in enumerate(jpgs[1:], start=2):
        extra = {k: "" for k in fieldnames}
        extra["Handle"] = handle
        extra["Image Src"] = f"{RAW_BASE}/{handle}/{name}"
        extra["Image Position"] = str(idx)
        extra["Image Alt Text"] = f"{prod.get('Title', '').strip()} — image {idx}"
        out_rows.append(extra)

    print(f"  [ok] {handle}: {len(jpgs)} images")

with OUT_CSV.open("w", newline='') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(out_rows)

print(f"\nWrote {OUT_CSV} ({len(out_rows)} rows, {len(first_rows)} products)")
