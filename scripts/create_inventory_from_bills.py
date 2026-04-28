#!/usr/bin/env python3
"""Create inventory items in Zoho + Shopify (DRAFT) for all unaccounted bill lines.

Reads zoho-import/03-per-piece-costs.csv, skips Bill 1 (already done), and for
each remaining piece:
  1. Generates a stable handle/SKU from (bill_id, line_index, piece_index)
  2. Computes selling price via pricing.target_sell_price() — apparel uses
     full overhead (var ₹280 + fixed ₹489); accessories (potlis, scarves) use
     variable-only (no fixed allocation, since they're add-ons not the
     volume driver)
  3. Creates Zoho item (sales_and_purchases) with cost + selling rate
  4. Creates Shopify product as DRAFT with cost + price + sku, tagged with
     vendor and bill reference
  5. Sets Min Sell Price (cf_min_sell_price) on the Zoho item

Idempotent: skips items that already exist by SKU in Zoho or by handle in Shopify.

Usage:
    python3 scripts/create_inventory_from_bills.py --dry-run
    python3 scripts/create_inventory_from_bills.py
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

from zoho_books_api import ZohoBooks
from pricing import (
    no_loss_sell_price, target_sell_price, real_margin_pct,
    VARIABLE_PER_PIECE, FIXED_PER_PIECE, DEFAULT_MARKUP,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PER_PIECE_CSV = REPO_ROOT / "zoho-import" / "03-per-piece-costs.csv"
SHOPIFY_STORE = "8chjhs-cd.myshopify.com"

CUSTOM_FIELD_API_NAME = "cf_min_sell_price"

# Categories — drives whether fixed-cost allocation applies
ACCESSORY_KEYWORDS = ["potli", "scarf"]   # no fixed-cost allocation; variable-only
# Everything else gets full overhead (suits, dupattas, kurtis, sets, tops, pants, kaftan)


# --- Handle/SKU generation --------------------------------------------------

VENDOR_CODES = {
    "Modern Chikan": "mc",
    "Nafasat Chikan": "nc",
    "Jasleen Lucknow": "jl",
    "Lucknow Market - Cash Purchase": "lm",
}


def slugify(text: str) -> str:
    """ASCII-safe slug for Shopify handles. Strips parentheticals, keeps key words."""
    # Drop parentheticals
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    # Replace non-alnum with hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    # Trim long slugs
    parts = text.split("-")
    if len(parts) > 6:
        parts = parts[:6]
    return "-".join(parts)


def make_sku(bill_num: int, line_idx: int, piece_idx: int, vendor: str, desc: str) -> str:
    """Stable SKU: b{bill}-{vendor}-{slug}-{seq}.

    Stable across runs: same (bill, line, piece) -> same SKU.
    The seq=line_idx*10+piece_idx ensures uniqueness when same desc has qty>1.
    """
    vc = VENDOR_CODES.get(vendor, "x")
    seq = line_idx * 10 + piece_idx
    slug = slugify(desc)
    return f"b{bill_num}-{vc}-{slug}-{seq:03d}"


def is_accessory(desc: str) -> bool:
    low = desc.lower()
    return any(k in low for k in ACCESSORY_KEYWORDS)


# --- Pricing for accessories (no fixed-cost allocation) ---------------------

def accessory_no_loss(cost: float) -> int:
    """No-loss for an accessory: cost + variable, divided by (1 - payment fee)."""
    from pricing import VARIABLE_PER_PIECE, PAYMENT_FEE_RATE, round_up_to_10
    raw = (cost + VARIABLE_PER_PIECE) / (1.0 - PAYMENT_FEE_RATE)
    return round_up_to_10(raw)


def accessory_target(cost: float, markup: float = DEFAULT_MARKUP) -> int:
    from pricing import round_up_to_10
    return round_up_to_10(accessory_no_loss(cost) * (1.0 + markup))


# --- Title generation -------------------------------------------------------

def make_title(desc: str, vendor: str) -> str:
    """Cleaner human title: drop short codes in parens, title-case nicely."""
    text = re.sub(r"\([^)]*\)", "", desc)
    text = re.sub(r"\s+", " ", text).strip()
    return text.title()


# --- Shopify GraphQL --------------------------------------------------------

def gql(query, variables=None, allow_mutations=False, retries=3):
    """Run a Shopify GraphQL call via CLI. Retry on transient failures.

    The CLI's animated spinner sometimes garbles output and the cli itself
    can hang. We retry up to 3 times with brief sleep between.
    """
    cmd = ["shopify", "store", "execute", "--store", SHOPIFY_STORE,
           "--query", query, "--json", "--no-color"]
    if variables:
        cmd.extend(["--variables", json.dumps(variables)])
    if allow_mutations:
        cmd.append("--allow-mutations")

    last_err = None
    for attempt in range(retries):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                env={**__import__("os").environ, "NO_COLOR": "1", "CI": "1"})
            if r.returncode != 0:
                raise RuntimeError(f"cli rc={r.returncode}: {r.stderr.strip()[:200]}")
            out = r.stdout
            # Extract JSON from output (CLI prints spinner frames first)
            i = out.find("{")
            if i < 0:
                raise RuntimeError(f"no JSON in output: {out[:200]}")
            data = json.loads(out[i:])
            if "errors" in data:
                raise RuntimeError(f"graphql errors: {data['errors']}")
            return data
        except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"failed after {retries} retries: {last_err}")
    raise RuntimeError(f"failed: {last_err}")


def shopify_find_by_handle(handle: str):
    q = """query($q:String!){ products(first:5,query:$q){ nodes{ id handle status } } }"""
    data = gql(q, {"q": f"handle:{handle}"})
    for p in data["products"]["nodes"]:
        if p["handle"] == handle:
            return p
    return None


def shopify_create_draft(handle: str, title: str, sku: str, cost: float,
                          price: int, vendor: str, bill_id: str, desc: str) -> dict:
    """Create draft product, then update its variant with sku/price/cost."""
    mut1 = """
    mutation($input: ProductInput!) {
      productCreate(input: $input) {
        product { id handle status
          variants(first:1){ nodes{ id sku inventoryItem { id } } }
        }
        userErrors { field message }
      }
    }
    """
    description_html = (
        f"<p><strong>Source:</strong> {bill_id} ({vendor}) — <em>{desc}</em></p>"
        f"<p><em>Photos pending. This product is a draft and not visible on the storefront.</em></p>"
    )
    variables = {
        "input": {
            "title": title,
            "handle": handle,
            "status": "DRAFT",
            "tags": ["draft-pending-photos", vendor.lower().replace(" ", "-"),
                      bill_id.lower().replace(" ", "-")],
            "vendor": vendor,
            "productType": guess_product_type(desc),
            "descriptionHtml": description_html,
        }
    }
    data = gql(mut1, variables, allow_mutations=True)
    errs = data["productCreate"]["userErrors"]
    if errs:
        raise RuntimeError(errs)
    product = data["productCreate"]["product"]
    variant = product["variants"]["nodes"][0]

    mut2 = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants { id sku price inventoryItem { id unitCost { amount } } }
        userErrors { field message }
      }
    }
    """
    variants_input = [{
        "id": variant["id"],
        "price": str(price),
        "inventoryItem": {
            "sku": sku,
            "cost": str(cost),
            "tracked": True,
        },
    }]
    data2 = gql(mut2, {"productId": product["id"], "variants": variants_input},
                 allow_mutations=True)
    errs2 = data2["productVariantsBulkUpdate"]["userErrors"]
    if errs2:
        raise RuntimeError(errs2)
    return product


