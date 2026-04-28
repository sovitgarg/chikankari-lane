#!/usr/bin/env python3
"""Shopify sync via Shopify CLI (no Admin API token needed).

Uses `shopify store execute` for all GraphQL operations. CLI handles auth.

Run `shopify store auth --store 8chjhs-cd.myshopify.com --scopes ...` once
before this script to set up the stored token.

Usage:
    python3 scripts/shopify_cli_sync.py
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from collections import defaultdict


REPO_ROOT = Path(__file__).resolve().parent.parent
STORE = "8chjhs-cd.myshopify.com"
COST_CSV = REPO_ROOT / "zoho-import" / "05-shopify-cost-update.csv"

# SKUs to add 'sold' tag to (qty=0 in Shopify but missing the tag)
SKUS_NEEDING_SOLD_TAG = [
    "14-ivory-mul-beige-chikankari-suit",
    "18-white-tonal-chikankari-suit",
]


def gql(query: str, variables: dict | None = None,
         allow_mutations: bool = False) -> dict:
    """Run a GraphQL query/mutation via Shopify CLI."""
    cmd = [
        "shopify", "store", "execute",
        "--store", STORE,
        "--query", query,
        "--json",
        "--no-color",
    ]
    if variables:
        cmd.extend(["--variables", json.dumps(variables)])
    if allow_mutations:
        cmd.append("--allow-mutations")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"CLI failed: {result.stderr}")

    # CLI prints progress + spinner before JSON; find the JSON line
    lines = result.stdout.strip().split("\n")
    json_text = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("{"):
            json_text = "\n".join(lines[i:])
            break
    if not json_text:
        raise RuntimeError(f"No JSON in CLI output:\n{result.stdout}")
    data = json.loads(json_text)
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data


def find_variant_by_sku(sku: str) -> dict | None:
    query = """
    query($q: String!) {
      productVariants(first: 5, query: $q) {
        nodes {
          id sku price
          inventoryItem { id unitCost { amount } }
          product { id handle title status tags }
        }
      }
    }
    """
    data = gql(query, {"q": f"sku:{sku}"})
    variants = data.get("productVariants", {}).get("nodes", [])
    for v in variants:
        if v.get("sku", "").strip().lower() == sku.strip().lower():
            return v
    return variants[0] if variants else None


def update_variant_cost(inventory_item_id: str, cost: float) -> None:
    mutation = """
    mutation($id: ID!, $input: InventoryItemInput!) {
      inventoryItemUpdate(id: $id, input: $input) {
        inventoryItem { id unitCost { amount } }
        userErrors { field message }
      }
    }
    """
    data = gql(mutation, {"id": inventory_item_id, "input": {"cost": str(cost)}},
                allow_mutations=True)
    errs = data.get("inventoryItemUpdate", {}).get("userErrors", [])
    if errs:
        raise RuntimeError(f"cost update errors: {errs}")


def update_product_tags(product_id: str, tags: list[str]) -> None:
    mutation = """
    mutation($input: ProductInput!) {
      productUpdate(input: $input) {
        product { id tags }
        userErrors { field message }
      }
    }
    """
    data = gql(mutation, {"input": {"id": product_id, "tags": tags}},
                allow_mutations=True)
    errs = data.get("productUpdate", {}).get("userErrors", [])
    if errs:
        raise RuntimeError(f"tag update errors: {errs}")


def list_orders() -> list[dict]:
    """Pull all orders via paginated query."""
    query = """
    query($cursor: String) {
      orders(first: 50, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id name createdAt
          totalPriceSet { shopMoney { amount } }
          displayFinancialStatus displayFulfillmentStatus
          customer { firstName lastName email }
          lineItems(first: 20) {
            nodes { name sku quantity originalUnitPriceSet { shopMoney { amount } } }
          }
        }
      }
    }
    """
    all_orders = []
    cursor = None
    while True:
        data = gql(query, {"cursor": cursor})
        page = data["orders"]
        all_orders.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return all_orders


def main() -> int:
    print("=== Step 1: Push Cost per item to 16 SKUs ===\n")
    stats = defaultdict(int)
    with COST_CSV.open() as f:
        for row in csv.DictReader(f):
            sku = row["Variant SKU"]
            cost = float(row["Cost per item"])
            v = find_variant_by_sku(sku)
            if not v:
                print(f"  ✗ NOT FOUND  {sku}")
                stats["not-found"] += 1
                continue
            current_cost = (v.get("inventoryItem", {}) or {}).get("unitCost") or {}
            current_amt = float(current_cost.get("amount", 0)) if current_cost else 0
            if abs(current_amt - cost) < 0.01:
                print(f"  · unchanged  {sku:50s} cost ₹{cost:>6,.0f}")
                stats["unchanged"] += 1
                continue
            try:
                update_variant_cost(v["inventoryItem"]["id"], cost)
                print(f"  ✓ updated    {sku:50s} cost ₹{cost:>6,.0f} (was ₹{current_amt:>6,.0f})")
                stats["updated"] += 1
            except Exception as e:
                print(f"  ✗ FAILED     {sku}: {e}")
                stats["failed"] += 1
    print(f"\nstats: {dict(stats)}")

    print("\n=== Step 2: Add 'sold' tag to 2 missing SKUs ===\n")
    for sku in SKUS_NEEDING_SOLD_TAG:
        v = find_variant_by_sku(sku)
        if not v:
            print(f"  ✗ NOT FOUND  {sku}")
            continue
        product = v["product"]
        current_tags = list(product.get("tags") or [])
        if "sold" in [t.lower() for t in current_tags]:
            print(f"  · already tagged  {sku}")
            continue
        new_tags = sorted(set(current_tags + ["sold"]), key=str.lower)
        try:
            update_product_tags(product["id"], new_tags)
            print(f"  ✓ tagged sold  {sku} (tags: {new_tags})")
        except Exception as e:
            print(f"  ✗ FAILED       {sku}: {e}")

    print("\n=== Step 3: Pull live orders and reconcile vs Zoho ===\n")
    try:
        orders = list_orders()
    except Exception as e:
        print(f"  ✗ FAILED to pull orders: {e}")
        return 1
    print(f"  Found {len(orders)} orders in Shopify\n")

    total_revenue = 0.0
    for o in orders:
        amt = float(o["totalPriceSet"]["shopMoney"]["amount"])
        total_revenue += amt
        items_str = ", ".join(li["name"] for li in o["lineItems"]["nodes"])
        cust = o.get("customer") or {}
        cust_name = f"{cust.get('firstName','')} {cust.get('lastName','')}".strip() or "(no customer)"
        print(f"  {o['createdAt'][:10]} {o['name']:10s} {cust_name[:25]:25s} ₹{amt:>9,.0f}  [{o['displayFinancialStatus']}/{o['displayFulfillmentStatus']}]")
        print(f"    items: {items_str}")

    print(f"\n  Shopify total revenue: ₹{total_revenue:,.0f}")
    print(f"  Zoho total invoiced:   ₹66,980  (from earlier query)")
    print(f"  Variance: ₹{total_revenue - 66980:,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
