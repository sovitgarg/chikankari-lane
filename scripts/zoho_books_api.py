#!/usr/bin/env python3
"""Zoho Books API client for Chikankari Lane.

Lightweight wrapper around Zoho Books REST API v3 with:
- OAuth2 refresh-token flow (auto-refreshes access tokens)
- Idempotent CRUD helpers (find-or-create, find-or-update)
- Rate limit handling (Zoho: 100 req/min per user)
- Org safety check (aborts if connected to wrong org)

Auth setup: see specs/02-zoho-books-api-setup.md

Usage:
    from zoho_books_api import ZohoBooks
    zb = ZohoBooks()
    zb.verify_org()  # raises if wrong org
    vendor = zb.find_or_create_vendor("Modern Chikan")
"""
from __future__ import annotations

import os
import time
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "config" / "zoho.env"
TOKEN_CACHE = REPO_ROOT / "config" / ".zoho_access_token.json"


def _load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        raise FileNotFoundError(
            f"Missing {ENV_FILE}. Copy config/zoho.env.example to config/zoho.env and fill in.\n"
            f"Setup: specs/02-zoho-books-api-setup.md"
        )
    load_dotenv(ENV_FILE)
    required = ["ZOHO_REGION", "ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET",
                "ZOHO_REFRESH_TOKEN", "ZOHO_ORG_ID", "ZOHO_ORG_NAME"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise ValueError(f"Missing env vars in {ENV_FILE}: {missing}")
    return {k: os.getenv(k) for k in required}


class ZohoBooks:
    """Zoho Books API client with idempotent helpers."""

    def __init__(self) -> None:
        self.env = _load_env()
        self.region = self.env["ZOHO_REGION"]
        self.client_id = self.env["ZOHO_CLIENT_ID"]
        self.client_secret = self.env["ZOHO_CLIENT_SECRET"]
        self.refresh_token = self.env["ZOHO_REFRESH_TOKEN"]
        self.org_id = self.env["ZOHO_ORG_ID"]
        self.expected_org_name = self.env["ZOHO_ORG_NAME"]

        self.api_base = f"https://www.zohoapis.{self.region}/books/v3"
        self.accounts_base = f"https://accounts.zoho.{self.region}/oauth/v2"

        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0
        self._load_cached_token()

    # ------------------------------------------------------------------
    # OAuth
    # ------------------------------------------------------------------
    def _load_cached_token(self) -> None:
        if TOKEN_CACHE.exists():
            try:
                data = json.loads(TOKEN_CACHE.read_text())
                if data.get("expires_at", 0) > time.time() + 60:
                    self._access_token = data["access_token"]
                    self._access_token_expires_at = data["expires_at"]
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_cached_token(self) -> None:
        TOKEN_CACHE.write_text(json.dumps({
            "access_token": self._access_token,
            "expires_at": self._access_token_expires_at,
        }))
        TOKEN_CACHE.chmod(0o600)

    def _refresh_access_token(self) -> None:
        params = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        resp = requests.post(f"{self.accounts_base}/token", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"Token refresh failed: {data}")
        self._access_token = data["access_token"]
        self._access_token_expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        self._save_cached_token()

    def _ensure_token(self) -> str:
        if not self._access_token or time.time() >= self._access_token_expires_at:
            self._refresh_access_token()
        return self._access_token

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, *, params: Optional[dict] = None,
                 json_body: Optional[dict] = None, retries: int = 3) -> dict:
        token = self._ensure_token()
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        params = dict(params or {})
        params["organization_id"] = self.org_id

        url = f"{self.api_base}{path}"
        for attempt in range(retries):
            resp = requests.request(method, url, headers=headers, params=params,
                                     json=json_body, timeout=60)
            if resp.status_code == 401 and attempt < retries - 1:
                self._refresh_access_token()
                token = self._ensure_token()
                headers["Authorization"] = f"Zoho-oauthtoken {token}"
                continue
            if resp.status_code == 429:
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
                raise RuntimeError(f"{method} {path} failed: {resp.status_code} {data}")
            return data
        raise RuntimeError(f"{method} {path} failed after {retries} retries")

    # ------------------------------------------------------------------
    # Org safety
    # ------------------------------------------------------------------
    def verify_org(self) -> None:
        """Abort if connected to the wrong org. Call before any write."""
        data = self._request("GET", "/organizations")
        orgs = data.get("organizations", [])
        match = next((o for o in orgs if o.get("organization_id") == self.org_id), None)
        if not match:
            raise RuntimeError(
                f"Org ID {self.org_id} not found in this Zoho account. "
                f"Available orgs: {[(o.get('organization_id'), o.get('name')) for o in orgs]}"
            )
        actual_name = match.get("name", "")
        if actual_name.strip().lower() != self.expected_org_name.strip().lower():
            raise RuntimeError(
                f"Org safety check FAILED. Expected '{self.expected_org_name}', "
                f"got '{actual_name}'. Refusing to write."
            )
        is_gst_registered = match.get("tax_basis") in ("gst", "vat") or match.get("is_org_active_in_dc") and match.get("gst_registered", False)
        if is_gst_registered:
            print(f"  [warn] Org reports GST-registered. Bills will be imported at 0% tax — "
                   "verify this is intended.")
        print(f"[org-check] ✓ Connected to '{actual_name}' (id={self.org_id})")

    # ------------------------------------------------------------------
    # Vendors (Contacts with contact_type=vendor)
    # ------------------------------------------------------------------
    def find_vendor(self, name: str) -> Optional[dict]:
        data = self._request("GET", "/contacts", params={
            "contact_name_contains": name,
            "contact_type": "vendor",
        })
        contacts = data.get("contacts", [])
        # exact match first
        for c in contacts:
            if c.get("contact_name", "").strip().lower() == name.strip().lower():
                return c
        # fuzzy: first result containing the name
        return contacts[0] if contacts else None

    def create_vendor(self, name: str, **fields) -> dict:
        body = {"contact_name": name, "contact_type": "vendor", **fields}
        data = self._request("POST", "/contacts", json_body=body)
        return data["contact"]

    def find_or_create_vendor(self, name: str, **fields) -> tuple[dict, str]:
        """Returns (vendor, action) where action is 'reused' or 'created'."""
        existing = self.find_vendor(name)
        if existing:
            return existing, "reused"
        return self.create_vendor(name, **fields), "created"

    # ------------------------------------------------------------------
    # Chart of Accounts
    # ------------------------------------------------------------------
    def find_account(self, name: str, account_type: str = "expense") -> Optional[dict]:
        # Zoho expects capitalized filter values like AccountType.Expense
        cap = account_type.capitalize()
        data = self._request("GET", "/chartofaccounts", params={
            "filter_by": f"AccountType.{cap}",
        })
        accounts = data.get("chartofaccounts", [])
        # exact match
        for a in accounts:
            if a.get("account_name", "").strip().lower() == name.strip().lower():
                return a
        # fuzzy match (substring either direction)
        n = name.strip().lower()
        for a in accounts:
            an = a.get("account_name", "").strip().lower()
            if n in an or an in n:
                return a
        return None

    def create_account(self, name: str, account_type: str = "expense") -> dict:
        body = {"account_name": name, "account_type": account_type}
        data = self._request("POST", "/chartofaccounts", json_body=body)
        return data["chart_of_account"]

    def find_or_create_account(self, name: str, account_type: str = "expense") -> tuple[dict, str]:
        existing = self.find_account(name, account_type)
        if existing:
            action = "reused" if existing.get("account_name", "").lower() == name.lower() else "fuzzy-reused"
            return existing, action
        return self.create_account(name, account_type), "created"

    # ------------------------------------------------------------------
    # Vendor Bills
    # ------------------------------------------------------------------
    def find_bill(self, vendor_id: str, bill_date: str, bill_number: Optional[str] = None) -> Optional[dict]:
        params = {"vendor_id": vendor_id, "date": bill_date}
        if bill_number:
            params["bill_number"] = bill_number
        data = self._request("GET", "/bills", params=params)
        bills = data.get("bills", [])
        return bills[0] if bills else None

    def create_bill(self, vendor_id: str, bill_date: str, bill_number: str,
                     line_items: list[dict], notes: str = "") -> dict:
        body = {
            "vendor_id": vendor_id,
            "bill_number": bill_number,
            "date": bill_date,
            "line_items": line_items,
            "notes": notes,
        }
        data = self._request("POST", "/bills", json_body=body)
        return data["bill"]

    def update_bill(self, bill_id: str, vendor_id: str, bill_date: str, bill_number: str,
                     line_items: list[dict], notes: str = "") -> dict:
        body = {
            "vendor_id": vendor_id,
            "bill_number": bill_number,
            "date": bill_date,
            "line_items": line_items,
            "notes": notes,
        }
        data = self._request("PUT", f"/bills/{bill_id}", json_body=body)
        return data["bill"]

    def upsert_bill(self, vendor_id: str, bill_date: str, bill_number: str,
                     line_items: list[dict], notes: str = "") -> tuple[dict, str]:
        existing = self.find_bill(vendor_id, bill_date, bill_number)
        if existing:
            updated = self.update_bill(existing["bill_id"], vendor_id, bill_date,
                                         bill_number, line_items, notes)
            return updated, "overwritten"
        created = self.create_bill(vendor_id, bill_date, bill_number, line_items, notes)
        return created, "created"

    def mark_bill_paid(self, bill_id: str, amount: float, payment_date: str,
                        payment_mode: str = "cash") -> dict:
        body = {
            "vendor_id": "",  # filled by API from bill
            "bill_ids": bill_id,
            "amount": amount,
            "date": payment_date,
            "payment_mode": payment_mode,
            "bills": [{"bill_id": bill_id, "amount_applied": amount}],
        }
        # /vendorpayments expects vendor_id; refetch bill to get it
        bill = self._request("GET", f"/bills/{bill_id}")["bill"]
        body["vendor_id"] = bill["vendor_id"]
        data = self._request("POST", "/vendorpayments", json_body=body)
        return data.get("vendorpayment", data)

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------
    def find_expense(self, account_id: str, expense_date: str, amount: float,
                     vendor_id: Optional[str] = None) -> Optional[dict]:
        params = {"account_id": account_id, "date_start": expense_date,
                  "date_end": expense_date}
        if vendor_id:
            params["vendor_id"] = vendor_id
        data = self._request("GET", "/expenses", params=params)
        expenses = data.get("expenses", [])
        for e in expenses:
            if abs(float(e.get("total", 0)) - amount) < 0.01:
                return e
        return None

    def create_expense(self, account_id: str, expense_date: str, amount: float,
                        description: str, vendor_id: Optional[str] = None,
                        paid_through_account_id: Optional[str] = None) -> dict:
        body = {
            "account_id": account_id,
            "date": expense_date,
            "amount": amount,
            "description": description,
        }
        if vendor_id:
            body["vendor_id"] = vendor_id
        if paid_through_account_id:
            body["paid_through_account_id"] = paid_through_account_id
        data = self._request("POST", "/expenses", json_body=body)
        return data["expense"]

    def update_expense(self, expense_id: str, account_id: str, expense_date: str,
                        amount: float, description: str,
                        vendor_id: Optional[str] = None) -> dict:
        body = {
            "account_id": account_id,
            "date": expense_date,
            "amount": amount,
            "description": description,
        }
        if vendor_id:
            body["vendor_id"] = vendor_id
        data = self._request("PUT", f"/expenses/{expense_id}", json_body=body)
        return data["expense"]

    def upsert_expense(self, account_id: str, expense_date: str, amount: float,
                        description: str, vendor_id: Optional[str] = None) -> tuple[dict, str]:
        existing = self.find_expense(account_id, expense_date, amount, vendor_id)
        if existing:
            updated = self.update_expense(existing["expense_id"], account_id,
                                            expense_date, amount, description, vendor_id)
            return updated, "overwritten"
        created = self.create_expense(account_id, expense_date, amount, description,
                                        vendor_id)
        return created, "created"

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------
    def find_item_by_sku(self, sku: str) -> Optional[dict]:
        data = self._request("GET", "/items", params={"sku": sku})
        items = data.get("items", [])
        for i in items:
            if i.get("sku", "").strip().lower() == sku.strip().lower():
                return i
        return items[0] if items else None

    def update_item_purchase_rate(self, item_id: str, purchase_rate: float) -> dict:
        body = {"purchase_rate": purchase_rate}
        data = self._request("PUT", f"/items/{item_id}", json_body=body)
        return data["item"]

    def upsert_item_cost(self, sku: str, purchase_rate: float) -> tuple[Optional[dict], str]:
        existing = self.find_item_by_sku(sku)
        if not existing:
            return None, "skipped (not found - run Shopify sync first)"
        updated = self.update_item_purchase_rate(existing["item_id"], purchase_rate)
        return updated, "updated"

    def create_item(self, name: str, sku: str, rate: float, purchase_rate: float,
                     item_type: str = "inventory") -> dict:
        """Create a new Item in Zoho Books with both selling rate and cost."""
        body = {
            "name": name,
            "sku": sku,
            "rate": rate,
            "purchase_rate": purchase_rate,
            "item_type": item_type,
            "product_type": "goods",
        }
        data = self._request("POST", "/items", json_body=body)
        return data["item"]

    def upsert_item_full(self, sku: str, name: str, rate: float,
                          purchase_rate: float) -> tuple[dict, str]:
        """Create item if missing; update rate+cost if exists. Returns (item, action)."""
        existing = self.find_item_by_sku(sku)
        if existing:
            # Update both rate and purchase_rate
            body = {"rate": rate, "purchase_rate": purchase_rate, "name": name}
            data = self._request("PUT", f"/items/{existing['item_id']}", json_body=body)
            return data["item"], "updated"
        # Try inventory first; fall back to non-inventory if Zoho org doesn't have inventory enabled
        try:
            return self.create_item(name, sku, rate, purchase_rate, "inventory"), "created-inventory"
        except RuntimeError as e:
            if "inventory" in str(e).lower() or "tracking" in str(e).lower():
                return self.create_item(name, sku, rate, purchase_rate, "sales_and_purchases"), "created-sales-purchase"
            raise


if __name__ == "__main__":
    # Quick smoke test
    zb = ZohoBooks()
    zb.verify_org()
    print("API client OK")
