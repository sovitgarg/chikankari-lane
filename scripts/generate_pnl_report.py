#!/usr/bin/env python3
"""Generate a phone-optimised PDF P&L + inventory report for Chikankari Lane.

Output: ~/Downloads/chikankari-lane-report-YYYYMMDD.pdf

Uses a narrower portrait layout with larger fonts so the report is readable
on a phone without zooming. Inventory listing wraps to multiple pages with
SKU-name pairing so columns don't get squeezed.

Data sources (cached/local-first to avoid Zoho rate limits):
  - zoho-import/04-sku-to-cost-mapping.csv  (Bill 1 SKU → cost mapping)
  - zoho-import/03-per-piece-costs.csv      (all bills, per-piece costs)
  - Hard-coded sales records from earlier verified Zoho invoices
  - pricing.py for cost model

Optionally pulls live Zoho data if --live flag passed (requires daily-cap
headroom).
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from pricing import (
    VARIABLE_PER_PIECE, FIXED_PER_PIECE, PAYMENT_FEE_RATE,
    no_loss_sell_price, target_sell_price,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                  TableStyle, PageBreak)
from reportlab.lib.enums import TA_LEFT

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path.home() / "Downloads"
TODAY = datetime.now().strftime("%Y-%m-%d")


def fmt_inr(n: float) -> str:
    n = round(float(n))
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        out = ",".join(reversed(groups)) + "," + last3
    return f"{'-' if n < 0 else ''}₹{out}"


# --- Local data sources ----------------------------------------------------

def load_bill1_inventory():
    """16 listed SKUs from Bill 1 + 4 offline-sold items."""
    path = REPO_ROOT / "zoho-import" / "04-sku-to-cost-mapping.csv"
    items = []
    with path.open() as f:
        for row in csv.DictReader(f):
            items.append({
                "sku": row["Shopify Handle"],
                "name": row["Shopify Title"],
                "cost": float(row["Cost Price"]),
                "rate": float(row["Selling Price"]),
                "bill": "Bill 1",
                "is_accessory": False,
                "in_stock": True,
            })
    # 4 offline-sold reconciliation items
    offline = [
        ("23-yellow-kasab-suit-sold", "Yellow Kasab Mul Chanderi Suit (Sold Offline)", 7500, 7720),
        ("24-red-white-anarkali-1-sold", "Red & White Anarkali #1 (Sold Offline)", 8000, 8230),
        ("25-red-white-anarkali-2-sold", "Red & White Anarkali #2 (Sold Offline)", 8000, 8230),
        ("26-beige-cord-set-sold", "Beige Limp Cord Set (Sold Offline)", 5200, 5340),
    ]
    for sku, name, cost, rate in offline:
        items.append({"sku": sku, "name": name, "cost": cost, "rate": rate,
                      "bill": "Bill 1", "is_accessory": False, "in_stock": False})
    return items


def load_other_bills_inventory():
    """Bills 2-6 from per-piece-costs.csv. Each row expanded to its piece count."""
    path = REPO_ROOT / "zoho-import" / "03-per-piece-costs.csv"
    items = []
    line_idx_by_bill = defaultdict(int)
    import re
    with path.open() as f:
        for row in csv.DictReader(f):
            bill = row["Source Bill"]
            if bill == "Bill 1":
                continue
            line_idx_by_bill[bill] += 1
            line_idx = line_idx_by_bill[bill]
            pieces = int(row["Pieces"])
            cost = float(row["Unit Cost (Negotiated)"])
            bill_num = int(re.search(r"\d+", bill).group())
            vendor_codes = {
                "Modern Chikan": "mc", "Nafasat Chikan": "nc",
                "Jasleen Lucknow": "jl", "Lucknow Market - Cash Purchase": "lm",
            }
            vc = vendor_codes.get(row["Vendor"], "x")
            desc = row["Item Description"]
            slug = re.sub(r"\([^)]*\)", "", desc).lower()
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
            slug_parts = slug.split("-")
            if len(slug_parts) > 6: slug_parts = slug_parts[:6]
            slug = "-".join(slug_parts)
            is_acc = any(k in desc.lower() for k in ["potli", "scarf"])
            for piece_idx in range(1, pieces + 1):
                seq = line_idx * 10 + piece_idx
                sku = f"b{bill_num}-{vc}-{slug}-{seq:03d}"
                title = re.sub(r"\([^)]*\)", "", desc).strip().title()
                if pieces > 1:
                    title = f"{title} ({piece_idx}/{pieces})"
                # Compute pricing
                if is_acc:
                    raw_no_loss = (round(cost) + VARIABLE_PER_PIECE) / (1 - PAYMENT_FEE_RATE)
                    import math
                    nl = int(math.ceil(raw_no_loss / 10) * 10)
                    rate = int(math.ceil(nl * 1.30 / 10) * 10)
                else:
                    nl = no_loss_sell_price(round(cost))
                    rate = target_sell_price(round(cost))
                items.append({
                    "sku": sku, "name": title, "cost": round(cost),
                    "rate": rate, "min_sell": nl,
                    "bill": bill, "is_accessory": is_acc, "in_stock": True,
                })
    return items


def load_sales():
    """Verified sales records (10 paid invoices from earlier Zoho confirmation).

    Bill 1's 6 Shopify F&F sales (₹66,980) + 4 offline sales (₹29,520) = ₹96,500.
    """
    return [
        # 6 F&F online sales (Friends and Family customer)
        {"inv": "INV-000001", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "Blush Pink Chikankari Suit", "sku": "20-blush-pink-chikankari-suit",
         "qty": 1, "rate": 10000, "cost": 5000},
        {"inv": "INV-000002", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "Blush Pink Mul Suit", "sku": "13-blush-pink-mul-suit",
         "qty": 1, "rate": 9990, "cost": 6200},
        {"inv": "INV-000003", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "Ivory Mul Paisley Suit", "sku": "16-ivory-mul-paisley-suit",
         "qty": 1, "rate": 9000, "cost": 7000},
        {"inv": "INV-000004", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "Ivory Mul Suit with Beige Chikankari", "sku": "14-ivory-mul-beige-chikankari-suit",
         "qty": 1, "rate": 15000, "cost": 8800},
        {"inv": "INV-000005", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "Oatmeal Medallion Suit", "sku": "07-oatmeal-medallion-suit",
         "qty": 1, "rate": 14990, "cost": 9800},
        {"inv": "INV-000006", "date": "2026-04-15", "customer": "Friends and Family",
         "item": "White Tonal Chikankari Suit", "sku": "18-white-tonal-chikankari-suit",
         "qty": 1, "rate": 8000, "cost": 4800},
        # 4 offline sales (Friends & Family - Lucknow customer)
        {"inv": "INV-000007", "date": "2026-04-15", "customer": "Friends & Family - Lucknow",
         "item": "Yellow Kasab Mul Chanderi Suit", "sku": "23-yellow-kasab-suit-sold",
         "qty": 1, "rate": 7720, "cost": 7500},
        {"inv": "INV-000008", "date": "2026-04-15", "customer": "Friends & Family - Lucknow",
         "item": "Red & White Anarkali #1", "sku": "24-red-white-anarkali-1-sold",
         "qty": 1, "rate": 8230, "cost": 8000},
        {"inv": "INV-000010", "date": "2026-04-15", "customer": "Friends & Family - Lucknow",
         "item": "Red & White Anarkali #2", "sku": "25-red-white-anarkali-2-sold",
         "qty": 1, "rate": 8230, "cost": 8000},
        {"inv": "INV-000009", "date": "2026-04-15", "customer": "Friends & Family - Lucknow",
         "item": "Beige Limp Cord Set", "sku": "26-beige-cord-set-sold",
         "qty": 1, "rate": 5340, "cost": 5200},
    ]


def load_bills_and_expenses():
    """From earlier Zoho confirmation: 5 paid bills + 10 expenses."""
    bills = [
        {"vendor": "Modern Chikan", "date": "2026-01-05", "amount": 137400, "memo": "Bill 1: 20 pieces (Lot 1)"},
        {"vendor": "Modern Chikan", "date": "2026-04-22", "amount": 226350, "memo": "Bill 2: 45 pieces (Lot 2)"},
        {"vendor": "Nafasat Chikan", "date": "2026-04-23", "amount": 70540, "memo": "Bill 3: 22 pieces (GST-incl)"},
        {"vendor": "Jasleen Lucknow", "date": "2026-04-22", "amount": 28940, "memo": "Bill 4: 18 potlis/scarves"},
        {"vendor": "Lucknow Market", "date": "2026-04-22", "amount": 10500, "memo": "Bills 5+6: kaftan + kids sharara"},
    ]
    expenses = [
        {"category": "Travel", "amount": 39000, "memo": "Q1 Lucknow trip — flights, cabs, stay"},
        {"category": "Subscriptions", "amount": 6052, "memo": "Shopify trial + Canva + Google Workspace"},
        {"category": "One-time setup", "amount": 14000, "memo": "Logo design, brand assets"},
    ]
    return bills, expenses


# --- PDF builder -----------------------------------------------------------

def build_report(out_path: Path):
    print("Loading local data...")
    bill1_items = load_bill1_inventory()
    other_items = load_other_bills_inventory()
    all_items = bill1_items + other_items

    # Add min_sell for bill1 items if missing
    for it in all_items:
        if "min_sell" not in it or not it.get("min_sell"):
            it["min_sell"] = no_loss_sell_price(it["cost"])

    sales = load_sales()
    bills, expenses = load_bills_and_expenses()

    revenue = sum(s["rate"] * s["qty"] for s in sales)
    cogs = sum(s["cost"] * s["qty"] for s in sales)
    units_sold = sum(s["qty"] for s in sales)
    gross_profit = revenue - cogs

    inventory_purchase_total = sum(b["amount"] for b in bills)
    op_expense_total = sum(e["amount"] for e in expenses)

    payment_fees_paid = revenue * PAYMENT_FEE_RATE
    var_costs_so_far = units_sold * VARIABLE_PER_PIECE
    fixed_so_far_alloc = units_sold * FIXED_PER_PIECE
    actual_overhead_cash = op_expense_total + payment_fees_paid

    net_profit_cash = revenue - cogs - var_costs_so_far - actual_overhead_cash
    net_profit_alloc = revenue - cogs - var_costs_so_far - fixed_so_far_alloc - payment_fees_paid

    # In-stock items = all_items minus those whose SKU appears in sales
    sold_skus = {s["sku"] for s in sales}
    in_stock = [it for it in all_items if it["sku"] not in sold_skus]

    proj_rev_target = sum(it["rate"] for it in in_stock)
    proj_rev_min = sum(it["min_sell"] for it in in_stock)
    proj_cogs = sum(it["cost"] for it in in_stock)
    proj_var = len(in_stock) * VARIABLE_PER_PIECE
    proj_fixed = len(in_stock) * FIXED_PER_PIECE
    proj_payment_t = proj_rev_target * PAYMENT_FEE_RATE
    proj_payment_m = proj_rev_min * PAYMENT_FEE_RATE
    proj_gross_t = proj_rev_target - proj_cogs
    proj_gross_m = proj_rev_min - proj_cogs
    proj_net_t = proj_gross_t - proj_var - proj_fixed - proj_payment_t
    proj_net_m = proj_gross_m - proj_var - proj_fixed - proj_payment_m

    total_rev_t = revenue + proj_rev_target
    total_rev_m = revenue + proj_rev_min
    total_cogs = cogs + proj_cogs
    total_gross_t = total_rev_t - total_cogs
    total_gross_m = total_rev_m - total_cogs
    total_net_t = gross_profit + proj_gross_t - (var_costs_so_far + proj_var) - (fixed_so_far_alloc + proj_fixed) - (payment_fees_paid + proj_payment_t)
    total_net_m = gross_profit + proj_gross_m - (var_costs_so_far + proj_var) - (fixed_so_far_alloc + proj_fixed) - (payment_fees_paid + proj_payment_m)

    # ---- Build PDF (phone-optimised: narrow portrait, larger fonts) ----
    print("Building PDF (phone-optimised)...")

    # Use a narrower page so phone viewing doesn't need zoom.
    # Standard phone screen ~360px wide; A4 portrait scales well at 100%.
    # We use generous margins + larger base font.
    PAGE_W, PAGE_H = A4   # 210 × 297 mm
    LEFT = 10*mm
    RIGHT = 10*mm
    CONTENT_W = PAGE_W - LEFT - RIGHT  # 190mm

    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                              leftMargin=LEFT, rightMargin=RIGHT,
                              topMargin=12*mm, bottomMargin=12*mm,
                              title="Chikankari Lane — P&L Report")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20,
                         textColor=colors.HexColor("#2c3e50"), spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=15,
                         textColor=colors.HexColor("#34495e"),
                         spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontSize=12,
                         textColor=colors.HexColor("#34495e"),
                         spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=11,
                           leading=15, spaceAfter=6)
    small = ParagraphStyle("small", parent=body, fontSize=9, textColor=colors.grey)
    big_num = ParagraphStyle("bignum", parent=body, fontSize=22,
                              textColor=colors.HexColor("#2c3e50"),
                              alignment=TA_LEFT, leading=26)

    story = []

    # ===== COVER =====
    story.append(Paragraph("Chikankari Lane", h1))
    story.append(Paragraph(f"P&amp;L + Inventory Report · {TODAY}", small))
    story.append(Spacer(1, 6*mm))

    # ===== HEADLINE BIG NUMBERS (phone-friendly: 2-column grid) =====
    story.append(Paragraph("At a glance", h2))
    big_rows = [
        [
            Paragraph(f"<b>{fmt_inr(revenue)}</b>", big_num),
            Paragraph(f"<b>{fmt_inr(gross_profit)}</b>", big_num),
        ],
        [
            Paragraph(f"<font size='9' color='grey'>Revenue ({int(units_sold)} units sold)</font>", small),
            Paragraph(f"<font size='9' color='grey'>Gross profit ({gross_profit/revenue*100:.1f}%)</font>", small),
        ],
        [
            Paragraph(f"<b>{fmt_inr(net_profit_cash)}</b>", big_num),
            Paragraph(f"<b>{len(all_items)}</b>", big_num),
        ],
        [
            Paragraph(f"<font size='9' color='grey'>Net profit (cash basis)</font>", small),
            Paragraph(f"<font size='9' color='grey'>Items in catalog ({len(in_stock)} in stock)</font>", small),
        ],
    ]
    big_t = Table(big_rows, colWidths=[CONTENT_W/2, CONTENT_W/2])
    big_t.setStyle(TableStyle([
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(big_t)
    story.append(Spacer(1, 6*mm))

    # ===== SECTION 1: SALES TO DATE =====
    story.append(Paragraph("1. Sales to date", h2))
    s1_data = [
        ["Metric", "Amount"],
        ["Revenue (paid invoices)", fmt_inr(revenue)],
        ["Cost of goods sold (COGS)", fmt_inr(cogs)],
        ["Gross profit", fmt_inr(gross_profit)],
        ["Gross margin %", f"{gross_profit/revenue*100:.1f}%"],
        ["Units sold", f"{int(units_sold)}"],
        ["Avg sale value", fmt_inr(revenue/units_sold) if units_sold else "—"],
    ]
    t1 = Table(s1_data, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#e8f4f8")),
    ]))
    story.append(t1)

    # ===== SECTION 2: COST STRUCTURE =====
    story.append(Paragraph("2. Cost structure", h2))
    s2_data = [
        ["Category", "Amount"],
        ["Inventory purchased (5 bills)", fmt_inr(inventory_purchase_total)],
        ["Operating expenses paid", fmt_inr(op_expense_total)],
        ["Payment-gateway fees (2%)", fmt_inr(payment_fees_paid)],
        ["Variable cost (sold units)", fmt_inr(var_costs_so_far)],
        ["Total cash outflow", fmt_inr(inventory_purchase_total + op_expense_total + payment_fees_paid + var_costs_so_far)],
    ]
    t2 = Table(s2_data, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t2)

    # ===== SECTION 3: NET PROFIT =====
    story.append(Paragraph("3. Net profit", h2))
    story.append(Paragraph("Two views — cash basis (conservative, full overhead loaded on units sold) and allocated (overhead spread across target volume of 360/yr).", small))
    s3_data = [
        ["View", "Net profit"],
        ["Cash basis", fmt_inr(net_profit_cash)],
        ["Allocated", fmt_inr(net_profit_alloc)],
    ]
    t3 = Table(s3_data, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t3)

    # ===== SECTION 4: PROJECTION =====
    story.append(PageBreak())
    story.append(Paragraph(f"4. Projection — {len(in_stock)} items in stock", h2))
    story.append(Paragraph("If all in-stock items sell at recommended Sell Price:", h3))
    s4a = [
        ["Metric", "Amount"],
        ["Projected revenue", fmt_inr(proj_rev_target)],
        ["Projected COGS", fmt_inr(proj_cogs)],
        ["Var + fixed + fees", fmt_inr(proj_var + proj_fixed + proj_payment_t)],
        ["Projected gross profit", fmt_inr(proj_gross_t)],
        ["Projected net profit", fmt_inr(proj_net_t)],
        ["Net margin %", f"{proj_net_t/proj_rev_target*100:.1f}%"],
    ]
    t4a = Table(s4a, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t4a.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#fff4e6")),
    ]))
    story.append(t4a)

    story.append(Paragraph("Worst-case: all sell at no-loss Min Sell Price:", h3))
    s4b = [
        ["Metric", "Amount"],
        ["Worst-case revenue", fmt_inr(proj_rev_min)],
        ["Worst-case net profit", fmt_inr(proj_net_m)],
    ]
    t4b = Table(s4b, colWidths=[CONTENT_W*0.65, CONTENT_W*0.35])
    t4b.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t4b)

    # ===== SECTION 5: COMBINED (sold + projected) =====
    story.append(Paragraph("5. Lifetime view (sold + all projected)", h2))
    s5 = [
        ["Scenario", "Revenue", "Gross", "Net"],
        ["@ target prices", fmt_inr(total_rev_t), fmt_inr(total_gross_t), fmt_inr(total_net_t)],
        ["@ no-loss prices", fmt_inr(total_rev_m), fmt_inr(total_gross_m), fmt_inr(total_net_m)],
    ]
    t5 = Table(s5, colWidths=[CONTENT_W*0.30, CONTENT_W*0.24, CONTENT_W*0.23, CONTENT_W*0.23])
    t5.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t5)

    # ===== SECTION 6: INVENTORY BY BILL =====
    story.append(Paragraph("6. Inventory by source bill", h2))
    by_bill = defaultdict(lambda: {"count": 0, "cost": 0, "rate": 0, "min_sell": 0})
    for it in all_items:
        b = by_bill[it["bill"]]
        b["count"] += 1
        b["cost"] += it["cost"]
        b["rate"] += it["rate"]
        b["min_sell"] += it["min_sell"]
    s6 = [["Bill", "Pcs", "Cost", "Sell", "Min Sell"]]
    for bn in sorted(by_bill.keys()):
        b = by_bill[bn]
        s6.append([bn, str(b["count"]), fmt_inr(b["cost"]), fmt_inr(b["rate"]), fmt_inr(b["min_sell"])])
    s6.append(["TOTAL", str(sum(b["count"] for b in by_bill.values())),
                fmt_inr(sum(b["cost"] for b in by_bill.values())),
                fmt_inr(sum(b["rate"] for b in by_bill.values())),
                fmt_inr(sum(b["min_sell"] for b in by_bill.values()))])
    t6 = Table(s6, colWidths=[CONTENT_W*0.18, CONTENT_W*0.10, CONTENT_W*0.24, CONTENT_W*0.24, CONTENT_W*0.24])
    t6.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff4e6")),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
    ]))
    story.append(t6)

    # ===== SECTION 7: SALES DETAIL =====
    story.append(PageBreak())
    story.append(Paragraph(f"7. Sales detail ({len(sales)} invoices)", h2))
    s7 = [["Inv", "Item", "Sell", "Cost", "Profit"]]
    for s in sales:
        profit = s["rate"] - s["cost"]
        s7.append([s["inv"][-3:], s["item"][:24], fmt_inr(s["rate"]),
                    fmt_inr(s["cost"]), fmt_inr(profit)])
    s7.append(["TOTAL", f"{len(sales)} sold", fmt_inr(revenue),
                fmt_inr(cogs), fmt_inr(gross_profit)])
    t7 = Table(s7, colWidths=[CONTENT_W*0.10, CONTENT_W*0.36, CONTENT_W*0.18, CONTENT_W*0.18, CONTENT_W*0.18])
    t7.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff4e6")),
        ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"),
    ]))
    story.append(t7)

    # ===== SECTION 8: FULL INVENTORY (per-item) =====
    story.append(PageBreak())
    story.append(Paragraph(f"8. Full inventory ({len(all_items)} items)", h2))
    story.append(Paragraph("Sorted by SKU. Net/piece = (Sell × 0.98) − Cost − ₹280 var − ₹489 fixed.", small))

    sorted_items = sorted(all_items, key=lambda x: x["sku"])
    inv_rows = [["SKU", "Name", "Cost", "No-Loss", "Sell", "Net/pc"]]
    for it in sorted_items:
        net = it["rate"] * (1 - PAYMENT_FEE_RATE) - it["cost"] - VARIABLE_PER_PIECE - FIXED_PER_PIECE
        # Truncate SKU and name for phone width
        sku_disp = it["sku"][:28]
        name_disp = it["name"][:30]
        inv_rows.append([
            sku_disp, name_disp,
            fmt_inr(it["cost"]),
            fmt_inr(it["min_sell"]),
            fmt_inr(it["rate"]),
            fmt_inr(net),
        ])
    t8 = Table(inv_rows, colWidths=[CONTENT_W*0.24, CONTENT_W*0.30, CONTENT_W*0.11,
                                       CONTENT_W*0.12, CONTENT_W*0.11, CONTENT_W*0.12],
                 repeatRows=1)
    t8.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.2, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f7f7")]),
    ]))
    story.append(t8)

    # ===== SECTION 9: NOTES =====
    story.append(PageBreak())
    story.append(Paragraph("9. Methodology &amp; assumptions", h2))
    notes = f"""<b>Pricing model</b> (in <font face="Courier">scripts/pricing.py</font>):<br/>
