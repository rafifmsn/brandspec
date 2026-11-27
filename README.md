<p align="center">
  <img src="./brandspec-thumb.jpg" alt="Brandspec" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/rafifmsn/brandspec/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/rafifmsn/brandspec/ci.yml?branch=main&label=CI" alt="CI" />
  </a>
  <a href="https://pypi.org/project/brandspec/">
    <img src="https://img.shields.io/pypi/v/brandspec" alt="PyPI" />
  </a>
  <a href="./pyproject.toml">
    <img src="https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue.svg" alt="Python 3.11+" />
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3" />
  </a>
</p>

<p align="center">
  An agent-first deterministic brand engineering toolkit. Instead of letting AI agents write fragile raw SVG coordinates or guess spacing, <code>brandspec</code> pairs structured design skills and declarative JSON schemas with an exact geometry compiler and automated visual audit gate.
</p>

<p align="center">
  <a href="#motivation">Motivation</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#project-layout">Project Layout</a> &middot;
  <a href="#installation">Installation</a> &middot;
  <a href="#specification">Specification</a> &middot;
  <a href="#visual-audit">Visual Audit</a> &middot;
  <a href="#archetypes">Archetypes</a>
</p>

## Motivation

AI agents can reason about brand metaphors and iterative feedback, yet generating raw SVG `<path>` coordinates by hand leads to uneven stroke weights, broken Boolean cutouts, and shapes that collapse at favicon sizes.
Treating visual identity as unverified text output makes agent-driven brand design unreliable.

`brandspec` solves this by separating design intent from vector math.
Agents author a compact, grid-aligned `spec.json`, while a deterministic geometry compiler and automated inspection gate (`sheet.png` and `metrics.json`) handle exact path Booleans, scale legibility checks, and production exports across marks, wordmarks, lockups, tokens, icons, patterns, and mockups.

## Architecture

- **Agent Interface (`skills/brandspec/`, `cli.py`)**: Supplies agents with design construction rules, starter archetypes, deterministic build and sweep commands, skill installation, and machine-readable pass/warn feedback.
- **Core Geometry (`core/`)**: Resolves centered `square`, `isometric` (30-degree axial), and `polar` grids, builds continuous `grid_path` polylines with exact cubic Bezier corner fillets, applies symmetry, and computes outward `halo` offsets (`round`, `miter`, `bevel` joins) via `skia-pathops`.
- **Engines (`engines/`)**: Includes `mark` (constructive primitives and optical effects with `clip_to` masks, `halo`, and `halo_targets`), `wordmark` (outlined font glyphs with kerning, ink traps, and stencil cuts), `lockup` (horizontal, stacked, and badge compositions with optical alignment), `mockup` (deterministic perspective compositing onto photographic scenes), `icons` (matched `24x24` icon sets), `pattern` (3x3 seamless tiling SVG patterns), `tokens` (WCAG/APCA contrast audits and palette quantization), and `kit` (favicons, PWA icons, OG cards, and CSS tokens).
- **Visual Inspection & Studio (`inspect/`, `studio/`)**: Rasterizes via `resvg-py` to render a 4-panel `sheet.png`, computes `metrics.json` checks via `numpy` and `pillow`, and serves an interactive localhost review and mockup console (`brandspec review` / `brandspec serve`).

## Project Layout

```text
brandspec/
├── .github/workflows/
│   ├── ci.yml                        # Pytest and wheel build checks
│   └── publish.yml                   # PyPI Trusted Publishing on v* tags
├── docs/
│   ├── PRD.md                        # Master product requirements
│   ├── decisions.md                  # Architecture decisions
│   ├── mockup-prompts.md             # Blank-surface mockup background prompts
│   └── specs/                        # Module specifications (01-07)
├── LICENSE                           # GNU General Public License v3.0
├── pyproject.toml
├── skills/brandspec/SKILL.md         # Agent workflow and DSL guide
├── src/brandspec/
│   ├── cli.py                        # CLI commands and subparsers
│   ├── core/                         # Shared grid, path, fillet, and round helpers
│   ├── engines/
│   │   ├── icons/                    # Matched 24x24 icon set compiler
│   │   ├── kit/                      # Favicon, PWA, OG card, and CSS token exporter
│   │   ├── lockup/                   # Mark and wordmark lockup composer
│   │   ├── mark/                     # Geometric and optical mark compiler, sweep, archetypes
│   │   ├── mockup/                   # Perspective mockup composer, renderer, and templates
│   │   ├── pattern/                  # Seamless 3x3 tiling SVG pattern compiler
│   │   ├── tokens/                   # WCAG/APCA contrast audit and palette extraction
│   │   └── wordmark/                 # Outlined font glyph wordmark compiler
│   ├── inspect/                      # 4-panel sheet.png renderer and metrics gate
│   └── studio/                       # Localhost interactive review console
└── tests/                            # Pytest suite
```

