#!/usr/bin/env python3
"""
Extract Preserve West Phase 1 interactive map from 8x11 marketing SVG + CAD.

Extracts:
  - Phase 1 lot polygons (48 lots, numbered 1-48)
  - Open space polygon (st3 dark green)
  - Water/stream polygons from 8x11 SVG (st10 cyan)
  - Ghost lot outlines from 8x11 SVG (st7/st27 lime)
  - Stream polylines from CAD (V-STREAM-TOB-SURVEY, V-STREAM-SURVEY)
  - Ghost lot boundary lines from CAD (C-PROP-5, C-PROP-8, all phases)
  - Road labels (internal + external, static SVG text)
  - Area labels (OPEN SPACE x2, HOA)

Usage:
  python scripts/extract_preserve_west.py            # normal run
  python scripts/extract_preserve_west.py --debug    # print centroid table
"""
import xml.etree.ElementTree as ET
import re, math, sys
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
SVG_8X11 = ROOT / "preserve west" / "Preserve West Map 8x11.svg"
SVG_CAD  = ROOT / "preserve west" / "WEMC 11-20-24.svg"
OUTPUT   = ROOT / "public" / "preserve-west-map.svg"

DEBUG = "--debug" in sys.argv

# ── output scale ──────────────────────────────────────────────────────────────
OUTPUT_SCALE = 4   # multiply all 8x11 coordinates by this factor

# ── fill colours ──────────────────────────────────────────────────────────────
LOT_FILLS   = {"#3fc30b", "#007a06"}   # Phase 1 lot fills (bright + med green)
OPEN_FILLS  = {"#338504"}              # Open space (dark green)
GHOST_FILLS = {"lime"}                 # Future-phase lot outlines (lime, opacity 0.5)
WATER_CLASS = "st10"                   # #00bfff cyan water polygons

# ── 8x11 SVG coordinate bounds (for clipping CAD ghost lines) ─────────────────
SVG_BOUNDS = (0, 0, 595, 842)   # (xmin, ymin, xmax, ymax)
GHOST_MARGIN = 80               # extra units beyond SVG bounds to allow

# ── CAD -> sequential lot-number mapping ──────────────────────────────────────
# CAD plat numbers (WEMC 11-20-24.svg C-PROP-LOTNUM-PHASE_1) -> marketing seq 1-48.
# Street layout (per Sept-2025 road-names doc):
#   Beckett Boulevard (right column, top->bottom): CAD 180..168  -> seq 20..7
#   Joyce Row lower cul-de-sac:                   CAD 1..6      -> seq 1..6
#   Joyce Row upper cul-de-sac:                   CAD 7..14     -> seq 21..28
#   Wilde Ridge cul-de-sac:                       CAD 15..27    -> seq 29..41
#   Swift Landing (bottom row):                   CAD 160..167  -> seq 42..49 (8 lots)
# NOTE: mapping is approximate; verify visually and update as needed.
CAD_TO_SEQ = {
    # Beckett Boulevard (CAD 168-180, top->bottom = seq 20->7)
    180: 20, 179: 19, 178: 18, 177: 17, 176: 16,
    175: 15, 174: 14, 173: 13, 172: 12, 171: 11,
    170: 10, 169:  9, 168:  7,
    # Joyce Row lower (CAD 1-6 -> seq 1-6)
    1: 1,  2: 2,  3: 3,  4: 4,  5: 5,  6: 6,
    # Joyce Row upper (CAD 7-14 -> seq 21-28)
    7: 21,  8: 22,  9: 23, 10: 24, 11: 25,
    12: 26, 13: 27, 14: 28,
    # Wilde Ridge (CAD 15-27 -> seq 29-41)
    15: 29, 16: 30, 17: 31, 18: 32, 19: 33,
    20: 34, 21: 35, 22: 36, 23: 37, 24: 38,
    25: 39, 26: 40, 27: 41,
    # Swift Landing (CAD 160-167 -> seq 42-48 + lot 8 on Beckett foot)
    160: 42, 161: 43, 162: 44, 163: 45,
    164: 46, 165: 47, 166: 48, 167: 8,
}

# ── road labels ───────────────────────────────────────────────────────────────
# CAD positions sourced from B-STREET_NAME-PHASE_1 (internal) with updated names,
# and approximate boundary positions (external roads).
# Format: (display_text, cad_x, cad_y, rotation_deg)
ROAD_LABELS = [
    # Internal Phase 1 roads (old CAD names -> updated 2025 names)
    ("BECKETT BOULEVARD", 3159.9, 3444.5,  -10.8),
    ("JOYCE ROW",         3025.6, 3342.0, -101.2),
    ("WILDE RIDGE",       2789.0, 3101.6,  -85.6),
    ("SWIFT LANDING",     2510.1, 3362.2,  -23.9),
    # External roads (approximate positions along Phase 1 boundary)
    ("BRUCE GARNER RD",   2600.0, 2395.0,    0.0),
    ("GRAHAM SHERRON RD", 3590.0, 3050.0,  -90.0),
    ("ALLENWOOD RD",      2450.0, 3710.0,    5.0),
]

