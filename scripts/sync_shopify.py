#!/usr/bin/env python3
"""Sync Chikankari Lane catalog data into Shopify via Admin API.

Currently scoped to: push Cost per item from zoho-import/05-shopify-cost-update.csv
onto the matching Shopify variants (matched by SKU).

Idempotent: skips variants whose cost already matches.

Usage:
    python3 scripts/sync_shopify.py [--dry-run]

The --dry-run flag prints what would be done without writing.

Auth setup: see specs/03-shopify-admin-api-setup.md
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

from shopify_admin_api import ShopifyAdmin


REPO_ROOT = Path(__file__).resolve().parent.parent
COST_CSV = REPO_ROOT / "zoho-import" / "05-shopify-cost-update.csv"


def log(msg: str, indent: int = 0) -> None:
    print("  " * indent + msg)


def sync_costs(sa: ShopifyAdmin, dry_run: bool) -> dict:
    log("Step 1: Cost per item updates")
    stats = defaultdict(int)
    total_cost = 0.0

    with COST_CSV.open() as f:
        for row in csv.DictReader(f):
            sku = row["Variant SKU"]
            cost = float(row["Cost per item"])
            total_cost += cost

            if dry_run:
                variant = sa.find_variant_by_sku(sku)
                if not variant:
                    action = "would-skip (not found)"
                else:
                    current = (variant.get("inventoryItem", {}) or {}).get("unitCost") or {}
                    current_amt = float(current.get("amount", 0)) if current else 0
                    if abs(current_amt - cost) < 0.01:
                        action = "would-skip (unchanged)"
                    else:
                        action = f"would-update (current ₹{current_amt:.0f})"
            else:
                _, action = sa.upsert_cost_by_sku(sku, cost)

            stats[action] += 1
            log(f"{action:32s} {sku:50s} cost ₹{cost:>6,.0f}", indent=1)

    log(f"\nstats: {dict(stats)}", indent=1)
    log(f"total cost across {sum(stats.values())} SKUs: ₹{total_cost:,.0f}", indent=1)
    return {"stats": dict(stats), "total_cost": total_cost}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would be done without writing")
    args = parser.parse_args()

    log(f"=== Shopify Sync (dry-run={args.dry_run}) ===\n")

    sa = ShopifyAdmin()
    sa.verify_store()

    result = sync_costs(sa, args.dry_run)

    log(f"\n=== Summary ===")
    skipped_not_found = result["stats"].get("skipped (not found)", 0) + result["stats"].get("would-skip (not found)", 0)
    if skipped_not_found:
        log(f"  ⚠️  {skipped_not_found} SKUs not found in Shopify — verify SKU naming or that products exist.")

    if args.dry_run:
        log("\n(dry-run — no writes made)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
