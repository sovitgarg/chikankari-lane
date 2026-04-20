#!/usr/bin/env python3
"""Generate a Shopify product-import CSV from a change-spec YAML.

Reads a "before" CSV (live Shopify export) and applies the changes described
in a YAML spec, writing an "after" CSV plus a human-readable diff.md.

Usage:
  generate-csv.py --spec <change-spec.yaml> [--before PATH] [--force] [--today YYYY-MM-DD]

Options:
  --spec PATH      Change-spec YAML. Required.
  --before PATH    Explicit path to the live Shopify export. If omitted, uses the
                   newest catalog/exports/YYYY-MM-DD-before.csv.
  --force          Overwrite today's after.csv if it already exists.
  --today DATE     Override today's date (for testing). Default: today in local tz.
  --repo-url URL   Override the GitHub raw-URL prefix. Default: computed from
                   `git remote get-url origin` + current branch.

Safety rails:
  - Refuses to run if --before is older than 24 hours (pass --force to bypass).
  - Refuses to overwrite an existing after.csv for the same date (pass --force).
  - Validates every handle in the spec exists in before.csv (unless action=new).
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.shopify_csv import (  # noqa: E402
    empty_row, format_price, is_product_row, normalize_tags, read_rows, write_rows,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--before", type=Path)
    p.add_argument("--force", action="store_true")
    p.add_argument("--today", type=str, default="")
    p.add_argument("--repo-url", type=str, default="")
    # Output-scope modes. Default: AUTO — if the spec has new_products but no
    # changes, emit only those new rows; otherwise emit the full catalog so
    # existing handles get refreshed by Shopify's Overwrite.
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--only-new-products", action="store_true",
                       help="Emit a minimal CSV with only the new_products rows. "
                            "Existing handles in before.csv are left untouched by Shopify.")
    scope.add_argument("--full-catalog", action="store_true",
                       help="Emit the full catalog (every existing row + any new ones). "
                            "Use when you want Shopify Overwrite to refresh existing products.")
    return p.parse_args()


def today_str(override: str) -> str:
    if override:
        # basic shape check
        dt.date.fromisoformat(override)
        return override
    return dt.date.today().isoformat()


def now_stamp() -> str:
    """YYYY-MM-DD-HHMM — used to make each generated output file unique."""
    return dt.datetime.now().strftime("%Y-%m-%d-%H%M")


def newest_before_csv(exports_dir: Path, today: str) -> Path:
    target = exports_dir / f"{today}-before.csv"
    if target.exists():
        return target
    candidates = sorted(exports_dir.glob("*-before.csv"))
    if not candidates:
        raise SystemExit(f"No before.csv found in {exports_dir}. Export from Shopify first.")
    return candidates[-1]


def ensure_fresh(path: Path, force: bool) -> None:
    age_hours = (dt.datetime.now().timestamp() - path.stat().st_mtime) / 3600
    if age_hours > 24 and not force:
        raise SystemExit(
            f"ERROR: {path.name} is {age_hours:.1f} hours old. "
            "Export a fresh copy from Shopify, or pass --force to bypass."
        )


def resolve_repo_url(override: str) -> str:
    if override:
        return override.rstrip("/")
    try:
        origin = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=REPO_ROOT, text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Could not determine GitHub remote/branch: {exc}") from exc

    # Normalize git@github.com:user/repo.git or https://github.com/user/repo.git
    m = re.match(r"^(?:git@github\.com:|https?://github\.com/)([^/]+)/([^/.]+)(?:\.git)?/?$", origin)
    if not m:
        raise SystemExit(f"Could not parse GitHub origin URL: {origin}")
    user, repo = m.group(1), m.group(2)
    return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}"


def github_image_url(repo_prefix: str, handle: str, filename: str) -> str:
    # image files live at catalog/products/<handle>/<filename>
    return f"{repo_prefix}/catalog/products/{handle}/{filename}"


def load_spec(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Spec at {path} did not parse as a mapping.")
    return data


def apply_update(row: OrderedDict, change: dict[str, Any]) -> list[str]:
    """Mutate the product-level row in place. Return list of human-readable changes."""
    log: list[str] = []
    action = change.get("action", "update_fields")

    if action == "mark_sold":
        price = change.get("price")
        if price is not None:
            old = row["Variant Price"]
            row["Variant Price"] = format_price(price)
            if old != row["Variant Price"]:
                log.append(f'price {old or "(blank)"} → {row["Variant Price"]}')
        old_qty = row["Variant Inventory Qty"]
        row["Variant Inventory Qty"] = "0"
        if old_qty != "0":
            log.append(f'qty {old_qty or "(blank)"} → 0')
        old_tags = row["Tags"]
        row["Tags"] = normalize_tags(old_tags, add=["sold"])
        if old_tags != row["Tags"]:
            log.append("tags: +sold")

    elif action == "update_fields":
        if "price" in change and change["price"] is not None:
            old = row["Variant Price"]
            row["Variant Price"] = format_price(change["price"])
            if old != row["Variant Price"]:
                log.append(f'price {old or "(blank)"} → {row["Variant Price"]}')
        if "qty" in change and change["qty"] is not None:
            old = row["Variant Inventory Qty"]
            row["Variant Inventory Qty"] = str(int(change["qty"]))
            if old != row["Variant Inventory Qty"]:
                log.append(f'qty {old or "(blank)"} → {row["Variant Inventory Qty"]}')
        if "set_type" in change:
            old = row["Type"]
            row["Type"] = change["set_type"]
            if old != row["Type"]:
                log.append(f'type "{old}" → "{row["Type"]}"')
        if "set_status" in change:
            old = row["Status"]
            row["Status"] = change["set_status"]
            if old != row["Status"]:
                log.append(f'status {old} → {row["Status"]}')
        add_tags = change.get("add_tags") or []
        remove_tags = change.get("remove_tags") or []
        if add_tags or remove_tags:
            old_tags = row["Tags"]
            row["Tags"] = normalize_tags(old_tags, add=add_tags, remove=remove_tags)
            if old_tags != row["Tags"]:
                delta_bits = []
                if add_tags:
                    delta_bits.append("+" + ",".join(add_tags))
                if remove_tags:
                    delta_bits.append("-" + ",".join(remove_tags))
                log.append("tags: " + " ".join(delta_bits))
    else:
        raise SystemExit(f'Unknown action "{action}" on handle {change.get("handle")}')
    return log


def normalize_all_available_qty(row: OrderedDict, log: list[str]) -> None:
    """If a product is active and qty != 0 and not sold, force qty = 1."""
    qty_str = (row["Variant Inventory Qty"] or "").strip()
    try:
        qty = int(qty_str)
    except (TypeError, ValueError):
        return  # don't touch rows we can't parse
    if qty == 0:
        return  # sold — leave alone
    if qty == 1:
        return  # already normalized
    row["Variant Inventory Qty"] = "1"
    log.append(f"qty {qty} → 1 (normalize)")


def build_new_product_rows(np: dict[str, Any], fieldnames: list[str], repo_prefix: str) -> list[OrderedDict]:
    handle = np["handle"]
    product_row = empty_row(fieldnames)
    product_row["Handle"] = handle
    product_row["Title"] = np["title"]
    product_row["Body (HTML)"] = np.get("body_html", "")
    product_row["Vendor"] = np.get("vendor", "Chikankari Lane")
    product_row["Product Category"] = np.get("product_category", "Apparel & Accessories > Clothing")
    product_row["Type"] = np.get("type", "Semistitched Suit")
    tags = np.get("tags") or []
    product_row["Tags"] = normalize_tags("", add=tags)
    status = np.get("status", "active")
    product_row["Published"] = "true" if status == "active" else "false"
    product_row["Option1 Name"] = "Title"
    product_row["Option1 Value"] = "Default Title"
    product_row["Variant SKU"] = np.get("sku", handle)
    product_row["Variant Grams"] = str(np.get("grams", "400.0"))
    product_row["Variant Inventory Tracker"] = "shopify"
    product_row["Variant Inventory Qty"] = str(int(np.get("qty", 1)))
    product_row["Variant Inventory Policy"] = "deny"
    product_row["Variant Fulfillment Service"] = "manual"
    product_row["Variant Price"] = format_price(np["price"])
    product_row["Variant Requires Shipping"] = "true"
    product_row["Variant Taxable"] = "true"
    product_row["Gift Card"] = "false"
    product_row["SEO Title"] = np.get("seo_title", f'{np["title"]} | Chikankari Lane')
    product_row["SEO Description"] = np.get("seo_description", np.get("body_html", "")[:160])
    product_row["Variant Weight Unit"] = np.get("weight_unit", "kg")
    product_row["Status"] = status

    # Image rows: first image goes on the product row itself.
    images = np.get("images") or []
    rows: list[OrderedDict] = []
    if images:
        product_row["Image Src"] = github_image_url(repo_prefix, handle, images[0])
        product_row["Image Position"] = "1"
        product_row["Image Alt Text"] = np.get("alt", np["title"])
        rows.append(product_row)
        for i, fname in enumerate(images[1:], start=2):
            r = empty_row(fieldnames)
            r["Handle"] = handle
            r["Image Src"] = github_image_url(repo_prefix, handle, fname)
            r["Image Position"] = str(i)
            r["Image Alt Text"] = np.get("alt", np["title"])
            rows.append(r)
    else:
        rows.append(product_row)
    return rows


def main() -> int:
    args = parse_args()
    today = today_str(args.today)
    exports_dir = REPO_ROOT / "catalog" / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    before_path = args.before or newest_before_csv(exports_dir, today)
    if not before_path.exists():
        raise SystemExit(f"Before CSV not found: {before_path}")
    ensure_fresh(before_path, args.force)

    spec = load_spec(args.spec)
    repo_prefix = resolve_repo_url(args.repo_url)
    print(f"Using before.csv : {before_path.relative_to(REPO_ROOT)}")
    print(f"Using spec       : {args.spec}")
    print(f"Raw-URL prefix   : {repo_prefix}")

    rows, fieldnames = read_rows(before_path)
    # Product-level rows keyed by handle
    product_row_by_handle: dict[str, OrderedDict] = {
        r["Handle"]: r for r in rows if is_product_row(r)
    }

    # Validate spec: every changed handle must exist, unless it's in new_products
    changes = spec.get("changes") or []
    new_products = spec.get("new_products") or []
    known_new_handles = {np["handle"] for np in new_products}
    for c in changes:
        h = c.get("handle")
        if not h:
            raise SystemExit(f"Spec change is missing handle: {c}")
        if h not in product_row_by_handle and h not in known_new_handles:
            raise SystemExit(f'Spec references unknown handle "{h}" (not in before.csv and not declared as new).')

    # Apply changes + normalize available qty to 1
    changelog: dict[str, list[str]] = {}
    for h, prow in product_row_by_handle.items():
        changelog.setdefault(h, [])

    normalize = bool(spec.get("normalize_qty_to_1", True))
    for c in changes:
        h = c["handle"]
        prow = product_row_by_handle[h]
        log = apply_update(prow, c)
        changelog[h].extend(log)

    if normalize:
        # Apply qty-normalization to everything not already acted on with qty=0
        for h, prow in product_row_by_handle.items():
            # Don't re-normalize if an explicit qty was set this round
            if any(entry.startswith("qty ") and entry.endswith("→ 0") for entry in changelog[h]):
                continue
            if any(entry.startswith("qty ") for entry in changelog[h]):
                continue
            normalize_all_available_qty(prow, changelog[h])

    # Collect any per-product video TODOs (CSV cannot carry videos)
    video_todos: dict[str, list[str]] = {}
    for c in changes:
        vids = c.get("videos") or []
        if vids:
            video_todos.setdefault(c["handle"], []).extend(vids)
    for np_spec in new_products:
        vids = np_spec.get("videos") or []
        if vids:
            video_todos.setdefault(np_spec["handle"], []).extend(vids)

    # Determine output scope.
    #   --only-new-products: emit only the new_products rows.
    #   --full-catalog: emit the whole before.csv + new rows.
    #   default (auto): if the spec has new_products but no changes, behave as
    #   --only-new-products so we don't accidentally rewrite untouched handles.
    if args.only_new_products:
        scope_mode = "only-new-products"
    elif args.full_catalog:
        scope_mode = "full-catalog"
    elif new_products and not changes:
        scope_mode = "only-new-products"
    else:
        scope_mode = "full-catalog"
    print(f"Output scope     : {scope_mode}")

    if scope_mode == "only-new-products":
        if not new_products:
            raise SystemExit("Spec has no new_products but --only-new-products was used.")
        out_rows: list[OrderedDict] = []
    else:
        out_rows = list(rows)

    for np_spec in new_products:
        new_rows = build_new_product_rows(np_spec, fieldnames, repo_prefix)
        out_rows.extend(new_rows)
        changelog[np_spec["handle"]] = [f'NEW  price={format_price(np_spec["price"])}  qty={np_spec.get("qty", 1)}  status={np_spec.get("status", "active")}']

    # Output filenames include a timestamp so repeated runs on the same day
    # never collide and remain auditable. Use --today to override the date.
    stamp = now_stamp() if not args.today else f'{args.today}-{dt.datetime.now().strftime("%H%M")}'
    scope_tag = "new" if scope_mode == "only-new-products" else "full"

    # Write after.csv
    after_path = exports_dir / f"{stamp}-{scope_tag}-after.csv"
    if after_path.exists() and not args.force:
        raise SystemExit(f"{after_path} already exists. Pass --force to overwrite.")
    write_rows(after_path, out_rows, fieldnames)
    print(f"Wrote {after_path.relative_to(REPO_ROOT)}  ({len(out_rows)} rows)")

    # Write diff.md
    diff_path = exports_dir / f"{stamp}-{scope_tag}-diff.md"
    diff_changelog = (
        {} if scope_mode == "only-new-products"
        else changelog
    )
    write_diff(diff_path, today, before_path, args.spec, repo_prefix, diff_changelog, product_row_by_handle, new_products, video_todos, scope_mode=scope_mode)
    print(f"Wrote {diff_path.relative_to(REPO_ROOT)}")

    if scope_mode == "only-new-products":
        print(f"\nProducts added  : {len(new_products)}")
        print("Existing products left untouched — this CSV will NOT modify any current Shopify product.")
    else:
        changed_count = sum(
            1 for h, log in changelog.items()
            if log and h in product_row_by_handle
        )
        print(f"\nProducts changed: {changed_count}")
        print(f"Products added  : {len(new_products)}")
    print("\nNext: review the diff, then upload after.csv to Shopify Products → Import")
    print('(enable "Overwrite any current products that have the same handle").')
    return 0


def write_diff(
    diff_path: Path,
    today: str,
    before_path: Path,
    spec_path: Path,
    repo_prefix: str,
    changelog: dict[str, list[str]],
    product_rows: dict[str, OrderedDict],
    new_products: list[dict],
    video_todos: dict[str, list[str]] | None = None,
    scope_mode: str = "full-catalog",
) -> None:
    video_todos = video_todos or {}
    lines: list[str] = []
    lines.append(f"# Shopify inventory diff — {today}\n\n")
    lines.append(f"- **Before**: `{before_path.relative_to(REPO_ROOT)}`\n")
    lines.append(f"- **Spec**:   `{spec_path}`\n")
    lines.append(f"- **Raw-URL prefix**: `{repo_prefix}`\n")
    lines.append(f"- **Scope**: `{scope_mode}`\n")
    if scope_mode == "only-new-products":
        lines.append(
            "- **Effect on existing products**: none. This CSV contains only new products; "
            "Shopify Overwrite only touches handles present in the CSV.\n"
        )
    lines.append("\n")

    changed = {h: log for h, log in changelog.items() if log and h in product_rows}
    unchanged = [h for h, log in changelog.items() if not log and h in product_rows]
    added = [np["handle"] for np in new_products]

    lines.append("## Summary\n\n")
    lines.append(f"- Products changed : **{len(changed)}**\n")
    lines.append(f"- Products added   : **{len(added)}**\n")
    lines.append(f"- Products unchanged: {len(unchanged)}\n\n")

    if changed:
        lines.append("## Changes\n\n")
        for h in sorted(changed):
            lines.append(f"### {h} — {product_rows[h]['Title']}\n")
            for entry in changed[h]:
                lines.append(f"- {entry}\n")
            lines.append("\n")

    if added:
        lines.append("## New products\n\n")
        for np in new_products:
            lines.append(f"### {np['handle']} — {np['title']}\n")
            lines.append(f"- price: `{format_price(np['price'])}`\n")
            lines.append(f"- qty: `{np.get('qty', 1)}`\n")
            lines.append(f"- status: `{np.get('status', 'active')}`\n")
            lines.append(f"- type: `{np.get('type', 'Semistitched Suit')}`\n")
            imgs = np.get("images") or []
            if imgs:
                lines.append(f"- images: {len(imgs)}\n")
            else:
                lines.append("- images: **none** (add via Shopify admin or re-run with images)\n")
            lines.append("\n")

    if video_todos:
        lines.append("## Video upload TODOs\n\n")
        lines.append(
            "Shopify's CSV import does not support video. Upload these files manually via "
            "Shopify Admin → Products → <product> → Media → Add media. Videos are stored in "
            "git under `catalog/products/<handle>/videos/`.\n\n"
        )
        for handle in sorted(video_todos):
            lines.append(f"- **{handle}**\n")
            for fname in video_todos[handle]:
                url = f"{repo_prefix}/catalog/products/{handle}/videos/{fname}"
                lines.append(f"  - `{fname}`  ·  {url}\n")
        lines.append("\n")

    if unchanged:
        lines.append("## Unchanged (for audit)\n\n")
        lines.append(", ".join(sorted(unchanged)) + "\n")

    diff_path.write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
