#!/usr/bin/env python
"""
cleanup_svg.py — Build a clean preserve-west-map.svg from two sources:
  1. Current SVG (on disk)  — provides user-labeled shapes (lots, road, spaces, HOA)
  2. Git HEAD SVG           — provides the River polyline (class st25) that was lost

Final output has:
  - Lots:       id="lot-N", class="lot", data-lot="N", data-lot-id="N"
  - Road:       id="Road",  class="road-fill"
  - Open space: id="smallspace"/"bigspace", class="open-space"
  - HOA:        id="HOA",   class="HOA"
  - River:      id="River", class="stream-tob", data-type="stream-tob"
  - Stroke/label groups preserved (empty — JS rebuilds content)
  - <g class="labels"> present for JS to inject labels into
"""

import subprocess
from lxml import etree

SVG_PATH = 'public/preserve-west-map.svg'
NS  = 'http://www.w3.org/2000/svg'
NSD = '{' + NS + '}'

def local(el):
    t = el.tag
    if not isinstance(t, str): return None
    return t.replace(NSD, '') if t.startswith(NSD) else t

def parse(data):
    return etree.fromstring(data, parser=etree.XMLParser(recover=True, remove_comments=True))

# ── 1. Load current SVG ────────────────────────────────────────────
with open(SVG_PATH, 'rb') as f:
    cur_root = parse(f.read())

# ── 2. Collect user-labeled shapes from current SVG ────────────────
# A "labeled" element has an id that isn't a structural/defs id.
STRUCTURAL_IDS = {'map-svg', 'lot-stroke-layer', 'lot-highlight-layer'}
SKIP_ID_PREFIXES = ('clippath',)
SHAPE_TAGS = {'polygon', 'path', 'rect', 'polyline', 'circle', 'ellipse', 'line'}

labeled = {}   # id → element
for el in cur_root.iter():
    tag = local(el)
    if tag not in SHAPE_TAGS:
        continue
    eid = el.get('id', '')
    if not eid:
        continue
    if eid in STRUCTURAL_IDS or any(eid.startswith(p) for p in SKIP_ID_PREFIXES):
        continue
    # Normalise lot ids: strip any existing "lot-" prefix, then re-add it
    dtype = el.get('data-type', '').strip()
    if dtype == 'lot':
        num = eid.replace('lot-', '')   # "lot-1" → "1", "1" → "1"
        canonical_id = 'lot-' + num
        el.set('id', canonical_id)
        el.set('data-lot', num)
        el.set('data-lot-id', num)
    else:
        canonical_id = eid
    # Apply semantic class
    if dtype:
        el.set('class', dtype)
    else:
        el.attrib.pop('class', None)
    labeled[canonical_id] = el

print(f"Labeled shapes found in current SVG: {len(labeled)}")

# ── 3. Get River polyline from git if missing ──────────────────────
has_river = any(el.get('id') == 'River' or el.get('data-type') == 'stream-tob'
                for el in cur_root.iter())

if not has_river:
    print("River missing — recovering from git HEAD...")
    try:
        git_svg = subprocess.check_output(
            ['git', 'show', 'HEAD:public/preserve-west-map.svg'],
            stderr=subprocess.DEVNULL
        )
        git_root = parse(git_svg)
        # The river is the polyline with class "st25" in the original Illustrator export
        for el in git_root.iter():
            if local(el) == 'polyline' and 'st25' in (el.get('class') or ''):
                river = etree.fromstring(etree.tostring(el))  # detached copy
                river.set('id', 'River')
                river.set('data-type', 'stream-tob')
                river.set('class', 'stream-tob')
                river.attrib.pop('style', None)
                labeled['River'] = river
                print(f"  River recovered (points length: {len(river.get('points',''))} chars)")
                break
        else:
            print("  WARNING: could not find River polyline in git HEAD")
    except Exception as e:
        print(f"  WARNING: git recovery failed: {e}")

# ── 4. Build clean SVG ─────────────────────────────────────────────
viewBox = cur_root.get('viewBox', '0 0 595 842')

new_root = etree.Element(NSD + 'svg', nsmap={
    None: NS,
    'xlink': 'http://www.w3.org/1999/xlink',
})
new_root.set('id', 'map-svg')
new_root.set('version', '1.1')
new_root.set('viewBox', viewBox)

# Main group holding all shapes
main_g = etree.SubElement(new_root, NSD + 'g')

for eid, el in labeled.items():
    main_g.append(el)

# Stroke layer and labels group (empty — JS fills them at runtime)
stroke_g = etree.SubElement(new_root, NSD + 'g')
stroke_g.set('id', 'lot-stroke-layer')

labels_g = etree.SubElement(new_root, NSD + 'g')
labels_g.set('class', 'labels')

# ── 5. Write output ────────────────────────────────────────────────
out = etree.tostring(new_root, pretty_print=True,
                     xml_declaration=True, encoding='UTF-8').decode('utf-8')

with open(SVG_PATH, 'w', encoding='utf-8', newline='') as f:
    f.write(out)

# Summary
classes = sorted(set(el.get('class', '(none)') for el in labeled.values()))
print(f"\nOutput: {len(labeled)} shapes, classes: {classes}")
print(f"File: {SVG_PATH}")
