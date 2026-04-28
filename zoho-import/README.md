# Zoho Books Import — Chikankari Lane (Jan–Apr 2026)

Source-of-truth CSVs for the Claude Code Chrome plugin to push into Zoho Books, plus the Shopify cost-update CSV for margin tracking.

## Tax stance (read first)

**Chikankari Lane is NOT GST-registered.** We do not collect GST from customers and do not file GST returns. Any GST paid to suppliers (e.g., on the Nafasat Chikan bill) is treated as **part of cost of goods**, not a recoverable Input Tax Credit. All bills below are recorded at gross/inclusive amounts with **Tax Rate = 0%** in Zoho. Do not split bills into base+tax. Do not configure GST tax rates on these vendors.

## Files

| File | Target | Path |
|---|---|---|
| `01-vendor-bills.csv` | Zoho Vendor Bills | Purchases → Bills → Import Bills |
| `02-operational-expenses.csv` | Zoho Expenses | Purchases → Expenses → Import Expenses |
| `03-per-piece-costs.csv` | Reference (cost lookup) | All 107 pieces extracted from bills with unit cost |
| `04-sku-to-cost-mapping.csv` | Reference / audit | Maps each Shopify SKU → bill row + cost. Confidence flag per row. |
| `05-shopify-cost-update.csv` | **Shopify Admin** | Products → Import. Sets `Cost per item` for the 16 active SKUs. Auto-syncs to Zoho Item Purchase Rate. |

## Three flows

### Flow 1 — Zoho Vendor Bills + Expenses (Chrome plugin handles this)
Captures cash outflow / COGS in P&L. Each bill is one line at the negotiated total (no per-piece itemization on the bill).

### Flow 2 — Per-piece costs (Shopify-side)
The 107 per-piece costs are kept in `03-per-piece-costs.csv` as reference. They land in Shopify's `Cost per item` field per SKU; the existing Shopify→Zoho sync then populates the Zoho Item Purchase Rate. Margin auto-calculates on every sale.

### Flow 3 — Shopify cost update (use `05-shopify-cost-update.csv`)
16 active SKUs mapped to source-bill costs (intelligent matching, ~40% homogenous margin target). Push via Shopify Admin → Products → Import.

## Inventory bills summary

All inventory was sourced in Lucknow.

| # | Date | Vendor | Pieces | Total |
|---|---|---|---|---|
| 1 | 2026-01-05 | Modern Chikan | 20 | ₹1,37,400 |
| 2 | 2026-04-22 | Modern Chikan | 45 | ₹2,39,000 |
| 3 | 2026-04-23 | Nafasat Chikan | 22 | ₹70,542 (GST-inclusive) |
| 4 | 2026-04-22 | Jasleen Lucknow (potlis & scarves) | 18 | ₹28,940 |
| 5 | 2026-04-22 | Lucknow Market - Cash Purchase (kaftan + kids sharara) | 2 | ₹10,500 |
| | | **Total** | **107** | **₹4,86,382** |

## Operational expenses summary

| Category | Amount | Type | Notes |
|---|---|---|---|
| Packaging (Printo) | ₹10,000 | One-time | Dated 2026-04-22 (approximate) |
| Flights — Jan trip | ₹18,000 | One-time | Estimated 50/50 split of ₹36,000 total |
| Flights — Apr trip | ₹18,000 | One-time | Estimated 50/50 split of ₹36,000 total |
| Cabs — Jan trip | ₹1,500 | One-time | Estimated 50/50 split of ₹3,000 total |
| Cabs — Apr trip | ₹1,500 | One-time | Estimated 50/50 split of ₹3,000 total |
| Product photo shoot | ₹4,000 | One-time | Dated 2026-04-22 (approximate) |
| ChatGPT (annual) | ₹400 | Recurring (yearly) | First billing date is approximate — update in Zoho |
| Canva Pro (annual) | ₹4,000 | Recurring (yearly) | First billing date is approximate — update in Zoho |
| Google Workspace (annual) | ₹1,632 | Recurring (yearly) | First billing date is approximate — update in Zoho |
| Shopify (trial) | ₹20/mo | Recurring (monthly) | First billing date is approximate — update in Zoho |

