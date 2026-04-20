---
name: catalog-ops
description: Repeatable Chikankari Lane catalog updates — photo/video ingestion, change-spec drafting, Shopify CSV generation with diff. Use when processing new product photos, interpreting signals from WhatsApp/suppliers ("sold", new prices, new SKUs), generating a Shopify import CSV, or adding videos (muted) to products. Do not use for theme edits, orders, or payments.
---

# Catalog Ops — Chikankari Lane

You are working inside `/Users/sovitgarg/Learning/chikankari-lane/`. This skill
gives you the rules and the tooling to safely update the Shopify catalog.

## Invariants (never violate)

1. **Products are one-of-a-kind unstitched-to-semistitched suits.** Every product
   has a single `Default Title` variant (no sizes, no colours). If you see a
   multi-variant product in any export, STOP and alert the user — the store
   shape has changed.

2. **Quantity rule:** available = `1`, sold = `0`. No other values.

3. **Sold pieces** stay `Status: active` (so the product page remains visible),
   `Variant Inventory Policy: deny` (so "Add to cart" is disabled), and get a
   `sold` tag added.

4. **Tag hygiene:** `bridal` is a forbidden tag on this catalog; remove wherever
   it appears. Tag `sold` is the canonical marker for sold pieces. Tag
   `unstitched-suit` is historical and currently unchanged — do NOT bulk-replace
   it unless explicitly told.

5. **Type:** every product is `Semistitched Suit`. If any row has `Unstitched
   Suit`, update it in the same change-spec.

6. **Prices:** Shopify expects `NNNN.00` (two decimals, no separator). The
   helpers handle this; do not hand-format.

7. **Never commit `config/`** — contains API tokens (already gitignored).

8. **Never push to Shopify production without showing a diff.** The `diff.md`
   produced alongside `after.csv` is the review artifact.

9. **Never guess an image-to-product match.** When a source photo doesn't
   clearly match an existing handle, mark it UNCERTAIN in the YAML and ask the
   user to confirm. We have already hit multiple ambiguous greys and pinks —
   this matters.

10. **Videos cannot be imported via CSV.** Track them in the spec under
    `videos:` and the diff will emit manual-upload TODOs with the GitHub raw
    URLs. Videos are always re-encoded with audio stripped at ingestion time.

11. **Scope:** when a session is ONLY adding new products, write a spec with
    `new_products:` and no `changes:`. `generate-csv.py` automatically emits
    a minimal "new-only" CSV that leaves every existing Shopify product
    untouched. To force this, pass `--only-new-products`. To force the
    opposite (refresh every existing product via Shopify Overwrite), pass
    `--full-catalog`. Default-new-only is the safe choice: you never touch a
    product you didn't mean to. Only write `changes:` entries when you
    deliberately want to update existing products in the same upload.

12. **Output filenames** include an HHMM timestamp (e.g.
    `2026-04-20-1336-new-after.csv`). Never rely on hard-coded filenames
    across sessions; always list the `catalog/exports/` directory first and
    pick the newest file.

## The four scripts

All scripts live at `scripts/catalog-ops/` and use the repo's `.venv`.

| Script | Purpose |
|---|---|
| `ingest-photos.py` | Raw folder → resized/stripped JPEGs in `catalog/products/<handle>/`. Writes a `PRODUCT.md` stub. Does not git-commit. |
| `ingest-videos.py` | Raw folder → H.264 MP4 (no audio, ≤60s, ≤1080p) in `catalog/products/<handle>/videos/`. Requires `ffmpeg`. |
| `ingest-signals.py` | Folder of source signals (WhatsApp screenshots, price-tag photos, notes) → draft change-spec YAML with UNCERTAIN entries. |
| `generate-csv.py` | Change-spec YAML + `before.csv` (live export) → `after.csv` + `diff.md` in `catalog/exports/`. Never runs without a diff. |

## Standard workflow

Run these from the repo root with the venv activated (`source .venv/bin/activate`
or prefix with `.venv/bin/python`):

1. **Export current Shopify state.** Shopify Admin → Products → Export → All
   products → Plain CSV. Save to `catalog/exports/YYYY-MM-DD-before.csv`.
2. **If there are new photos:**
   ```
   .venv/bin/python scripts/catalog-ops/ingest-photos.py \
     --raw ~/Downloads/<folder> \
     --handle 20-blush-pink-chikankari-suit
   ```
   Then `git add catalog/products/20-blush-pink-chikankari-suit && git commit && git push`.
3. **If there are new videos:**
   ```
   .venv/bin/python scripts/catalog-ops/ingest-videos.py \
     --raw ~/Downloads/<folder> \
     --handle 20-blush-pink-chikankari-suit
   ```
   Then `git add catalog/products/20-blush-pink-chikankari-suit/videos && git commit && git push`.
