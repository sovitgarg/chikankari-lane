#!/bin/bash
# Organize Chikankari Lane product photos into per-product folders
# Source: /Users/sovitgarg/Downloads/Chikankari Lane/Content photos/{Smash,Smash (1)}
# Output: /Users/sovitgarg/Learning/chikankari-lane/catalog/products/<slug>/

set -euo pipefail

SRC_A="/Users/sovitgarg/Downloads/Chikankari Lane/Content photos/Smash"
SRC_B="/Users/sovitgarg/Downloads/Chikankari Lane/Content photos/Smash (1)"
OUT="/Users/sovitgarg/Learning/chikankari-lane/catalog/products"
mkdir -p "$OUT"

# Find source file (could be in either folder)
src_path() {
  local f="$1.JPG"
  if [[ -f "$SRC_A/$f" ]]; then
    echo "$SRC_A/$f"
  elif [[ -f "$SRC_B/$f" ]]; then
    echo "$SRC_B/$f"
  else
    echo "MISSING: $f" >&2
    return 1
  fi
}

# Resize + copy: $1=source-DSC-id $2=output-folder $3=role-name (e.g., "01-front")
copy_resized() {
  local dsc="$1"
  local outdir="$2"
  local role="$3"
  local src
  src="$(src_path "$dsc")" || return 1
  mkdir -p "$outdir"
  sips -Z 2000 -s formatOptions 82 "$src" --out "$outdir/${role}.jpg" >/dev/null 2>&1
  echo "  $dsc -> $role"
}