# ── area labels (from V-OS-TXT-PHASE_1 / HOA CAD label) ──────────────────────
# Format: (display_text, cad_x, cad_y, rotation_deg)
AREA_LABELS = [
    ("OPEN SPACE", 3023.8, 2904.1, 63.5),
    ("OPEN SPACE", 2584.0, 3583.7, 63.5),
    ("HOA",        3568.4, 3360.8, 63.5),
]

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

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def fmt_pts(pts):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)

def fmt_poly_pts(pts):
    return " ".join(f"{x:.2f} {y:.2f}" for x, y in pts)

def in_svg_bounds(pts, margin=GHOST_MARGIN):
    xmin, ymin, xmax, ymax = SVG_BOUNDS
    return all(
        xmin - margin <= x <= xmax + margin and
        ymin - margin <= y <= ymax + margin
        for x, y in pts
    )

# ── step 1: parse 8x11 SVG ────────────────────────────────────────────────────
print("Parsing 8x11 SVG ...")
tree8 = ET.parse(SVG_8X11)
root8 = tree8.getroot()
ns = "http://www.w3.org/2000/svg"

# Build fill map from <style> block
style_text = ""
for el in root8.iter("{%s}style" % ns):
    style_text += el.text or ""

fill_map = {}
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

lot_polys   = []   # [(pts, fill)]  -- Phase 1 lots
open_polys  = []   # [pts]          -- open space
ghost_polys = []   # [pts]          -- lime future-phase outlines
water_polys = []   # [pts]          -- st10 water polygons

for el in root8.iter("{%s}polygon" % ns):
    cls  = el.get("class", "")
    fill = get_fill(cls)
    pts_str = el.get("points", "")
    if not pts_str:
        continue
    pts = parse_points(pts_str)
    if len(pts) < 3:
        continue

    if fill in LOT_FILLS:
        a = polygon_area(pts)
        if 50 < a < 10000:
            lot_polys.append((pts, fill))
    elif fill in OPEN_FILLS:
        open_polys.append(pts)
    elif fill in GHOST_FILLS:
        ghost_polys.append(pts)
    elif WATER_CLASS in cls.split():
        water_polys.append(pts)

print(f"  {len(lot_polys)} lot polygons, {len(open_polys)} open-space, "
      f"{len(ghost_polys)} ghost outlines, {len(water_polys)} water polygons")

# ── step 2: parse CAD SVG ─────────────────────────────────────────────────────
print("Parsing CAD SVG ...")
treeC = ET.parse(SVG_CAD)
rootC = treeC.getroot()

# Phase 1 lot label centroids
cad_labels = {}
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

print(f"  {len(cad_labels)} CAD lot labels: {sorted(cad_labels.keys())}")

# Stream polylines (V-STREAM-TOB-SURVEY, V-STREAM-SURVEY)
# Children are wrapped in <g id="LWPOLYLINE..."> sub-groups, so use .iter()
cad_streams = []   # [[(cad_x, cad_y)]]
for g in rootC.iter("{%s}g" % ns):
    if g.get("id", "") in ("V-STREAM-TOB-SURVEY", "V-STREAM-SURVEY"):
        for el in g.iter():
            tag = el.tag.split("}")[-1]
            if tag == "polyline":
                pts_str = el.get("points", "")
                if pts_str:
                    pts = parse_points(pts_str)
                    if len(pts) >= 2:
                        cad_streams.append(pts)
print(f"  {len(cad_streams)} CAD stream polylines")

# Ghost lot boundary lines from all phases (C-PROP-5, C-PROP-8)
# Same nested structure: <g id="LWPOLYLINE..."><line/></g>
cad_ghost = []   # [[(cad_x, cad_y)]]
for g in rootC.iter("{%s}g" % ns):
    if g.get("id", "") not in ("C-PROP-5", "C-PROP-8"):
        continue
    for el in g.iter():
        tag = el.tag.split("}")[-1]
        if tag == "line":
            try:
                seg = [(float(el.get("x1", 0)), float(el.get("y1", 0))),
                       (float(el.get("x2", 0)), float(el.get("y2", 0)))]
                cad_ghost.append(seg)
            except (ValueError, TypeError):
                pass
        elif tag == "polyline":
            pts_str = el.get("points", "")
            if pts_str:
                pts = parse_points(pts_str)
                if len(pts) >= 2:
                    cad_ghost.append(pts)
