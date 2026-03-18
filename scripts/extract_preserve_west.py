#!/usr/bin/env python3
"""
Extract Preserve West Phase 1 lot polygons from 8x11 marketing SVG.
Associates lot numbers via CAD SVG label centroids + affine transform.
Outputs public/preserve-west-map.svg ready for the interactive web map.

Usage:
  python scripts/extract_preserve_west.py            # normal run
  python scripts/extract_preserve_west.py --debug    # print centroid table
"""
import xml.etree.ElementTree as ET
import re, math, sys
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
SVG_8X11   = ROOT / "preserve west" / "Preserve West Map 8x11.svg"
SVG_CAD    = ROOT / "preserve west" / "WEMC 11-20-24.svg"
OUTPUT     = ROOT / "public" / "preserve-west-map.svg"

DEBUG = "--debug" in sys.argv

# ── fill colours that indicate a lot polygon ─────────────────────────────────
LOT_FILLS  = {"#3fc30b", "#007a06"}   # st4/st17 (bright green), st8 (med green)
OPEN_FILLS = {"#338504"}              # st3 (dark green open space)

# ── CAD -> sequential-1-48 lot-number mapping ─────────────────────────────────
# Derived from visual comparison of street-names PDF (CAD plat numbers)
# vs marketing-map PDF (sequential 1-48 display numbers).
# Layout (street-names PDF, 9-17-2025):
#   Beckett Boulevard right column (top->bottom): 180,179,178,177,176,175,174,173,172,171,170,169,168
#   Joyce Row cul-de-sac:  1,2,3,4,5,6,7,8,9,10,11,12,13,14
#   Wilde Ridge cul-de-sac: 15,16,17,18,19,20,21,22,23,24,25,26,27
#   Swift Landing (bottom):  160,161,162,163,164,165,166,167
#
# Marketing map sequential numbering (read from 8x11 PDF image):
#   Beckett Blvd (top->bottom): seq 20,19,18,17,16,15,14,13,12,11,10,9,8,7
#   Joyce Row:                  seq 6,5,4,3,2,1 (bottom half), 21,22,23,24,25,26 (upper)
#   Wilde Ridge:                seq 27,28,29,30,31,32,33,34,35
#   Swift Landing (bottom):     seq 36,37,38,39,40,41,42,43,44,45,46,47,48
#
# NOTE: this mapping is approximate; verified by visual review after script run.
CAD_TO_SEQ = {
    # Beckett Boulevard (CAD 168-180 -> seq 7-20)
    168: 7,  169: 8,  170: 9,  171: 10, 172: 11,
    173: 12, 174: 13, 175: 14, 176: 15, 177: 16,
    178: 17, 179: 18, 180: 19,
    # Joyce Row lower (CAD 1-6 -> seq 1-6)
    1: 1,  2: 2,  3: 3,  4: 4,  5: 5,  6: 6,
    # Joyce Row upper (CAD 7-14 -> seq 20-27 roughly; needs visual check)
    7: 20,  8: 21,  9: 22,  10: 23, 11: 24,
    12: 25, 13: 26, 14: 27,
    # Wilde Ridge (CAD 15-27 -> seq 28-40 roughly)
    15: 28, 16: 29, 17: 30, 18: 31, 19: 32,
    20: 33, 21: 34, 22: 35, 23: 36, 24: 37,
    25: 38, 26: 39, 27: 40,
    # Swift Landing (CAD 160-167 -> seq 41-48)
    160: 41, 161: 42, 162: 43, 163: 44,
    164: 45, 165: 46, 166: 47, 167: 48,
}

# ── helpers ───────────────────────────────────────────────────────────────────
def parse_points(s):
    nums = list(map(float, re.findall(r'-?[0-9]+\.?[0-9]*', s)))
    return [(nums[i], nums[i+1]) for i in range(0, len(nums)-1, 2)]

def centroid(pts):
    n = len(pts)
    return sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n

def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def polygon_area(pts):
    n = len(pts)
    a = 0
    for i in range(n):
        j = (i+1) % n
        a += pts[i][0]*pts[j][1] - pts[j][0]*pts[i][1]
    return abs(a) / 2

def point_in_polygon(px, py, poly):
    inside = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj-xi)*(py-yi)/(yj-yi) + xi):
            inside = not inside
        j = i
    return inside

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def format_pts(pts):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)

# ── step 1: parse 8x11 SVG ────────────────────────────────────────────────────
print("Parsing 8x11 SVG …")
tree8 = ET.parse(SVG_8X11)
root8 = tree8.getroot()
ns = "http://www.w3.org/2000/svg"

