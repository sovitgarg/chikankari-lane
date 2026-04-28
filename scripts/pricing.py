#!/usr/bin/env python3
"""Pricing helpers for Chikankari Lane.

Two pure functions that can be imported anywhere:

  - no_loss_sell_price(cost)        → break-even floor (covers all costs + payment fees)
  - target_sell_price(cost, ...)    → no-loss × (1 + margin) = recommended Shopify price

All inputs are ₹ (INR). Outputs round UP to the nearest ₹10 (we never want to
land below the no-loss floor by a rounding cent).

Usage:
    from pricing import no_loss_sell_price, target_sell_price, breakdown

    floor = no_loss_sell_price(cost=8200)
    rec   = target_sell_price(cost=8200, markup=0.30)
    print(breakdown(cost=8200))      # full table for one item

CLI:
    python3 scripts/pricing.py 8200          → prints breakdown
    python3 scripts/pricing.py --csv items.csv  → adds columns to a CSV with `Cost Price`
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# --- Pricing assumptions (single source of truth) ---------------------------
# Update these here; everything else recomputes automatically.

VARIABLE_PER_PIECE = 280.0          # ₹100 packaging + ₹180 avg shipping
ANNUAL_FIXED_COST = 176_052.0       # ₹156K travel + ₹14K one-time + ₹6,052 subs
PIECES_PER_MONTH = 30               # planning volume (FY27)
PAYMENT_FEE_RATE = 0.02             # Razorpay
DEFAULT_MARKUP = 0.30               # 30% on top of no-loss floor

# Derived
PIECES_PER_YEAR = PIECES_PER_MONTH * 12
FIXED_PER_PIECE = ANNUAL_FIXED_COST / PIECES_PER_YEAR


# --- Public functions -------------------------------------------------------

def round_up_to_10(x: float) -> int:
    """Round up to nearest ₹10. Never round down (don't dip below floor)."""
    return int(math.ceil(x / 10.0) * 10)


def no_loss_sell_price(cost: float, *,
                        variable: float = VARIABLE_PER_PIECE,
                        fixed: float = FIXED_PER_PIECE,
                        payment_fee: float = PAYMENT_FEE_RATE) -> int:
    """Break-even sell price.

    At this price: net revenue (sell - payment fee) exactly covers
    cost + variable + fixed allocation. Profit = 0.

    Formula: (cost + variable + fixed) / (1 - payment_fee)

    Args:
        cost: per-piece purchase cost from vendor (₹)
        variable: per-piece variable cost — packaging + shipping (₹)
        fixed: per-piece allocation of annual fixed cost (₹)
        payment_fee: payment gateway fee as decimal (0.02 = 2%)

    Returns:
        Sell price in ₹, rounded up to nearest ₹10.
    """
    raw = (cost + variable + fixed) / (1.0 - payment_fee)
    return round_up_to_10(raw)


def target_sell_price(cost: float, *,
                       markup: float = DEFAULT_MARKUP,
                       variable: float = VARIABLE_PER_PIECE,
                       fixed: float = FIXED_PER_PIECE,
                       payment_fee: float = PAYMENT_FEE_RATE) -> int:
    """Recommended sell price = no-loss × (1 + markup).

    Args:
        cost: per-piece purchase cost (₹)
        markup: profit markup as decimal on top of no-loss (0.30 = 30%)
        variable, fixed, payment_fee: see no_loss_sell_price

    Returns:
        Sell price in ₹, rounded up to nearest ₹10.
    """
    floor = no_loss_sell_price(cost, variable=variable, fixed=fixed,
                                 payment_fee=payment_fee)
    return round_up_to_10(floor * (1.0 + markup))


@dataclass
class PriceBreakdown:
    cost: float
    variable: float
    fixed: float
    payment_fee_rate: float
    no_loss: int
    target: int
    markup: float

    def __str__(self) -> str:
        return (
            f"  Cost                  ₹{self.cost:>8,.0f}\n"
            f"  + Variable            ₹{self.variable:>8,.0f}  (packaging + shipping)\n"
            f"  + Fixed allocation    ₹{self.fixed:>8,.0f}  (₹{ANNUAL_FIXED_COST:,.0f}/yr ÷ {PIECES_PER_YEAR}/yr)\n"
            f"  Total cost basis      ₹{self.cost + self.variable + self.fixed:>8,.0f}\n"
            f"  ÷ (1 - {self.payment_fee_rate*100:.0f}% payment fee)\n"
            f"  ─────────────────────────────────\n"
            f"  No-loss sell price    ₹{self.no_loss:>8,d}  (break-even)\n"
            f"  × (1 + {self.markup*100:.0f}% markup)\n"
            f"  ─────────────────────────────────\n"
            f"  Target sell price     ₹{self.target:>8,d}  (recommended)\n"
        )


def breakdown(cost: float, markup: float = DEFAULT_MARKUP) -> PriceBreakdown:
    """Full pricing breakdown for one item, suitable for printing."""
    return PriceBreakdown(
        cost=cost,
        variable=VARIABLE_PER_PIECE,
        fixed=FIXED_PER_PIECE,
        payment_fee_rate=PAYMENT_FEE_RATE,
        no_loss=no_loss_sell_price(cost),
        target=target_sell_price(cost, markup=markup),
        markup=markup,
    )


def real_margin_pct(cost: float, sell_price: float) -> float:
    """Real gross margin % at given sell price, after var+fixed+payment fee.

    Useful for auditing existing prices against the model.
    """
    if sell_price <= 0:
        return 0.0
    net = sell_price * (1.0 - PAYMENT_FEE_RATE)
    full_cost = cost + VARIABLE_PER_PIECE + FIXED_PER_PIECE
    return (net - full_cost) / sell_price * 100.0


# --- CLI --------------------------------------------------------------------

def annotate_csv(in_path: Path, out_path: Path,
                  cost_col: str = "Cost Price",
                  markup: float = DEFAULT_MARKUP) -> None:
    """Read a CSV with a cost column, add no_loss + target columns, write to out."""
    with in_path.open() as f:
        reader = list(csv.DictReader(f))
    if not reader:
        raise ValueError(f"{in_path} has no rows")
    if cost_col not in reader[0]:
        raise ValueError(f"Column '{cost_col}' not found. Have: {list(reader[0].keys())}")

    fieldnames = list(reader[0].keys()) + ["No Loss Price", f"Target Price (+{int(markup*100)}%)", "Real Margin %"]
    sell_col = "Selling Price"

    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in reader:
            cost = float(row[cost_col])
            row["No Loss Price"] = no_loss_sell_price(cost)
            row[f"Target Price (+{int(markup*100)}%)"] = target_sell_price(cost, markup=markup)
            if sell_col in row and row[sell_col]:
                row["Real Margin %"] = round(real_margin_pct(cost, float(row[sell_col])), 1)
            else:
                row["Real Margin %"] = ""
            w.writerow(row)
    print(f"  ✓ wrote {len(reader)} rows to {out_path}")


def main() -> int:
    p = argparse.ArgumentParser(description="Chikankari Lane pricing helper")
    p.add_argument("cost", nargs="?", type=float, help="single cost to price (₹)")
    p.add_argument("--markup", type=float, default=DEFAULT_MARKUP,
                    help="markup on top of no-loss (default: %(default)s)")
    p.add_argument("--csv", type=Path, help="CSV with Cost Price column to annotate")
    p.add_argument("--out", type=Path, help="output CSV (default: <input>.priced.csv)")
    args = p.parse_args()

    print(f"\nAssumptions:")
    print(f"  Variable per piece:   ₹{VARIABLE_PER_PIECE:,.0f}")
    print(f"  Annual fixed:         ₹{ANNUAL_FIXED_COST:,.0f}")
    print(f"  Volume:               {PIECES_PER_MONTH}/mo × 12 = {PIECES_PER_YEAR}/yr")
    print(f"  Fixed per piece:      ₹{FIXED_PER_PIECE:,.2f}")
    print(f"  Payment fee:          {PAYMENT_FEE_RATE*100:.0f}%")
    print(f"  Markup:               {args.markup*100:.0f}%\n")

    if args.csv:
        out = args.out or args.csv.with_suffix(".priced.csv")
        annotate_csv(args.csv, out, markup=args.markup)
        return 0

    if args.cost is not None:
        print(breakdown(args.cost, markup=args.markup))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
