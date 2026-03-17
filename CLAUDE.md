# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an interactive real estate lot map for **Tennyson — Phase One**, a residential subdivision with 20 lots (lots 1–18 + Lot A + Lot B). All runtime files live in the **`public/`** directory.

**To preview:** serve `public/` via HTTP (e.g. `python -m http.server 8765 --directory public`) and open `http://localhost:8765/`. The HTML fetches `tennyson-map.svg`, `tennyson-lots.csv`, and `map-styles.css` via `fetch()` so a server is required.

## Architecture

Runtime files — all in `public/`:

- **`public/index.html`** — layout, CSS, and JavaScript
- **`public/tennyson-map.svg`** — static SVG geometry (roads, streams, easements, lot polygons, labels)
- **`public/tennyson-lots.csv`** — lot data (acreage, status, builder assignments)
- **`public/map-styles.css`** — map visual styles (fetched and injected at runtime)
- **`public/plat_full.png`** — 3600×2700px plat PDF scan, used as a togglable overlay
- **`public/svg/JWRG_Positive.svg`** — JWRG watermark logo

### `public/index.html` structure:

1. **CSS** (lines 7–560): Styles for layout, lot states (available/sold/reserved), overlays, mobile responsive layout, `#map-svg-container` sizing
2. **Hidden SVG filter defs** (just after `<body>`): `<svg id="svg-filter-defs">` containing the `grainy-inner-glow` filter and builder-colored glow variants (injected by JS). Kept here so visual-effect logic lives with the HTML, not the geometry SVG.
3. **HTML body**: Header, toolbar buttons, `#map-svg-container` placeholder, info panel, stats bar
4. **JavaScript**: All interactivity — `loadResources()`, `parseCSV()`, `rebuildFromCSV()`, `populateLabels()`, `rebuildBuilderLegend()`, `init()`, lot selection, status management, pan/zoom, builder view, plat/topo overlay controls
5. **External script**: JWRG contact form from `https://office.jwrgnc.com/js/forms.js`

### Load sequence:

1. `loadResources()` fetches `tennyson-map.svg`, `tennyson-lots.csv`, and `map-styles.css` in parallel via `fetch()`
2. SVG text is injected into `#map-svg-container` via `innerHTML`
3. CSS text is injected into a `<style>` tag
4. CSV rows are parsed → `LOT_DATA`, `BUILDER_DATA`, `statuses`, `builderByLot` are built
5. Lot label text populated from CSV, builder legend HTML rebuilt
6. Status classes applied to lot polygons, `init()` called

### Data files (in `public/`, served alongside HTML):

- `tennyson-lots.csv` — lot data in CSV format. **Edit this to update statuses, acreage, and builders.**
- `tennyson-map.svg` — full SVG geometry. Edit this for geometry changes (roads, easements, lot polygons).

## Key Data Structures

- **`LOT_DATA`**: Array of `{id, acres}` for all 20 lots (built from CSV)
- **`BUILDER_DATA`**: Array of builder objects with `{name, short, contact, address, phone, email, lots[], color, border}` (built from CSV; deduplicated by builder name)
- **`statuses`**: Object mapping lot ID → `'available'|'sold'|'reserved'` (built from CSV)
- **`builderByLot`**: Object mapping lot ID → builder object

## Assets

- `public/tennyson-map.svg` — standalone SVG with all map geometry; lot polygons have `data-lot` and `data-lot-id` attributes, label text is empty (populated by JS from CSV)
- `public/tennyson-lots.csv` — one row per lot; columns: `lot_id, lot_number, acres, status, builder_name, builder_short, builder_contact, builder_address, builder_phone, builder_email, builder_color, builder_border`
- `public/plat_full.png` — 3600×2700px plat PDF scan, used as a togglable overlay
- `public/svg/JWRG_Positive.svg` — JWRG watermark logo
- `svg/Tennyson_TopoContour.svg` — source topo contour SVG (topo data is embedded inline in `tennyson-map.svg`; this file is not served at runtime)
- `tennysun.dwg` / `dxf_output_new/tennysun.dxf` — source CAD files (not used at runtime)
- `example.html` — standalone static map variant (Cannady Mill Road / Blackwell Builders)

## SVG Filter Defs

The `grainy-inner-glow` filter and per-builder glow variants live in a hidden `<svg id="svg-filter-defs">` block in `public/index.html` (just after `<body>`), **not** in `tennyson-map.svg`. This keeps visual-effect logic with the HTML/JS layer.

- `createBuilderGlowFilters()` injects builder-colored filter variants into `#svg-filter-defs defs` at runtime
- Lot polygons reference filters via `filter="url(#grainy-inner-glow)"` or `filter="url(#grainy-glow-builder-N)"`

## SVG Coordinate System

The SVG viewBox is `"-20 -20 1240 1000"`. All lot polygon `points` are in this coordinate space. The overlay alignment matrices map external image pixel coordinates to these SVG units:

- **Plat PNG**: `matrix(0.3768, 0, 0, 0.3768, -119, 26)` — constants `BASE_SX/SY/TX/TY` in JS
- **Topo SVG**: `matrix(1.8792, 0, 0, 1.8792, -70.62, -128.57)` — constants `TOPO_BASE_*` in JS

## Pan/Zoom Implementation

Zoom and pan modify the SVG `viewBox` attribute rather than CSS transforms. State: `scale`, `panX`, `panY` globals. Both mouse wheel+drag and touch pinch-zoom/pan are supported. The "Reset View" button resets all view state plus all filter/overlay toggles.

## Mobile Layout

At `max-width: 768px`, the info panel becomes a bottom sheet (slides up from bottom) instead of a right sidebar. Touch events handle panning and pinch-to-zoom.

## Modifying Lot Statuses

Edit `public/tennyson-lots.csv` — change the `status` column to `available`, `sold`, or `reserved`. Reload the page to see the change.

## Adding/Changing Builders

Edit the builder columns in `public/tennyson-lots.csv`. Builder info is repeated per lot row; JS deduplicates by `builder_name`. The builder legend and builder-colored inner glow filters (`createBuilderGlowFilters()`) are generated dynamically from the rebuilt `BUILDER_DATA`.
