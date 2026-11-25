# Architecture and Design Decisions

## Product Positioning: Agent-First Compiler Over Browser Suite

BrandSpec does not try to replace Figma, Illustrator, or Coolors.co.
Browser design suites optimize for manual mouse dragging and visual palette browsing by humans, which demands heavy frontend frameworks and large dependency trees.
BrandSpec occupies the deterministic compiler layer for AI agents.
Agents handle coordinate math, color extraction from reference images, multi-variant parameter sweeps, and automated legibility and contrast checks in Python.
Humans focus strictly on creative direction: inspecting compiled sheets, comparing candidates, dropping coordinate-pinned notes, and signing off on deliverables.

## Runtime and Distribution: Pure Python Single Wheel

The CLI and all compilation engines must run with zero Node.js or browser build-tool runtime dependencies when installed via `uv tool install brandspec` or `uvx brandspec`.
Python stdlib `http.server.ThreadingHTTPServer` serves zero-build vanilla HTML, CSS, and JS for the localhost studio.
Keeping `studio/` asset files directly inside the Python wheel ensures instant cold startup and eliminates npm lockfile maintenance.

## Wordmarks and Mockups: `fontTools` Plus Browser Studio Over Satori

Satori converts HTML/CSS into SVG, but it requires Node.js and yields layout trees rather than editable glyph contours.
For production vector typography, `engines/wordmark` uses `fontTools` and `skia-pathops` in pure Python so agents can carve real ink traps, add stencil cuts, adjust optical kerning, and output clean flattened SVG paths.
Rich contextual mockups (such as website headers, social cards, and app-icon previews) render inside the `studio` browser UI using HTML/CSS wrappers around the compiled SVGs, giving human reviewers real-world context without introducing Node.js into the Python package.

## Schema Composition: Modular Specs Over Monolith

`MarkSpec` (`schemaVersion: 1`) remains focused on single-mark geometry so agents can iterate without navigating unrelated token or export blocks.
New engines (`tokens`, `wordmark`, `lockup`, `kit`, `icons`, `pattern`) use dedicated sibling schema files (`*.spec.json`) composed optionally by a root `brand.json` manifest.
Sweep configurations stay external via CLI `--set` flags or a separate `sweep.json` file rather than embedding sweep matrices inside `MarkSpec`.

## Studio Visual Design System and Anti-Slop Rules

The `studio` web interface follows the exact monochrome obsidian and graphite aesthetic established in the repository's reference UIs (`rafifmsn/exchange` and `Celerum`).
Implementing agents must adhere strictly to these tokens and constraints:

| Token | Value | Role |
| :--- | :--- | :--- |
| `--bg-canvas` | `#0b0c0e` | Root viewport background |
| `--bg-surface` | `#121316` | Primary cards and stage panels |
| `--bg-elevated` | `#181a1f` | Inputs, hover states, and recessed wells |
| `--border-hairline` | `#26282e` | Default `1px solid` hairline dividers and card edges |
| `--border-active` | `#3a3e47` | Hover, focus, and selected state borders |
| `--text-primary` | `#f3f4f6` | Headings, active labels, and primary metrics |
| `--text-secondary` | `#9ca3af` | Subtitles, descriptions, and secondary labels |
| `--text-muted` | `#6b7280` | Axis markers and quiet captions |
| `--btn-primary-bg` | `linear-gradient(180deg, #ffffff 0%, #e5e7eb 100%)` | Primary submit and active filter pills (ink `#0b0c0e`) |
| `--btn-secondary-bg` | `linear-gradient(180deg, #1d1f24 0%, #15171b 100%)` | Secondary buttons and view toggles (ink `#e5e7eb`) |

Typography uses a single sans-serif family throughout (`"Inter", system-ui, -apple-system, "Segoe UI", sans-serif`).
Do not load or pair a monospace font anywhere in the UI; apply `font-variant-numeric: tabular-nums` on the same sans-serif font for all coordinates, ratios, and counts.
Reject AI-slop clutter: omit decorative status dots, sparkle icons, gradient text, nested cards-inside-cards, unrequested notification bells, and filler copy.
Use clean `16px` to `24px` panel spacing, `1px` hairline separation, and clear functional controls only.

## Skill Packaging: Single Source via Hatchling

`skills/brandspec/SKILL.md` remains the sole canonical skill file in git so both repo clones and `npx skills add rafifmsn/brandspec` stay aligned.
`pyproject.toml` maps `skills/brandspec/SKILL.md` into the wheel via `[tool.hatch.build.targets.wheel.force-include]` so `brandspec install-skill` reads it from `importlib.resources` with zero duplicate files checked into git.
