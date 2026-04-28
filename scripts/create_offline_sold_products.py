#!/usr/bin/env python3
"""Create 4 placeholder Shopify products for Bill 1 pieces sold offline.

Status: DRAFT (not on storefront)
Tag: 'sold' (and qty=0 so they show as sold-out if ever activated)
Purpose: bookkeeping reconciliation — Bill 1 had 20 pieces, 16 are listed,
4 were sold to Friends & Family offline. This makes Shopify mirror reality.
"""
import json
import subprocess

STORE = "8chjhs-cd.myshopify.com"

# Revenue distribution: 4 offline pieces sold for ₹29,520 total (vendor: ₹96,500 - ₹66,980 Shopify)
# Distributed proportional to cost.
OFFLINE_PIECES = [
    {
        "handle": "23-yellow-kasab-suit-sold",
        "title": "Yellow Kasab Mul Chanderi Suit (Sold)",
        "sku": "23-yellow-kasab-suit-sold",
        "cost": 7500,
        "price": 7720,
        "bill_desc": "Suit Mul Chanderi Kasab (S/T) Yellow",
    },
    {
        "handle": "24-red-white-anarkali-1-sold",
        "title": "Red & White Anarkali #1 (Sold)",
        "sku": "24-red-white-anarkali-1-sold",
        "cost": 8000,
        "price": 8230,
        "bill_desc": "Anarkali Mul Chanderi (F/B) Red & White #1",
    },
    {
        "handle": "25-red-white-anarkali-2-sold",
        "title": "Red & White Anarkali #2 (Sold)",
        "sku": "25-red-white-anarkali-2-sold",
        "cost": 8000,
        "price": 8230,
        "bill_desc": "Anarkali Mul Chanderi (F/B) Red & White #2",
    },
    {
        "handle": "26-beige-cord-set-sold",
        "title": "Beige Limp Cord Set (Sold)",
        "sku": "26-beige-cord-set-sold",
        "cost": 5200,
        "price": 5340,
        "bill_desc": "Cord Set Limp Straight Beige",
    },
]


def gql(query, variables=None, allow_mutations=False):
    cmd = ["shopify", "store", "execute", "--store", STORE,
           "--query", query, "--json", "--no-color"]
    if variables:
        cmd.extend(["--variables", json.dumps(variables)])
    if allow_mutations:
        cmd.append("--allow-mutations")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    out = r.stdout
    i = out.find("{")
    data = json.loads(out[i:])
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data


def find_product_by_handle(handle):
    q = """query($q:String!){ products(first:5,query:$q){ nodes{ id handle status tags } } }"""
    data = gql(q, {"q": f"handle:{handle}"})
    for p in data["products"]["nodes"]:
        if p["handle"] == handle:
            return p
    return None


def create_draft_product(item):
    """Create DRAFT product, then update its default variant with sku/price/cost."""
    # Step 1: create product
    mut1 = """
    mutation($input: ProductInput!) {
      productCreate(input: $input) {
        product { id handle status tags
          variants(first:1){ nodes{ id sku inventoryItem { id } } }
        }
        userErrors { field message }
      }
    }
    """
    variables = {
        "input": {
            "title": item["title"],
            "handle": item["handle"],
            "status": "DRAFT",
            "tags": ["sold", "offline-sold", "first-lot"],
            "vendor": "Modern Chikan",
            "productType": "Suit",
            "descriptionHtml": (
                f"<p><em>This piece was sold offline to Friends &amp; Family on or before April 2026."
                f" It is recorded here for inventory reconciliation only and is not for sale.</em></p>"
                f"<p><strong>Source:</strong> Bill 1 (Modern Chikan, 2026-01-05) — "
                f"<em>{item['bill_desc']}</em></p>"
            ),
        }
    }
    data = gql(mut1, variables, allow_mutations=True)
    errs = data["productCreate"]["userErrors"]
    if errs:
        raise RuntimeError(errs)
    product = data["productCreate"]["product"]
    variant = product["variants"]["nodes"][0]

    # Step 2: update variant with sku + price + cost
    mut2 = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants { id sku price inventoryItem { id unitCost { amount } } }
        userErrors { field message }
      }
    }
    """
    variants_input = [{
        "id": variant["id"],
        "price": str(item["price"]),
        "inventoryItem": {
            "sku": item["sku"],
            "cost": str(item["cost"]),
            "tracked": True,
        },
    }]
    data2 = gql(mut2, {"productId": product["id"], "variants": variants_input},
                allow_mutations=True)
    errs2 = data2["productVariantsBulkUpdate"]["userErrors"]
    if errs2:
        raise RuntimeError(errs2)
    return product


def main():
    print("=== Creating 4 Shopify draft products for offline-sold Bill 1 pieces ===\n")
    for item in OFFLINE_PIECES:
        existing = find_product_by_handle(item["handle"])
        if existing:
            print(f"  · already exists  {item['handle']:35s} (status={existing['status']}, tags={existing['tags']})")
            continue
        try:
            p = create_draft_product(item)
            v = p["variants"]["nodes"][0]
            print(f"  ✓ created  {item['handle']:35s} sku={v['sku']} price=₹{item['price']} cost=₹{item['cost']}")
        except Exception as e:
            print(f"  ✗ FAILED  {item['handle']}: {e}")
    print()


if __name__ == "__main__":
    main()