**Total Jan–Apr 2026 spend: ₹4,86,382 inventory + ₹54,000 one-time opex + ₹6,032 annual subs + ₹240 annual Shopify est. = ₹5,46,654**

## Plugin instructions

**IMPORTANT — this Zoho org is NOT empty.** The plugin must check before every insert. **If a matching record exists, OVERWRITE it with the CSV data (this is the latest source of truth).** If no match exists, create new. Never delete records that exist in Zoho but aren't in these CSVs.

### Step-by-step

1. **Open Zoho Books** → confirm org = Chikankari Lane. Abort if wrong org.

2. **Verify GST setting** on the org → should be **NOT registered for GST**. If the org is configured as GST-registered, **stop and ask the user** before proceeding. Do not configure GST tax rates on vendors or bills.

3. **Check Chart of Accounts** for these expense accounts (used in `02-operational-expenses.csv`):
   - `Packaging Materials`, `Travel Expenses`, `Marketing - Photography`, `Software Subscriptions`
   - Exact match → reuse. Fuzzy match (e.g., "Travel" instead of "Travel Expenses") → reuse the existing account, log which one was used. No match → create under Expenses parent.

4. **Check Vendors** — for each below, search Zoho first:
   - Modern Chikan (Lucknow)
   - Nafasat Chikan (Hazratganj, Lucknow — GSTIN 09AFTPK5160M1ZQ)
   - Jasleen Lucknow
   - Lucknow Market - Cash Purchase (placeholder for unlisted/walk-in)
   - Printo
   - OpenAI, Canva, Google, Shopify

   Exact match → reuse. Fuzzy match → reuse and update details (GSTIN, address) from this README. No match → create.

5. **Vendor Bills** — for each row in `01-vendor-bills.csv`:
   - Match by **vendor + bill date**.
   - Match found → **OVERWRITE** all fields with CSV data.
   - No match → create new.
   - **All bills go in at Tax Rate 0%** (we are not GST-registered).

6. **Expenses** — for each row in `02-operational-expenses.csv`:
   - Match by **vendor + month + expense account** (or by description if vendor blank).
   - Match found → **OVERWRITE** with CSV data.
   - For recurring subscriptions (ChatGPT, Canva, Google, Shopify): if a recurring expense template exists, **update** to match CSV; if not, create a recurring expense template (do not create one-off entries).
   - No match → create new.

7. **Payment status** — mark all bills/expenses as **Paid**, payment date = bill/expense date (cash basis).

8. **Final report** — at the end, output:
   - X vendors created, Y reused/updated
   - X bills created, Y overwritten — total ₹4,86,382 (verify)
   - X expenses created, Y overwritten — total ₹54,000 one-time + recurring set up
   - Org-level Jan–Apr 2026 total spend vs. expected **₹5,46,654** — flag variance.

### Hard rules

- **Overwrite on match — this CSV is the latest source of truth.**
- **Never push if org is wrong.** Confirm Chikankari Lane before any write.
- **Do not configure GST.** Org is not registered. All bills at 0% tax.
- **Do not delete** records in Zoho that aren't in these CSVs.
- **Log every action** (created / overwritten / reused) for audit.

## Notes & caveats

1. **Estimated dates** — flights, cabs, packaging, photo shoot dates are approximate. Update in Zoho if exact dates are known.
2. **Subscription start dates** — set to 2026-01-01 placeholder. Confirm and adjust actual first-billing-date in Zoho's recurring expense setup.
3. **Bill numbers** for cash purchases use pattern `<Vendor>-<Date>` (no formal invoice numbers on handwritten bills).
4. **Nafasat bill is GST-inclusive ₹70,542** at 0% in Zoho (since we don't claim ITC). The breakdown ₹62,113.86 base + ₹8,428.14 GST is informational only.
