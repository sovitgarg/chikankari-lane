#!/usr/bin/env python3
"""Generate PRODUCT.md for each product folder + a Shopify import CSV."""
import csv
import os
from pathlib import Path

ROOT = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/products")
CSV_OUT = Path("/Users/sovitgarg/Learning/chikankari-lane/catalog/shopify_products.csv")

# (slug, title, type, color, fabric, primary_tag, occasion_tags, body_html_paragraphs)
PRODUCTS = [
    ("01-crimson-paisley-kurta",
     "Crimson Paisley Kurta",
     "Kurta", "Crimson Red", "Mul Cotton", "kurta",
     ["festive", "bridal"],
     ["Hand-embroidered in Lucknow with white chikankari paisley and floral motifs on a deep crimson mul cotton base.",
      "The yoke and borders carry generous keri (paisley) and bel (vine) work in dense bakhiya shadow stitch — the most striking signature of Lucknowi chikankari, where the embroidery is worked from the reverse and shows through softly on the front.",
      "A festive piece designed to anchor wedding-season dressing. Pair with churidar and a contrasting dupatta."]),

    ("02-powder-blue-floral-kurta",
     "Powder Blue Floral Kurta",
     "Kurta", "Powder Blue", "Mul Cotton", "kurta",
     ["festive", "everyday"],
     ["A tonal study in powder blue and white. Dense allover chikankari floral work in fine bakhiya and jaali — the embroidery so closely set it reads almost like lace.",
      "Mul cotton keeps it breathable through long summer afternoons. The whole piece is the work of weeks of hand-stitching by a single artisan family in Lucknow.",
      "Wears beautifully on its own with white churidar, or layered with deeper jewel tones for festive occasions."]),

    ("03-sky-blue-chikankari-dupatta",
     "Sky Blue Chikankari Dupatta",
     "Dupatta", "Sky Blue", "Mul Cotton", "dupatta",
     ["everyday", "festive"],
     ["A featherweight sky-blue mul dupatta with open jaali (net) and linear floral chikankari — sparser, sketch-like work that lets the fabric breathe.",
      "The scalloped embroidered edge is a defining touch — chikankari at its most restrained.",
      "Drapes effortlessly over a plain kurta or a fitted blouse for an instant lift."]),

    ("04-sky-blue-striped-sequin-kurta",
     "Sky Blue Striped Sequin Kurta",
     "Kurta", "Sky Blue", "Cotton Chanderi", "kurta",
     ["festive"],
     ["Vertical pinstripe stitching runs the length of this sky-blue kurta, broken by a delicate floral medallion at the centre of the yoke.",
      "Mukaish (metallic dotting) and fine murri stitches catch the light — a quietly glamorous touch usually reserved for festive chikankari.",
      "Best styled with a contrast dupatta and kundan jewellery."]),

    ("05-silver-grey-floral-dupatta",
     "Silver Grey Floral Dupatta",
     "Dupatta", "Silver Grey", "Georgette", "dupatta",
     ["festive", "bridal"],
     ["A long, sheer silver-grey georgette dupatta with scattered floral cluster motifs — small bouquets in jaali and phanda, distributed in airy, hand-placed groupings.",
      "Light, almost weightless. Designed to drape over festive lehengas and anarkalis without weight or fuss.",
      "The grey base is rare in chikankari and pairs particularly well with both pastels and jewel tones."]),

    ("06-pearl-cluster-chikankari-kurta",
     "Pearl Cluster Chikankari Kurta",
     "Kurta", "Pale Silver Blue", "Cotton Chanderi", "kurta",
     ["festive", "bridal"],
     ["Vertical panels of raised murri-cluster floral work — tiny rice-shaped knots arranged like pearls — give this pale silver-blue kurta its name.",
      "The texture is unusually three-dimensional for chikankari, the result of layered phanda and murri stitches placed densely in vertical bands.",
      "An understated festive piece. Pair with a matching dupatta and silver jewellery."]),

    ("07-oatmeal-medallion-kurta",
     "Oatmeal Medallion Kurta",
     "Kurta", "Oatmeal", "Mul Cotton", "kurta",
     ["everyday", "festive"],
     ["A warm oatmeal mul kurta with vertical panels of white chikankari — large circular sunflower medallions framed by dense bel (vine) borders.",
      "Fine murri and phanda stitches catch the light and add depth across the body.",
      "Equally at home for daytime occasions and quiet evening events."]),

    ("08-beige-striped-border-dupatta",
     "Beige Striped Border Dupatta",
     "Dupatta", "Beige", "Striped Cotton", "dupatta",
     ["everyday"],
     ["A subtly striped beige cotton dupatta finished with a single horizontal band of white chikankari medallions and bel work along one border.",
      "Restrained, everyday-wearable — the kind of piece that quietly elevates a plain kurta into something thought-through."]),

    ("09-oatmeal-collared-chikankari-kurta",
     "Oatmeal Collared Chikankari Kurta",
     "Kurta", "Oatmeal", "Textured Cotton", "kurta",
     ["workwear", "everyday"],
     ["A shirt-style collared kurta in oatmeal textured cotton — a less common silhouette in chikankari, designed to bridge ethnic and contemporary wardrobes.",
      "Vertical panels alternate between jaali (net) stripes and floral medallion bands. The jaali work is created by separating the warp and weft threads of the fabric and binding the spaces with tiny buttonhole stitches — no thread is pulled through the cloth.",
      "Wear with straight pants for work, or with churidar and jhumkas for an evening out."]),

    ("10-cornflower-blue-sunflower-kurta",
     "Cornflower Blue Sunflower Kurta",
     "Kurta", "Cornflower Blue", "Checkered Mul Cotton", "kurta",
     ["festive", "everyday"],
     ["The deepest blue in the collection — a cornflower mul cotton kurta with a fine self-checked weave running through the body.",
      "White chikankari concentrates at the yoke in a large central sunflower motif framed by bel borders. Murri and shadow-work stitches sit close together, building texture without weight.",
      "Pairs beautifully with white or off-white bottoms and contrast jewellery."]),

    ("11-ivory-pink-chikankari-dupatta",
     "Ivory & Pink Chikankari Dupatta",
     "Dupatta", "Ivory & Pink", "Mul Cotton", "dupatta",
     ["festive", "everyday"],
     ["An ivory mul dupatta worked in a soft pink chikankari thread — a geometric diamond-lattice pattern with a tasselled, fringed edge.",
      "Pink-on-ivory is a deeply traditional Lucknowi colourway. The diamond lattice is built from short repeated stitches, hand-counted across the weave."]),

    ("12-ivory-mul-pink-chikankari-kurta",
     "Ivory Mul Kurta with Pink Chikankari",
     "Kurta", "Ivory with Pink", "Mul Cotton", "kurta",
     ["festive", "everyday"],
     ["Dense allover small-floral chikankari in pale pink thread on an ivory mul base.",
      "Jaali (net) and murri (knot) stitches build a continuous floral field across the yoke, with denser borders at the hem.",
      "A versatile piece — light enough for daywear, finished enough for evening."]),

    ("13-blush-pink-mul-kurta",
     "Blush Pink Mul Kurta",
     "Kurta", "Blush Pink", "Mul Cotton", "kurta",
     ["festive", "bridal"],
     ["A blush-pink mul cotton kurta with dense allover white chikankari — large Mughal-style buta (paisley) panels along the borders, accented with mukaish (metallic) dotting.",
      "The combination of bakhiya, murri and jaali gives the embroidery dimension and a soft inner glow.",
      "A festive piece that reads beautifully against both warm and cool jewellery tones."]),

    ("14-ivory-mul-beige-chikankari-kurta",
     "Ivory Mul Kurta with Beige Chikankari",
     "Kurta", "Ivory with Beige", "Mul Cotton", "kurta",
     ["everyday", "festive"],
     ["Allover floral chikankari worked in warm beige and champagne thread on ivory mul — a tonal palette that reads softer and more sophisticated than the classic white-on-white.",
      "Mughal-style butas and a dense floral border, finished with light mukaish accents and jaali along the edges.",
      "Effortless to style — the warm tonal embroidery flatters most skin tones."]),

    ("15-navy-mul-chikankari-kurta",
     "Navy Mul Chikankari Kurta",
     "Kurta", "Navy Indigo", "Mul Cotton", "kurta",
     ["festive", "bridal"],
     ["The most dramatic piece in the collection — a navy mul kurta worked end to end in dense white chikankari, including the rare bird and peacock motifs traditional to Awadhi embroidery.",
      "Bakhiya shadow-work and murri knots are layered over the entire surface in white thread that pops against the deep navy ground.",
      "An evening piece — pair with kundan or polki and a sheer dupatta."]),

    ("16-ivory-mul-paisley-kurta",
     "Ivory Mul Paisley Kurta",
     "Kurta", "Ivory", "Mul Cotton", "kurta",
     ["everyday"],
     ["An understated ivory mul kurta with an open paisley medallion outline at the yoke — chikankari at its most restrained and graphic.",
      "The airy, spaced-out design lets the soft mul fabric speak. Best worn for daytime occasions where the embroidery is the only ornament."]),

    ("17-ivory-mul-sequinned-chikankari-kurta",
     "Ivory Mul Sequinned Chikankari Kurta",
     "Kurta", "Ivory", "Mul Cotton", "kurta",
     ["festive", "bridal"],
     ["Dense allover floral chikankari on the yoke and front placket — phanda, murri and jaali stitches in white, accented with sequins and mukaish.",
      "Intricate paisley medallions frame a V-neckline. Substantially heavier embroidery than our lighter pieces — a true festive kurta.",
      "Best paired with churidar, a sheer dupatta, and statement earrings."]),

    ("18-white-tonal-chikankari-kurta",
     "White Tonal Chikankari Kurta",
     "Kurta", "White", "Cotton", "kurta",
     ["everyday", "workwear"],
     ["Subtle white-on-white tonal chikankari across a textured white cotton base — the most quietly elegant piece in the collection.",
      "The all-over light pattern is built from jaali and bakhiya stitches in matching white thread, so the embroidery reveals itself only in shifting light.",
      "Endlessly versatile. Wears beautifully with both gold and silver jewellery."]),

    ("19-ivory-peach-butti-chikankari-saree",
     "Ivory Peach-Butti Chikankari Saree",
     "Saree", "Ivory with Peach", "Mul Chanderi", "saree",
     ["festive", "bridal"],
     ["A six-yard saree in lightweight mul chanderi, scattered with small peach butti (paisley) motifs in repeating rhythm.",
      "Vertical bands of dense white chikankari — jaali and phanda — run down the pallu in classic Lucknowi pallu treatment.",
      "Light enough to drape effortlessly. Wear with a contrast blouse and minimal jewellery."]),
]