def guess_product_type(desc: str) -> str:
    low = desc.lower()
    if "potli" in low: return "Potli Bag"
    if "scarf" in low: return "Scarf"
    if "kurti" in low or "kurta" in low: return "Kurti"
    if "anarkali" in low: return "Anarkali"
    if "gharara" in low: return "Gharara Set"
    if "cord set" in low or "co-ord" in low: return "Co-ord Set"
    if "dupatta" in low: return "Dupatta"
    if "pant" in low: return "Pants"
    if "top" in low: return "Top"
    if "kaftan" in low: return "Kaftan"
    if "sharara" in low: return "Sharara"
    if "shrug" in low: return "Shrug"
    if "dress" in low: return "Dress"
    if "suit" in low: return "Suit"
    return "Apparel"


# --- Main flow --------------------------------------------------------------

def expand_bill_lines(rows):
    """Expand qty>1 rows into individual piece records, each with stable indices."""
    items = []
    line_idx_by_bill = defaultdict(int)
    for row in rows:
        bill = row["Source Bill"]
        if bill == "Bill 1":
            continue   # already done
        line_idx_by_bill[bill] += 1
        line_idx = line_idx_by_bill[bill]
        pieces = int(row["Pieces"])
        cost = float(row["Unit Cost (Negotiated)"])
        bill_num = int(re.search(r"\d+", bill).group())
        for piece_idx in range(1, pieces + 1):
            sku = make_sku(bill_num, line_idx, piece_idx, row["Vendor"], row["Item Description"])
            base_desc = row["Item Description"]
            title = make_title(base_desc, row["Vendor"])
            if pieces > 1:
                title = f"{title} ({piece_idx}/{pieces})"
            items.append({
                "bill": bill, "bill_num": bill_num,
                "vendor": row["Vendor"],
                "date": row["Bill Date"],
                "desc": base_desc,
                "title": title,
                "sku": sku,
                "handle": sku,   # handle = sku for stability
                "cost": round(cost),
                "is_accessory": is_accessory(base_desc),
            })
    return items


