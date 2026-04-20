# Catalog Ops Protocol

Reference doc for the repeatable inventory-update workflow. See the invokable
skill at `.claude/skills/catalog-ops/SKILL.md` for the machine-readable version.

## One-time setup

```bash
cd /Users/sovitgarg/Learning/chikankari-lane

# Python venv with Pillow + pillow-heif + pyyaml
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install Pillow pillow-heif pyyaml

# ffmpeg for video processing (strips audio, re-encodes for Shopify)
brew install ffmpeg
```

## Per-session workflow

### 1. Export current Shopify state

Shopify Admin → **Products** → **Export** → **All products** → **Plain CSV**.
Save the file to:

```
catalog/exports/YYYY-MM-DD-before.csv
```

This is the single source of truth for "what's live right now." The
`generate-csv.py` script refuses to proceed if this file is older than 24 hours
(staleness risk).

### 2. Bring in new photos (if any)

Drop raw photos in `~/Downloads/<any-folder>/`. They can be HEIC, JPEG, PNG,
WEBP — mixed formats are fine.

```bash
.venv/bin/python scripts/catalog-ops/ingest-photos.py \
  --raw ~/Downloads/<folder> \
  --handle 20-blush-pink-chikankari-suit
```

This produces 2048px progressive JPEGs at quality 90, with EXIF stripped
(privacy), saved to `catalog/products/<handle>/NN-<hint>.jpg`. It also writes
a `PRODUCT.md` stub if one doesn't already exist.

Commit and push so GitHub serves the raw URLs:

```bash
git add catalog/products/20-blush-pink-chikankari-suit/
git commit -m "Add photos for 20-blush-pink-chikankari-suit"
git push
```

### 3. Bring in new videos (if any)

```bash
.venv/bin/python scripts/catalog-ops/ingest-videos.py \
  --raw ~/Downloads/<folder> \
  --handle 20-blush-pink-chikankari-suit
```

This trims to 60s, strips the audio track, scales to ≤1080p, and re-encodes as
MP4/H.264 with `+faststart`. Saved to `catalog/products/<handle>/videos/`.

Commit and push:

```bash
git add catalog/products/20-blush-pink-chikankari-suit/videos/
git commit -m "Add videos for 20-blush-pink-chikankari-suit"
git push
```

### 4. Draft a change-spec

Option A — **from a folder of signals** (WhatsApp screenshots, price tag
photos, whatever):

```bash
.venv/bin/python scripts/catalog-ops/ingest-signals.py \
  --source ~/Downloads/<folder-of-screenshots> \
  --label ruchi-whatsapp
```

This scaffolds `catalog/change-specs/YYYY-MM-DD-draft-ruchi-whatsapp.yaml`
with one UNCERTAIN placeholder per input file. Fill it in (usually with
Claude's help — the `catalog-ops` skill walks through it), then rename to
remove the `draft-` prefix.

Option B — **write by hand**. Copy an existing file in
`catalog/change-specs/` and edit.

### 5. Generate the CSV and diff

```bash
.venv/bin/python scripts/catalog-ops/generate-csv.py \
  --spec catalog/change-specs/YYYY-MM-DD-ruchi-whatsapp.yaml
```

Outputs:

- `catalog/exports/YYYY-MM-DD-after.csv` — upload this to Shopify.
- `catalog/exports/YYYY-MM-DD-diff.md` — review this first.

### 6. Review the diff

Read `diff.md` end to end. If any change looks wrong, edit the spec and re-run
with `--force`. Pay special attention to:

- `mark_sold` entries (going to qty=0)
- Any new-product row (status, price, images present)
- "Video upload TODOs" section — these must be uploaded manually

### 7. Upload to Shopify

Shopify Admin → **Products** → **Import**. Upload `after.csv`.

- ✅ Check **"Overwrite any current products that have the same handle"**.
- ⚠️  If you have `status: draft` rows and you see a "Publish new products to
  all sales channels" option, leave it unchecked so drafts stay drafts.

Wait for the completion email. Spot-check at least:

- Each product marked sold (qty=0, `sold` tag present)
- Any new product row (status, price correct; photos loaded from GitHub)

### 8. Upload videos (manual, for now)

For each entry in the "Video upload TODOs" section of `diff.md`:

1. Open the product in Shopify admin.
2. Media → Add media → Upload file.
3. Pick the file from `catalog/products/<handle>/videos/<filename>`.

(Once the Shopify Custom App token is provisioned, this can be automated via
the Admin GraphQL API. Parked for now.)

### 9. Rollback if needed

If an import goes wrong:

```bash
# Upload catalog/exports/YYYY-MM-DD-before.csv to Shopify Import with
# "Overwrite" checked. That restores the pre-import state for the 19
# existing products.
```

New products added in the bad import must be deleted manually in the admin —
CSV import cannot delete.

## Shopify gotchas we've already hit

1. **"Publish to all sales channels" language** on the Import preview dialog
   is misleading. `Status` from the CSV is still honored — drafts stay drafts.
   But double-check anyway.
2. **`Variant Inventory Qty` is only applied when Overwrite is on.** Without
   Overwrite, Shopify ignores the qty column on existing products.
3. **Tags are alphabetized by Shopify on save** regardless of their order in
   the CSV. The scripts sort them too, so diffs stay small.
4. **Image URLs must be publicly reachable.** The GitHub raw URLs work because
   the repo is public. If the repo goes private, image imports will silently
   fail.
5. **CSV does not support video.** Always manual-upload for now.
6. **HEIC from iPhone needs conversion** — handled transparently by
   `ingest-photos.py` via `pillow-heif`.

## Refining the skill over time

The skill at `.claude/skills/catalog-ops/SKILL.md` contains a "Refinement log"
at the bottom. After each session where you learn something new (a Shopify
quirk, a convention decision, a gotcha), add a dated one-line entry there so
the next run picks it up. Don't delete prior entries — they're useful history.

Good things to add:
- New conventions you adopt (e.g. "use `sale` tag instead of `sold` for
  limited-time discounts").
- Shopify behaviors you verify (e.g. what a specific import checkbox does).
- Mistakes you catch and want to prevent next time.

## File layout

```
chikankari-lane/
├── .claude/skills/catalog-ops/SKILL.md   # invokable skill
├── scripts/catalog-ops/
│   ├── ingest-photos.py
│   ├── ingest-videos.py
│   ├── ingest-signals.py
│   ├── generate-csv.py
│   └── lib/
│       ├── shopify_csv.py
│       ├── image_ops.py
│       └── video_ops.py
├── catalog/
│   ├── products/<handle>/
│   │   ├── 01-flatlay.jpg
│   │   ├── 02-yoke-detail.jpg
│   │   ├── videos/
│   │   │   └── 01-drape.mp4
│   │   └── PRODUCT.md
│   ├── change-specs/YYYY-MM-DD-<label>.yaml
│   └── exports/
│       ├── YYYY-MM-DD-before.csv
│       ├── YYYY-MM-DD-after.csv
│       └── YYYY-MM-DD-diff.md
└── specs/catalog-ops-protocol.md   # this file
```