# Product format: slug | dsc1:role1 dsc2:role2 ...
products=(
"01-crimson-paisley-kurta|DSC05086:01-flatlay DSC05087:02-flatlay-alt DSC05088:03-yoke-detail DSC05091:04-yoke-styled DSC05092:05-embroidery-macro"
"02-powder-blue-floral-kurta|DSC05093:01-flatlay DSC05094:02-yoke-detail DSC05096:03-folded-tray DSC05097:04-pleated-texture DSC05098:05-embroidery-macro DSC05099:06-folded-alt DSC05100:07-portrait-flatlay DSC05101:08-portrait-flatlay-alt"
"03-sky-blue-chikankari-dupatta|DSC05102:01-flatlay DSC05103:02-flatlay-alt DSC05109:03-flatlay-alt-2"
"04-sky-blue-striped-sequin-kurta|DSC05104:01-flatlay DSC05105:02-portrait DSC05106:03-yoke-medallion DSC05107:04-yoke-tilted DSC05108:05-yoke-alt DSC05110:06-styled-jewelry DSC05111:07-yoke-angle DSC05112:08-embroidery-macro"
"05-silver-grey-floral-dupatta|DSC05113:01-flatlay DSC05114:02-flatlay-alt"
"06-pearl-cluster-chikankari-kurta|DSC05115:01-yoke-tray DSC05116:02-yoke-alt"
"07-oatmeal-medallion-kurta|DSC05136:01-yoke-medallion DSC05140:02-macro-wood DSC05141:03-portrait DSC05142:04-styled-gold"
"08-beige-striped-border-dupatta|DSC05144:01-flatlay"
"09-oatmeal-collared-chikankari-kurta|DSC05148:01-flatlay DSC05149:02-yoke-collar DSC05150:03-collar-alt DSC05151:04-portrait DSC05152:05-portrait-alt DSC05153:06-portrait-overhead"
"10-cornflower-blue-sunflower-kurta|DSC05154:01-flatlay DSC05156:02-flatlay-alt DSC05157:03-yoke-body DSC05158:04-yoke-angle DSC05159:05-portrait DSC05160:06-portrait-alt DSC05161:07-yoke-detail DSC05162:08-embroidery-macro DSC05163:09-yoke-closeup"
"11-ivory-pink-chikankari-dupatta|DSC05164:01-flatlay-fringe DSC05165:02-flatlay-angle DSC05166:03-flatlay-fringe-alt DSC05167:04-flatlay-alt"
"12-ivory-mul-pink-chikankari-kurta|DSC05168:01-folded DSC05169:02-folded-alt DSC05170:03-neckline DSC05171:04-fold-detail DSC05172:05-portrait DSC05173:06-flatlay DSC05174:07-flatlay-alt DSC05175:08-flatlay-alt-2 DSC05176:09-yoke-earrings"
"13-blush-pink-mul-kurta|DSC05177:01-flatlay DSC05178:02-flatlay-alt DSC05179:03-portrait DSC05180:04-folded DSC05181:05-flatlay-alt-2 DSC05182:06-portrait-alt DSC05183:07-flatlay-kalash DSC05184:08-yoke DSC05185:09-folded-alt DSC05186:10-yoke-alt DSC05187:11-border-macro DSC05188:12-buta-sequins-macro"
"14-ivory-mul-beige-chikankari-kurta|DSC05189:01-flatlay DSC05190:02-flatlay-alt DSC05191:03-flatlay-alt-2 DSC05192:04-portrait DSC05193:05-yoke-border DSC05194:06-portrait-neckline DSC05195:07-portrait-alt DSC05196:08-border-detail DSC05197:09-yoke-macro DSC05198:10-yoke-folded DSC05199:11-portrait-alt-2"
"15-navy-mul-chikankari-kurta|DSC05251:01-yoke DSC05253:02-yoke-alt DSC05254:03-yoke-folded DSC05255:04-yoke-alt-2 DSC05256:05-portrait DSC05257:06-portrait-alt DSC05258:07-yoke-macro DSC05259:08-bird-motif-macro DSC05260:09-yoke-folded-alt DSC05261:10-bird-border-macro"
"16-ivory-mul-paisley-kurta|DSC05262:01-flatlay DSC05263:02-flatlay-alt DSC05264:03-flatlay-alt-2"
"17-ivory-mul-sequinned-chikankari-kurta|DSC05265:01-yoke DSC05266:02-yoke-earrings DSC05267:03-yoke-side-light DSC05268:04-yoke-styled DSC05269:05-yoke-similar DSC05270:06-yoke-three-quarter DSC05271:07-portrait DSC05272:08-yoke-tray DSC05273:09-yoke-neckline DSC05274:10-embroidery-macro DSC05275:11-yoke-neckline-detail DSC05276:12-yoke-angle DSC05277:13-stitches-macro"
"18-white-tonal-chikankari-kurta|DSC05278:01-jewelry-styled DSC05279:02-styled-tighter DSC05280:03-chain-draped DSC05281:04-necklace-centered DSC05282:05-side-view DSC05283:06-necklace-diagonal DSC05284:07-pendant-detail DSC05285:08-pendant-detail-alt DSC05286:09-pendant-detail-alt-2 DSC05287:10-pendant-detail-alt-3 DSC05288:11-necklace-draped DSC05289:12-jewelry-hero DSC05290:13-with-earrings DSC05291:14-necklace-styled DSC05292:15-earrings-tray DSC05293:16-tray-styling DSC05294:17-with-jhumkas"
"19-ivory-peach-butti-chikankari-saree|DSC05295:01-flatlay DSC05296:02-flatlay-alt DSC05297:03-folded-angled DSC05298:04-vertical-bands DSC05299:05-portrait DSC05300:06-bands-detail DSC05301:07-folded-angled-alt DSC05302:08-portrait-alt DSC05303:09-portrait-alt-2 DSC05304:10-bands-butti-detail DSC05305:11-portrait-alt-3 DSC05306:12-bands-macro DSC05307:13-folded-detail"
)

count=0
for entry in "${products[@]}"; do
  slug="${entry%%|*}"
  files="${entry#*|}"
  outdir="$OUT/$slug"
  echo "Processing: $slug"
  for pair in $files; do
    dsc="${pair%%:*}"
    role="${pair#*:}"
    copy_resized "$dsc" "$outdir" "$role"
    count=$((count + 1))
  done
done

echo ""
echo "Done. Total images processed: $count"
echo "Output: $OUT"
