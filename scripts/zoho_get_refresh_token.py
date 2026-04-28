#!/usr/bin/env python3
"""One-time script: exchange a Zoho self-client grant token for a refresh token.

Setup steps (do these in browser first):
  1. Go to https://api-console.zoho.in (use .in for India data center)
  2. Add Client -> Self Client -> create
  3. Copy Client ID and Client Secret to config/zoho.env
  4. Click "Generate Code" tab
  5. Scope: ZohoBooks.fullaccess.all
     Time Duration: 10 minutes (you must use it before it expires)
  6. Copy the generated code and pass to this script:
       python3 scripts/zoho_get_refresh_token.py <grant_code>
  7. The script writes ZOHO_REFRESH_TOKEN into config/zoho.env

The refresh token is long-lived. You only do this once.
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / "config" / "zoho.env"


def main(grant_code: str) -> None:
    if not ENV_FILE.exists():
        print(f"ERROR: {ENV_FILE} missing. Copy from config/zoho.env.example first.")
        sys.exit(1)

    load_dotenv(ENV_FILE)
    region = os.getenv("ZOHO_REGION", "in")
    client_id = os.getenv("ZOHO_CLIENT_ID")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET not set in config/zoho.env")
        sys.exit(1)

    url = f"https://accounts.zoho.{region}/oauth/v2/token"
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": grant_code,
    }
    resp = requests.post(url, params=params, timeout=30)
    data = resp.json()
    if "refresh_token" not in data:
        print(f"ERROR: no refresh_token in response: {data}")
        sys.exit(1)

    refresh_token = data["refresh_token"]
    print(f"Got refresh token: {refresh_token[:12]}...")

    # Update .env file in place
    lines = ENV_FILE.read_text().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("ZOHO_REFRESH_TOKEN="):
            new_lines.append(f"ZOHO_REFRESH_TOKEN={refresh_token}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"ZOHO_REFRESH_TOKEN={refresh_token}")
    ENV_FILE.write_text("\n".join(new_lines) + "\n")
    print(f"✓ Wrote refresh token to {ENV_FILE}")
    print("\nNext: run `python3 scripts/sync_zoho.py --dry-run` to verify auth.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
