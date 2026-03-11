# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an interactive real estate lot map for **Tennyson — Phase One**, a residential subdivision with 20 lots (lots 1–18 + Lot A + Lot B). The primary deliverable is `tennyson-map.html` — a standalone HTML file that requires no build step, bundler, or server.

**To preview:** serve via HTTP (e.g. `python -m http.server 8765`) and open `http://localhost:8765/tennyson-map.html`. The HTML fetches `tennyson-map.svg` and `tennyson-lots.csv` via `fetch()` so a server is required.

## Architecture

The project is now split into three runtime files:

- **`tennyson-map.html`** — layout, CSS, and JavaScript
- **`tennyson-map.svg`** — static SVG geometry (roads, streams, easements, lot polygons, labels)
- **`tennyson-lots.csv`** — lot data (acreage, status, builder assignments)

### `tennyson-map.html` structure:

1. **CSS** (lines 7–560): Styles for layout, lot states (available/sold/reserved), overlays, mobile responsive layout, `#map-svg-container` sizing
2. **HTML body** (lines 562–660): Header, toolbar buttons, `#map-svg-container` placeholder, info panel, stats bar
3. **JavaScript** (lines 663–1230): All interactivity — `loadResources()`, `parseCSV()`, `rebuildFromCSV()`, `populateLabels()`, `rebuildBuilderLegend()`, `init()`, lot selection, status management, pan/zoom, builder view, plat/topo overlay controls
4. **External script**: JWRG contact form from `https://office.jwrgnc.com/js/forms.js`

### Load sequence:

1. `loadResources()` reads `#map-svg-src` and `#lots-data` script block content (synchronous, no fetch)
2. SVG is injected into `#map-svg-container` via `innerHTML`
3. CSV rows are parsed → `LOT_DATA`, `BUILDER_DATA`, `statuses`, `builderByLot` are built
4. Lot label text populated from CSV, builder legend HTML rebuilt
5. Status classes applied to lot polygons, `init()` called

### Embedded data blocks (end of `<body>`):

- `<script id="lots-data" type="text/csv">` — lot data in CSV format; browser ignores this as a script. **Edit this to update statuses, acreage, and builders.** Also update `tennyson-lots.csv` to keep the companion file in sync.
- `<script id="map-svg-src" type="image/svg+xml">` — full SVG geometry. Edit `tennyson-map.svg` for geometry changes, then copy its content here.

## Key Data Structures

- **`LOT_DATA`**: Array of `{id, acres}` for all 18 lots (built from CSV)
- **`BUILDER_DATA`**: Array of builder objects with `{name, short, contact, address, phone, email, lots[], color, border}` (built from CSV; deduplicated by builder name)
- **`statuses`**: Object mapping lot ID → `'available'|'sold'|'reserved'` (built from CSV)
- **`builderByLot`**: Object mapping lot ID → builder object

## Assets

- `tennyson-map.svg` — standalone SVG with all map geometry; lot polygons have `data-lot` and `data-lot-id` attributes, label text is empty (populated by JS from CSV)
- `tennyson-lots.csv` — one row per lot; columns: `lot_id, lot_number, acres, status, builder_name, builder_short, builder_contact, builder_address, builder_phone, builder_email, builder_color, builder_border`
- `plat_full.png` — 3600×2700px plat PDF scan, used as a togglable overlay
- `svg/Tennyson_TopoContour.svg` — topo contour overlay
- `svg/JWRG_Positive.svg` — JWRG watermark logo
- `tennysun.dwg` / `dxf_output_new/tennysun.dxf` — source CAD files (not used at runtime)
- `example.html` — standalone static map variant (Cannady Mill Road / Blackwell Builders)

## SVG Coordinate System

The SVG viewBox is `"-20 -20 1240 1000"`. All lot polygon `points` are in this coordinate space. The overlay alignment matrices map external image pixel coordinates to these SVG units:

- **Plat PNG**: `matrix(0.3768, 0, 0, 0.3768, -119, 26)` — constants `BASE_SX/SY/TX/TY` in JS
- **Topo SVG**: `matrix(1.8792, 0, 0, 1.8792, -70.62, -128.57)` — constants `TOPO_BASE_*` in JS

## Pan/Zoom Implementation

Zoom and pan modify the SVG `viewBox` attribute rather than CSS transforms. State: `scale`, `panX`, `panY` globals. Both mouse wheel+drag and touch pinch-zoom/pan are supported. The "Reset View" button resets all view state plus all filter/overlay toggles.

## Mobile Layout

At `max-width: 768px`, the info panel becomes a bottom sheet (slides up from bottom) instead of a right sidebar. Touch events handle panning and pinch-to-zoom.

## Modifying Lot Statuses

Edit the `<script id="lots-data" type="text/csv">` block near the end of `tennyson-map.html` — change the `status` column to `available`, `sold`, or `reserved`. Also update `tennyson-lots.csv` to keep the companion file in sync. Reload the page to see the change (works with `file://`).

## Adding/Changing Builders

Edit the builder columns in the `lots-data` CSV block. Builder info is repeated per lot row; JS deduplicates by `builder_name`. The builder legend and colored strokes (`createBuilderDots()`) are generated dynamically from the rebuilt `BUILDER_DATA`.