4. **Draft the change-spec** (optional — can also write by hand):
   ```
   .venv/bin/python scripts/catalog-ops/ingest-signals.py \
     --source ~/Downloads/<folder-of-screenshots> \
     --label ruchi-whatsapp
   ```
   This creates `catalog/change-specs/YYYY-MM-DD-draft-ruchi-whatsapp.yaml`.
   Open it, resolve every UNCERTAIN match, and rename to drop the `draft-`
   prefix when done.
5. **Generate the CSV:**
   ```
   .venv/bin/python scripts/catalog-ops/generate-csv.py \
     --spec catalog/change-specs/YYYY-MM-DD-ruchi-whatsapp.yaml
   ```
   Writes `catalog/exports/YYYY-MM-DD-after.csv` and
   `catalog/exports/YYYY-MM-DD-diff.md`.
6. **Review the diff.** If anything looks wrong, edit the spec and re-run with
   `--force`.
7. **Upload `after.csv`** to Shopify Admin → Products → Import. Check
   "Overwrite any current products that have the same handle". Leave "Publish
   new products to all sales channels" unchecked if you have any `draft` rows.
8. **Upload videos manually** from the TODO list in `diff.md` (CSV can't carry
   videos until we add a Shopify Admin API client).

## Change-spec YAML shape

```yaml
date: 2026-04-20
normalize_qty_to_1: true           # default true — force available qty to 1

changes:
  - handle: 07-oatmeal-medallion-suit
    action: mark_sold              # sets qty=0, adds sold tag, optionally updates price
    price: 14990
    source: "WhatsApp Ruchi Garg 10:02 AM"

  - handle: 01-crimson-paisley-suit
    action: update_fields          # any combination of field updates
    set_type: Semistitched Suit
    remove_tags: [bridal]
    # add_tags: [festive]
    # set_status: draft
    # price: 12000
    # qty: 1

  - handle: 04-sky-blue-striped-sequin-suit
    action: update_fields
    videos:                        # emits manual-upload TODO in diff.md
      - 01-drape.mp4

new_products:
  - handle: 20-blush-pink-chikankari-suit
    title: Blush Pink Chikankari Suit
    price: 10000
    qty: 0
    status: draft                  # stays hidden until you confirm details
    type: Semistitched Suit
    tags: [blush-pink, chikankari, lucknow, mul-cotton, sold, unstitched-suit]
    body_html: "<p>Placeholder record…</p>"
    images:                        # filenames inside catalog/products/<handle>/
      - 01-flatlay.jpg
      - 02-yoke-detail.jpg
    videos:                        # filenames inside catalog/products/<handle>/videos/
      - 01-drape.mp4
    source: "WhatsApp Ruchi Garg 10:07 AM"
```

## Safety behaviors the scripts enforce

- `generate-csv.py` refuses if `before.csv` is >24h old (pass `--force` to
  bypass; rarely right).
- `generate-csv.py` refuses to overwrite an existing `after.csv` for the same
  date (pass `--force`).
- `generate-csv.py` errors if a change references an unknown handle that isn't
  also in `new_products`.
- `ingest-photos.py` / `ingest-videos.py` never overwrite without `--force`.
- Every script is idempotent — re-running is safe.

## Refinement log

Keep this skill evolving. When the user says something like "we learned X —
update the skill," or when a session surfaces a rule, gotcha, or convention
that wasn't captured, add an entry here with the date and one-line rule. Don't
delete prior entries; they're history.

- **2026-04-20** — Initial skill. Invariants 1-10 established from the first
  live catalog update session.
- **2026-04-20** — Smoke test caught that the hand-built diff had an incorrect
  "qty 5 → 0" for handle `16`; actual before-state was qty=1. Lesson:
  always trust the live export, never hand-edit qty numbers in the spec.
- **2026-04-20** — Adding default "new-only" CSV mode. When a spec has
  `new_products` but no `changes`, `generate-csv.py` now emits a minimal CSV
  containing only the new rows so existing products are never accidentally
  overwritten. Also: output filenames now include HHMM timestamps so
  repeated runs on the same day don't collide. Invariants 11 and 12 added.

## What you should refuse to do

- Add a new product to the CSV without confirmed price, handle, and photos (use
  `status: draft` as the only exception, and say so in the diff).
- Match a source photo to an existing handle when the match is ambiguous.
  Leave it as UNCERTAIN and ask.
- Bulk-rename tags or change descriptions without an explicit user
  instruction.
- Run a Shopify upload yourself. Even once the Custom App token is unblocked,
  the user reviews the diff and clicks Import themselves.
