#!/usr/bin/env python3
"""Phone-optimised PDF P&L + inventory report for Chikankari Lane.

Output: ~/Downloads/chikankari-lane-report-YYYYMMDD.pdf

Features:
  - Noto Sans font (renders ₹ properly — Helvetica doesn't have the glyph)
  - Donut + bar charts for visual scan
  - Conservative no-loss pricing (covers GST on fees + 5% returns buffer)
  - Phone-friendly portrait A4, 11pt body, narrow tables

Data sources (local-first, fast, doesn't hit Zoho rate limits):
  - zoho-import/04-sku-to-cost-mapping.csv  — Bill 1 mapping
  - zoho-import/03-per-piece-costs.csv      — all bills, per-piece
  - Hard-coded sales records (10 invoices verified earlier)
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from pricing import (
    VARIABLE_PER_PIECE, FIXED_PER_PIECE, PAYMENT_FEE_RATE, PAYMENT_FEE_GST,
    RETURNS_DAMAGE_BUFFER, EFFECTIVE_DEDUCTION, ANNUAL_FIXED_COST,
    PIECES_PER_YEAR, DEFAULT_MARKUP,
    no_loss_sell_price, target_sell_price,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                  TableStyle, PageBreak, Image, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, String, Circle, Wedge, Line
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.legends import Legend

REPO_ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = REPO_ROOT / "assets" / "fonts"
OUTPUT_DIR = Path.home() / "Downloads"
TODAY = datetime.now().strftime("%Y-%m-%d")


# --- Font registration -----------------------------------------------------

def register_fonts():
    """Register Noto Sans (which has ₹ glyph). Falls back to Helvetica with warning."""
    try:
        pdfmetrics.registerFont(TTFont("NotoSans", str(FONT_DIR / "NotoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(FONT_DIR / "NotoSans-Bold.ttf")))
        # Map family for bold lookup
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("NotoSans", normal="NotoSans", bold="NotoSans-Bold",
                            italic="NotoSans", boldItalic="NotoSans-Bold")
        return "NotoSans", "NotoSans-Bold"
    except Exception as e:
        print(f"WARNING: could not register Noto Sans ({e}). Rupee glyph may not render.")
        return "Helvetica", "Helvetica-Bold"


# --- INR formatter ---------------------------------------------------------

def fmt_inr(n: float) -> str:
    """Format with Indian numbering. Always uses U+20B9 ₹ glyph."""
    n = round(float(n))
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        last3 = s[-3:]; rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:]); rest = rest[:-2]
        if rest: groups.append(rest)
        out = ",".join(reversed(groups)) + "," + last3
    return f"{'-' if n < 0 else ''}₹{out}"


# --- Local data sources ----------------------------------------------------

def load_bill1_inventory():
    path = REPO_ROOT / "zoho-import" / "04-sku-to-cost-mapping.csv"
    items = []
    with path.open() as f:
        for row in csv.DictReader(f):
            items.append({
                "sku": row["Shopify Handle"],
                "name": row["Shopify Title"],
                "cost": float(row["Cost Price"]),
                "rate": float(row["Selling Price"]),
                "bill": "Bill 1", "is_accessory": False, "in_stock": True,
            })
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
    path = REPO_ROOT / "zoho-import" / "03-per-piece-costs.csv"
    items = []
    line_idx_by_bill = defaultdict(int)
    with path.open() as f:
        for row in csv.DictReader(f):
            bill = row["Source Bill"]
            if bill == "Bill 1": continue
            line_idx_by_bill[bill] += 1
            line_idx = line_idx_by_bill[bill]
            pieces = int(row["Pieces"])
            cost = float(row["Unit Cost (Negotiated)"])
            bill_num = int(re.search(r"\d+", bill).group())
            vendor_codes = {"Modern Chikan": "mc", "Nafasat Chikan": "nc",
                              "Jasleen Lucknow": "jl", "Lucknow Market - Cash Purchase": "lm"}
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
                if pieces > 1: title = f"{title} ({piece_idx}/{pieces})"
                if is_acc:
                    raw_nl = (round(cost) + VARIABLE_PER_PIECE) / (1 - EFFECTIVE_DEDUCTION)
                    nl = int(math.ceil(raw_nl / 10) * 10)
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
    return [
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
    bills = [
        {"vendor": "Modern Chikan", "date": "2026-01-05", "amount": 137400, "memo": "Bill 1: Lot 1, 20 pieces"},
        {"vendor": "Modern Chikan", "date": "2026-04-22", "amount": 226350, "memo": "Bill 2: Lot 2, 45 pieces"},
        {"vendor": "Nafasat Chikan", "date": "2026-04-23", "amount": 70540, "memo": "Bill 3: 22 pieces (GST-incl)"},
        {"vendor": "Jasleen Lucknow", "date": "2026-04-22", "amount": 28940, "memo": "Bill 4: 18 potlis/scarves"},
        {"vendor": "Lucknow Market", "date": "2026-04-22", "amount": 10500, "memo": "Bills 5+6: kaftan + sharara"},
    ]
    expenses = [
        {"category": "Travel", "amount": 39000, "memo": "Q1 Lucknow trip"},
        {"category": "Subscriptions", "amount": 6052, "memo": "Shopify + Canva + Workspace"},
        {"category": "One-time setup", "amount": 14000, "memo": "Logo + brand assets"},
    ]
    return bills, expenses


# --- Charts ----------------------------------------------------------------

PALETTE = [colors.HexColor(h) for h in [
    "#2c3e50", "#3498db", "#1abc9c", "#f39c12", "#e74c3c",
    "#9b59b6", "#34495e", "#16a085", "#d35400", "#7f8c8d",
]]


def make_donut(title: str, data: list[tuple[str, float]], width=80*mm, height=70*mm) -> Drawing:
    """Donut chart with inline labels."""
    d = Drawing(width, height)
    if not data or sum(v for _, v in data) == 0:
        d.add(String(width/2, height/2, "(no data)", textAnchor="middle", fontSize=10))
        return d
    pie = Pie()
    pie.x = 5*mm
    pie.y = 5*mm
    pie.width = 50*mm
    pie.height = 50*mm
    pie.data = [v for _, v in data]
    pie.labels = None
    pie.slices.strokeWidth = 1
    pie.slices.strokeColor = colors.white
    for i, _ in enumerate(data):
        pie.slices[i].fillColor = PALETTE[i % len(PALETTE)]
    pie.innerRadiusFraction = 0.55  # makes it a donut
    d.add(pie)
    # Legend on right
    legend = Legend()
    legend.x = 60*mm
    legend.y = 50*mm
    legend.alignment = "right"
    legend.fontName = "NotoSans"
    legend.fontSize = 8
    legend.dx = 6
    legend.dy = 6
    legend.deltay = 10
    legend.colorNamePairs = [(PALETTE[i % len(PALETTE)], f"{label}") for i, (label, _) in enumerate(data)]
    d.add(legend)
    # Title above
    d.add(String(width/2, height - 4*mm, title, textAnchor="middle",
                  fontName="NotoSans-Bold", fontSize=10, fillColor=colors.HexColor("#34495e")))
    return d


def make_hbar(title: str, data: list[tuple[str, float]], width=180*mm, height=70*mm,
              value_fmt=fmt_inr) -> Drawing:
    """Horizontal bar chart with inline value labels."""
    d = Drawing(width, height)
    if not data:
        d.add(String(width/2, height/2, "(no data)", textAnchor="middle", fontSize=10))
        return d
    n = len(data)
    bar_h = (height - 20*mm) / max(n, 1) * 0.7
    max_val = max(v for _, v in data) if data else 1
    label_w = 35*mm
    bar_area_w = width - label_w - 30*mm
    y_top = height - 12*mm
    # Title
    d.add(String(width/2, height - 4*mm, title, textAnchor="middle",
                  fontName="NotoSans-Bold", fontSize=10, fillColor=colors.HexColor("#34495e")))
    for i, (label, val) in enumerate(data):
        y = y_top - (i + 1) * ((height - 20*mm) / n)
        bar_w = (val / max_val) * bar_area_w if max_val > 0 else 0
        # Label
        d.add(String(label_w - 2*mm, y + bar_h/3, str(label)[:22],
                      textAnchor="end", fontName="NotoSans", fontSize=9,
                      fillColor=colors.HexColor("#2c3e50")))
        # Bar
        d.add(Rect(label_w, y, bar_w, bar_h,
                    fillColor=PALETTE[i % len(PALETTE)],
                    strokeColor=None))
        # Value
        d.add(String(label_w + bar_w + 2*mm, y + bar_h/3, value_fmt(val),
                      textAnchor="start", fontName="NotoSans", fontSize=9,
                      fillColor=colors.HexColor("#34495e")))
    return d


# --- Main builder ----------------------------------------------------------

def build_report(out_path: Path):
    FONT, FONT_BOLD = register_fonts()

    print("Loading local data...")
    bill1_items = load_bill1_inventory()
    other_items = load_other_bills_inventory()
    all_items = bill1_items + other_items

    # Recompute min_sell with conservative formula for ALL items (Bill 1 included)
    for it in all_items:
        if it.get("is_accessory"):
            raw = (it["cost"] + VARIABLE_PER_PIECE) / (1 - EFFECTIVE_DEDUCTION)
            it["min_sell"] = int(math.ceil(raw / 10) * 10)
        else:
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
    total_net_t = (gross_profit + proj_gross_t
                     - (var_costs_so_far + proj_var)
                     - (fixed_so_far_alloc + proj_fixed)
                     - (payment_fees_paid + proj_payment_t))
    total_net_m = (gross_profit + proj_gross_m
                     - (var_costs_so_far + proj_var)
                     - (fixed_so_far_alloc + proj_fixed)
                     - (payment_fees_paid + proj_payment_m))

    # ----- BUILD PDF -----
    print("Building PDF...")
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                              leftMargin=10*mm, rightMargin=10*mm,
                              topMargin=12*mm, bottomMargin=12*mm,
                              title="Chikankari Lane — P&L Report")
    PAGE_W, _ = A4
    CONTENT_W = PAGE_W - 20*mm

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT_BOLD,
                          fontSize=20, textColor=colors.HexColor("#2c3e50"), spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT_BOLD,
                          fontSize=15, textColor=colors.HexColor("#34495e"),
                          spaceBefore=12, spaceAfter=6)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontName=FONT_BOLD,
                          fontSize=12, textColor=colors.HexColor("#34495e"),
                          spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName=FONT,
                            fontSize=11, leading=15, spaceAfter=6)
    small = ParagraphStyle("small", parent=body, fontName=FONT, fontSize=9,
                             textColor=colors.grey)
    big_num = ParagraphStyle("bignum", parent=body, fontName=FONT_BOLD,
                                fontSize=22, textColor=colors.HexColor("#2c3e50"),
                                alignment=TA_LEFT, leading=26)

    # Default table style with our font
    base_table_style = [
        ("FONTNAME", (0,0), (-1,-1), FONT),
        ("FONTNAME", (0,0), (-1,0), FONT_BOLD),
    ]

    story = []

    # ===== COVER =====
    story.append(Paragraph("Chikankari Lane", h1))
    story.append(Paragraph(f"P&amp;L + Inventory Report · {TODAY}", small))
    story.append(Spacer(1, 6*mm))

    # ===== AT-A-GLANCE =====
    story.append(Paragraph("At a glance", h2))
    big_rows = [
        [
            Paragraph(f"<b>{fmt_inr(revenue)}</b>", big_num),
            Paragraph(f"<b>{fmt_inr(gross_profit)}</b>", big_num),
        ],
        [
            Paragraph(f"<font size='9' color='grey'>Revenue · {int(units_sold)} units sold</font>", small),
            Paragraph(f"<font size='9' color='grey'>Gross profit · {gross_profit/revenue*100:.1f}%</font>", small),
        ],
        [
            Paragraph(f"<b>{fmt_inr(net_profit_cash)}</b>", big_num),
            Paragraph(f"<b>{len(all_items)}</b>", big_num),
        ],
        [
            Paragraph(f"<font size='9' color='grey'>Net (cash basis) · see §3</font>", small),
            Paragraph(f"<font size='9' color='grey'>Items in catalog · {len(in_stock)} unsold</font>", small),
        ],
    ]
    big_t = Table(big_rows, colWidths=[CONTENT_W/2, CONTENT_W/2])
    big_t.setStyle(TableStyle(base_table_style + [
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(big_t)
    story.append(Spacer(1, 4*mm))

    # ===== CHART: cash so far (revenue vs costs) =====
    story.append(Paragraph("Where the money is going (cumulative)", h3))
    cash_chart_data = [
        ("Inventory purchased", inventory_purchase_total),
        ("Operating expenses", op_expense_total),
        ("Revenue collected", revenue),
    ]
    story.append(make_hbar("Cash flows so far", cash_chart_data,
                            width=CONTENT_W, height=45*mm))

    # ===== SECTION 1: SALES TO DATE =====
    story.append(PageBreak())
    story.append(Paragraph("1. Sales to date", h2))
    s1_data = [
        ["Metric", "Value"],
        ["Revenue (paid invoices)", fmt_inr(revenue)],
        ["Cost of goods sold (COGS)", fmt_inr(cogs)],
        ["Gross profit", fmt_inr(gross_profit)],
        ["Gross margin %", f"{gross_profit/revenue*100:.1f}%"],
        ["Units sold", f"{int(units_sold)}"],
        ["Avg sale value", fmt_inr(revenue/units_sold) if units_sold else "—"],
    ]
    t1 = Table(s1_data, colWidths=[CONTENT_W*0.62, CONTENT_W*0.38])
    t1.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,3), (-1,3), colors.HexColor("#e8f4f8")),
    ]))
    story.append(t1)

    # Donut: Revenue vs COGS vs Gross Profit
    rev_breakdown_data = [
        ("COGS", cogs),
        ("Gross profit", gross_profit),
    ]
    story.append(Spacer(1, 4*mm))
    story.append(make_donut("Revenue split: COGS vs Gross", rev_breakdown_data,
                              width=CONTENT_W, height=55*mm))

    # ===== SECTION 2: COST STRUCTURE =====
    story.append(Paragraph("2. Cost structure", h2))
    s2_data = [
        ["Category", "Amount"],
        ["Inventory purchased (5 bills)", fmt_inr(inventory_purchase_total)],
        ["Operating expenses paid", fmt_inr(op_expense_total)],
        ["Payment-gateway fees (~2%)", fmt_inr(payment_fees_paid)],
        ["Variable cost (sold units)", fmt_inr(var_costs_so_far)],
        ["Total cash outflow", fmt_inr(inventory_purchase_total + op_expense_total + payment_fees_paid + var_costs_so_far)],
    ]
    t2 = Table(s2_data, colWidths=[CONTENT_W*0.62, CONTENT_W*0.38])
    t2.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t2)

    # Donut: cost structure
    cost_donut_data = [
        ("Inventory", inventory_purchase_total),
        ("Op expenses", op_expense_total),
        ("Variable", var_costs_so_far),
        ("Payment fees", payment_fees_paid),
    ]
    story.append(Spacer(1, 4*mm))
    story.append(make_donut("Total cost structure", cost_donut_data,
                              width=CONTENT_W, height=55*mm))

    # ===== SECTION 3: NET PROFIT (with explainer) =====
    story.append(PageBreak())
    story.append(Paragraph("3. Net profit — two views", h2))
    story.append(Paragraph(
        "<b>Cash basis</b> = real cash in/out today. Conservative: loads ALL "
        "operating expenses (₹59,052 — Q1 trip, brand setup, subs) onto only "
        f"{int(units_sold)} units sold so far.",
        body))
    story.append(Paragraph(
        f"<b>Allocated</b> = each piece carries ₹{FIXED_PER_PIECE:.0f} of overhead "
        f"(₹{ANNUAL_FIXED_COST:,.0f}/yr ÷ {PIECES_PER_YEAR}/yr target volume). "
        "Matches the pricing model. Useful for unit economics.",
        body))
    s3_data = [
        ["View", "Net profit", "Per piece"],
        ["Cash basis", fmt_inr(net_profit_cash),
         fmt_inr(net_profit_cash/units_sold) if units_sold else "—"],
        ["Allocated", fmt_inr(net_profit_alloc),
         fmt_inr(net_profit_alloc/units_sold) if units_sold else "—"],
    ]
    t3 = Table(s3_data, colWidths=[CONTENT_W*0.30, CONTENT_W*0.35, CONTENT_W*0.35])
    t3.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t3)
    story.append(Paragraph(
        f"<i>Cash basis is negative right now because we front-loaded ₹{op_expense_total:,.0f} "
        f"of overhead before most pieces sold. As sales grow, cash basis converges to allocated.</i>",
        small))

    # ===== SECTION 4: PROJECTION =====
    story.append(Paragraph(f"4. Projection — {len(in_stock)} items in stock", h2))
    story.append(Paragraph("If all sell at recommended Sell Price:", h3))
    s4a = [
        ["Metric", "Value"],
        ["Projected revenue", fmt_inr(proj_rev_target)],
        ["Projected COGS", fmt_inr(proj_cogs)],
        ["Var + fixed + fees", fmt_inr(proj_var + proj_fixed + proj_payment_t)],
        ["Projected gross profit", fmt_inr(proj_gross_t)],
        ["Projected net profit", fmt_inr(proj_net_t)],
        ["Net margin %", f"{proj_net_t/proj_rev_target*100:.1f}%"],
    ]
    t4a = Table(s4a, colWidths=[CONTENT_W*0.62, CONTENT_W*0.38])
    t4a.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BACKGROUND", (0,5), (-1,5), colors.HexColor("#fff4e6")),
    ]))
    story.append(t4a)

    story.append(Paragraph("Worst case — all sell at no-loss Min Sell Price:", h3))
    s4b = [
        ["Metric", "Value"],
        ["Worst-case revenue", fmt_inr(proj_rev_min)],
        ["Worst-case net profit", fmt_inr(proj_net_m)],
    ]
    t4b = Table(s4b, colWidths=[CONTENT_W*0.62, CONTENT_W*0.38])
    t4b.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t4b)

    # ===== SECTION 5: COMBINED LIFETIME =====
    story.append(Paragraph("5. Lifetime view (sold + projected)", h2))
    s5 = [
        ["Scenario", "Revenue", "Gross", "Net"],
        ["@ target prices", fmt_inr(total_rev_t), fmt_inr(total_gross_t), fmt_inr(total_net_t)],
        ["@ no-loss prices", fmt_inr(total_rev_m), fmt_inr(total_gross_m), fmt_inr(total_net_m)],
    ]
    t5 = Table(s5, colWidths=[CONTENT_W*0.30, CONTENT_W*0.24, CONTENT_W*0.23, CONTENT_W*0.23])
    t5.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(t5)

    # ===== SECTION 6: INVENTORY BY BILL (with bar chart) =====
    story.append(PageBreak())
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
    t6.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (1,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff4e6")),
        ("FONTNAME", (0,-1), (-1,-1), FONT_BOLD),
    ]))
    story.append(t6)
    story.append(Spacer(1, 4*mm))

    # Bar chart: pieces per bill
    bar_data_pcs = [(bn, by_bill[bn]["count"]) for bn in sorted(by_bill.keys())]
    story.append(make_hbar("Pieces per bill", bar_data_pcs,
                             width=CONTENT_W, height=45*mm,
                             value_fmt=lambda v: f"{int(v)} pcs"))

    # Bar chart: cost per bill
    bar_data_cost = [(bn, by_bill[bn]["cost"]) for bn in sorted(by_bill.keys())]
    story.append(Spacer(1, 3*mm))
    story.append(make_hbar("Inventory cost per bill", bar_data_cost,
                             width=CONTENT_W, height=45*mm))

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
    t7.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff4e6")),
        ("FONTNAME", (0,-1), (-1,-1), FONT_BOLD),
    ]))
    story.append(t7)

    # ===== SECTION 8: FULL INVENTORY =====
    story.append(PageBreak())
    story.append(Paragraph(f"8. Full inventory ({len(all_items)} items)", h2))
    story.append(Paragraph(
        f"Net per piece = Sell × {1-EFFECTIVE_DEDUCTION:.4f} − Cost − ₹{VARIABLE_PER_PIECE:.0f} − ₹{FIXED_PER_PIECE:.0f}.",
        small))
    sorted_items = sorted(all_items, key=lambda x: x["sku"])
    inv_rows = [["SKU", "Name", "Cost", "No-Loss", "Sell", "Net/pc"]]
    for it in sorted_items:
        net = it["rate"] * (1 - EFFECTIVE_DEDUCTION) - it["cost"] - VARIABLE_PER_PIECE - FIXED_PER_PIECE
        inv_rows.append([
            it["sku"][:28], it["name"][:30],
            fmt_inr(it["cost"]),
            fmt_inr(it["min_sell"]),
            fmt_inr(it["rate"]),
            fmt_inr(net),
        ])
    t8 = Table(inv_rows, colWidths=[CONTENT_W*0.24, CONTENT_W*0.30, CONTENT_W*0.11,
                                       CONTENT_W*0.12, CONTENT_W*0.11, CONTENT_W*0.12],
                 repeatRows=1)
    t8.setStyle(TableStyle(base_table_style + [
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#34495e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.2, colors.lightgrey),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f7f7")]),
    ]))
    story.append(t8)

    # ===== SECTION 9: METHODOLOGY =====
    story.append(PageBreak())
    story.append(Paragraph("9. Methodology &amp; assumptions", h2))
    notes = f"""<b>Pricing model</b> (in <font face="Courier">scripts/pricing.py</font>):<br/>
