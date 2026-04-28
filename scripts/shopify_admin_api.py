#!/usr/bin/env python3
"""Shopify Admin API client for Chikankari Lane.

GraphQL-based wrapper around the Shopify Admin API with:
- Token auth from config/shopify.env
- Idempotent CRUD helpers (find by SKU, update cost, update price, update tags, etc.)
- Rate-limit handling (Shopify uses leaky-bucket cost-based limits)
- Store safety check (aborts if connected to wrong store)

Auth setup: see specs/03-shopify-admin-api-setup.md (extends specs/01-...)

Usage:
    from shopify_admin_api import ShopifyAdmin
    sa = ShopifyAdmin()
    sa.verify_store()  # raises if wrong store
    variant = sa.find_variant_by_sku("01-crimson-paisley-suit")
    sa.update_variant_cost(variant["id"], 8200)
"""
from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "config" / "shopify.env"

# Latest stable Shopify API version. Bump quarterly.
API_VERSION = "2025-01"


def _load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        raise FileNotFoundError(
            f"Missing {ENV_FILE}. See specs/01-shopify-custom-app-setup.md and "
            f"specs/03-shopify-admin-api-setup.md for setup."
        )
    load_dotenv(ENV_FILE)
    required = ["SHOPIFY_STORE_HANDLE", "SHOPIFY_ADMIN_API_TOKEN"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing env vars in {ENV_FILE}: {missing}")
    return {k: os.getenv(k) for k in [
        "SHOPIFY_STORE_DOMAIN", "SHOPIFY_STORE_HANDLE", "SHOPIFY_ADMIN_API_TOKEN"
    ] if os.getenv(k)}


class ShopifyAdmin:
    """Shopify Admin API client (GraphQL) with idempotent helpers."""

    def __init__(self) -> None:
        self.env = _load_env()
        self.store_handle = self.env["SHOPIFY_STORE_HANDLE"]
        self.token = self.env["SHOPIFY_ADMIN_API_TOKEN"]
        self.store_domain = self.env.get(
            "SHOPIFY_STORE_DOMAIN", f"{self.store_handle}.myshopify.com"
        )
        self.graphql_url = (
            f"https://{self.store_domain}/admin/api/{API_VERSION}/graphql.json"
        )
        self._default_location_id: Optional[str] = None

    # ------------------------------------------------------------------
    # HTTP / GraphQL
    # ------------------------------------------------------------------
    def _request(self, query: str, variables: Optional[dict] = None,
                  retries: int = 3) -> dict:
        headers = {
            "X-Shopify-Access-Token": self.token,
            "Content-Type": "application/json",
        }
        body = {"query": query, "variables": variables or {}}

        for attempt in range(retries):
            resp = requests.post(self.graphql_url, headers=headers,
                                  json=body, timeout=60)
            if resp.status_code == 429 and attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  [rate-limit] sleeping {wait}s")
                time.sleep(wait)
                continue
            try:
                data = resp.json()
            except json.JSONDecodeError:
                resp.raise_for_status()
                raise
            if not resp.ok:
                raise RuntimeError(
                    f"GraphQL HTTP {resp.status_code}: {data}"
                )
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            # Check for rate-limit signal in extensions
            cost = data.get("extensions", {}).get("cost", {})
            throttle = cost.get("throttleStatus", {})
            available = throttle.get("currentlyAvailable", 1000)
            if available < 100:
                # Sleep proportional to how depleted the bucket is
                time.sleep(1)
            return data["data"]
        raise RuntimeError(f"Request failed after {retries} retries")

    # ------------------------------------------------------------------
    # Store safety
    # ------------------------------------------------------------------
    def verify_store(self) -> None:
        """Abort if connected to the wrong store. Call before any write."""
        query = """
        query { shop { name myshopifyDomain } }
        """
        data = self._request(query)
        shop = data["shop"]
        actual_domain = shop["myshopifyDomain"]
        expected = f"{self.store_handle}.myshopify.com"
        if actual_domain != expected:
            raise RuntimeError(
                f"Store safety check FAILED. Expected '{expected}', "
                f"got '{actual_domain}'. Refusing to write."
            )
        print(f"[store-check] ✓ Connected to '{shop['name']}' ({actual_domain})")

    # ------------------------------------------------------------------
    # Locations (needed for inventory updates)
    # ------------------------------------------------------------------
    def get_default_location_id(self) -> str:
        """Returns the primary fulfillment location ID. Cached."""
        if self._default_location_id:
            return self._default_location_id
        query = """
        query { locations(first: 5) { nodes { id name isPrimary } } }
        """
        data = self._request(query)
        locs = data["locations"]["nodes"]
        primary = next((l for l in locs if l["isPrimary"]), None) or locs[0]
        self._default_location_id = primary["id"]
        return primary["id"]

    # ------------------------------------------------------------------
    # Products / Variants — read
    # ------------------------------------------------------------------
    def find_variant_by_sku(self, sku: str) -> Optional[dict]:
        """Look up a variant by SKU. Returns variant dict or None.

        Variant includes: id, sku, price, inventoryItem.id, product.id,
        product.handle, product.title.
        """
        query = """
        query($q: String!) {
          productVariants(first: 5, query: $q) {
            nodes {
              id sku price
              inventoryItem { id unitCost { amount } }
              product { id handle title status tags productType }
            }
          }
        }
        """
        data = self._request(query, {"q": f"sku:{sku}"})
        variants = data["productVariants"]["nodes"]
        # exact match first
        for v in variants:
            if v.get("sku", "").strip().lower() == sku.strip().lower():
                return v
        return variants[0] if variants else None

    def find_product_by_handle(self, handle: str) -> Optional[dict]:
        query = """
        query($q: String!) {
          products(first: 5, query: $q) {
            nodes {
              id handle title status tags productType
              variants(first: 10) { nodes { id sku price } }
            }
          }
        }
        """
        data = self._request(query, {"q": f"handle:{handle}"})
        products = data["products"]["nodes"]
        for p in products:
            if p.get("handle", "").strip().lower() == handle.strip().lower():
                return p
        return products[0] if products else None

    def list_all_active_variants(self) -> list[dict]:
        """Pages through all variants on active products. Returns list of dicts."""
        all_variants = []
        cursor = None
        query = """
        query($cursor: String) {
          products(first: 50, after: $cursor, query: "status:active") {
            pageInfo { hasNextPage endCursor }
            nodes {
              id handle title
              variants(first: 10) {
                nodes {
                  id sku price
                  inventoryItem { id unitCost { amount } }
                }
              }
            }
          }
        }
        """
        while True:
            data = self._request(query, {"cursor": cursor})
            for product in data["products"]["nodes"]:
                for v in product["variants"]["nodes"]:
                    v["product_handle"] = product["handle"]
                    v["product_title"] = product["title"]
                    all_variants.append(v)
            page = data["products"]["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]
        return all_variants

    # ------------------------------------------------------------------
    # Cost (Cost per item) — InventoryItem.unitCost
    # ------------------------------------------------------------------
    def update_variant_cost(self, inventory_item_id: str, cost: float) -> dict:
        """Set Cost per item on a variant via its inventoryItem."""
        mutation = """
        mutation($id: ID!, $input: InventoryItemInput!) {
          inventoryItemUpdate(id: $id, input: $input) {
            inventoryItem { id unitCost { amount } }
            userErrors { field message }
          }
        }
        """
        variables = {
            "id": inventory_item_id,
            "input": {"cost": str(cost)},
        }
        data = self._request(mutation, variables)
        result = data["inventoryItemUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"inventoryItemUpdate errors: {result['userErrors']}")
        return result["inventoryItem"]

    def upsert_cost_by_sku(self, sku: str, cost: float) -> tuple[Optional[dict], str]:
        """Idempotent cost update by SKU. Returns (variant, action).

        Actions: 'updated', 'unchanged', 'skipped (not found)'
        """
        variant = self.find_variant_by_sku(sku)
        if not variant:
            return None, "skipped (not found)"
        current_cost_str = (variant.get("inventoryItem", {}) or {}).get("unitCost") or {}
        current_cost = float(current_cost_str.get("amount", 0)) if current_cost_str else 0
        if abs(current_cost - cost) < 0.01:
            return variant, "unchanged"
        inv_item_id = variant["inventoryItem"]["id"]
        self.update_variant_cost(inv_item_id, cost)
        return variant, "updated"

    # ------------------------------------------------------------------
    # Price — ProductVariant.price (via productVariantsBulkUpdate)
    # ------------------------------------------------------------------
    def update_variant_price(self, product_id: str, variant_id: str,
                              price: float) -> dict:
        mutation = """
        mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
          productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            productVariants { id price }
            userErrors { field message }
          }
        }
        """
        variables = {
            "productId": product_id,
            "variants": [{"id": variant_id, "price": str(price)}],
        }
        data = self._request(mutation, variables)
        result = data["productVariantsBulkUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"price update errors: {result['userErrors']}")
        return result["productVariants"][0]

    def upsert_price_by_sku(self, sku: str, price: float) -> tuple[Optional[dict], str]:
        variant = self.find_variant_by_sku(sku)
        if not variant:
            return None, "skipped (not found)"
        current_price = float(variant.get("price", 0))
        if abs(current_price - price) < 0.01:
            return variant, "unchanged"
        self.update_variant_price(variant["product"]["id"], variant["id"], price)
        return variant, "updated"

    # ------------------------------------------------------------------
    # Tags / Type / Status — Product-level fields
    # ------------------------------------------------------------------
    def update_product_fields(self, product_id: str, *,
                                tags: Optional[list[str]] = None,
                                product_type: Optional[str] = None,
                                status: Optional[str] = None) -> dict:
        """Update product-level fields. Pass only the ones you want changed."""
        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id tags productType status }
            userErrors { field message }
          }
        }
        """
        product_input = {"id": product_id}
        if tags is not None:
            product_input["tags"] = tags
        if product_type is not None:
            product_input["productType"] = product_type
        if status is not None:
            product_input["status"] = status.upper()
        data = self._request(mutation, {"input": product_input})
        result = data["productUpdate"]
        if result["userErrors"]:
            raise RuntimeError(f"productUpdate errors: {result['userErrors']}")
        return result["product"]

    def add_tag_to_product(self, sku: str, tag: str) -> tuple[Optional[dict], str]:
        variant = self.find_variant_by_sku(sku)
        if not variant:
            return None, "skipped (not found)"
        product = variant["product"]
        current_tags = [t.strip() for t in product.get("tags", []) if t.strip()]
        if tag.lower() in [t.lower() for t in current_tags]:
            return product, "unchanged"
        new_tags = sorted(set(current_tags + [tag]), key=str.lower)
        self.update_product_fields(product["id"], tags=new_tags)
        return product, "tag-added"

    def remove_tag_from_product(self, sku: str, tag: str) -> tuple[Optional[dict], str]:
        variant = self.find_variant_by_sku(sku)
        if not variant:
            return None, "skipped (not found)"
        product = variant["product"]
        current_tags = [t.strip() for t in product.get("tags", []) if t.strip()]
        new_tags = [t for t in current_tags if t.lower() != tag.lower()]
        if len(new_tags) == len(current_tags):
            return product, "unchanged"
        self.update_product_fields(product["id"], tags=sorted(new_tags, key=str.lower))
        return product, "tag-removed"

    # ------------------------------------------------------------------
    # Inventory — set absolute quantity at default location
    # ------------------------------------------------------------------
    def set_variant_inventory(self, sku: str, qty: int) -> tuple[Optional[dict], str]:
        variant = self.find_variant_by_sku(sku)
        if not variant:
            return None, "skipped (not found)"
        location_id = self.get_default_location_id()
        inv_item_id = variant["inventoryItem"]["id"]
        mutation = """
        mutation($input: InventorySetOnHandQuantitiesInput!) {
          inventorySetOnHandQuantities(input: $input) {
            inventoryAdjustmentGroup { id }
            userErrors { field message }
          }
        }
        """
        variables = {
            "input": {
                "reason": "correction",
                "setQuantities": [{
                    "inventoryItemId": inv_item_id,
                    "locationId": location_id,
                    "quantity": qty,
                }],
            }
        }
        data = self._request(mutation, variables)
        result = data["inventorySetOnHandQuantities"]
        if result["userErrors"]:
            raise RuntimeError(f"inventory set errors: {result['userErrors']}")
        return variant, "inventory-set"


if __name__ == "__main__":
    sa = ShopifyAdmin()
    sa.verify_store()
    print("API client OK")