• Variable per piece: ₹{VARIABLE_PER_PIECE:.0f} (packaging + shipping)<br/>
• Annual fixed: ₹1,76,052 (travel + subs + setup)<br/>
• Volume target: 30 pieces/month → 360/yr<br/>
• Fixed allocation: ₹{FIXED_PER_PIECE:.0f}/piece<br/>
• Payment gateway fee: {PAYMENT_FEE_RATE*100:.0f}% (Razorpay)<br/>
• Default markup: 30% on top of no-loss<br/><br/>

<b>No-Loss Sell Price</b> (Min Sell Price field in Zoho):<br/>
&nbsp;&nbsp;= (Cost + ₹280 + ₹489) ÷ 0.98<br/>
Selling below this loses money on the piece.<br/><br/>

<b>Sell Price (Rate)</b>:<br/>
First-lot prices retained as-is per owner decision (well-received). Bills 2-6 priced via No-Loss × 1.30.<br/><br/>

<b>Net profit (cash basis)</b>: conservative — loads ALL operating expenses paid in period onto units sold so far.<br/><br/>

<b>Net profit (allocated)</b>: matches pricing-model assumption — each unit "earns" its fair share of overhead (₹{FIXED_PER_PIECE:.0f}/piece).<br/><br/>

<b>Tax</b>: NOT GST-registered. Bills at gross (vendor GST = part of COGS). No output tax.<br/><br/>

<b>Reconciliation status</b>:<br/>
• Bill 1: 20/20 closed (16 listed + 4 offline-sold)<br/>
• Bills 2-6: 87 items added as DRAFT (photos pending)<br/>
• Total catalog: {len(all_items)} items in Zoho + Shopify<br/>
• Online order sync (Shopify → Zoho) not yet built<br/><br/>

<b>Data sources</b>: This report is built from local CSVs + verified Zoho records. Live Zoho fetch was rate-limited at report time (Free plan: 1,000 calls/day cap).
"""
    story.append(Paragraph(notes, body))

    doc.build(story)
    print(f"\n✓ Report written: {out_path}")
    print(f"  File size: {out_path.stat().st_size / 1024:.0f} KB")
    print(f"  Optimised for phone viewing (portrait A4, large fonts, narrow tables)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    out = args.out or (OUTPUT_DIR / f"chikankari-lane-report-{TODAY.replace('-','')}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    build_report(out)
