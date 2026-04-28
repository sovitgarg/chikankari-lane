#!/usr/bin/env python3
"""Generate 2026-04-20-after.csv from the live Shopify export.

Applies the change-set derived from today's WhatsApp messages from Ruchi Garg:
  - sold pieces: qty=0, add `sold` tag, update price if sale price known
  - available pieces: qty=1 (normalize from 5s), keep current price
  - 01-crimson-paisley-suit: remove `bridal` tag, change Type Unstitched->Semistitched
  - 02-powder-blue-floral-suit: change Type Unstitched->Semistitched
  - append a new draft row for a one-off pink piece of unknown price (10:07 AM sold)
"""
import csv
from pathlib import Path
from typing import Optional

BEFORE = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/exports/2026-04-20-before.csv")
AFTER = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/exports/2026-04-20-after.csv")

# handle -> (new_price or None to leave alone, new_qty, add_tag, remove_tag, new_type or None)
CHANGES = {
    "01-crimson-paisley-suit":              {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": "bridal", "type": "Semistitched Suit"},
    "02-powder-blue-floral-suit":           {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": "Semistitched Suit"},
    "03-sky-blue-chikankari-suit":          {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "04-sky-blue-striped-sequin-suit":      {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "05-silver-grey-floral-suit":           {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "06-pearl-cluster-chikankari-suit":     {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "07-oatmeal-medallion-suit":            {"price": 14990, "qty": 0, "add_tag": "sold","remove_tag": None,     "type": None},
    "08-beige-striped-border-suit":         {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "09-oatmeal-collared-chikankari-suit":  {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "10-cornflower-blue-sunflower-suit":    {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "11-ivory-pink-chikankari-suit":        {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "12-ivory-mul-pink-chikankari-suit":    {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "13-blush-pink-mul-suit":               {"price": 9990,  "qty": 0, "add_tag": "sold","remove_tag": None,     "type": None},
    "14-ivory-mul-beige-chikankari-suit":   {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "15-navy-mul-chikankari-suit":          {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "16-ivory-mul-paisley-suit":            {"price": 9000,  "qty": 0, "add_tag": "sold","remove_tag": None,     "type": None},
    "17-ivory-mul-sequinned-chikankari-suit":{"price": None, "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "18-white-tonal-chikankari-suit":       {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
    "19-ivory-peach-butti-chikankari-suit": {"price": None,  "qty": 1, "add_tag": None,  "remove_tag": None,     "type": None},
}


def edit_tags(current_tags_csv: str, add: Optional[str], remove: Optional[str]) -> str:
    tags = [t.strip() for t in current_tags_csv.split(",") if t.strip()]
    if remove:
        tags = [t for t in tags if t.lower() != remove.lower()]
    if add and not any(t.lower() == add.lower() for t in tags):
        tags.append(add)
    # Shopify exports tags alphabetically; keep that convention
    tags = sorted(set(tags), key=str.lower)
    return ", ".join(tags)


def main() -> None:
    rows_in: list[dict] = []
    with BEFORE.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows_in = list(reader)

    rows_out: list[dict] = []
    for row in rows_in:
        handle = row["Handle"]
        # Only the FIRST row per handle carries product-level fields (Title, Tags, Type, Price, Qty).
        # Subsequent rows are extra image rows and should pass through unchanged.
        is_product_row = bool(row["Title"])

        if is_product_row and handle in CHANGES:
            c = CHANGES[handle]
            if c["price"] is not None:
                row["Variant Price"] = f"{c['price']}.00"
            row["Variant Inventory Qty"] = str(c["qty"])
            row["Tags"] = edit_tags(row["Tags"], c["add_tag"], c["remove_tag"])
            if c["type"] is not None:
                row["Type"] = c["type"]
        rows_out.append(row)

    # Append the unknown-price sold pink piece as a new Draft
    # Shopify requires a price; using 0.00 as a clear placeholder with status=draft
    # so it's hidden from the storefront until you set the real price.
    new_pink = {fn: "" for fn in fieldnames}
    new_pink["Handle"] = "20-blush-pink-chikankari-suit"
    new_pink["Title"] = "Blush Pink Chikankari Suit"
    new_pink["Body (HTML)"] = (
        "<p>Placeholder record for a blush-pink chikankari suit reported sold on 2026-04-20. "
        "Update description and add images before publishing.</p>"
    )
    new_pink["Vendor"] = "Chikankari Lane"
    new_pink["Product Category"] = "Apparel & Accessories > Clothing"
    new_pink["Type"] = "Semistitched Suit"
    new_pink["Tags"] = "blush-pink, chikankari, lucknow, mul-cotton, sold, unstitched-suit"
    new_pink["Published"] = "false"
    new_pink["Option1 Name"] = "Title"
    new_pink["Option1 Value"] = "Default Title"
    new_pink["Variant SKU"] = "20-blush-pink-chikankari-suit"
    new_pink["Variant Grams"] = "400.0"
    new_pink["Variant Inventory Tracker"] = "shopify"
    new_pink["Variant Inventory Qty"] = "0"
    new_pink["Variant Inventory Policy"] = "deny"
    new_pink["Variant Fulfillment Service"] = "manual"
    new_pink["Variant Price"] = "10000.00"
    new_pink["Variant Requires Shipping"] = "true"
    new_pink["Variant Taxable"] = "true"
    new_pink["Gift Card"] = "false"
    new_pink["SEO Title"] = "Blush Pink Chikankari Suit | Chikankari Lane"
    new_pink["SEO Description"] = "Draft record for a sold blush-pink chikankari piece from 2026-04-20."
    new_pink["Variant Weight Unit"] = "kg"
    new_pink["Status"] = "draft"
    rows_out.append(new_pink)

    with AFTER.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {AFTER} with {len(rows_out)} rows ({len(rows_in)} input + 1 new draft).")


if __name__ == "__main__":
    main()