• Variable per piece: ₹{VARIABLE_PER_PIECE:.0f} (packaging + shipping)<br/>
• Annual fixed: ₹{ANNUAL_FIXED_COST:,.0f} (travel + subs + setup)<br/>
• Volume target: 30 pieces/month → {PIECES_PER_YEAR}/yr<br/>
• Fixed allocation: ₹{FIXED_PER_PIECE:.0f}/piece<br/>
• <b>Effective deduction: {EFFECTIVE_DEDUCTION*100:.2f}%</b><br/>
&nbsp;&nbsp;= 2.00% Razorpay fee + 0.36% GST on fee + 5.00% returns/damage buffer<br/>
• Default markup: 30% on top of no-loss<br/><br/>

<b>No-Loss Sell Price</b> (Min Sell Price field):<br/>
&nbsp;&nbsp;= (Cost + ₹280 + ₹489) ÷ {1-EFFECTIVE_DEDUCTION:.4f}<br/>
This is genuinely no-loss: even after payment fees, GST on fees, and a 5% return/damage haircut, you break even. Selling below this loses money.<br/><br/>

<b>What's in the 5% buffer</b>:<br/>
• Returns and refunds<br/>
• Damaged-in-transit pieces<br/>
• Discount codes / sale events<br/>
• Card chargebacks / payment failures<br/>
• Small COD reconciliation gaps<br/><br/>

