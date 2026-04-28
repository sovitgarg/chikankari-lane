#!/usr/bin/env python3
"""Set Min Sell Price (no-loss floor) on all 16 Zoho items.

Min Sell formula:
    Min Sell = (Cost + Variable + Fixed_per_piece) / (1 - payment_fee_rate)

Where:
    - Cost           = per-piece purchase cost from 04-sku-to-cost-mapping.csv
    - Variable       = ₹280 (₹100 packaging + ₹180 shipping average)
    - Fixed_per_piece = ₹1,76,052 / (30 pieces/month × 12) = ₹489
    - payment_fee_rate = 0.02 (Razorpay)

Reference Target = Min Sell × 1.30 (30% on top of no-loss floor) — only printed,
NOT pushed anywhere. Selling prices on Shopify and Zoho `rate` are left untouched
per user instruction (first-lot pricing was well-received).

Steps:
    1. Try to create custom field `cf_min_sell_price` via API. If unsupported,
       print exact UI steps and bail before writes.
    2. PUT each of 16 items with `cf_min_sell_price` = computed Min Sell (rounded to 10).
"""
import csv
from pathlib import Path
from collections import defaultdict
from zoho_books_api import ZohoBooks
from pricing import (
    VARIABLE_PER_PIECE, ANNUAL_FIXED_COST, PIECES_PER_MONTH, PIECES_PER_YEAR,
    FIXED_PER_PIECE, PAYMENT_FEE_RATE, DEFAULT_MARKUP,
    no_loss_sell_price, target_sell_price, real_margin_pct,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPPING_CSV = REPO_ROOT / "zoho-import" / "04-sku-to-cost-mapping.csv"

# Aliases for local readability (assumptions live in pricing.py)
PAYMENT_FEE = PAYMENT_FEE_RATE
MARGIN_REFERENCE = DEFAULT_MARKUP

CUSTOM_FIELD_LABEL = "Min Sell Price"
CUSTOM_FIELD_API_NAME = "cf_min_sell_price"


def ensure_custom_field(zb: ZohoBooks) -> bool:
    """Try to create the Item-level custom field. Return True if available, False otherwise.

    Zoho's documented endpoint for item custom fields is not stable across editions.
    We probe by reading one item and checking if `custom_fields` already contains
    our field. If not, we attempt POST /settings/preferences/customfields and
    fall back to UI instructions on failure.
    """
    # Probe: fetch any one item, look for the field in custom_fields
    data = zb._request("GET", "/items", params={"per_page": 1})
    items = data.get("items", [])
    if items:
        item_id = items[0]["item_id"]
        item = zb._request("GET", f"/items/{item_id}")["item"]
        cfs = item.get("custom_fields", []) or []
        for cf in cfs:
            if cf.get("api_name") == CUSTOM_FIELD_API_NAME or \
               cf.get("label", "").strip().lower() == CUSTOM_FIELD_LABEL.lower():
                print(f"  ✓ custom field '{CUSTOM_FIELD_LABEL}' already exists "
                       f"(api_name={cf.get('api_name')})")
                return True

    # Try to create via API (undocumented endpoint, may 404)
    print(f"  [info] Custom field not found. Attempting API creation...")
    body = {
        "label": CUSTOM_FIELD_LABEL,
        "api_name": CUSTOM_FIELD_API_NAME,
        "data_type": "amount",
        "entity": "item",
        "is_mandatory": False,
        "show_in_pdf": False,
        "show_on_pdf": False,
        "show_in_all_pdf": False,
        "is_active": True,
    }
    try:
        zb._request("POST", "/settings/preferences/customfields", json_body=body)
        print(f"  ✓ created custom field '{CUSTOM_FIELD_LABEL}' via API")
        return True
    except Exception as e:
        msg = str(e).lower()
        # If Zoho says it already exists, that's success — the probe just missed it
        # (item.custom_fields can be empty when no values are set yet).
        if "already exists" in msg or "120106" in msg:
            print(f"  ✓ custom field '{CUSTOM_FIELD_LABEL}' already exists (per Zoho)")
            return True
        print(f"\n  ✗ API creation failed: {e}")
        print(f"\n  [action required] Please create the custom field manually in Zoho UI:")
        print(f"    1. Open Zoho Books → Settings (gear icon) → Customization → Custom Fields")
        print(f"    2. Click 'Items' tab → '+ New Custom Field'")
        print(f"    3. Label: {CUSTOM_FIELD_LABEL}")
        print(f"    4. Data Type: Currency (Amount)")
        print(f"    5. Save, then re-run this script.")
        return False


def main() -> int:
    zb = ZohoBooks()
    zb.verify_org()

    print(f"\n=== Pricing model ===")
    print(f"  Variable per piece:   ₹{VARIABLE_PER_PIECE:,.0f}")
    print(f"  Annual fixed cost:    ₹{ANNUAL_FIXED_COST:,.0f}")
    print(f"  Volume:               {PIECES_PER_MONTH}/mo × 12 = {PIECES_PER_YEAR}/yr")
    print(f"  Fixed per piece:      ₹{FIXED_PER_PIECE:,.2f}")
    print(f"  Payment fee:          {PAYMENT_FEE*100:.0f}%")
    print(f"  Reference markup:     +{MARGIN_REFERENCE*100:.0f}% on top of no-loss")

    print(f"\n=== Step 1: Ensure custom field exists ===")
    if not ensure_custom_field(zb):
        return 1

    print(f"\n=== Step 2: Compute & write Min Sell Price for all 16 items ===\n")
    print(f"  {'SKU':50s} {'Cost':>7s} {'Shopify':>8s} {'MinSell':>8s} {'Ref+30%':>8s} {'Margin%':>8s}")
    print(f"  {'-'*50} {'-'*7} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    stats = defaultdict(int)
    rows_for_print = []

    with MAPPING_CSV.open() as f:
        reader = list(csv.DictReader(f))

    for row in reader:
        sku = row["Shopify Handle"]
        name = row["Shopify Title"]
        cost = float(row["Cost Price"])
        shopify_price = float(row["Selling Price"])

        min_sell = no_loss_sell_price(cost)
        ref_target = target_sell_price(cost, markup=MARGIN_REFERENCE)
        margin_pct = real_margin_pct(cost, shopify_price)

        rows_for_print.append((sku, cost, shopify_price, min_sell, ref_target, margin_pct))

        item = zb.find_item_by_sku(sku)
        if not item:
            print(f"  ✗ NOT FOUND  {sku}")
            stats["not-found"] += 1
            continue

        body = {
            "custom_fields": [
                {"api_name": CUSTOM_FIELD_API_NAME, "value": min_sell}
            ]
        }
        try:
            zb._request("PUT", f"/items/{item['item_id']}", json_body=body)
            stats["updated"] += 1
            mark = "✓"
        except Exception as e:
            print(f"  ✗ FAILED {sku}: {e}")
            stats["failed"] += 1
            mark = "✗"

        print(f"  {mark} {sku:48s} ₹{cost:>6,.0f} ₹{shopify_price:>7,.0f} "
              f"₹{min_sell:>7,.0f} ₹{ref_target:>7,.0f} {margin_pct:>7.1f}%")

    print(f"\n  stats: {dict(stats)}")
    print(f"\n  Note: Shopify selling prices and Zoho `rate` were NOT modified")
    print(f"        (per user: first-lot pricing well-received, keep same strategy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
