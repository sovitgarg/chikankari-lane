#!/usr/bin/env python3
"""Read-only audit of Chikankari Lane's current Zoho Books state.

Lists all vendors, bills, expenses, and items that match what the CSVs
in zoho-import/ would push. Compares actual vs expected. No writes.

Usage:
    python3 scripts/audit_zoho.py
"""
from __future__ import annotations

import csv
from pathlib import Path
from collections import defaultdict

from zoho_books_api import ZohoBooks


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORT_DIR = REPO_ROOT / "zoho-import"


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> None:
    zb = ZohoBooks()
    zb.verify_org()

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------
    section("VENDORS")
    expected_vendors = {
        "Modern Chikan", "Nafasat Chikan", "Jasleen Lucknow",
        "Lucknow Market - Cash Purchase", "Printo",
        "OpenAI", "Canva", "Google", "Shopify",
    }
    found = {}
    for name in sorted(expected_vendors):
        v = zb.find_vendor(name)
        if v:
            found[name] = v
            actual_name = v.get("contact_name", "")
            match_type = "EXACT" if actual_name.strip().lower() == name.strip().lower() else "FUZZY"
            print(f"  ✓ {match_type:6s} {name:40s} -> '{actual_name}' (id={v['contact_id']})")
        else:
            print(f"  ✗ MISSING {name}")
    print(f"\n  {len(found)}/{len(expected_vendors)} vendors found")

    # ------------------------------------------------------------------
    # Expense accounts
    # ------------------------------------------------------------------
    section("EXPENSE ACCOUNTS")
    expected_accounts = {"Packaging Materials", "Travel Expenses",
                          "Marketing - Photography", "Software Subscriptions"}
    for name in sorted(expected_accounts):
        a = zb.find_account(name, "expense")
        if a:
            actual = a.get("account_name", "")
            match_type = "EXACT" if actual.strip().lower() == name.strip().lower() else "FUZZY"
            print(f"  ✓ {match_type:6s} {name:30s} -> '{actual}'")
        else:
            print(f"  ✗ MISSING {name}")

    # ------------------------------------------------------------------
    # Bills
    # ------------------------------------------------------------------
    section("BILLS (vs zoho-import/01-vendor-bills.csv)")
    bills_csv = IMPORT_DIR / "01-vendor-bills.csv"
    csv_total = 0.0
    found_bills = 0
    missing_bills = []
    with bills_csv.open() as f:
        for row in csv.DictReader(f):
            vendor_name = row["Vendor Name"]
            bill_date = row["Bill Date"]
            expected_total = float(row["Total"])
            csv_total += expected_total

            v = found.get(vendor_name) or zb.find_vendor(vendor_name)
            if not v:
                print(f"  ✗ {bill_date} {vendor_name:35s} ₹{expected_total:>9,.0f}  vendor missing")
                missing_bills.append((bill_date, vendor_name, expected_total))
                continue

            existing = zb.find_bill(v["contact_id"], bill_date, row.get("Bill Number"))
            if existing:
                actual_total = float(existing.get("total", 0))
                status = existing.get("status", "?")
                match = "✓" if abs(actual_total - expected_total) < 1 else "Δ"
                print(f"  {match} {bill_date} {vendor_name:35s} ₹{actual_total:>9,.0f} [{status}] (expected ₹{expected_total:>9,.0f})")
                found_bills += 1
            else:
                print(f"  ✗ {bill_date} {vendor_name:35s} ₹{expected_total:>9,.0f}  NOT FOUND")
                missing_bills.append((bill_date, vendor_name, expected_total))

    print(f"\n  {found_bills}/{found_bills + len(missing_bills)} bills found in Zoho")
    print(f"  CSV total: ₹{csv_total:,.0f} (expected)")

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------
    section("EXPENSES (vs zoho-import/02-operational-expenses.csv)")
    exp_csv = IMPORT_DIR / "02-operational-expenses.csv"
    exp_total = 0.0
    found_exp = 0
    missing_exp = []
    with exp_csv.open() as f:
        for row in csv.DictReader(f):
            account_name = row["Expense Account"]
            date = row["Date"]
            amount = float(row["Amount"])
            desc = row["Description"][:50]
            vendor_name = row.get("Vendor", "").strip()
            exp_total += amount

            account = zb.find_account(account_name, "expense")
            if not account:
                print(f"  ✗ {date} {account_name:25s} {desc:52s} ₹{amount:>7,.0f}  account missing")
                missing_exp.append((date, account_name, amount))
                continue

            vendor_id = found.get(vendor_name, {}).get("contact_id") if vendor_name else None
            if vendor_name and not vendor_id:
                v = zb.find_vendor(vendor_name)
                vendor_id = v["contact_id"] if v else None

            existing = zb.find_expense(account["account_id"], date, amount, vendor_id)
            if existing:
                actual = float(existing.get("total", 0))
                print(f"  ✓ {date} {account_name:25s} {desc:52s} ₹{actual:>7,.0f}")
                found_exp += 1
            else:
                print(f"  ✗ {date} {account_name:25s} {desc:52s} ₹{amount:>7,.0f}  NOT FOUND")
                missing_exp.append((date, account_name, amount))

    print(f"\n  {found_exp}/{found_exp + len(missing_exp)} expenses found in Zoho")
    print(f"  CSV total: ₹{exp_total:,.0f} (expected)")

    # ------------------------------------------------------------------
    # Items (Purchase Rate set?)
    # ------------------------------------------------------------------
    section("ITEMS - Purchase Rate (vs zoho-import/06-zoho-items-cost-update.csv)")
    items_csv = IMPORT_DIR / "06-zoho-items-cost-update.csv"
    found_items = 0
    items_with_cost = 0
    missing_items = []
    with items_csv.open() as f:
        for row in csv.DictReader(f):
            sku = row["SKU"]
            expected_cost = float(row["Purchase Rate"])
            existing = zb.find_item_by_sku(sku)
            if existing:
                actual_cost = float(existing.get("purchase_rate", 0) or 0)
                status = existing.get("status", "?")
                cost_match = "✓" if abs(actual_cost - expected_cost) < 1 else "Δ"
                if actual_cost > 0:
                    items_with_cost += 1
                print(f"  {cost_match} {sku:50s} cost ₹{actual_cost:>6,.0f} (expected ₹{expected_cost:>6,.0f}) [{status}]")
                found_items += 1
            else:
                print(f"  ✗ {sku:50s}  NOT FOUND in Zoho")
                missing_items.append(sku)

    print(f"\n  {found_items}/{found_items + len(missing_items)} items exist in Zoho")
    print(f"  {items_with_cost}/{found_items} items have a non-zero Purchase Rate set")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("SUMMARY")
    print(f"  Vendors:  {len(found)}/{len(expected_vendors)} present")
    print(f"  Bills:    {found_bills}/{found_bills + len(missing_bills)} present  (CSV total ₹{csv_total:,.0f})")
    print(f"  Expenses: {found_exp}/{found_exp + len(missing_exp)} present  (CSV total ₹{exp_total:,.0f})")
    print(f"  Items:    {found_items}/{found_items + len(missing_items)} present, {items_with_cost} with cost set")
    print(f"\n  Expected total spend Jan-Apr 2026: ₹5,45,434")


if __name__ == "__main__":
    main()