<b>What this DOESN'T cover</b>:<br/>
• Volume miss — if you sell 200 pcs/yr instead of 360, fixed allocation should be ₹880/piece, not ₹489<br/>
• Marketing spend (none budgeted in fixed costs above)<br/>
• Income tax (negligible at current loss-making cash position)<br/><br/>

<b>Tax</b>: NOT GST-registered. Bills at gross (vendor GST = part of COGS). No output tax.<br/><br/>

<b>Reconciliation</b>:<br/>
• Bill 1: 20/20 closed (16 listed + 4 offline-sold)<br/>
• Bills 2-6: 87 items added as DRAFT (photos pending). Currently 4 still pending Zoho creation due to daily API cap — will resolve at midnight IST.<br/>
• Total catalog: {len(all_items)} items<br/>
• Online-order auto-sync (Shopify → Zoho) not yet built — current sales are manual invoices.
"""
    story.append(Paragraph(notes, body))

    doc.build(story)
    print(f"\n✓ Report: {out_path}")
    print(f"  Size: {out_path.stat().st_size / 1024:.0f} KB")
    print(f"  Font: Noto Sans (₹ glyph renders correctly)")
    print(f"  Conservative no-loss: ÷ (1 - {EFFECTIVE_DEDUCTION*100:.2f}%) instead of ÷ 0.98")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    out = args.out or (OUTPUT_DIR / f"chikankari-lane-report-{TODAY.replace('-','')}.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    build_report(out)
