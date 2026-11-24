# brandspec

[![CI](https://img.shields.io/github/actions/workflow/status/rafifmsn/brandspec/ci.yml?branch=main&label=CI)](https://github.com/rafifmsn/brandspec/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/brandspec)](https://pypi.org/project/brandspec/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue.svg)](pyproject.toml)

`brandspec` separates **conceptual direction** (authored as a declarative JSON specification) from **geometric execution** (compiled with exact Bezier booleans, symmetry, and optical normalization).
Given the same `spec.json`, `brandspec` produces a byte-identical monochrome SVG, a 4-panel PNG inspection sheet, and deterministic raster quality metrics with zero headless browser dependencies.

![Brandspec Thumbnail](./brandspec-thumb.jpg)

## Architecture

- **Core Geometry (`core/`)**: Resolves centered `square`, `isometric` (30-degree axial), and `polar` grids, builds continuous `grid_path` polylines with exact cubic Bezier corner fillets, applies symmetry, and computes outward `halo` offsets via `skia-pathops`.
- **Mark Engine (`engines/mark/`)**: Compiles constructive primitives (`grid_path`, `arc_band`, `circle`, `ring`, `rect`, `polygon`) and parametric optical effects (`line_screen`, `radial_blades`, `halftone_grid`) with `clip_to` masks, `halo`, and scoped `halo_targets`.
- **Visual Inspection (`inspect/`)**: Rasterizes via `resvg-py` to render a 4-panel `sheet.png` and computes `metrics.json` checks via `numpy` and `pillow`.
- **Expandable Engine Layout**: Designed so future engines (`wordmark`, `lockup`, `icons`, `pattern`, `kit`, `tokens`) and an interactive localhost review surface can plug into the same core and `spec.json` loop.

## Project Layout

```text
brandspec/
├── .github/workflows/
│   ├── ci.yml                        # Pytest and wheel build checks
│   └── publish.yml                   # PyPI Trusted Publishing on v* tags
├── LICENSE                           # GNU General Public License v3.0
├── pyproject.toml
├── skills/brandspec/SKILL.md         # Agent workflow and DSL guide
├── samples/                          # Reference brand mark specs
│   ├── kronos-chambers.json
│   ├── solaris-aperture.json
│   └── vela-sails.json
├── src/brandspec/
│   ├── cli.py                        # CLI commands: archetypes, init, build, check
│   ├── core/                         # Shared grid, path, fillet, and symmetry helpers
│   ├── engines/mark/                 # Geometric and optical mark compiler + archetypes
│   └── inspect/                      # 4-panel sheet.png renderer and metrics gate
└── tests/
    └── test_compiler.py
```

## Installation and Usage

Requires Python 3.11 to 3.13 and [`uv`](https://docs.astral.sh/uv/).

Install the CLI globally from GitHub (or PyPI once published):

```bash
uv tool install git+https://github.com/rafifmsn/brandspec
brandspec archetypes
```

Or run directly in one command with `uvx`:

```bash
uvx --from git+https://github.com/rafifmsn/brandspec brandspec archetypes
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

## Design Specification (`spec.json`)

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
To weave bands over and under each other without cutting earlier segments of the same band, set `"halo_targets": ["<crossing-layer-id>"]` so the clearance carve applies only to the specified target layers.

## Visual Audit and Metrics Gate

Every `brandspec build` outputs:

1. `logo.svg`: Flattened single-path monochrome vector normalized to `1000x1000`.
2. `sheet.png`: 4-panel visual sheet showing (1) the construction grid overlay, (2) 400px positive render, (3) 400px inverted render, and (4) 96px, 48px, and 24px positive/inverted scale tests.
3. `metrics.json`: Automated checks covering `ink_ratio` (target `0.16` to `0.72`), `ink_ratio_24px` (`0.06` to `0.74`), `bbox_aspect` (`<= 2.6`), `island_count`, `tiny_island_count` (`0` tolerated), and `optical_drift_pct`.
4. `spec.json`: Locked specification for deterministic reproduction.

## Bundled Archetypes and Samples

| Recipe | Category | Grid | Focus |
| :--- | :--- | :--- | :--- |
| `ribbon-weave` | `geometric` | `square` | Interlocking stadium links using `halo` and `halo_targets` |
| `iso-impossible` | `geometric` | `isometric` | Three-fold rotational folded hexagon |
| `line-screen-disc` | `effect` | `square` | Linearly modulated stripes clipped to a sphere with diagonal cut |
| `radial-vortex` | `effect` | `polar` | Six-blade twisted optical aperture |
| `stencil-monogram` | `monogram` | `square` | Modular figure-ground letterform with rounded arches |
| `samples/vela-sails.json` | `effect` | `square` | Concave curved sails over a modulated stripe hull |
| `samples/solaris-aperture.json` | `effect` | `polar` | Eight-blade kinetic core inside a segmented corona ring |
| `samples/kronos-chambers.json` | `geometric` | `square` | Four-way interlocking acoustic chambers around a central core |

## Development

```bash
uv run pytest -v
uv build
```

## License

GNU General Public License v3.0 ([LICENSE](LICENSE)).
