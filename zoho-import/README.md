# Zoho Books Import — Chikankari Lane (Jan–Apr 2026)

Two CSVs for the Claude Code Chrome plugin to push into Zoho Books.

## Files

| File | Target | Path |
|---|---|---|
| `01-vendor-bills.csv` | Zoho Vendor Bills | Purchases → Bills → Import Bills |
| `02-operational-expenses.csv` | Zoho Expenses | Purchases → Expenses → Import Expenses |
| `03-per-piece-costs.csv` | Reference data (cost lookup) | All 107 pieces extracted from bills with unit cost |
| `04-sku-to-cost-mapping.csv` | Reference / audit | Maps each Shopify SKU → bill row + cost. Confidence flag per row (HIGH/MEDIUM/LOW) — review LOW rows. |
| `05-shopify-cost-update.csv` | **Shopify Admin** | Products → Import (overwrite). Sets `Cost per item` for the 16 active SKUs. Auto-syncs to Zoho Item Purchase Rate. |

## Three flows for the plugin

This is **not just a bill import**. To track margin per item, three things need to happen:

### Flow 1 — Vendor Bills + Expenses (records cash outflow)
Import `01-vendor-bills.csv` and `02-operational-expenses.csv` into Zoho. Captures total spend correctly in P&L. **Bill totals only — no per-piece itemization on bills.**

### Flow 2 — Per-piece costs (records cost-of-goods at item level)
Per-piece costs from the bills are extracted in `03-per-piece-costs.csv` (~107 rows). **These costs need to land on the Item master in Shopify (Cost per item field), not on the Zoho bill.** The Shopify→Zoho sync then carries cost into the Zoho Item's Purchase Rate. Margin = automatic on every sale.

### Flow 3 — SKU cost update (intelligent matching)
`05-shopify-cost-update.csv` updates the Cost per item for all 16 active SKUs. Costs were intelligently matched from `03-per-piece-costs.csv` based on:
- **Selling price tier** (premium ₹14k+ pieces matched to high-cost suits, mid ₹9–11k to mid-cost, etc.)
- **Color/fabric/motif descriptors** (e.g., "Pearl Cluster" ↔ "Cutdana", "Black Chikankari" ↔ "Anarkali Black")
- **Homogenous margin target of ~40% gross** (cost ≈ 60% of price)

Match confidence is flagged per row in `04-sku-to-cost-mapping.csv`:
- **HIGH** (10 SKUs): direct color/fabric/pattern match
- **MEDIUM** (3 SKUs): price-tier + category match
- **LOW** (3 SKUs: 16, 19, 20, 22): best-fit guesses — please review

Push `05-shopify-cost-update.csv` via Shopify Admin → Products → Import (overwrite mode). The Shopify→Zoho sync will then populate the Zoho Item Purchase Rate, and margin will compute automatically on every sale.