print(f"  {len(cad_ghost)} CAD ghost lot line segments")

# ── step 3: affine transform CAD -> 8x11 ──────────────────────────────────────
if cad_labels:
    cad_pts = list(cad_labels.values())
    lot_cxs = [centroid(p)[0] for p, _ in lot_polys]
    lot_cys = [centroid(p)[1] for p, _ in lot_polys]

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
        print(f"\n  CAD->8x11: sx={sx:.4f} sy={sy:.4f} tx={tx:.2f} ty={ty:.2f}")

    # Bipartite greedy matching
    poly_centroids = [centroid(pts) for pts, _ in lot_polys]
    pairs = []
    for lot_num, (cx, cy) in cad_labels.items():
        mapped = cad_to_8x11(cx, cy)
        for i, pc in enumerate(poly_centroids):
            pairs.append((dist(mapped, pc), lot_num, i))
    pairs.sort()

    lot_num_assignments = {}
    assigned_lots  = set()
    assigned_polys = set()
    for d, lot_num, pi in pairs:
        if lot_num not in assigned_lots and pi not in assigned_polys:
            lot_num_assignments[pi] = lot_num
            assigned_lots.add(lot_num)
            assigned_polys.add(pi)

    if DEBUG:
        print("\n  Polygon -> CAD lot assignments:")
        for pi, ln in sorted(lot_num_assignments.items(), key=lambda x: x[1]):
            cx, cy = poly_centroids[pi]
            seq = CAD_TO_SEQ.get(ln, f"?{ln}")
            print(f"    poly[{pi:2d}] ({cx:.1f},{cy:.1f})  CAD={ln:3d}  seq={seq}")
else:
    print("  WARNING: no CAD labels -- lot numbers unassigned")
    lot_num_assignments = {}

    def cad_to_8x11(cx, cy):
        return cx, cy

# ── step 4: scale all 8x11 coordinates by OUTPUT_SCALE ───────────────────────
def scale_pts(pts):
    return [(x * OUTPUT_SCALE, y * OUTPUT_SCALE) for x, y in pts]

lot_polys   = [(scale_pts(pts), fill) for pts, fill in lot_polys]
open_polys  = [scale_pts(pts) for pts in open_polys]
ghost_polys = [scale_pts(pts) for pts in ghost_polys]
water_polys = [scale_pts(pts) for pts in water_polys]

# Transform CAD streams -> 8x11 -> output scale (filter to SVG bounds)
stream_lines_out = []
for seg in cad_streams:
    mapped = [cad_to_8x11(x, y) for x, y in seg]
    if in_svg_bounds(mapped):
        stream_lines_out.append([(x * OUTPUT_SCALE, y * OUTPUT_SCALE)
                                 for x, y in mapped])

# Transform CAD ghost lines -> 8x11 -> output scale (filter to SVG bounds)
ghost_lines_out = []
for seg in cad_ghost:
    mapped = [cad_to_8x11(x, y) for x, y in seg]
    if in_svg_bounds(mapped):
        ghost_lines_out.append([(x * OUTPUT_SCALE, y * OUTPUT_SCALE)
                                for x, y in mapped])

print(f"  {len(stream_lines_out)} stream lines after filtering")
print(f"  {len(ghost_lines_out)} ghost lot lines after filtering")

# ── step 5: compute output viewBox ───────────────────────────────────────────
all_pts = (
    [p for pts, _ in lot_polys for p in pts] +
    [p for pts in open_polys   for p in pts] +
    [p for pts in water_polys  for p in pts] +
    [p for pts in ghost_polys  for p in pts]
)
if not all_pts:
    print("ERROR: no geometry extracted"); sys.exit(1)

x0, y0, x1, y1 = bbox(all_pts)
pad = 60
vx, vy = x0 - pad, y0 - pad
vw, vh = (x1 - x0) + 2*pad, (y1 - y0) + 2*pad

print(f"\n  Output viewBox: {vx:.1f} {vy:.1f} {vw:.1f} {vh:.1f}")

# ── step 6: build output SVG ─────────────────────────────────────────────────
print("Building output SVG ...")

out = []
out.append('<?xml version="1.0" encoding="UTF-8"?>')
out.append(f'<svg id="map-svg" xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="{vx:.2f} {vy:.2f} {vw:.2f} {vh:.2f}" '
           f'preserveAspectRatio="xMidYMid meet">')
out.append('  <!-- Preserve West Phase One -- generated by scripts/extract_preserve_west.py -->')
out.append('')

