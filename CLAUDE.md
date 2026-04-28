# CLAUDE.md — Chikankari Lane

Project-specific instructions for Claude Code working on the Chikankari Lane Shopify store.

## Project

**Chikankari Lane** — D2C clothing brand selling hand-embroidered Lucknowi chikankari garments. Built on Shopify (store: `chikankari-lane-2`).

## Owner

Sovit Garg (`sovitgarg1@gmail.com`).

## Current state

Pre-launch. Shopify store created (empty). Awaiting:
- Custom App API token (blocks all automation)
- Razorpay KYC approval (blocks payments)
- Logo + product photos (blocks visual launch)

## Directory layout

```
chikankari-lane/
├── CLAUDE.md              # This file
├── README.md              # Project overview + status
├── brand/                 # Logo, colors, fonts, voice
├── content/
│   ├── policies/          # Privacy, Terms, Shipping, Returns, Refund
│   ├── pages/             # About, The Craft, Contact, FAQ
│   └── products/          # Product description templates
├── catalog/               # Product CSV (the source of truth for products)
├── specs/                 # Navigation, shipping, theme, app specs
├── scripts/               # Shopify + Zoho API automation scripts
├── config/                # API tokens (gitignored)
├── zoho-import/           # Source-of-truth CSVs for Zoho Books bookkeeping
└── assets/                # Logo files, product photos, lifestyle shots
```

## Working rules for Claude

1. **Never commit `config/` to git** — contains API tokens. Already in `.gitignore`.
2. **Source of truth for products = `catalog/products.csv`**. Edit there, then push to Shopify via script. Never edit Shopify products directly without updating the CSV.
3. **Source of truth for content = `content/` markdown files**. Push to Shopify via script.
4. **Shopify automation lives in `scripts/`**. All scripts read from `config/shopify.env`.
5. **Never push to Shopify production without showing the user a diff first.** Use draft themes for theme changes; preview before publishing.
6. **Brand voice:** to be defined in `brand/voice.md` — until then, default to warm-luxury (heritage + craftsmanship + accessible).
7. **Zoho Books automation:** all bookkeeping flows through `zoho-import/*.csv` → `scripts/sync_zoho.py`. Edit the CSV, run the script. Idempotent overwrite on (vendor + date) for bills, (vendor + date + account) for expenses, SKU for items. Setup spec: `specs/02-zoho-books-api-setup.md`. Zoho login: `hello@chikankarilane.com` (Google), data center `.in`.
8. **Tax stance:** Chikankari Lane is NOT GST-registered. Bills are recorded at gross (incl. any GST paid to vendors) with 0% tax in Zoho. GST paid is part of COGS. Don't split bills into base+tax unless the brand registers for GST.
9. **Shopify Admin API automation:** catalog writes go through `scripts/shopify_admin_api.py` (GraphQL client, idempotent helpers) + orchestrator scripts (`sync_shopify.py` for cost updates today; more orchestrators added as needs arise). Helpers exist for: cost, price, tags, inventory, product fields. Setup spec: `specs/03-shopify-admin-api-setup.md`. Match key for everything is **SKU**. Always run with `--dry-run` first.
10. **Known automation gap (store is live):** Shopify orders do NOT yet flow into Zoho Books as Sales Invoices. Currently only expenses are in Zoho → P&L shows costs but no revenue. When ready, build `scripts/sync_orders_to_zoho.py` to map Shopify orders → Zoho Sales Invoices + Customers + Payments. Idempotent via Shopify order number. Tax stance per rule 8 (0% / gross).

## Tech stack

- Shopify Basic plan
- Theme: Dawn (free) to start, possibly Prestige later
- Payment: Razorpay (Shopify Payments not available in India)
- Shipping: Shiprocket (multi-courier) — TBD
- Reviews: Judge.me — TBD
- Email: Klaviyo — TBD
- Domain: TBD (likely chikankarilane.com or .in)
- Bookkeeping: Zoho Books (`hello@chikankarilane.com`, India DC). Cost-of-goods cost field is NOT auto-synced from Shopify → must be written to both via the API script.

## What's blocking what

| Blocker | Blocks |
|---|---|
| Shopify Custom App token | All theme/product/page automation |
| Razorpay KYC | Live payments (can build store without it) |
| Logo | Theme finalization, business cards, social |
| Product photos | Listing products live |
| Domain purchase | Going live on real URL |
| GSTIN | GST-compliant invoicing app, B2B sales |

## Next concrete step

User needs to create a Shopify Custom App and paste the Admin API token. Setup instructions in `specs/01-shopify-custom-app-setup.md`.
