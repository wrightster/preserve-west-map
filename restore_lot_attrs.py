"""
restore_lot_attrs.py
====================
Two-step helper for editing tennyson-map.svg in Illustrator.

Illustrator strips data-* attributes from lot polygons and flattens
<textPath> elements (curved road labels) to static text. This script
saves a reference before you edit, then restores those elements after export.

STEP 1 — before opening in Illustrator:
    python restore_lot_attrs.py prepare

STEP 2 — after saving your Illustrator export as tennyson-map.svg:
    python restore_lot_attrs.py restore

Or restore from a specific file:
    python restore_lot_attrs.py restore my-export.svg
"""

import csv
import re
import sys
import shutil
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
SVG_PATH     = SCRIPT_DIR / "tennyson-map.svg"
REF_PATH     = SCRIPT_DIR / "tennyson-map-reference.svg"
CSV_PATH     = SCRIPT_DIR / "tennyson-lots.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_acres(csv_path):
    """Return dict mapping lot_id (str) -> acres (str)."""
    acres = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            acres[row["lot_id"]] = row["acres"]
    return acres


REQUIRED_DEFS = '''
    <!-- Required by HTML CSS: lot status fill patterns and shadow filter -->
    <filter id="lotShadow" x="-2%" y="-2%" width="104%" height="104%">
      <feDropShadow dx="1" dy="2" stdDeviation="3" flood-color="#000" flood-opacity="0.06"/>
    </filter>
    <pattern id="pat-available" x="0" y="0" width="28" height="28" patternUnits="userSpaceOnUse" patternTransform="scale(.5)">
      <rect width="28" height="28" fill="#ccd9b8" fill-opacity="0.7"/>
      <g fill="#ccd9b8">
        <circle cx="7" cy="7" r="5"/>
        <circle cx="21" cy="7" r="5"/>
        <circle cx="0" cy="21" r="5"/>
        <circle cx="14" cy="21" r="5"/>
        <circle cx="28" cy="21" r="5"/>
      </g>
    </pattern>
    <pattern id="pat-sold" x="0" y="0" width="14" height="14" patternUnits="userSpaceOnUse" patternTransform="scale(.5)">
      <rect width="14" height="14" fill="#e8c0b8" fill-opacity="0.7"/>
      <polygon points="7,1 13,7 7,13 1,7" fill="#e8c0b8"/>
    </pattern>
    <pattern id="pat-reserved" x="0" y="0" width="28" height="33.48" patternUnits="userSpaceOnUse" patternTransform="scale(.5)">
      <rect width="28" height="33.48" fill="#e8dca0" fill-opacity="0.7"/>
      <g fill="#e8dca0">
        <polygon points="7,1.37 15.09,15.37 -1.09,15.37"/>
        <polygon points="21,15.37 12.91,1.37 29.09,1.37"/>
        <polygon points="0,32.11 -8.09,18.11 8.09,18.11"/>
        <polygon points="14,18.11 22.09,32.11 5.91,32.11"/>
        <polygon points="28,32.11 19.91,18.11 36.09,18.11"/>
      </g>
    </pattern>'''


def fix_plat_lines(svg_text):
    """
    Restore plat/survey line classes that Illustrator collapses to 'st1'.
    The outer lot-zone boundary polygon gets 'lot-boundary';
    interior survey lines/polylines/small polygons get 'plat-line'.
    Identified by being in the group before the lot polygons group and having
    class="st1" with no id attribute.
    """
    # The outer boundary is a large polygon (many points); interior lines are shorter.
    # We use a simple threshold: polygons with >20 point-pairs → lot-boundary, rest → plat-line
    def classify(m):
        tag = m.group(0)
        # Count coordinate pairs by counting spaces in points attr
        pts_match = re.search(r'points="([^"]*)"', tag)
        if pts_match:
            n = len(pts_match.group(1).split()) // 2
            return tag.replace('class="st1"', 'class="lot-boundary"' if n > 20 else 'class="plat-line"')
        return tag.replace('class="st1"', 'class="plat-line"')

    # Only replace st1 on elements that are NOT lot polygons (no id="lot-")
    pattern = re.compile(r'<(?:line|polyline|polygon)\s[^>]*class="st1"[^>]*/>', re.DOTALL)
    count = 0
    def replacer(m):
        nonlocal count
        if 'id="lot-' in m.group(0):
            return m.group(0)
        count += 1
        return classify(m)
    svg_text = pattern.sub(replacer, svg_text)
    print(f"  Fixed {count} plat-line/lot-boundary element(s).")
    return svg_text


