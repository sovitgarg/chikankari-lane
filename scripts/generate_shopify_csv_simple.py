#!/usr/bin/env python3
"""Generate Shopify product import CSV — all products are unstitched suits.
Single variant per product, no images (uploaded manually)."""
import csv
from pathlib import Path

OUT = Path("/Users/sovitgarg/Downloads/Chikankari Lane/chikankari-lane-products.csv")

PTYPE = "Unstitched Suit"

# (handle, title, color, fabric, extra_tags, paragraphs)
PRODUCTS = [
    ("01-crimson-paisley-suit", "Crimson Paisley Suit", "Crimson Red", "Mul Cotton",
     ["bridal", "crimson-red", "festive"],
     ["An unstitched suit hand-embroidered in Lucknow — white chikankari paisley and floral motifs on a deep crimson mul cotton base.",
      "The yoke and borders carry generous keri (paisley) and bel (vine) work in dense bakhiya shadow stitch — the most striking signature of Lucknowi chikankari, where the embroidery is worked from the reverse and shows through softly on the front.",
      "A festive piece designed to anchor wedding-season dressing. Stitch into a kurta and pair with churidar and a contrasting dupatta."]),

    ("02-powder-blue-floral-suit", "Powder Blue Floral Suit", "Powder Blue", "Mul Cotton",
     ["everyday", "festive", "powder-blue"],
     ["A tonal study in powder blue and white. Dense allover chikankari floral work in fine bakhiya and jaali — the embroidery so closely set it reads almost like lace.",
      "Mul cotton keeps it breathable through long summer afternoons. The whole piece is the work of weeks of hand-stitching by a single artisan family in Lucknow.",
      "Stitches up beautifully into an everyday kurta or a festive set with deeper jewel-tone bottoms."]),

    ("03-sky-blue-chikankari-suit", "Sky Blue Chikankari Suit", "Sky Blue", "Mul Cotton",
     ["everyday", "festive", "sky-blue"],
     ["A featherweight sky-blue mul suit with open jaali (net) and linear floral chikankari — sparser, sketch-like work that lets the fabric breathe.",
      "The scalloped embroidered edge is a defining touch — chikankari at its most restrained.",
      "An easy choice for daytime stitching. Pair with white or contrast bottoms once tailored."]),

    ("04-sky-blue-striped-sequin-suit", "Sky Blue Striped Sequin Suit", "Sky Blue", "Cotton Chanderi",
     ["festive", "sky-blue"],
     ["Vertical pinstripe stitching runs the length of this sky-blue suit, broken by a delicate floral medallion at the centre of the yoke.",
      "Mukaish (metallic dotting) and fine murri stitches catch the light — a quietly glamorous touch usually reserved for festive chikankari.",
      "Best stitched into a kurta and styled with a contrast dupatta and kundan jewellery."]),

    ("05-silver-grey-floral-suit", "Silver Grey Floral Suit", "Silver Grey", "Georgette",
     ["bridal", "festive", "silver-grey"],
     ["A long, sheer silver-grey georgette suit with scattered floral cluster motifs — small bouquets in jaali and phanda, distributed in airy, hand-placed groupings.",
      "Light, almost weightless. Designed to stitch into festive layers without weight or fuss.",
      "The grey base is rare in chikankari and pairs particularly well with both pastels and jewel tones."]),

    ("06-pearl-cluster-chikankari-suit", "Pearl Cluster Chikankari Suit", "Pale Silver Blue", "Cotton Chanderi",
     ["bridal", "festive", "pale-silver-blue"],
     ["Vertical panels of raised murri-cluster floral work — tiny rice-shaped knots arranged like pearls — give this pale silver-blue suit its name.",
      "The texture is unusually three-dimensional for chikankari, the result of layered phanda and murri stitches placed densely in vertical bands.",
      "An understated festive piece. Stitch into a kurta and pair with silver jewellery."]),

    ("07-oatmeal-medallion-suit", "Oatmeal Medallion Suit", "Oatmeal", "Mul Cotton",
     ["everyday", "festive", "oatmeal"],
     ["A warm oatmeal mul suit with vertical panels of white chikankari — large circular sunflower medallions framed by dense bel (vine) borders.",
      "Fine murri and phanda stitches catch the light and add depth across the body.",
      "Equally at home for daytime occasions and quiet evening events once tailored."]),

    ("08-beige-striped-border-suit", "Beige Striped Border Suit", "Beige", "Striped Cotton",
     ["beige", "everyday"],
     ["A subtly striped beige cotton suit finished with a single horizontal band of white chikankari medallions and bel work along one border.",
      "Restrained, everyday-wearable — the kind of piece that quietly elevates a simple kurta into something thought-through."]),

    ("09-oatmeal-collared-chikankari-suit", "Oatmeal Collared Chikankari Suit", "Oatmeal", "Textured Cotton",
     ["everyday", "oatmeal", "workwear"],
     ["A shirt-style collared suit in oatmeal textured cotton — a less common silhouette in chikankari, designed to bridge ethnic and contemporary wardrobes.",
      "Vertical panels alternate between jaali (net) stripes and floral medallion bands. The jaali work is created by separating the warp and weft threads of the fabric and binding the spaces with tiny buttonhole stitches — no thread is pulled through the cloth.",
      "Stitch into a collared kurta — pairs equally well with straight pants for work or churidar and jhumkas for evening."]),

    ("10-cornflower-blue-sunflower-suit", "Cornflower Blue Sunflower Suit", "Cornflower Blue", "Checkered Mul Cotton",
     ["cornflower-blue", "everyday", "festive"],
     ["The deepest blue in the collection — a cornflower mul cotton suit with a fine self-checked weave running through the body.",
      "White chikankari concentrates at the yoke in a large central sunflower motif framed by bel borders. Murri and shadow-work stitches sit close together, building texture without weight.",
      "Pairs beautifully with white or off-white bottoms once stitched."]),

    ("11-ivory-pink-chikankari-suit", "Ivory & Pink Chikankari Suit", "Ivory & Pink", "Mul Cotton",
     ["everyday", "festive", "ivory-and-pink"],
     ["An ivory mul suit worked in a soft pink chikankari thread — a geometric diamond-lattice pattern with a tasselled, fringed edge.",
      "Pink-on-ivory is a deeply traditional Lucknowi colourway. The diamond lattice is built from short repeated stitches, hand-counted across the weave."]),

    ("12-ivory-mul-pink-chikankari-suit", "Ivory Mul Suit with Pink Chikankari", "Ivory with Pink", "Mul Cotton",
     ["everyday", "festive", "ivory-with-pink"],
     ["Dense allover small-floral chikankari in pale pink thread on an ivory mul base.",
      "Jaali (net) and murri (knot) stitches build a continuous floral field across the yoke, with denser borders at the hem.",
      "A versatile piece — light enough for daywear, finished enough for evening."]),

    ("13-blush-pink-mul-suit", "Blush Pink Mul Suit", "Blush Pink", "Mul Cotton",
     ["blush-pink", "bridal", "festive"],
     ["A blush-pink mul cotton suit with dense allover white chikankari — large Mughal-style buta (paisley) panels along the borders, accented with mukaish (metallic) dotting.",
      "The combination of bakhiya, murri and jaali gives the embroidery dimension and a soft inner glow.",
      "A festive piece that reads beautifully against both warm and cool jewellery tones."]),

    ("14-ivory-mul-beige-chikankari-suit", "Ivory Mul Suit with Beige Chikankari", "Ivory with Beige", "Mul Cotton",
     ["everyday", "festive", "ivory-with-beige"],
     ["Allover floral chikankari worked in warm beige and champagne thread on ivory mul — a tonal palette that reads softer and more sophisticated than the classic white-on-white.",
      "Mughal-style butas and a dense floral border, finished with light mukaish accents and jaali along the edges.",
      "Effortless to style — the warm tonal embroidery flatters most skin tones."]),

    ("15-navy-mul-chikankari-suit", "Navy Mul Chikankari Suit", "Navy Indigo", "Mul Cotton",
     ["bridal", "festive", "navy-indigo"],
     ["The most dramatic piece in the collection — a navy mul suit worked end to end in dense white chikankari, including the rare bird and peacock motifs traditional to Awadhi embroidery.",
      "Bakhiya shadow-work and murri knots are layered over the entire surface in white thread that pops against the deep navy ground.",
      "An evening piece — pair with kundan or polki and a sheer dupatta once stitched."]),

    ("16-ivory-mul-paisley-suit", "Ivory Mul Paisley Suit", "Ivory", "Mul Cotton",
     ["everyday", "ivory"],
     ["An understated ivory mul suit with an open paisley medallion outline at the yoke — chikankari at its most restrained and graphic.",
      "The airy, spaced-out design lets the soft mul fabric speak. Best worn for daytime occasions where the embroidery is the only ornament."]),

    ("17-ivory-mul-sequinned-chikankari-suit", "Ivory Mul Sequinned Chikankari Suit", "Ivory", "Mul Cotton",
     ["bridal", "festive", "ivory"],
     ["Dense allover floral chikankari on the yoke and front placket — phanda, murri and jaali stitches in white, accented with sequins and mukaish.",
      "Intricate paisley medallions frame a V-neckline. Substantially heavier embroidery than our lighter pieces — a true festive suit.",
      "Best paired with churidar, a sheer dupatta, and statement earrings once tailored."]),

    ("18-white-tonal-chikankari-suit", "White Tonal Chikankari Suit", "White", "Cotton",
     ["everyday", "white", "workwear"],
     ["Subtle white-on-white tonal chikankari across a textured white cotton base — the most quietly elegant piece in the collection.",
      "The all-over light pattern is built from jaali and bakhiya stitches in matching white thread, so the embroidery reveals itself only in shifting light.",
      "Endlessly versatile. Wears beautifully with both gold and silver jewellery."]),

    ("19-ivory-peach-butti-chikankari-suit", "Ivory Peach-Butti Chikankari Suit", "Ivory with Peach", "Mul Chanderi",
     ["bridal", "festive", "ivory-with-peach"],
     ["A lightweight mul chanderi suit, scattered with small peach butti (paisley) motifs in repeating rhythm.",
      "Vertical bands of dense white chikankari — jaali and phanda — run down the length in classic Lucknowi pallu treatment.",
      "Light enough to drape effortlessly once stitched. Wear with a contrast blouse and minimal jewellery."]),
]