## Installation

Requires Python 3.11 to 3.13 and [`uv`](https://docs.astral.sh/uv/).

Install the CLI globally from PyPI:

```bash
uv tool install brandspec
brandspec archetypes
```

Or run directly in one command with `uvx`:

```bash
uvx brandspec archetypes
```

Or run locally from a clone:

```bash
uv sync --extra dev
uv run brandspec archetypes
uv run brandspec init ribbon-weave --out spec.json
uv run brandspec build spec.json --out-dir out/ribbon-weave
uv run brandspec check spec.json
```

Install the bundled agent skill:

```bash
npx skills add rafifmsn/brandspec
```

### CLI Commands

| Command | Description |
| :--- | :--- |
| `brandspec archetypes` | Lists all bundled mark starter templates. |
| `brandspec init <archetype> --out <path>` | Copies a bundled archetype spec to a working `spec.json`. |
| `brandspec build <spec.json> [--out-dir <dir>] [--strict]` | Compiles `logo.svg`, `sheet.png`, `metrics.json`, and locked `spec.json`. Exits with code `2` under `--strict` if any quality warning triggers. |
| `brandspec check <spec.json>` | Validates the schema and prints `metrics.json` without writing output files. |
| `brandspec schema <engine>` | Prints the JSON Schema for `mark`, `wordmark`, `lockup`, `tokens`, `kit`, `icons`, `pattern`, `sweep`, or `manifest`. |
| `brandspec sweep <spec.json> [--set path=v1,v2] [--sweep <sweep.json>]` | Compiles a bounded parameter matrix (`--max-variants`, `--only-passed`, `--review`) into studio-ready variants and `contact_sheet.png`. |
| `brandspec review --dir <dir> [--wait] [--timeout 900]` | Starts the localhost review console and optionally blocks until human pin feedback is submitted to `review.json`. |
| `brandspec serve --dir <dir> [--port 8420]` | Serves compiled outputs in the localhost review UI. |
| `brandspec tokens check <tokens.spec.json>` | Audits WCAG 2.1 and APCA contrast across declared token and surface pairs. |
| `brandspec palette extract <image> [--colors 6] [--out <path>]` | Quantizes a reference image into deterministic hex `tokens.spec.json`. |
| `brandspec kit build <kit.spec.json> [--out-dir <dir>]` | Exports SVG variants, `favicon.ico`, PWA icons, `og-card.png`, and `tokens.css`. |
| `brandspec wordmark fonts [--query <text>] [--json]` | Lists available `.ttf` and `.otf` system font paths for wordmarks. |
| `brandspec wordmark build <wordmark.spec.json> [--out-dir <dir>]` | Outlines `.ttf`/`.otf` glyphs via `fontTools` with kerning, ink traps, stencil cuts, and `sheet.png`. |
| `brandspec lockup build <lockup.spec.json> [--out-dir <dir>]` | Pairs mark and wordmark into horizontal, stacked, or badge lockups with optical alignment, clearspace guides, and `sheet.png`. |
| `brandspec mockup list` | Lists all bundled photographic mockup scene templates. |
| `brandspec mockup build <target> [--brand-name <name>] [--headline <text>]` | Composites a mark, wordmark, or lockup onto perspective mockup scenes. |
| `brandspec icons build <icons.spec.json> [--out-dir <dir>]` | Compiles matched `24x24` icon sets inheriting mark geometry defaults. |
| `brandspec pattern build <pattern.spec.json> [--out-dir <dir>]` | Compiles 3x3 periodic-wrapped seamless tiling SVG patterns. |
| `brandspec install-skill [--target <preset-or-path>] [--force]` | Installs the bundled `SKILL.md` for AI agents (`agents`, `project`, `claude`, `cursor`, `codex`, `antigravity`, or a custom path). |

### Development

Run the test suite and build locally from a synced clone:

```bash
uv run pytest -v
uv build
```

In offline or sandboxed environments where `uv run` cannot resolve build dependencies, invoke `.venv/bin/pytest` and `.venv/bin/brandspec` directly.

## Specification

All coordinates, widths, and clearances are expressed in multiples of `unit` on a centered grid origin `(0, 0)`.

### Grids

- `square`: `[x, y]` in grid units (`+x` right, `+y` down).
- `isometric`: `[q, r]` 30-degree axial coordinates (`(1, 0)` down-right 30 deg, `(0, 1)` straight down, `(1, -1)` up-right 30 deg).
- `polar`: `[ring, angle_deg]` (`0` deg at 12 o'clock, increasing clockwise).

### Shapes

- `grid_path`: Continuous open or closed polyline through grid points with optional `width` (`0` for filled polygon), `corner_radius`, `cap` (`butt`, `round`, `square`), and `join` (`miter`, `round`, `bevel`).
- `arc_band`: Circular arc or filled pie wedge defined by `center`, `radius`, `start_deg`, `end_deg`, `width`, and `fill_sector`.
- `circle`, `ring`, `rect`, `polygon`: Standard geometric primitives with optional `angle_deg` and `corner_radius`.
- `line_screen`: Parallel stripes modulated by `constant`, `linear`, `center_bulge`, `center_pinch`, `sine`, or `exponential` thickness profiles.
- `radial_blades`: N-fold twisted curved blades arranged radially around a center.
- `halftone_grid`: Grid of `circle`, `square`, or `diamond` cells scaled by `radial_decay`, `radial_grow`, `linear_x`, `linear_y`, `diagonal`, or `sine_ripple`.

### Layered Booleans, `halo`, and `halo_targets`

Each entry in `layers` supports `op` (`unite`, `subtract`, `intersect`, `xor`), optional `clip_to` silhouette masks, and optional per-layer `symmetry` (`none`, `mirror_x`, `mirror_y`, `mirror_xy`, `rotate`, `glide_x`).

Setting `"halo": 0.38` on a `unite` layer automatically dilates that layer outward and subtracts the clearance gap from earlier layers before uniting.
Use `"halo_join"` (`"round"`, `"miter"`, `"bevel"`) and `"halo_cap"` (`"round"`, `"butt"`, `"square"`) to control offset corner and cap geometry.
To weave bands over and under each other without cutting earlier segments of the same band, set `"halo_targets": ["<crossing-layer-id>"]` so the clearance carve applies only to the specified target layers.

## Visual Audit

Every `brandspec build` outputs:

1. `logo.svg`: Flattened single-path monochrome vector normalized to `1000x1000`.
2. `sheet.png`: 4-panel visual sheet showing (1) the construction grid overlay, (2) 400px positive render, (3) 400px inverted render, and (4) 96px, 48px, and 24px positive/inverted scale tests.
3. `metrics.json`: Automated checks covering `ink_ratio` (target `0.16` to `0.72`), `ink_ratio_24px` (`0.06` to `0.74`), `bbox_aspect` (`<= 2.6`), `island_count`, `tiny_island_count` (`0` tolerated), and `optical_drift_pct`.
4. `spec.json`: Locked specification for deterministic reproduction.

## Archetypes

| Recipe | Category | Grid | Focus |
| :--- | :--- | :--- | :--- |
| `ribbon-weave` | `geometric` | `square` | Interlocking stadium links using `halo` and `halo_targets` |
| `iso-impossible` | `geometric` | `isometric` | Three-fold rotational folded hexagon |
| `line-screen-disc` | `effect` | `square` | Linearly modulated stripes clipped to a sphere with diagonal cut |
| `radial-vortex` | `effect` | `polar` | Six-blade twisted optical aperture |
| `stencil-monogram` | `monogram` | `square` | Modular figure-ground letterform with rounded arches |
| `vela-sails` | `effect` | `square` | Concave curved sails over a modulated stripe hull |
| `solaris-aperture` | `effect` | `polar` | Eight-blade kinetic core inside a segmented corona ring |
| `kronos-chambers` | `geometric` | `square` | Four-way interlocking acoustic chambers around a central core |
