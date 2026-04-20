#!/usr/bin/env python3
"""Draft a change-spec YAML from a folder of source signals.

Source signals can be anything: WhatsApp screenshots, photos of price tags, a
freeform text note you saved, a CSV. This script does NOT do image-to-product
matching on its own (that's an AI-judgment step handled in-conversation). It
scaffolds a YAML file with one placeholder entry per input file, flagged
UNCERTAIN, so you can fill it in confidently with Claude's help.

The resulting YAML is always prefixed `draft-` and intended to be reviewed.
Promote it to a final spec by renaming and completing the fields.

Usage:
  ingest-signals.py --source <folder> [--label LABEL] [--today DATE]

Options:
  --source PATH   Folder of screenshots/photos/etc. Required.
  --label STR     Short free-text label embedded in the filename, e.g. "ruchi-whatsapp".
  --today DATE    Override today's date (default: local today).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--label", type=str, default="signals")
    p.add_argument("--today", type=str, default="")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source.exists() or not args.source.is_dir():
        print(f"ERROR: source folder not found: {args.source}", file=sys.stderr)
        return 1

    today = args.today or dt.date.today().isoformat()
    files = sorted(p for p in args.source.iterdir() if p.is_file())
    if not files:
        print(f"ERROR: no files in {args.source}", file=sys.stderr)
        return 1

    specs_dir = REPO_ROOT / "catalog" / "change-specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    out = specs_dir / f"{today}-draft-{args.label}.yaml"
    if out.exists():
        print(f"ERROR: {out} already exists. Rename or delete first.", file=sys.stderr)
        return 1

    lines: list[str] = []
    lines.append(f"# Draft change-spec from signals in: {args.source}\n")
    lines.append(f"# Generated {today}. Every entry below is UNCERTAIN — review and\n")
    lines.append("# fill in handle, price, action before running generate-csv.py.\n\n")
    lines.append(f"date: {today}\n")
    lines.append("normalize_qty_to_1: true\n\n")
    lines.append("# Each signal below corresponds to one input file. Delete entries that\n")
    lines.append("# aren't actionable. For each kept entry:\n")
    lines.append('#   action: "mark_sold" | "update_fields"\n')
    lines.append('#   handle: <existing product handle> (or move into new_products:)\n')
    lines.append("#   price: <rupees as integer/float>\n")
    lines.append("#   source: <where the signal came from>\n\n")
    lines.append("changes:\n")
    for f in files:
        lines.append(f'  # source file: {f.name}\n')
        lines.append('  - handle: UNCERTAIN\n')
        lines.append('    action: mark_sold   # or update_fields\n')
        lines.append('    price: null\n')
        lines.append(f'    source: "{f.name}"\n\n')
    lines.append("# Any input file that represents a NEW SKU not in the current catalog\n")
    lines.append("# should move into this list instead:\n\n")
    lines.append("new_products: []\n")

    out.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote draft spec: {out.relative_to(REPO_ROOT)}")
    print()
    print("Next: open the YAML, resolve each UNCERTAIN entry (optionally with Claude),")
    print("rename to remove the `draft-` prefix, then run:")
    print(f"  python3 scripts/catalog-ops/generate-csv.py --spec catalog/change-specs/{today}-{args.label}.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
