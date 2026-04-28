# Zoho Books API — One-Time Setup

This walkthrough sets up direct Zoho Books API access so `scripts/sync_zoho.py` can push CSVs from `zoho-import/` directly into Zoho. Replaces the Chrome-plugin workflow.

## Prereqs

- Zoho Books account: **`hello@chikankarilane.com`** (Google login)
- Data center: **India** (`.in` domain)
- Org name: **Chikankari Lane**
- Python 3.10+ with `requests` and `python-dotenv` (`pip install requests python-dotenv`)

## Step 0 — Create the credentials file

```bash
cp specs/zoho.env.example config/zoho.env
```

The `config/` directory is gitignored, so the real credentials never get committed.

## Step 1 — Find the Organization ID

1. Log into [books.zoho.in](https://books.zoho.in) with `hello@chikankarilane.com`.
2. Settings (gear icon top right) → **Organization Profile**.
3. Copy the **Organization ID** (a long number near the top).
4. Paste into `config/zoho.env` as `ZOHO_ORG_ID=...`.

## Step 2 — Create a Self Client app

1. Go to [api-console.zoho.in](https://api-console.zoho.in) (must be `.in`, not `.com`).
2. Sign in with the same Google account: `hello@chikankarilane.com`.
3. Click **+ Add Client** → choose **Self Client** → **Create**.
4. Confirm in the popup ("OK").
5. You're now on the client detail page. Switch to the **Client Secret** tab.
6. Copy **Client ID** and **Client Secret** into `config/zoho.env`:
   ```
   ZOHO_CLIENT_ID=1000.XXXXXXXXXXXXXXXXXXXXXXXXX
   ZOHO_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

## Step 3 — Generate a one-time grant code

1. Still on the same page, switch to the **Generate Code** tab.
2. **Scope:** `ZohoBooks.fullaccess.all`
3. **Time Duration:** 10 minutes
4. **Scope Description:** "Initial setup — bookkeeping sync" (or anything)
5. Click **Create**.
6. Copy the generated code (looks like `1000.abcd1234...`).

⚠️ The code expires in 10 minutes. Move to Step 4 immediately.

## Step 4 — Exchange grant code for refresh token

```bash
cd /Users/sovitgarg/Learning/chikankari-lane
python3 scripts/zoho_get_refresh_token.py <paste-grant-code-here>
```

This calls Zoho's `/token` endpoint, gets a long-lived refresh token, and writes it into `config/zoho.env` as `ZOHO_REFRESH_TOKEN=...`. You only do this once. Refresh tokens don't expire unless you revoke them.

## Step 5 — Verify

```bash
python3 scripts/zoho_books_api.py
```

Expected output:
```
[org-check] ✓ Connected to 'Chikankari Lane' (id=...)
API client OK
```

If you see `Org safety check FAILED`, double-check `ZOHO_ORG_ID` and `ZOHO_ORG_NAME` in `config/zoho.env`.

## Step 6 — Dry-run the sync

```bash
python3 scripts/sync_zoho.py --dry-run
```

This reads `zoho-import/*.csv`, queries Zoho to see what already exists, and prints what *would* be created/overwritten — without making any writes. Verify the plan looks right.

## Step 7 — Real sync

```bash
python3 scripts/sync_zoho.py
```

Pushes everything. Idempotent — safe to re-run; existing records get overwritten with the latest CSV data. Final summary line should show:
```
Grand total: ₹545,434
Expected:    ₹545,434
✓ Within tolerance.
```

---

## Files this setup creates / uses

| Path | Purpose | Committed? |
|---|---|---|
| `specs/zoho.env.example` | Template showing required env vars | ✅ Yes |
| `config/zoho.env` | Real credentials (copied from template) | ❌ No (gitignored via `config/`) |
| `config/.zoho_access_token.json` | Cached access token (auto-refreshed) | ❌ No |
| `scripts/zoho_books_api.py` | API client with idempotent CRUD helpers | ✅ Yes |
| `scripts/zoho_get_refresh_token.py` | One-time grant→refresh exchange | ✅ Yes |
| `scripts/sync_zoho.py` | Orchestrator — reads CSVs, calls API | ✅ Yes |

## Recurring use (every month)

Once setup is done, monthly bookkeeping is one command:

```bash
# 1. Edit zoho-import/01-vendor-bills.csv and 02-operational-expenses.csv
#    to add new month's data
# 2. Sync
python3 scripts/sync_zoho.py --dry-run   # preview
python3 scripts/sync_zoho.py             # commit
```

No Chrome plugin needed. No clicking through Zoho UI. Idempotent → safe to re-run if interrupted.

## Token rotation / revocation

If the refresh token leaks or you want to rotate:
1. [api-console.zoho.in](https://api-console.zoho.in) → Self Client → **Settings** tab
2. Click **Rotate Client Secret** (this also invalidates all refresh tokens for this client)
3. Repeat Steps 2–4 above with the new secret

## Tax stance baked into the script

Chikankari Lane is **NOT GST-registered**. The script imports all bills with `tax_id=""` (no tax). If you later register for GST, you'll need to:
- Update `zoho_books_api.py` to pass real `tax_id` values per line item
- Split the Nafasat-style bills into base + GST lines
- Configure tax rates in Zoho first

For now, intentionally simple: 0% on everything.

## API rate limits

Zoho Books API allows **100 requests/min** per user. The script does ~2 requests per record (find + create/update), so a full sync of 30 records uses ~60 requests — well under the limit. The client auto-retries with exponential backoff on 429s.
