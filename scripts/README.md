# Scripts — Chikankari Lane

Automation for Shopify (catalog/cost) and Zoho Books (bookkeeping).

## Setup

```bash
# Python deps
pip install requests python-dotenv

# Zoho — credentials in config/zoho.env (gitignored)
# Setup walkthrough: specs/02-zoho-books-api-setup.md
python3 scripts/zoho_books_api.py    # smoke test

# Shopify — uses Shopify CLI (no token in repo)
shopify store auth --store 8chjhs-cd.myshopify.com \
  --scopes read_products,write_products,read_inventory,write_inventory,read_orders
```

## Pricing helper (single source of truth)

`pricing.py` defines all pricing assumptions. Update there, every other script picks it up.

```python
from pricing import no_loss_sell_price, target_sell_price, real_margin_pct

floor = no_loss_sell_price(cost=8200)         # break-even (rounded ↑ ₹10)
rec   = target_sell_price(cost=8200, markup=0.30)   # +30% on top of floor
real  = real_margin_pct(cost=8200, sell_price=13990)  # current real margin %
```

CLI:
```bash
python3 scripts/pricing.py 8200                   # one-item breakdown
python3 scripts/pricing.py --csv items.csv        # annotate CSV with prices
```

Current assumptions (in `pricing.py`):
- Variable per piece: ₹280 (packaging + shipping)
- Annual fixed: ₹1,76,052 (travel + subs + one-time)
- Volume: 30 pieces/month → 360/year
- Payment fee: 2% (Razorpay)
- Default markup: 30% on top of no-loss

## Routine workflows

### When new lot arrives
1. Add bill to `zoho-import/01-vendor-bills.csv` + per-piece costs to `03-per-piece-costs.csv`
2. Map new SKUs → bill lines in `04-sku-to-cost-mapping.csv`
3. Regenerate cost CSVs (`05-shopify-cost-update.csv`, `06-zoho-items-cost-update.csv`)
4. Push to Zoho: `python3 scripts/sync_zoho.py`
5. Push to Shopify: `python3 scripts/shopify_cli_sync.py`
6. Refresh Min Sell Price: `python3 scripts/zoho_set_min_sell_price.py`

### Selling prices
**Don't update Shopify selling prices automatically** — first-lot pricing was deliberately set and well-received. Use `pricing.py` only as a *reference* when listing new SKUs.

### Audit Zoho state vs source CSVs
```bash
python3 scripts/audit_zoho.py
```

## Script index

| Script | Purpose | Idempotent? |
|---|---|---|
| `pricing.py` | Pure pricing functions (no_loss, target, real_margin) | n/a |
| `zoho_books_api.py` | Zoho REST client + idempotent helpers | n/a |
| `sync_zoho.py` | Push 01-03 CSVs → Zoho (vendors, bills, expenses, items) | yes |
| `audit_zoho.py` | Read-only diff: source CSVs vs live Zoho | yes |
| `fix_zoho_items.py` | Update items by name (when Shopify→Zoho sync left SKU empty) | yes |
| `fix_zoho_gaps.py` | One-shot bill payment + items create | yes |
| `zoho_set_min_sell_price.py` | Compute + write `cf_min_sell_price` on all items | yes |
| `zoho_record_offline_sales.py` | Create offline-sold items + invoices in Zoho | yes (by SKU+ref) |
| `shopify_cli_sync.py` | Push costs from `05-shopify-cost-update.csv` | yes |
| `shopify_admin_api.py` | Direct GraphQL client (legacy, before CLI pivot) | n/a |
| `create_offline_sold_products.py` | Create draft Shopify products for offline-sold | yes (by handle) |
| `generate_*.py`, `regen_*.py`, `organize_catalog.sh`, `catalog-ops` | Catalog file ops | n/a |

## Repeatability checklist

Every state-changing script must:
- ✅ Read `config/zoho.env` (never hard-code creds)
- ✅ Call `zb.verify_org()` first (refuses to write to wrong org)
- ✅ Be safe to re-run (find-or-create, find-or-update with stable match key)
- ✅ Use `pricing.py` for any price calculation (don't hardcode formulas)
- ✅ Print a stats dict at the end (`{updated, created, unchanged, failed}`)

## Books reconciliation history

- **Bill 1 (Jan 5, ₹1,37,400, 20 pieces)**: closed. 16 listed on Shopify + 4 sold offline (handles `23-26-…-sold`, draft status, tag `sold`). All 10 sold pieces invoiced in Zoho (₹96,500), 10 still in stock.
- **Cost reassignments** (Apr 2026): 5 SKU costs updated when vendor confirmed all Shopify pieces came from Bill 1 — see commit history for details.
