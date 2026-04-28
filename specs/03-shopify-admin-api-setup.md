# Shopify Admin API — Token Setup

This walkthrough completes the Custom App install (started in `01-shopify-custom-app-setup.md`) and gets the Admin API token into `config/shopify.env` so `scripts/sync_shopify.py` can drive the store directly.

**Prereq:** complete `specs/01-shopify-custom-app-setup.md` first (creates the Custom App, configures scopes). This spec picks up at the install + token step.

## Step 1 — Install the Custom App

1. In Shopify admin → **Settings → Apps and sales channels → Develop apps**.
2. Click into your `Claude Automation` custom app.
3. **API credentials** tab → **Install app** → confirm **Install**.
4. Under **Admin API access token**, click **Reveal token once**.

⚠️ Shopify shows the token **exactly once**. Copy it before clicking away. If you lose it, you have to uninstall and reinstall the app.

The token looks like: `shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

## Step 2 — Save the token

Edit `config/shopify.env`:

```
SHOPIFY_ADMIN_API_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The other values (`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_STORE_HANDLE`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`) should already be present from the earlier setup.

Set strict permissions on the file:
```bash
chmod 600 /Users/sovitgarg/Learning/chikankari-lane/config/shopify.env
```

## Step 3 — Verify

```bash
cd /Users/sovitgarg/Learning/chikankari-lane
python3 scripts/shopify_admin_api.py
```

Expected output:
```
[store-check] ✓ Connected to 'Chikankari Lane' (chikankari-lane-2.myshopify.com)
API client OK
```

If you see "Store safety check FAILED" — verify `SHOPIFY_STORE_HANDLE` matches the actual store (in this case `chikankari-lane-2`).

## Step 4 — Dry-run the cost sync

```bash
python3 scripts/sync_shopify.py --dry-run
```

This reads `zoho-import/05-shopify-cost-update.csv` and prints what it *would* do (per SKU: would-update / would-skip-unchanged / would-skip-not-found) — no writes.

## Step 5 — Real sync

```bash
python3 scripts/sync_shopify.py
```

Pushes Cost per item to all 16 active SKUs. Idempotent — variants whose cost already matches the CSV are skipped.

After this, in Shopify Admin → Products → any product → **Inventory section → Cost per item** field should show the updated value.

---

## Files this setup creates / uses

| Path | Purpose | Committed? |
|---|---|---|
| `config/shopify.env` | Real credentials | ❌ No (gitignored via `config/`) |
| `config/.shopify_token_cache` | (Future use — none today) | ❌ No |
| `scripts/shopify_admin_api.py` | API client (GraphQL, idempotent helpers) | ✅ Yes |
| `scripts/sync_shopify.py` | Orchestrator (currently: cost sync) | ✅ Yes |

## What the API client can do today

The client (`shopify_admin_api.py`) exposes idempotent helpers for:

| Operation | Method | Used by |
|---|---|---|
| Find variant by SKU | `find_variant_by_sku(sku)` | All upserts |
| Set Cost per item | `upsert_cost_by_sku(sku, cost)` | `sync_shopify.py` (today) |
| Set Variant Price | `upsert_price_by_sku(sku, price)` | (not wired up yet) |
| Add tag to product | `add_tag_to_product(sku, tag)` | (not wired up yet) |
| Remove tag from product | `remove_tag_from_product(sku, tag)` | (not wired up yet) |
| Set inventory quantity | `set_variant_inventory(sku, qty)` | (not wired up yet) |
| Update product type / status | `update_product_fields(...)` | (not wired up yet) |
| List all active variants | `list_all_active_variants()` | (utility) |

Future orchestrator scripts can build on these without touching the API client.

## What is NOT built (deliberate scope cap)

- **Order sync to Zoho Books** — biggest known gap now that the store is live. Every Shopify order that comes in needs to become a Zoho Sales Invoice + Customer + Payment, otherwise Zoho only sees expenses (P&L is wrong). Build this when ready: `sync_orders_to_zoho.py`.
- **Shiprocket fulfillment** — when packing volume justifies it.
- **Webhooks** — for real-time event handling at higher order volume.
- **Theme automation** — not needed yet.

## API version

Currently pinned to **`2025-01`** in `shopify_admin_api.py`. Shopify rolls out a new stable version each quarter; bump quarterly to stay supported.

## Token rotation / revocation

If the Admin API token leaks:
1. Shopify Admin → **Settings → Apps and sales channels → Develop apps → Claude Automation**
2. Click **Uninstall** (immediately revokes the token)
3. Reinstall and grab a new token via Step 1 above.

The "kill switch" — uninstalling the app stops all API access instantly.

## Rate limits

Shopify Admin API GraphQL uses a **leaky-bucket cost system**:
- Each query has a "cost" (typically 1–50 points)
- Bucket capacity: 1000 points, refills at 50 points/sec
- The client auto-checks `extensions.cost.throttleStatus.currentlyAvailable` and sleeps if the bucket is depleted

At our volume (~20 SKUs/sync), throttling won't kick in.