# Build fill map from <style> block
style_text = ""
for el in root8.iter("{%s}style" % ns):
    style_text += el.text or ""

fill_map = {}  # classname -> fill colour
# parse blocks like: .st4, .st17 { fill: #3fc30b; }
for block in re.finditer(r'([^{}]+)\{([^}]+)\}', style_text, re.DOTALL):
    selectors, body = block.group(1), block.group(2)
    fill_m = re.search(r'fill\s*:\s*(#[0-9a-fA-F]{3,6}|[a-z]+)', body)
    if fill_m:
        fill = fill_m.group(1).lower()
        for sel in selectors.split(','):
            sel = sel.strip()
            if sel.startswith('.'):
                fill_map[sel[1:]] = fill

def get_fill(cls_str):
    for c in (cls_str or "").split():
        if c in fill_map:
            return fill_map[c]
    return None

lot_polys   = []   # [(pts, fill)]
open_polys  = []   # [pts]

for el in root8.iter("{%s}polygon" % ns):
    cls = el.get("class", "")
    fill = get_fill(cls)
    pts_str = el.get("points", "")
    if not pts_str:
        continue
    pts = parse_points(pts_str)
    if len(pts) < 3:
        continue
    if fill in LOT_FILLS:
        a = polygon_area(pts)
        if 50 < a < 10000:   # ignore tiny shapes and the large background polygon
            lot_polys.append((pts, fill))
    elif fill in OPEN_FILLS:
        open_polys.append(pts)

print(f"  Found {len(lot_polys)} lot polygons, {len(open_polys)} open-space polygon(s)")

# ── step 2: parse CAD SVG — lot label centroids ───────────────────────────────
print("Parsing CAD SVG …")
treeC = ET.parse(SVG_CAD)
rootC = treeC.getroot()

cad_labels = {}   # lot_number -> (cx, cy) in CAD 4096 space

for g in rootC.iter("{%s}g" % ns):
    gid = g.get("id", "")
    if "LOTNUM" not in gid or "PHASE_1" not in gid:
        continue
    for sub in g.iter("{%s}g" % ns):
        for text_el in sub.iter("{%s}text" % ns):
            transform = text_el.get("transform", "")
            content = "".join(text_el.itertext()).strip()
            tm = re.search(r'translate\(\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s*\)', transform)
            if tm and re.match(r'^[0-9]+$', content):
                lot_num = int(content)
                cx, cy = float(tm.group(1)), float(tm.group(2))
                cad_labels[lot_num] = (cx, cy)

print(f"  Found {len(cad_labels)} CAD lot labels: {sorted(cad_labels.keys())}")

# ── step 3: affine transform CAD -> 8x11 ──────────────────────────────────────
# Use bounding-box alignment of the Phase-1 lot-label point clouds.
if cad_labels:
    cad_pts  = list(cad_labels.values())
    lot_cxs  = [centroid(p)[0] for p,_ in lot_polys]
    lot_cys  = [centroid(p)[1] for p,_ in lot_polys]

    cad_x0, cad_x1 = min(p[0] for p in cad_pts), max(p[0] for p in cad_pts)
    cad_y0, cad_y1 = min(p[1] for p in cad_pts), max(p[1] for p in cad_pts)
    web_x0, web_x1 = min(lot_cxs), max(lot_cxs)
    web_y0, web_y1 = min(lot_cys), max(lot_cys)

    sx = (web_x1 - web_x0) / (cad_x1 - cad_x0) if cad_x1 != cad_x0 else 1
    sy = (web_y1 - web_y0) / (cad_y1 - cad_y0) if cad_y1 != cad_y0 else 1
    tx = web_x0 - cad_x0 * sx
    ty = web_y0 - cad_y0 * sy

    def cad_to_8x11(cx, cy):
        return cx * sx + tx, cy * sy + ty

    if DEBUG:
        print(f"\n  CAD->8x11 transform: sx={sx:.4f} sy={sy:.4f} tx={tx:.2f} ty={ty:.2f}")

    poly_centroids = [centroid(pts) for pts, _ in lot_polys]

    # Bipartite greedy matching: build all (distance, cad_lot, poly_idx) pairs,
    # sort by distance, assign greedily (closest unmatched pair wins).
    pairs = []
    for lot_num, (cx, cy) in cad_labels.items():
        mapped = cad_to_8x11(cx, cy)
        for i, pc in enumerate(poly_centroids):
            pairs.append((dist(mapped, pc), lot_num, i))
    pairs.sort()

    lot_num_assignments = {}   # polygon_index -> cad_lot_number
    assigned_lots  = set()
    assigned_polys = set()
    for d, lot_num, pi in pairs:
        if lot_num not in assigned_lots and pi not in assigned_polys:
            lot_num_assignments[pi] = lot_num
            assigned_lots.add(lot_num)
            assigned_polys.add(pi)

    if DEBUG:
        print("\n  Polygon -> CAD lot number assignments:")
        for pi, ln in sorted(lot_num_assignments.items(), key=lambda x: x[1]):
            cx, cy = poly_centroids[pi]
            seq = CAD_TO_SEQ.get(ln, f"?{ln}")
            print(f"    poly[{pi:2d}] centroid=({cx:.1f},{cy:.1f})  CAD={ln:3d}  seq={seq}")