PRICE = "8000.00"
CURRENCY_HINT = "INR"

# CSV header — Shopify product import format
HEADERS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags",
    "Published", "Option1 Name", "Option1 Value", "Option2 Name", "Option2 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker", "Variant Inventory Qty",
    "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
    "Variant Compare At Price", "Variant Requires Shipping", "Variant Taxable",
    "Variant Barcode", "Image Src", "Image Position", "Image Alt Text", "Gift Card",
    "SEO Title", "SEO Description", "Status",
]

SIZES = ["XS", "S", "M", "L", "XL", "XXL"]

rows = []
for slug, title, ptype, color, fabric, primary_tag, occasion_tags, paragraphs in PRODUCTS:
    folder = ROOT / slug
    if not folder.exists():
        print(f"WARN: missing folder {folder}")
        continue

    images = sorted(folder.glob("*.jpg"))

    body_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)
    body_html += "\n<p><strong>Fabric:</strong> " + fabric + "</p>"
    body_html += "\n<p><strong>Colour:</strong> " + color + "</p>"
    body_html += "\n<p><strong>Care:</strong> Dry clean only. Store flat, away from direct sunlight.</p>"
    body_html += "\n<p><strong>Origin:</strong> Hand-embroidered in Lucknow, India.</p>"

    fabric_tag = fabric.lower().replace(" ", "-")
    color_tag = color.lower().replace(" ", "-").replace("&", "and")
    tags = [primary_tag, fabric_tag, color_tag] + occasion_tags
    tag_str = ", ".join(sorted(set(tags)))

    seo_desc = paragraphs[0]
    if len(seo_desc) > 320:
        seo_desc = seo_desc[:317] + "..."

    # Write PRODUCT.md
    md = [
        f"# {title}",
        "",
        f"**Type:** {ptype}",
        f"**Colour:** {color}",
        f"**Fabric:** {fabric}",
        f"**Tags:** {tag_str}",
        f"**Sizes:** {', '.join(SIZES)}",
        f"**Price:** ₹{PRICE.split('.')[0]}",
        "",
        "## Description",
        "",
    ] + paragraphs + [
        "",
        "## Care",
        "Dry clean only. Store flat, away from direct sunlight.",
        "",
        "## Images",
        "",
    ] + [f"- `{img.name}`" for img in images]

    (folder / "PRODUCT.md").write_text("\n".join(md))

    # Build CSV rows. Shopify import: first row per variant, additional rows for extra images
    # We'll create one variant per size (6 sizes), all priced at ₹8000.
    image_idx = 0
    for size_idx, size in enumerate(SIZES):
        is_first_variant = size_idx == 0
        row = {h: "" for h in HEADERS}
        row["Handle"] = slug
        row["Option1 Name"] = "Size"
        row["Option1 Value"] = size
        row["Variant SKU"] = f"{slug}-{size}"
        row["Variant Inventory Tracker"] = "shopify"
        row["Variant Inventory Qty"] = "5"
        row["Variant Inventory Policy"] = "deny"
        row["Variant Fulfillment Service"] = "manual"
        row["Variant Price"] = PRICE
        row["Variant Requires Shipping"] = "true"
        row["Variant Taxable"] = "true"
        row["Variant Grams"] = "400"

        if is_first_variant:
            row["Title"] = title
            row["Body (HTML)"] = body_html
            row["Vendor"] = "Chikankari Lane"
            row["Product Category"] = "Apparel & Accessories > Clothing"
            row["Type"] = ptype
            row["Tags"] = tag_str
            row["Published"] = "true"
            row["Status"] = "active"
            row["Gift Card"] = "false"
            row["SEO Title"] = f"{title} | Hand-Embroidered Lucknowi Chikankari | Chikankari Lane"
            row["SEO Description"] = seo_desc
            # Attach first image to first variant row
            if images:
                row["Image Src"] = f"FILE://{images[0].name}"
                row["Image Position"] = "1"
                row["Image Alt Text"] = f"{title} — {images[0].stem.split('-', 1)[1].replace('-', ' ')}"
                image_idx = 1
        rows.append(row)

    # Additional image-only rows (no variant data)
    for i, img in enumerate(images[1:], start=2):
        row = {h: "" for h in HEADERS}
        row["Handle"] = slug
        row["Image Src"] = f"FILE://{img.name}"
        row["Image Position"] = str(i)
        role = img.stem.split("-", 1)[1].replace("-", " ") if "-" in img.stem else img.stem
        row["Image Alt Text"] = f"{title} — {role}"
        rows.append(row)

# Write CSV
with CSV_OUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(PRODUCTS)} PRODUCT.md files")
print(f"Wrote CSV: {CSV_OUT} ({len(rows)} rows)")
