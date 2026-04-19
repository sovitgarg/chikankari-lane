# Shopify Custom App Setup

**This is the single blocker for all automation.** ~5 minutes of clicks. After this, Claude can drive everything else via API.

## Steps

1. Go to [admin.shopify.com/store/chikankari-lane-2](https://admin.shopify.com/store/chikankari-lane-2)
2. Click **Settings** (bottom-left gear icon)
3. Click **Apps and sales channels** in the left menu
4. Click **Develop apps** (top-right)
5. If prompted, click **Allow custom app development** → confirm
6. Click **Create an app** (top-right)
7. App name: `Claude Automation` → Click **Create app**
8. Click **Configure Admin API scopes**
9. Check these scopes (use the search box to find each):

### Required scopes

**Products & inventory**
- `write_products`, `read_products`
- `write_product_listings`, `read_product_listings`
- `write_inventory`, `read_inventory`
- `write_publications`, `read_publications`

**Themes & content**
- `write_themes`, `read_themes`
- `write_content`, `read_content`
- `write_online_store_pages`, `read_online_store_pages`
- `write_online_store_navigation`, `read_online_store_navigation`
- `write_files`, `read_files`
- `write_locales`, `read_locales`
- `write_translations`, `read_translations`

**Commerce**
- `write_shipping`, `read_shipping`
- `write_orders`, `read_orders`
- `write_customers`, `read_customers`
- `write_discounts`, `read_discounts`
- `write_price_rules`, `read_price_rules`

**Metafields (for fabric, stitch type, care instructions)**
- `write_metaobjects`, `read_metaobjects`
- `write_metaobject_definitions`, `read_metaobject_definitions`

10. Click **Save** (top-right)
11. Click **API credentials** tab
12. Click **Install app** → **Install**
13. Under **Admin API access token**, click **Reveal token once** and copy it immediately
    - **Critical:** Shopify only shows it once. If you lose it, you have to regenerate.
14. Also copy **API key** and **API secret key** (shown lower on the same page)

## Paste credentials back to Claude

Reply in chat with this exact format (so Claude knows what's what):

```
SHOPIFY_STORE: chikankari-lane-2
SHOPIFY_ADMIN_API_TOKEN: shpat_xxxxxxxxxxxxx
SHOPIFY_API_KEY: xxxxxxxxxxxx
SHOPIFY_API_SECRET: xxxxxxxxxxxx
```

Claude will save these to `config/shopify.env` (gitignored) with restricted file permissions.

## Kill switch

If you ever want to revoke Claude's access:
- Settings → Apps and sales channels → Develop apps → Claude Automation → Uninstall
- Instant. No further API calls possible after that.