else:
    print("  WARNING: No CAD labels found — assigning lot numbers spatially")
    lot_num_assignments = {}

# ── step 4: compute output viewBox ───────────────────────────────────────────
OUTPUT_SCALE = 4   # multiply all coordinates by this factor

def scale_pts(pts):
    return [(x * OUTPUT_SCALE, y * OUTPUT_SCALE) for x, y in pts]

lot_polys   = [(scale_pts(pts), fill) for pts, fill in lot_polys]
open_polys  = [scale_pts(pts) for pts in open_polys]

all_pts = [p for pts, _ in lot_polys for p in pts] + \
          [p for pts    in open_polys for p in pts]
if not all_pts:
    print("ERROR: no geometry extracted"); sys.exit(1)

x0, y0, x1, y1 = bbox(all_pts)
pad = 40
vx, vy = x0 - pad, y0 - pad
vw, vh = (x1 - x0) + 2*pad, (y1 - y0) + 2*pad

print(f"\n  Output viewBox: {vx:.1f} {vy:.1f} {vw:.1f} {vh:.1f}")

# ── step 5: build output SVG ─────────────────────────────────────────────────
print("Building output SVG …")

lines = []
lines.append('<?xml version="1.0" encoding="UTF-8"?>')
lines.append(f'<svg id="map-svg" xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}" preserveAspectRatio="xMidYMid meet">')
lines.append('  <!-- Preserve West Phase One — generated by scripts/extract_preserve_west.py -->')
lines.append('')

# Open space
if open_polys:
    lines.append('  <!-- ═══ open space ═══ -->')
    # id="open-space" must be on the polygon itself (tree-layer JS uses getElementById + getAttribute('points'))
    for i, pts in enumerate(open_polys):
        oid = "open-space" if i == 0 else f"open-space-{i}"
        lines.append(f'  <polygon id="{oid}" class="open-space-poly" points="{format_pts(pts)}"/>')
    lines.append('')

# Lot polygons
lines.append('  <!-- ═══ lots ═══ -->')
lines.append('  <g id="lots">')

# Build final lot list with sequential numbers
lots_out = []
for i, (pts, fill) in enumerate(lot_polys):
    cad_num = lot_num_assignments.get(i)
    seq_num = CAD_TO_SEQ.get(cad_num) if cad_num is not None else None
    if seq_num is None:
        # unmatched — assign to next available number
        used = {v for v in CAD_TO_SEQ.values()}
        assigned = {CAD_TO_SEQ.get(lot_num_assignments.get(j))
                    for j in range(len(lot_polys)) if j != i
                    if lot_num_assignments.get(j) in CAD_TO_SEQ}
        for n in range(1, 49):
            if n not in assigned:
                seq_num = n
                break
        print(f"  WARNING: polygon[{i}] (CAD {cad_num}) not in mapping table -> assigned seq {seq_num}")
    lots_out.append((seq_num, pts))

# Sort by sequential number and emit
# id="lot-N" is required by getElementById('lot-'+id) in JS
# class="lot" is required by map-styles.css (.lot.available / .lot.sold / .lot.reserved)
for seq_num, pts in sorted(lots_out, key=lambda x: (x[0] or 999)):
    lines.append(f'    <polygon id="lot-{seq_num}" class="lot" data-lot="{seq_num}" '
                 f'data-lot-id="lot-{seq_num}" points="{format_pts(pts)}"/>')

lines.append('  </g>')
lines.append('')

# Empty labels group — JS populateLabels() will create <g class="lot-label-group"> children here
lines.append('  <!-- lot labels: JS populateLabels() appends .lot-label-group children here -->')
lines.append('  <g class="labels"></g>')
lines.append('')

lines.append('</svg>')

# ── write output ──────────────────────────────────────────────────────────────
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nWrote {len(lots_out)} lots -> {OUTPUT}")
print("Next: serve public/ and visually verify lot numbering, then update CAD_TO_SEQ if needed.")