PRICE = "8000.00"

# Universal tag added to every product
BASE_TAGS = ["unstitched-suit", "chikankari", "lucknow"]

HEADERS = [
    "Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags",
    "Published",
    "Option1 Name", "Option1 Value",
    "Variant SKU", "Variant Grams", "Variant Inventory Tracker", "Variant Inventory Qty",
    "Variant Inventory Policy", "Variant Fulfillment Service", "Variant Price",
    "Variant Compare At Price", "Variant Requires Shipping", "Variant Taxable",
    "Variant Barcode",
    "Image Src", "Image Position", "Image Alt Text",
    "Gift Card",
    "SEO Title", "SEO Description",
    "Status",
]

rows = []
for handle, title, color, fabric, extra_tags, paragraphs in PRODUCTS:
    # Minimal: lead paragraph + fabric/colour/origin only
    body_html = f"<p>{paragraphs[0]}</p>"
    body_html += f"\n<p><strong>Fabric:</strong> {fabric}</p>"
    body_html += f"\n<p><strong>Colour:</strong> {color}</p>"
    body_html += "\n<p><strong>Origin:</strong> Hand-embroidered in Lucknow.</p>"

    seo_desc = paragraphs[0]
    if len(seo_desc) > 320:
        seo_desc = seo_desc[:317] + "..."

    fabric_tag = fabric.lower().replace(" ", "-")
    tags = sorted(set(BASE_TAGS + extra_tags + [fabric_tag]))

    row = {h: "" for h in HEADERS}
    row["Handle"] = handle
    row["Title"] = title
    row["Body (HTML)"] = body_html
    row["Vendor"] = "Chikankari Lane"
    row["Product Category"] = "Apparel & Accessories > Clothing"
    row["Type"] = PTYPE
    row["Tags"] = ", ".join(tags)
    row["Published"] = "true"
    row["Option1 Name"] = "Title"
    row["Option1 Value"] = "Default Title"
    row["Variant SKU"] = handle
    row["Variant Grams"] = "400"
    row["Variant Inventory Tracker"] = "shopify"
    row["Variant Inventory Qty"] = "5"
    row["Variant Inventory Policy"] = "deny"
    row["Variant Fulfillment Service"] = "manual"
    row["Variant Price"] = PRICE
    row["Variant Requires Shipping"] = "true"
    row["Variant Taxable"] = "true"
    row["Gift Card"] = "false"
    row["SEO Title"] = f"{title} | Hand-Embroidered Lucknowi Chikankari | Chikankari Lane"
    row["SEO Description"] = seo_desc
    row["Status"] = "active"
    rows.append(row)

with OUT.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=HEADERS)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} rows to {OUT}")
