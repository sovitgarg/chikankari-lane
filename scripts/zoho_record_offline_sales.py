#!/usr/bin/env python3
"""Record 4 offline-sold Bill 1 pieces in Zoho.

Steps:
  1. Create 4 Items (sales_and_purchases) with cost
  2. Find/create offline customer "Friends & Family - Lucknow"
  3. Create 4 individual Sales Invoices, each for 1 piece, dated 2026-04-15
     (matching the F&F sales date used for the original 6 Shopify invoices)
  4. Mark each invoice as paid (cash, same date)

Idempotent: skips items that exist by SKU; skips invoices that already exist
for the customer/date/amount triple.
"""
from datetime import date
from collections import defaultdict
from zoho_books_api import ZohoBooks

OFFLINE_DATE = "2026-04-15"
CUSTOMER_NAME = "Friends & Family - Lucknow (Offline)"

OFFLINE_PIECES = [
    {"sku": "23-yellow-kasab-suit-sold",     "name": "Yellow Kasab Mul Chanderi Suit (Sold Offline)",  "cost": 7500.0, "price": 7720.0},
    {"sku": "24-red-white-anarkali-1-sold",  "name": "Red & White Anarkali #1 (Sold Offline)",         "cost": 8000.0, "price": 8230.0},
    {"sku": "25-red-white-anarkali-2-sold",  "name": "Red & White Anarkali #2 (Sold Offline)",         "cost": 8000.0, "price": 8230.0},
    {"sku": "26-beige-cord-set-sold",        "name": "Beige Limp Cord Set (Sold Offline)",             "cost": 5200.0, "price": 5340.0},
]


def find_or_create_customer(zb, name):
    data = zb._request("GET", "/contacts", params={
        "contact_name_contains": name, "contact_type": "customer"
    })
    for c in data.get("contacts", []):
        if c.get("contact_name", "").strip().lower() == name.strip().lower():
            return c, "reused"
    body = {"contact_name": name, "contact_type": "customer"}
    data = zb._request("POST", "/contacts", json_body=body)
    return data["contact"], "created"


def find_invoice(zb, customer_id, invoice_date, total, reference):
    """Match on reference_number — unique per piece — to avoid collisions on equal totals."""
    data = zb._request("GET", "/invoices", params={
        "customer_id": customer_id, "date": invoice_date,
    })
    for inv in data.get("invoices", []):
        if (inv.get("reference_number", "") == reference and
            abs(float(inv.get("total", 0)) - total) < 0.5):
            return inv
    return None


def create_invoice(zb, customer_id, invoice_date, item_id, item_name, rate, reference):
    body = {
        "customer_id": customer_id,
        "date": invoice_date,
        "reference_number": reference,
        "line_items": [{
            "item_id": item_id,
            "name": item_name,
            "quantity": 1,
            "rate": rate,
        }],
    }
    data = zb._request("POST", "/invoices", json_body=body)
    return data["invoice"]


def mark_invoice_paid(zb, invoice_id, customer_id, amount, payment_date):
    body = {
        "customer_id": customer_id,
        "payment_mode": "cash",
        "amount": amount,
        "date": payment_date,
        "invoices": [{"invoice_id": invoice_id, "amount_applied": amount}],
    }
    data = zb._request("POST", "/customerpayments", json_body=body)
    return data.get("payment", data)


def main():
    zb = ZohoBooks()
    zb.verify_org()

    print("\n=== Step 1: Create/update 4 Zoho items ===")
    item_by_sku = {}
    for p in OFFLINE_PIECES:
        try:
            item, action = zb.upsert_item_full(p["sku"], p["name"], p["price"], p["cost"])
            print(f"  ✓ {action:25s} {p['sku']:35s} (id={item['item_id']})")
            item_by_sku[p["sku"]] = item
        except Exception as e:
            print(f"  ✗ FAILED {p['sku']}: {e}")
            return 1

    print("\n=== Step 2: Find/create offline customer ===")
    customer, action = find_or_create_customer(zb, CUSTOMER_NAME)
    print(f"  ✓ {action} customer (id={customer['contact_id']})")

    print(f"\n=== Step 3: Create 4 individual sales invoices (date={OFFLINE_DATE}) ===")
    stats = defaultdict(int)
    invoices_created = []
    for p in OFFLINE_PIECES:
        item = item_by_sku[p["sku"]]
        existing = find_invoice(zb, customer["contact_id"], OFFLINE_DATE, p["price"], p["sku"])
        if existing:
            print(f"  · already exists  {p['sku']:35s} ₹{p['price']:,.0f} (inv={existing['invoice_number']})")
            invoices_created.append((existing, p))
            stats["existing"] += 1
            continue
        try:
            inv = create_invoice(zb, customer["contact_id"], OFFLINE_DATE,
                                  item["item_id"], p["name"], p["price"], p["sku"])
            print(f"  ✓ created         {p['sku']:35s} ₹{p['price']:,.0f} (inv={inv['invoice_number']})")
            invoices_created.append((inv, p))
            stats["created"] += 1
        except Exception as e:
            print(f"  ✗ FAILED {p['sku']}: {e}")
            stats["failed"] += 1

    print(f"\n=== Step 4: Mark invoices paid (cash, {OFFLINE_DATE}) ===")
    for inv, p in invoices_created:
        if inv.get("status", "").lower() == "paid":
            print(f"  · already paid    {p['sku']:35s}")
            continue
        try:
            mark_invoice_paid(zb, inv["invoice_id"], customer["contact_id"],
                               p["price"], OFFLINE_DATE)
            print(f"  ✓ paid            {p['sku']:35s} ₹{p['price']:,.0f}")
        except Exception as e:
            print(f"  ✗ FAILED {p['sku']}: {e}")

    print(f"\n  stats: {dict(stats)}")
    print(f"\n  Total offline revenue recorded: ₹{sum(p['price'] for p in OFFLINE_PIECES):,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
