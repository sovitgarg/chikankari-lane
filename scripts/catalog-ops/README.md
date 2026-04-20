# scripts/catalog-ops

Repeatable Chikankari Lane catalog update tooling.

See `../../.claude/skills/catalog-ops/SKILL.md` for the invokable Claude Code
skill and `../../specs/catalog-ops-protocol.md` for the human reference doc.

## Scripts

| Script | What it does |
|---|---|
| `ingest-photos.py` | Raw folder → Shopify-ready JPEGs in `catalog/products/<handle>/` |
| `ingest-videos.py` | Raw folder → muted MP4s in `catalog/products/<handle>/videos/` |
| `ingest-signals.py` | Folder of signals → draft change-spec YAML |
| `generate-csv.py` | Change-spec + before.csv → after.csv + diff.md |

## Quick start

```bash
# One-time
python3 -m venv .venv
.venv/bin/python -m pip install Pillow pillow-heif pyyaml
brew install ffmpeg   # only needed for video ingestion

# Per session
.venv/bin/python scripts/catalog-ops/generate-csv.py \
  --spec catalog/change-specs/2026-04-20-example.yaml
```

All four scripts respond to `--help`.