def fix_topo_overlay(svg_text):
    """
    Ensure #topo-overlay is a direct child of the SVG root (not inside a masked
    wrapper group) and has no Illustrator st* class hiding it.
    Handles: <g class="stN"><g id="topo-overlay" ...> → <g id="topo-overlay" style="opacity:0.1">
    """
    # Remove masked wrapper: <g class="st..."> immediately followed by topo-overlay
    svg_text = re.sub(
        r'<g class="st\d+">\s*(<g id="topo-overlay")',
        r'\1',
        svg_text
    )
    # Remove the corresponding extra </g> that closed the wrapper (after topo's own </g>)
    # We find the topo-overlay closing </g> followed by a spare </g> before a top-level <g>
    svg_text = re.sub(
        r'(</g>\s*)(</g>)(\s*<g(?:\s|>))',
        lambda m: m.group(1) + m.group(3),
        svg_text,
        count=1
    )
    # Remove Illustrator class from topo-overlay, set visible style
    svg_text = re.sub(
        r'<g id="topo-overlay"[^>]*>',
        '<g id="topo-overlay" style="opacity:0.1">',
        svg_text
    )
    print("  Topo overlay class/wrapper fixed.")
    return svg_text


def remove_flattened_road_labels(svg_text):
    """
    Remove individual-letter <text class="stN"> elements that Illustrator creates
    when it flattens <textPath> road labels. These appear as single-character
    <text> elements at small y coordinates, positioned near the SVG origin.
    """
    # Match <g> blocks that contain only individual-letter st* text elements
    pattern = re.compile(
        r'<g>\s*(?:<text class="st\d+"[^>]*><tspan[^>]*>[^<]*</tspan></text>\s*)+</g>\n?',
        re.DOTALL
    )
    before = len(re.findall(pattern, svg_text))
    svg_text = pattern.sub('', svg_text)
    # Also remove any stray individual-letter text elements between the groups
    stray = re.compile(r'  <text class="st\d+" transform="translate\([^)]+\)"><tspan[^>]*>.</tspan></text>\n')
    before_stray = len(stray.findall(svg_text))
    svg_text = stray.sub('', svg_text)
    print(f"  Removed {before} flattened letter group(s), {before_stray} stray letter(s).")
    return svg_text


def inject_required_groups(svg_text):
    """Inject builder-dots and labels groups before </svg> if missing."""
    injected = []
    if 'id="builder-dots"' not in svg_text:
        svg_text = svg_text.replace('</svg>', '  <g id="builder-dots"></g>\n</svg>', 1)
        injected.append('builder-dots')
    if 'class="labels"' not in svg_text:
        svg_text = svg_text.replace('</svg>', '  <g class="labels"></g>\n</svg>', 1)
        injected.append('labels')
    if injected:
        print(f"  Injected groups: {injected}")
    else:
        print("  Required groups already present.")
    return svg_text


def inject_required_defs(svg_text):
    """Inject pat-available/sold/reserved and lotShadow into <defs> if missing."""
    needed = ['pat-available', 'pat-sold', 'pat-reserved', 'lotShadow']
    if all(n in svg_text for n in needed):
        print("  Required defs already present.")
        return svg_text
    missing = [n for n in needed if n not in svg_text]
    svg_text = svg_text.replace('</defs>', REQUIRED_DEFS + '\n  </defs>', 1)
    print(f"  Injected defs: {missing}")
    return svg_text


def restore_lot_attributes(svg_text, acres_by_id):
    """
    Find every element with id="lot-N" and:
      - Set class="lot" (stripping Illustrator st* classes)
      - Inject data-lot, data-lot-id, data-acres
      - Fix self-closing tag syntax if needed
    Works on <polygon>, <path>, <rect>, or any SVG element type.
    """
    def replacer(m):
        tag = m.group(0)
        lot_num = m.group(1)

        # Fix stray slash from Illustrator self-closing tags: ..."/>  -> ... />
        # and cases where restore inserted attrs after the slash: .../ data-lot=
        tag = re.sub(r'"/ (data-[a-z])', r'" \1', tag)

        # Strip Illustrator st* classes, keep only 'lot'
        if 'class=' in tag:
            def fix_class(cm):
                tokens = [t for t in cm.group(1).split() if not re.match(r'st\d+$', t)]
                if 'lot' not in tokens:
                    tokens.append('lot')
                return f'class="{" ".join(tokens)}"'
            tag = re.sub(r'class="([^"]*)"', fix_class, tag)
        else:
            tag = tag.replace('>', ' class="lot">', 1)

        if 'data-lot=' not in tag:
            tag = tag.replace('>', f' data-lot="{lot_num}">', 1)
        if 'data-lot-id=' not in tag:
            tag = tag.replace('>', f' data-lot-id="{lot_num}">', 1)
        if 'data-acres=' not in tag and lot_num in acres_by_id:
            tag = tag.replace('>', f' data-acres="{acres_by_id[lot_num]}">', 1)

        return tag

    pattern = re.compile(r'<[a-zA-Z][^>]*\bid="lot-([^"]+)"[^>]*/?>',  re.DOTALL)
    return pattern.sub(replacer, svg_text)


def extract_textpath_blocks(svg_text):
    """
    Extract all <text> elements that contain a <textPath> child,
    plus the <path> elements they reference from <defs>.
    Returns (def_paths, text_blocks) as lists of raw strings.
    """
    # <path> elements in <defs> that are referenced by textPath
    def_paths = re.findall(
        r'<path\s[^>]*\bid="[^"]*-path"[^>]*/?>',
        svg_text
    )

    # <text> elements containing <textPath ...>...</textPath>
    text_blocks = re.findall(
        r'<text[^>]*>\s*<textPath[^>]*>.*?</textPath>\s*</text>',
        svg_text,
        re.DOTALL
    )

    return def_paths, text_blocks