For the ~91 pieces not yet in Shopify: cost is captured **when each SKU is created** (don't backfill — just enter cost from `03-per-piece-costs.csv` into the Shopify Cost field at SKU creation time).


## Strategy (why one bill = one line)

The handwritten bills don't reference Shopify SKUs — they use supplier-side codes (e.g., 565, 4715) and Hindi/English garment descriptions. Trying to map each row to a Shopify SKU is slow and error-prone.

**So:** each bill is recorded as a single Vendor Bill with one consolidated line at the negotiated total. This:

- Captures cash outflow and COGS correctly in P&L
- Matches bank/cash records cleanly
- Avoids fake SKU mappings
- Per-piece costs already live in Shopify item costs (which sync to Zoho via the existing flow)

If you later want unit-cost analytics, do it in a side spreadsheet — not Zoho.

## Inventory bills summary

All inventory was sourced in Lucknow.

| # | Date | Vendor | Pieces | Negotiated Total |
|---|---|---|---|---|
| 1 | 2026-01-05 | Modern Chikan | 20 | ₹1,37,400 |
| 2 | 2026-04-22 | Modern Chikan | 45 | ₹2,39,000 |
| 3 | 2026-04-23 | Nafasat Chikan | 22 | ₹70,542 (incl. GST) |
| 4 | 2026-04-22 | Jasleen Lucknow (potlis & scarves) | 18 | ₹28,940 |
| 5 | 2026-04-22 | Lucknow Market - Cash Purchase (kaftan) | 1 | ₹8,000 |
| 6 | 2026-04-22 | Lucknow Market - Cash Purchase (kids sharara) | 1 | ₹2,500 |
| | | **Total** | **107** | **₹4,86,382** |

## Operational expenses summary

| Category | Amount | Type |
|---|---|---|
| Packaging (Printo) | ₹10,000 | One-time |
| Flights (sourcing) | ₹36,000 | One-time |
| Cabs (sourcing) | ₹3,000 | One-time |
| Product photo shoot | ₹4,000 | One-time |
| ChatGPT (annual) | ₹400 | Recurring (yearly) |
| Canva Pro (annual) | ₹4,000 | Recurring (yearly) |
| Google Workspace (annual) | ₹1,632 | Recurring (yearly) |
| Shopify (trial pricing) | ₹20/mo | Recurring (monthly) |

## Notes for import

1. **Ruchi Garg bill (#2)** is recorded as one combined bill of ₹2,39,000 (paid in two installments of ₹1,00,000 + ₹1,39,000).
2. **GST on Nafasat bill:** ₹70,542 total = ₹59,766.96 base + ₹10,775.04 GST (9% CGST + 9% SGST = 18%). Zoho will compute taxes if you enter the base amount and tax rate.
3. **Bill numbers** for Modern Chikan and Ruchi Garg use the pattern `<Vendor>-<Date>` (no formal invoice numbers on handwritten bills).
4. **Vendor master:** Create these vendors in Zoho first if they don't exist:
   - Modern Chikan (Lucknow)
   - Ruchi Garg (Bangalore)
   - Nafasat Chikan (Hazratganj, Lucknow — GSTIN 09AFTPK5160M1ZQ)
   - Printo
   - OpenAI / Canva / Google / Shopify (subscription vendors)

## Plugin instructions (Flow 1 only)

The plugin handles **Flow 1** (Zoho bills + expenses). Flows 2 and 3 are Shopify-side and need the user mapping first.



**IMPORTANT — this Zoho org is NOT empty.** The Chrome plugin must check for existing data at every step. **If a matching record exists, OVERWRITE it with the info from these CSVs (this data is the latest source of truth).** If no match exists, create new. Report what was overwritten vs. created.

### Step-by-step (with idempotency checks at each stage)

1. **Open Zoho Books** → confirm org = Chikankari Lane. Abort if wrong org.

2. **Check Chart of Accounts** for the expense accounts used in `02-operational-expenses.csv`:
   - `Packaging Materials`, `Travel Expenses`, `Marketing - Photography`, `Software Subscriptions`
   - If found exactly → reuse.
   - If a fuzzy match exists (e.g., "Travel" instead of "Travel Expenses") → **reuse the existing account** (don't create a near-duplicate). Log which existing account was used.
   - If no match → create under the Expenses parent.

3. **Check Vendors** — for each vendor below, search the Zoho vendor list first:
   - Modern Chikan (Lucknow)
   - Nafasat Chikan (Hazratganj, Lucknow — GSTIN 09AFTPK5160M1ZQ)
   - Jasleen Lucknow
   - Lucknow Market - Cash Purchase (placeholder for unlisted/walk-in market vendors)
   - Printo
   - OpenAI, Canva, Google, Shopify

   For each: if found exactly → reuse. If fuzzy match (e.g., "Nafasat Chikkan" vs "Nafasat Chikan") → **reuse existing vendor and update its details** (GSTIN, address) with the info in this README. If no match → create.

4. **Vendor Bills** — for each row in `01-vendor-bills.csv`:
   - Search Zoho bills filtered by **vendor + bill date** (amount can change if user corrected it).
   - If a match exists → **OVERWRITE** with the data from the CSV (description, amount, tax, payment status). This CSV is the latest source of truth.
   - If no match exists → create new.

5. **Expenses** — for each row in `02-operational-expenses.csv`:
   - Search Zoho expenses filtered by **vendor + month + expense account**.
   - If a match exists → **OVERWRITE** with the CSV data (amount, description, recurring flag).
   - For recurring subscriptions (ChatGPT, Canva, Google Workspace, Shopify): if a recurring expense template already exists, **update it** to match the CSV (frequency, amount). Don't create duplicate one-offs.
   - If no match → create new.

6. **Payment status** — mark all bills/expenses (new and overwritten) as **Paid** with payment date = bill date (cash basis).

7. **Final report** — at the end, output a summary:
   - X vendors created, Y reused (with details updated where applicable)
   - X bills created, Y overwritten
   - X expenses created, Y overwritten
   - Final org totals for Jan–Apr 2026 vs. the ₹5,45,434 expected target — flag any variance.

### Hard rules for the plugin

- **Overwrite existing records when matched** — this CSV is the latest source of truth.
- **Never push if the org is wrong.** Confirm Chikankari Lane org before any write.
- **Log every action** (created / overwritten / reused) so the user can audit afterwards.
- **Do not delete** any records that exist in Zoho but aren't in these CSVs — leave them alone.
