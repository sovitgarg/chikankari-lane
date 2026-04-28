#!/usr/bin/env python3
"""Sync Chikankari Lane financial data into Zoho Books.

Reads the source-of-truth CSVs in zoho-import/ and pushes them into Zoho Books
via the API. Idempotent: matches existing records by (vendor + date) for bills,
(vendor + date + account) for expenses, SKU for items. Overwrites on match.

Usage:
    python3 scripts/sync_zoho.py [--dry-run]

The --dry-run flag prints what would be done without making any writes.

Auth setup: see specs/02-zoho-books-api-setup.md
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

from zoho_books_api import ZohoBooks


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORT_DIR = REPO_ROOT / "zoho-import"

BILLS_CSV = IMPORT_DIR / "01-vendor-bills.csv"
EXPENSES_CSV = IMPORT_DIR / "02-operational-expenses.csv"
ITEMS_CSV = IMPORT_DIR / "06-zoho-items-cost-update.csv"


def log(msg: str, indent: int = 0) -> None:
    print("  " * indent + msg)


def sync_vendors(zb: ZohoBooks, names: set[str], dry_run: bool) -> dict[str, str]:
    """Returns {vendor_name: vendor_id}. Creates if missing."""
    log("Step 1: Vendors")
    result: dict[str, str] = {}
    stats = defaultdict(int)
    for name in sorted(names):
        if dry_run:
            existing = zb.find_vendor(name)
            action = "would-reuse" if existing else "would-create"
            vendor_id = existing.get("contact_id", "?") if existing else "(new)"
        else:
            vendor, action = zb.find_or_create_vendor(name)
            vendor_id = vendor["contact_id"]
        result[name] = vendor_id
        stats[action] += 1
        log(f"{action:18s} {name} -> {vendor_id}", indent=1)
    log(f"vendors: {dict(stats)}", indent=1)
    return result


def sync_accounts(zb: ZohoBooks, names: set[str], dry_run: bool) -> dict[str, str]:
    """Returns {account_name: account_id}. Creates expense accounts if missing."""
    log("\nStep 2: Chart of Accounts")
    result: dict[str, str] = {}
    stats = defaultdict(int)
    for name in sorted(names):
        if dry_run:
            existing = zb.find_account(name, "expense")
            action = "would-reuse" if existing else "would-create"
            acc_id = existing.get("account_id", "?") if existing else "(new)"
        else:
            acc, action = zb.find_or_create_account(name, "expense")
            acc_id = acc["account_id"]
        result[name] = acc_id
        stats[action] += 1
        log(f"{action:18s} {name} -> {acc_id}", indent=1)
    log(f"accounts: {dict(stats)}", indent=1)
    return result


def sync_bills(zb: ZohoBooks, vendor_ids: dict[str, str],
                cogs_account_id: str, dry_run: bool) -> dict:
    log("\nStep 3: Vendor Bills")
    stats = defaultdict(int)
    bill_total = 0.0
    with BILLS_CSV.open() as f:
        for row in csv.DictReader(f):
            vendor_name = row["Vendor Name"]
            vendor_id = vendor_ids.get(vendor_name)
            if not vendor_id and not dry_run:
                log(f"SKIP: vendor not found: {vendor_name}", indent=1)
                stats["skipped"] += 1
                continue
            line_items = [{
                "name": row["Item Name"],
                "description": row["Description"],
                "quantity": float(row["Quantity"]),
                "rate": float(row["Rate"]),
                "account_id": cogs_account_id,
                "tax_id": "",  # 0% — we are not GST-registered
            }]
            total = float(row["Total"])
            bill_total += total
            if dry_run:
                log(f"would-upsert    {row['Bill Date']} {vendor_name:35s} ₹{total:>9,.0f}", indent=1)
                stats["would-process"] += 1
            else:
                bill, action = zb.upsert_bill(
                    vendor_id=vendor_id,
                    bill_date=row["Bill Date"],
                    bill_number=row["Bill Number"],
                    line_items=line_items,
                    notes=row.get("Notes", ""),
                )
                log(f"{action:14s} {row['Bill Date']} {vendor_name:35s} ₹{total:>9,.0f} (id={bill['bill_id']})", indent=1)
                stats[action] += 1
                # Mark paid
                if row.get("Payment Status", "").strip().lower() == "paid":
                    try:
                        zb.mark_bill_paid(bill["bill_id"], total, row["Bill Date"], "cash")
                        log(f"marked-paid", indent=2)
                    except Exception as e:
                        log(f"WARN: mark_paid failed: {e}", indent=2)
    log(f"bills: {dict(stats)}, total ₹{bill_total:,.0f}", indent=1)
    return {"stats": dict(stats), "total": bill_total}


def sync_expenses(zb: ZohoBooks, vendor_ids: dict[str, str],
                    account_ids: dict[str, str], dry_run: bool) -> dict:
    log("\nStep 4: Expenses")
    stats = defaultdict(int)
    expense_total = 0.0
    with EXPENSES_CSV.open() as f:
        for row in csv.DictReader(f):
            account_name = row["Expense Account"]
            account_id = account_ids.get(account_name)
            if not account_id and not dry_run:
                log(f"SKIP: account not found: {account_name}", indent=1)
                stats["skipped"] += 1
                continue
            vendor_name = row.get("Vendor", "").strip()
            vendor_id = vendor_ids.get(vendor_name) if vendor_name else None
            amount = float(row["Amount"])
            expense_total += amount
            if dry_run:
                log(f"would-upsert    {row['Date']} {account_name:25s} {row['Description'][:40]:40s} ₹{amount:>7,.0f}", indent=1)
                stats["would-process"] += 1
            else:
                _, action = zb.upsert_expense(
                    account_id=account_id,
                    expense_date=row["Date"],
                    amount=amount,
                    description=row["Description"],
                    vendor_id=vendor_id,
                )
                log(f"{action:14s} {row['Date']} {account_name:25s} ₹{amount:>7,.0f}", indent=1)
                stats[action] += 1
    log(f"expenses: {dict(stats)}, total ₹{expense_total:,.0f}", indent=1)
    return {"stats": dict(stats), "total": expense_total}


def sync_item_costs(zb: ZohoBooks, dry_run: bool) -> dict:
    log("\nStep 5: Item Costs (Purchase Rate on existing Items)")
    stats = defaultdict(int)
    with ITEMS_CSV.open() as f:
        for row in csv.DictReader(f):
            sku = row["SKU"]
            cost = float(row["Purchase Rate"])
            if dry_run:
                existing = zb.find_item_by_sku(sku)
                action = "would-update" if existing else "would-skip (not found)"
                log(f"{action:25s} {sku:50s} cost ₹{cost:>6,.0f}", indent=1)
                stats[action] += 1
            else:
                _, action = zb.upsert_item_cost(sku, cost)
                log(f"{action:25s} {sku:50s} cost ₹{cost:>6,.0f}", indent=1)
                stats[action] += 1
    log(f"items: {dict(stats)}", indent=1)
    return {"stats": dict(stats)}


def collect_unique_names() -> tuple[set[str], set[str]]:
    """Scan CSVs to find all unique vendors and expense accounts."""
    vendors: set[str] = set()
    accounts: set[str] = set()

    with BILLS_CSV.open() as f:
        for row in csv.DictReader(f):
            vendors.add(row["Vendor Name"])

    with EXPENSES_CSV.open() as f:
        for row in csv.DictReader(f):
            accounts.add(row["Expense Account"])
            v = row.get("Vendor", "").strip()
            if v:
                vendors.add(v)

    return vendors, accounts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="Show what would be done without making any writes")
    args = parser.parse_args()

    log(f"=== Zoho Books Sync (dry-run={args.dry_run}) ===\n")

    zb = ZohoBooks()
    zb.verify_org()

    vendors, accounts = collect_unique_names()
    log(f"Found {len(vendors)} unique vendors, {len(accounts)} unique expense accounts in CSVs\n")

    vendor_ids = sync_vendors(zb, vendors, args.dry_run)
    account_ids = sync_accounts(zb, accounts, args.dry_run)

    # COGS account for inventory bills (not in expenses CSV — use a sane default)
    cogs_account = None if args.dry_run else zb.find_or_create_account("Cost of Goods Sold", "expense")[0]
    cogs_account_id = cogs_account["account_id"] if cogs_account else "(dry-run)"

    bill_result = sync_bills(zb, vendor_ids, cogs_account_id, args.dry_run)
    expense_result = sync_expenses(zb, vendor_ids, account_ids, args.dry_run)
    item_result = sync_item_costs(zb, args.dry_run)

    grand_total = bill_result["total"] + expense_result["total"]
    expected = 545434
    log(f"\n=== Summary ===")
    log(f"  Bills total:    ₹{bill_result['total']:>10,.0f}")
    log(f"  Expenses total: ₹{expense_result['total']:>10,.0f}")
    log(f"  Grand total:    ₹{grand_total:>10,.0f}")
    log(f"  Expected:       ₹{expected:>10,.0f}")
    variance = grand_total - expected
    log(f"  Variance:       ₹{variance:>10,.0f}")
    if abs(variance) > 100:
        log(f"  ⚠️  Variance exceeds ₹100 — investigate.")
    else:
        log(f"  ✓ Within tolerance.")

    if args.dry_run:
        log("\n(dry-run — no writes made)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
