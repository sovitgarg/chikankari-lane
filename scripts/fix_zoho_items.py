#!/usr/bin/env python3
"""Update existing Zoho items by NAME with cost + SKU.

The Shopify->Zoho integration creates items in Zoho with the product
name but doesn't populate the SKU field, so find_item_by_sku() returns
empty. This script:
  1. Lists ALL items in Zoho (paginated)
  2. For each row in 04-sku-to-cost-mapping.csv, finds the matching item
     by name, then updates: sku + purchase_rate + rate
"""
import csv
from pathlib import Path
from collections import defaultdict
from zoho_books_api import ZohoBooks

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_CSV = REPO_ROOT / "zoho-import" / "04-sku-to-cost-mapping.csv"


def list_all_items(zb):
    """Page through all items in Zoho."""
    items = []
    page = 1
    while True:
        data = zb._request("GET", "/items", params={"page": page, "per_page": 200})
        batch = data.get("items", [])
        items.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    return items


def main():
    zb = ZohoBooks()
    zb.verify_org()

    print("\nFetching all items from Zoho...")
    all_items = list_all_items(zb)
    print(f"  Found {len(all_items)} items in Zoho")

    # Build name -> item lookup (case-insensitive)
    by_name = {i.get("name", "").strip().lower(): i for i in all_items}
    by_sku = {i.get("sku", "").strip().lower(): i for i in all_items if i.get("sku")}

    print(f"  {sum(1 for i in all_items if i.get('sku'))} have SKU set")
    print(f"  {sum(1 for i in all_items if i.get('purchase_rate'))} have purchase_rate set\n")

    print("=== Updating items with cost + SKU ===")
    stats = defaultdict(int)
    with MAPPING_CSV.open() as f:
        for row in csv.DictReader(f):
            sku = row["Shopify Handle"]
            name = row["Shopify Title"]
            rate = float(row["Selling Price"])
            cost = float(row["Cost Price"])

            # Try SKU first, then name
            item = by_sku.get(sku.lower()) or by_name.get(name.lower())
            if not item:
                print(f"  ✗ NOT FOUND  {name} (sku={sku})")
                stats["not-found"] += 1
                continue

            current_sku = item.get("sku", "")
            current_cost = float(item.get("purchase_rate", 0) or 0)
            current_rate = float(item.get("rate", 0) or 0)

            body = {}
            changes = []
            if current_sku.strip().lower() != sku.strip().lower():
                body["sku"] = sku
                changes.append(f"sku:{current_sku!r}->{sku!r}")
            if abs(current_cost - cost) > 0.5:
                body["purchase_rate"] = cost
                changes.append(f"cost:{current_cost:.0f}->{cost:.0f}")
            if abs(current_rate - rate) > 0.5:
                body["rate"] = rate
                changes.append(f"rate:{current_rate:.0f}->{rate:.0f}")

            if not body:
                print(f"  ✓ unchanged  {name:50s} (sku={sku}, cost ₹{cost:,.0f})")
                stats["unchanged"] += 1
                continue

            try:
                data = zb._request("PUT", f"/items/{item['item_id']}", json_body=body)
                print(f"  ✓ updated    {name:50s} {', '.join(changes)}")
                stats["updated"] += 1
            except Exception as e:
                print(f"  ✗ FAILED     {name}: {e}")
                stats["failed"] += 1

    print(f"\nstats: {dict(stats)}")


if __name__ == "__main__":
    main()