def restore_textpaths(svg_text, ref_def_paths, ref_text_blocks):
    """
    Replace flattened road-label <text> elements in svg_text with the
    original <textPath> versions from the reference, and ensure the
    referenced <path> definitions exist in <defs>.
    """
    # Restore <path> defs — insert any missing ones before </defs>
    for def_path in ref_def_paths:
        path_id = re.search(r'id="([^"]+)"', def_path).group(1)
        if path_id not in svg_text:
            svg_text = svg_text.replace('</defs>', f'  {def_path}\n  </defs>', 1)
            print(f"  Restored def path: #{path_id}")

    # For each original textPath block, find and replace the flattened version.
    # Illustrator replaces <text><textPath>Label</textPath></text> with a
    # <text> (or <g>) that contains the label string as a tspan/direct text.
    for block in ref_text_blocks:
        label = re.search(r'<textPath[^>]*>([^<]+)</textPath>', block).group(1).strip()
        # Match any <text ...> element that contains this label string (flattened form)
        flattened_pattern = re.compile(
            rf'<text\b[^>]*>(?:(?!<text).)*?{re.escape(label)}(?:(?!<text).)*?</text>',
            re.DOTALL
        )
        if flattened_pattern.search(svg_text):
            svg_text = flattened_pattern.sub(block, svg_text, count=1)
            print(f"  Restored textPath label: \"{label}\"")
        elif label not in svg_text:
            # Label missing entirely — append before </svg>
            svg_text = svg_text.replace('</svg>', f'  {block}\n</svg>', 1)
            print(f"  Re-inserted missing textPath label: \"{label}\"")
        else:
            print(f"  textPath label already intact: \"{label}\"")

    return svg_text


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_prepare():
    if not SVG_PATH.exists():
        print(f"Error: {SVG_PATH} not found.")
        sys.exit(1)
    shutil.copy2(SVG_PATH, REF_PATH)
    print(f"Reference saved to {REF_PATH}")
    print("You can now open tennyson-map.svg in Illustrator.")

    # Preview what will be preserved
    text = SVG_PATH.read_text(encoding="utf-8")
    def_paths, text_blocks = extract_textpath_blocks(text)
    lots = re.findall(r'id="lot-(\d+)"', text)
    print(f"\nWill preserve on restore:")
    print(f"  {len(lots)} lot polygons: {sorted(lots, key=int)}")
    print(f"  {len(def_paths)} road path def(s) in <defs>")
    print(f"  {len(text_blocks)} textPath label(s):")
    for b in text_blocks:
        label = re.search(r'<textPath[^>]*>([^<]+)</textPath>', b).group(1).strip()
        print(f"    - \"{label}\"")


def cmd_restore(export_path=None):
    if not REF_PATH.exists():
        print(f"Error: reference file not found at {REF_PATH}")
        print("Run 'python restore_lot_attrs.py prepare' before opening Illustrator.")
        sys.exit(1)

    target = Path(export_path) if export_path else SVG_PATH
    if not target.exists():
        print(f"Error: file not found: {target}")
        sys.exit(1)

    # Backup the export
    bak = target.with_suffix(".svg.bak")
    shutil.copy2(target, bak)
    print(f"Backup saved to {bak}")

    acres    = load_acres(CSV_PATH)
    ref_text = REF_PATH.read_text(encoding="utf-8")
    svg_text = target.read_text(encoding="utf-8")

    print("\nInjecting required defs (patterns + filters)...")
    svg_text = inject_required_defs(svg_text)

    print("\nRestoring lot attributes...")
    svg_text = restore_lot_attributes(svg_text, acres)
    lots = re.findall(r'id="lot-([^"]+)"', svg_text)
    numeric = [l for l in lots if l.isdigit()]
    named = [l for l in lots if not l.isdigit()]
    print(f"  Lots processed: {sorted(numeric, key=int) + sorted(named)}")

    print("\nRestoring textPath road labels...")
    ref_def_paths, ref_text_blocks = extract_textpath_blocks(ref_text)
    svg_text = restore_textpaths(svg_text, ref_def_paths, ref_text_blocks)

    print("\nFixing plat line classes...")
    svg_text = fix_plat_lines(svg_text)

    print("\nFixing topo overlay class...")
    svg_text = fix_topo_overlay(svg_text)

    print("\nRemoving flattened road label letters...")
    svg_text = remove_flattened_road_labels(svg_text)

    print("\nInjecting required SVG groups...")
    svg_text = inject_required_groups(svg_text)

    target.write_text(svg_text, encoding="utf-8")
    print(f"\nDone. Restored file written to {target}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args[0] == "prepare":
        cmd_prepare()
    elif args[0] == "restore":
        cmd_restore(args[1] if len(args) > 1 else None)
    else:
        # Legacy: treat first arg as export path (backwards compat)
        cmd_restore(args[0])


if __name__ == "__main__":
    main()
