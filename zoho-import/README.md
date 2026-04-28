# Zoho Books Import — Chikankari Lane (Jan–Apr 2026)

Source-of-truth CSVs for Zoho Books bookkeeping, plus the Shopify cost-update CSV for margin tracking.

## Two ways to push these to Zoho

**Recommended (faster, scriptable, repeatable):**
```bash
python3 scripts/sync_zoho.py --dry-run   # preview
python3 scripts/sync_zoho.py             # commit
```
One-time setup: `specs/02-zoho-books-api-setup.md` (~10 min).

**Alternative (manual):**
Use the Claude Code Chrome plugin or import each CSV via Zoho UI (Purchases → Bills → Import, etc.). See "Plugin instructions" section below.

## Tax stance (read first)

**Chikankari Lane is NOT GST-registered.** We do not collect GST from customers and do not file GST returns. Any GST paid to suppliers (e.g., on the Nafasat Chikan bill) is treated as **part of cost of goods**, not a recoverable Input Tax Credit. All bills below are recorded at gross/inclusive amounts with **Tax Rate = 0%** in Zoho. Do not split bills into base+tax. Do not configure GST tax rates on these vendors.

## Files

| File | Target | Path |
|---|---|---|
| `01-vendor-bills.csv` | Zoho Vendor Bills | Purchases → Bills → Import Bills |
| `02-operational-expenses.csv` | Zoho Expenses | Purchases → Expenses → Import Expenses |
| `03-per-piece-costs.csv` | Reference (cost lookup) | All 107 pieces extracted from bills with unit cost |
| `04-sku-to-cost-mapping.csv` | Reference / audit | Maps each Shopify SKU → bill row + cost. Confidence flag per row. |
| `05-shopify-cost-update.csv` | **Shopify Admin** | Products → Import. Sets `Cost per item` for the 16 active SKUs. |
| `06-zoho-items-cost-update.csv` | **Zoho Books Items** | Items → Import Items. Sets `Purchase Rate` (cost) on the same 16 SKUs in Zoho. |

## Three flows

### Flow 1 — Zoho Vendor Bills + Expenses (Chrome plugin handles this)
Captures cash outflow / COGS in P&L. Each bill is one line at the negotiated total (no per-piece itemization on the bill).

### Flow 2 — Per-piece cost reference
The 107 per-piece costs are kept in `03-per-piece-costs.csv` as a lookup. Used to generate Flow 3 files and to set cost when new SKUs are created in Shopify.

### Flow 3 — Cost update to BOTH Shopify and Zoho Books (16 active SKUs)
**Important:** The Shopify→Zoho Books integration does NOT auto-sync the cost field. Cost must be written to both systems independently. Two parallel imports:

1. **Shopify side** — push `05-shopify-cost-update.csv` via Shopify Admin → Products → Import. Sets `Cost per item`. Used by Shopify Analytics' margin reports.
2. **Zoho Books side** — push `06-zoho-items-cost-update.csv` via Zoho Books → Items → Import Items. Sets `Purchase Rate` (cost) on each Item. Used by Zoho's profit reports.

Both files contain the same SKU/cost data (intelligent matching, ~40% homogenous margin target). Match key for both = SKU.

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

8. **Items cost update** — import `06-zoho-items-cost-update.csv` into Zoho Books → Items → Import Items.
   - For each row, match by **SKU** to existing Items (created earlier by the Shopify sync).
   - If match → **OVERWRITE** the `Purchase Rate` (cost) field with the CSV value. Don't change other fields.
   - If no match for a SKU → skip and log (means the Shopify sync hasn't created that item in Zoho yet — re-run Shopify sync first).
   - Do NOT create duplicate items if SKUs match existing ones.
   - Verify: 16 items should have Purchase Rate set.

9. **Final report** — at the end, output:
   - X vendors created, Y reused/updated
   - X bills created, Y overwritten — total ₹4,86,382 (verify)
   - X expenses created, Y overwritten — total ₹53,000 one-time + recurring set up
   - X items had Purchase Rate updated, Y skipped (not found)
   - Org-level Jan–Apr 2026 total spend vs. expected **₹5,45,434** — flag variance.

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