def compute_prices(item):
    if item["is_accessory"]:
        item["no_loss"] = accessory_no_loss(item["cost"])
        item["target"]  = accessory_target(item["cost"])
    else:
        item["no_loss"] = no_loss_sell_price(item["cost"])
        item["target"]  = target_sell_price(item["cost"])
    return item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="Compute prices and print plan, do NOT create anything")
    ap.add_argument("--limit", type=int, default=0,
                     help="Process only the first N items (testing)")
    args = ap.parse_args()

    with PER_PIECE_CSV.open() as f:
        rows = list(csv.DictReader(f))
    items = expand_bill_lines(rows)
    items = [compute_prices(it) for it in items]
    if args.limit:
        items = items[:args.limit]

    print(f"\n=== {len(items)} new pieces to create (Bill 1 already done) ===\n")
    by_bill = defaultdict(int)
    by_cat  = defaultdict(int)
    total_cost = 0
    total_target = 0
    for it in items:
        by_bill[it["bill"]] += 1
        by_cat["accessory" if it["is_accessory"] else "apparel"] += 1
        total_cost += it["cost"]
        total_target += it["target"]
    for bill, n in by_bill.items():
        print(f"  {bill}: {n} pieces")
    print(f"  apparel: {by_cat['apparel']}, accessories: {by_cat['accessory']}")
    print(f"  Total cost basis: ₹{total_cost:,}")
    print(f"  Total target revenue (if all sold @ target): ₹{total_target:,}")
    print(f"  Implied gross profit: ₹{total_target - total_cost:,} ({(total_target-total_cost)/total_target*100:.1f}%)")

    if args.dry_run:
        print(f"\n[dry-run] Sample (first 5):\n")
        for it in items[:5]:
            print(f"  {it['sku']:55s} cost ₹{it['cost']:>5,} no-loss ₹{it['no_loss']:>5,} target ₹{it['target']:>5,}  {it['title']}")
        return 0

    # Real run
    zb = ZohoBooks()
    zb.verify_org()

    stats = defaultdict(int)
    print(f"\n=== Creating items ===\n")
    for i, it in enumerate(items, 1):
        prefix = f"  [{i:>3}/{len(items)}] {it['sku']:55s}"
        try:
            # 1. Zoho item (upsert by SKU). Zoho enforces unique item names —
            # if name collides (Bill 2 has 2 "Suit Mul Chanderi Booti Jaal"
            # lines, Bill 3 has 3 "Kurti Muslin"), append SKU suffix and retry.
            existing = zb.find_item_by_sku(it["sku"])
            if existing:
                body = {"rate": it["target"], "purchase_rate": it["cost"], "name": it["title"]}
                try:
                    zb._request("PUT", f"/items/{existing['item_id']}", json_body=body)
                except RuntimeError as e:
                    if "already exists" in str(e):
                        body["name"] = f"{it['title']} [{it['sku'].split('-')[-1]}]"
                        zb._request("PUT", f"/items/{existing['item_id']}", json_body=body)
                    else:
                        raise
                zoho_action = "zoho-updated"
                item_id = existing["item_id"]
            else:
                try:
                    created = zb.create_item(it["title"], it["sku"], it["target"],
                                              it["cost"], item_type="sales_and_purchases")
                except RuntimeError as e:
                    if "already exists" in str(e):
                        unique_name = f"{it['title']} [{it['sku'].split('-')[-1]}]"
                        created = zb.create_item(unique_name, it["sku"], it["target"],
                                                  it["cost"], item_type="sales_and_purchases")
                    else:
                        raise
                zoho_action = "zoho-created"
                item_id = created["item_id"]
            stats[zoho_action] += 1

            # 2. Min Sell Price custom field
            zb._request("PUT", f"/items/{item_id}", json_body={
                "custom_fields": [{"api_name": CUSTOM_FIELD_API_NAME, "value": it["no_loss"]}]
            })

            # 3. Shopify draft product (skip if handle exists)
            existing_sp = shopify_find_by_handle(it["handle"])
            if existing_sp:
                shop_action = "shopify-exists"
            else:
                shopify_create_draft(it["handle"], it["title"], it["sku"],
                                      it["cost"], it["target"], it["vendor"],
                                      it["bill"], it["desc"])
                shop_action = "shopify-created"
            stats[shop_action] += 1

            print(f"{prefix} cost ₹{it['cost']:>5,} target ₹{it['target']:>6,} [{zoho_action}, {shop_action}]")

            # Gentle throttle for Shopify CLI (each run spawns a process)
            if shop_action == "shopify-created":
                time.sleep(0.5)
        except Exception as e:
            print(f"{prefix} ✗ FAILED: {e}")
            stats["failed"] += 1

    print(f"\n  stats: {dict(stats)}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