# ── ghost lots (future phases, bottom layer) ──────────────────────────────────
out.append('  <!-- Ghost lots: future phases -->')
out.append('  <g id="ghost-lots">')
# CAD all-phase property lines (line segments)
for seg in ghost_lines_out:
    if len(seg) == 2:
        x1s, y1s = seg[0]; x2s, y2s = seg[1]
        out.append(f'    <line class="ghost-lot-line"'
                   f' x1="{x1s:.1f}" y1="{y1s:.1f}"'
                   f' x2="{x2s:.1f}" y2="{y2s:.1f}"/>')
    elif len(seg) > 2:
        out.append(f'    <polyline class="ghost-lot-line" points="{fmt_poly_pts(seg)}"/>')
# 8x11 SVG lime polygon outlines of visible future-phase lots
for pts in ghost_polys:
    out.append(f'    <polygon class="ghost-lot-outline" points="{fmt_pts(pts)}"/>')
out.append('  </g>')
out.append('')

# ── water polygons from 8x11 SVG ─────────────────────────────────────────────
if water_polys:
    out.append('  <!-- Water / stream fill (from 8x11 SVG st10) -->')
    out.append('  <g id="water">')
    for pts in water_polys:
        out.append(f'    <polygon class="stream-buffer" points="{fmt_pts(pts)}"/>')
    out.append('  </g>')
    out.append('')

# ── CAD stream centerlines ────────────────────────────────────────────────────
if stream_lines_out:
    out.append('  <!-- Stream top-of-bank (from CAD V-STREAM-TOB-SURVEY) -->')
    out.append('  <g id="streams">')
    for pts in stream_lines_out:
        out.append(f'    <polyline class="stream-tob" points="{fmt_poly_pts(pts)}"/>')
    out.append('  </g>')
    out.append('')

# ── open space ────────────────────────────────────────────────────────────────
if open_polys:
    out.append('  <!-- Open space -->')
    for i, pts in enumerate(open_polys):
        oid = "open-space" if i == 0 else f"open-space-{i}"
        out.append(f'  <polygon id="{oid}" class="open-space-poly" points="{fmt_pts(pts)}"/>')
    out.append('')

# ── Phase 1 lots ──────────────────────────────────────────────────────────────
out.append('  <!-- Phase 1 lots -->')
out.append('  <g id="lots">')

lots_out = []
for i, (pts, fill) in enumerate(lot_polys):
    cad_num = lot_num_assignments.get(i)
    seq_num = CAD_TO_SEQ.get(cad_num) if cad_num is not None else None
    if seq_num is None:
        assigned = {CAD_TO_SEQ.get(lot_num_assignments.get(j))
                    for j in range(len(lot_polys)) if j != i
                    if lot_num_assignments.get(j) in CAD_TO_SEQ}
        for n in range(1, 49):
            if n not in assigned:
                seq_num = n
                break
        print(f"  WARNING: polygon[{i}] CAD={cad_num} -> fallback seq {seq_num}")
    lots_out.append((seq_num, pts))

for seq_num, pts in sorted(lots_out, key=lambda x: (x[0] or 999)):
    out.append(f'    <polygon id="lot-{seq_num}" class="lot"'
               f' data-lot="{seq_num}" data-lot-id="lot-{seq_num}"'
               f' points="{fmt_pts(pts)}"/>')
out.append('  </g>')
out.append('')

# ── road labels ───────────────────────────────────────────────────────────────
out.append('  <!-- Road labels -->')
out.append('  <g id="road-labels">')
for text, cx, cy, rot in ROAD_LABELS:
    ox, oy = cad_to_8x11(cx, cy)
    ox *= OUTPUT_SCALE
    oy *= OUTPUT_SCALE
    out.append(f'    <text class="road-label"'
               f' transform="translate({ox:.1f} {oy:.1f}) rotate({rot:.1f})"'
               f' text-anchor="middle">{text}</text>')
out.append('  </g>')
out.append('')

# ── area labels (Open Space, HOA) ─────────────────────────────────────────────
out.append('  <!-- Area labels -->')
out.append('  <g id="area-labels">')
for text, cx, cy, rot in AREA_LABELS:
    ox, oy = cad_to_8x11(cx, cy)
    ox *= OUTPUT_SCALE
    oy *= OUTPUT_SCALE
    out.append(f'    <text class="area-label"'
               f' transform="translate({ox:.1f} {oy:.1f}) rotate({rot:.1f})"'
               f' text-anchor="middle">{text}</text>')
out.append('  </g>')
out.append('')

# ── lot labels (JS populates) ─────────────────────────────────────────────────
out.append('  <!-- lot labels: JS populateLabels() appends .lot-label-group here -->')
out.append('  <g class="labels"></g>')
out.append('')
out.append('</svg>')

# ── write output ──────────────────────────────────────────────────────────────
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text("\n".join(out), encoding="utf-8")
print(f"\nWrote {len(lots_out)} lots -> {OUTPUT}")
print("Open http://localhost:8765/ to verify lot numbering and adjust CAD_TO_SEQ if needed.")
