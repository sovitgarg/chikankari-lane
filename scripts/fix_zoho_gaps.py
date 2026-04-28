#!/usr/bin/env python3
"""One-shot fixes for the gaps found in Zoho:
1. Mark the Lucknow Market bill (₹10,500) as paid
2. Create all 16 items in Zoho with cost (since Shopify->Zoho item sync isn't running)

Reads zoho-import/04-sku-to-cost-mapping.csv (has both selling price + cost).
"""
import csv
from pathlib import Path
from collections import defaultdict
from zoho_books_api import ZohoBooks

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_CSV = REPO_ROOT / "zoho-import" / "04-sku-to-cost-mapping.csv"


def main():
    zb = ZohoBooks()
    zb.verify_org()

    print("\n=== Step 1: Mark Lucknow Market bill paid ===")
    lucknow_vendor = zb.find_vendor("Lucknow Market - Cash Purchase")
    bill = zb.find_bill(lucknow_vendor["contact_id"], "2026-04-22")
    if not bill:
        print("  ✗ Lucknow Market bill not found — skipping")
    elif bill.get("status", "").lower() == "paid":
        print(f"  ✓ already paid (id={bill['bill_id']})")
    else:
        try:
            zb.mark_bill_paid(bill["bill_id"], 10500.0, "2026-04-22", "cash")
            print(f"  ✓ marked paid (id={bill['bill_id']}, status was {bill.get('status')})")
        except Exception as e:
            print(f"  ✗ payment failed: {e}")

    print("\n=== Step 2: Create/update all 16 items with cost ===")
    stats = defaultdict(int)
    with MAPPING_CSV.open() as f:
        for row in csv.DictReader(f):
            sku = row["Shopify Handle"]
            name = row["Shopify Title"]
            rate = float(row["Selling Price"])
            cost = float(row["Cost Price"])
            try:
                item, action = zb.upsert_item_full(sku, name, rate, cost)
                print(f"  {action:25s} {sku:50s} sell ₹{rate:>6,.0f} cost ₹{cost:>6,.0f} (id={item['item_id']})")
                stats[action] += 1
            except Exception as e:
                print(f"  ✗ FAILED {sku}: {e}")
                stats["failed"] += 1
    print(f"\n  stats: {dict(stats)}")


if __name__ == "__main__":
    main()
