"""CLI entrypoint for brandspec."""

from __future__ import annotations

import argparse
from importlib import resources
import json
import sys
import threading
import webbrowser
from pathlib import Path

from pydantic import ValidationError

from .core.rounds import snapshot_prior_round_before_build
from .engines.icons.compiler import compile_icon_set
from .engines.icons.schema import IconSetSpec
from .engines.kit.exporter import export_kit
from .engines.kit.schema import BrandManifest, KitSpec
from .engines.lockup.compiler import compile_lockup
from .engines.lockup.schema import LockupSpec
from .engines.mark.artifacts import write_mark_artifacts
from .engines.mark.compiler import compile_spec
from .engines.mark.schema import MarkSpec
from .engines.mark.sweep import SweepSpec, merge_axes, run_sweep
from .engines.mockup import MockupContext, discover_templates, render_all_mockups
from .engines.pattern.compiler import compile_pattern
from .engines.pattern.schema import PatternSpec
from .engines.tokens.contrast import audit_tokens_contrast
from .engines.tokens.extract import extract_tokens_from_image
from .engines.tokens.schema import TokensSpec
from .engines.wordmark.compiler import compile_wordmark
from .engines.wordmark.schema import WordmarkSpec
from .inspect import analyze_compiled, render_inspection_sheet
from .studio.server import create_studio_server


def _find_archetypes_dir() -> Path:
    pkg_dir = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))
    if pkg_dir.is_dir():
        return pkg_dir
    raise FileNotFoundError("Could not locate bundled mark archetypes directory.")


def cmd_archetypes(_args: argparse.Namespace) -> int:
    arch_dir = _find_archetypes_dir()
    files = sorted(arch_dir.glob("*.json"))
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        print(f"{f.stem:20s} [{data.get('category', 'geometric'):9s}] {data.get('concept', '')}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    arch_dir = _find_archetypes_dir()
    src = arch_dir / f"{args.archetype}.json"
    if not src.is_file():
        available = ", ".join(p.stem for p in sorted(arch_dir.glob("*.json")))
        print(f"Unknown archetype '{args.archetype}'. Available: {available}", file=sys.stderr)
        return 1
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


def _load_spec(spec_path: Path) -> MarkSpec:
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    return MarkSpec.model_validate(raw)


def cmd_build(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    try:
        spec = _load_spec(spec_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Spec error: {exc}", file=sys.stderr)
        return 1

    compiled = compile_spec(spec)
    metrics = analyze_compiled(compiled)
    out_dir = Path(args.out_dir) if args.out_dir else spec_path.parent / "out" / spec_path.stem
    snapshot_prior_round_before_build(out_dir)
    paths = write_mark_artifacts(spec, compiled, metrics, out_dir)

    print(
        json.dumps(
            {
                "svg": str(paths["svg"]),
                "sheet": str(paths["sheet"]),
                "metrics": str(paths["metrics"]),
                "meta": str(paths["meta"]),
                **metrics.to_dict(),
            },
            indent=2,
        )
    )
    return 0 if (metrics.passed or not args.strict) else 2


def cmd_check(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    try:
        spec = _load_spec(spec_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Spec error: {exc}", file=sys.stderr)
        return 1

    compiled = compile_spec(spec)
    metrics = analyze_compiled(compiled)
    print(json.dumps(metrics.to_dict(), indent=2))
    return 0 if metrics.passed else 2


def _load_bundled_skill() -> str:
    pkg_skill = resources.files("brandspec").joinpath("skills/SKILL.md")
    try:
        return pkg_skill.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        repo_skill = Path(__file__).resolve().parents[2] / "skills" / "brandspec" / "SKILL.md"
        if repo_skill.is_file():
            return repo_skill.read_text(encoding="utf-8")
        raise FileNotFoundError("Could not locate bundled SKILL.md.")


def resolve_skill_target(target: str) -> Path:
    """Resolve a named skill preset or explicit filesystem target to a SKILL.md path."""
    home = Path.home()
    presets = {
        "agents": home / ".agents" / "skills" / "brandspec" / "SKILL.md",
        "project": Path.cwd() / ".agents" / "skills" / "brandspec" / "SKILL.md",
        "claude": home / ".claude" / "skills" / "brandspec" / "SKILL.md",
        "cursor": home / ".cursor" / "skills" / "brandspec" / "SKILL.md",
        "codex": home / ".codex" / "skills" / "brandspec" / "SKILL.md",
        "antigravity": home / ".gemini" / "skills" / "brandspec" / "SKILL.md",
    }
    if target in presets:
        return presets[target]
    candidate = Path(target).expanduser()
    if candidate.suffix.lower() == ".md":
        return candidate
    return candidate / "SKILL.md"


def cmd_install_skill(args: argparse.Namespace) -> int:
    dest = resolve_skill_target(args.target)
    if dest.exists() and not args.force:
        print(
            f"Refusing to overwrite existing skill at {dest}. Pass --force to replace it.",
            file=sys.stderr,
        )
        return 1
    content = _load_bundled_skill()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print(f"Installed skill to {dest}")
    return 0


def run_studio_server(
    target_dir: Path,
    port: int,
    open_browser: bool,
    wait: bool,
    timeout: int,
    on_ready: callable | None = None,
) -> int:
    """Start the localhost studio server and optionally block until review submission."""
    if not target_dir.is_dir():
        print(f"Studio error: directory does not exist: {target_dir}", file=sys.stderr)
        return 1

    try:
        server, state = create_studio_server(target_dir, host="127.0.0.1", port=port)
    except OSError as exc:
        print(f"Studio error: could not bind 127.0.0.1:{port} ({exc})", file=sys.stderr)
        return 1

    bound_port = server.server_address[1]
    url = f"http://127.0.0.1:{bound_port}/"
    print(f"BrandSpec Studio listening on {url}", flush=True)
    if on_ready is not None:
        on_ready(url, state)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if open_browser:
        webbrowser.open(url)

    try:
        if wait:
            wait_seconds = None if timeout <= 0 else float(timeout)
            submitted = state.submitted_event.wait(timeout=wait_seconds)
            if not submitted:
                print(f"Studio review timed out after {timeout}s.", file=sys.stderr)
                return 3
            print(json.dumps(state.submitted_review, indent=2))
            return 0

        while thread.is_alive():
            thread.join(timeout=0.5)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()


def cmd_review(args: argparse.Namespace) -> int:
    return run_studio_server(
        target_dir=Path(args.dir),
        port=args.port,
        open_browser=args.open,
        wait=args.wait,
        timeout=args.timeout,
    )


def cmd_serve(args: argparse.Namespace) -> int:
    return run_studio_server(
        target_dir=Path(args.dir),
        port=args.port,
        open_browser=args.open,
        wait=False,
        timeout=0,
    )


def cmd_sweep(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    try:
        raw_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        sweep_spec = (
            SweepSpec.model_validate(json.loads(Path(args.sweep).read_text(encoding="utf-8")))
            if args.sweep
            else None
        )
        axes, max_variants = merge_axes(
            sweep_spec,
            args.set or [],
            max_variants_override=args.max_variants,
        )
        out_dir = (
            Path(args.out_dir)
            if args.out_dir
            else spec_path.parent / "out" / f"{spec_path.stem}-sweep"
        )
        result = run_sweep(
            raw_spec=raw_spec,
            axes=axes,
            out_dir=out_dir,
            max_variants=max_variants,
            only_passed=args.only_passed,
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Sweep error: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "out_dir": str(result.out_dir),
                "variants": str(result.variants_file),
                "contact_sheet": str(result.contact_sheet_file),
                "count": len(result.variants),
            },
            indent=2,
        )
    )
    if args.review:
        return run_studio_server(
            target_dir=result.out_dir,
            port=0,
            open_browser=True,
            wait=True,
            timeout=900,
        )
    return 0


def cmd_tokens_check(args: argparse.Namespace) -> int:
    tokens_path = Path(args.spec)
    try:
        raw = json.loads(tokens_path.read_text(encoding="utf-8"))
        spec = TokensSpec.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Tokens error: {exc}", file=sys.stderr)
        return 1

    report = audit_tokens_contrast(spec)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 2


def cmd_palette_extract(args: argparse.Namespace) -> int:
    image_path = Path(args.image)
    if not image_path.is_file():
        print(f"Palette error: image not found: {image_path}", file=sys.stderr)
        return 1
    try:
        tokens = extract_tokens_from_image(image_path, colors=args.colors)
    except (OSError, ValueError) as exc:
        print(f"Palette error: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(tokens, indent=2) + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(text, end="")
    return 0


def cmd_kit_build(args: argparse.Namespace) -> int:
    kit_path = Path(args.spec)
    try:
        raw = json.loads(kit_path.read_text(encoding="utf-8"))
        spec = KitSpec.model_validate(raw)
        out_dir = Path(args.out_dir) if args.out_dir else kit_path.parent / "out" / kit_path.stem
        outputs = export_kit(spec, kit_path.parent, out_dir)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Kit error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({k: str(v) for k, v in outputs.items()}, indent=2))
    return 0


def cmd_wordmark_build(args: argparse.Namespace) -> int:
    wm_path = Path(args.spec)
    try:
        raw = json.loads(wm_path.read_text(encoding="utf-8"))
        spec = WordmarkSpec.model_validate(raw)
        compiled = compile_wordmark(spec, base_dir=wm_path.parent)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Wordmark error: {exc}", file=sys.stderr)
        return 1

    metrics = analyze_compiled(compiled)
    out_dir = Path(args.out_dir) if args.out_dir else wm_path.parent / "out" / wm_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    wordmark_svg = out_dir / "wordmark.svg"
    logo_svg = out_dir / "logo.svg"
    metrics_file = out_dir / "metrics.json"
    spec_file = out_dir / "spec.json"
    meta_file = out_dir / "meta.json"

    wordmark_svg.write_text(compiled.svg_markup, encoding="utf-8")
    logo_svg.write_text(compiled.svg_markup, encoding="utf-8")
    render_inspection_sheet(compiled).save(out_dir / "sheet.png", format="PNG")
    metrics_file.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")
    spec_file.write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )
    meta_file.write_text(
        json.dumps(
            {
                "name": spec.name,
                "concept": f"Wordmark: {spec.text}",
                "unit": spec.unit,
                "canvas_size": spec.post.canvas_size,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "svg": str(wordmark_svg),
                "metrics": str(metrics_file),
                "contour_count": compiled.contour_count,
                **metrics.to_dict(),
            },
            indent=2,
        )
    )
    return 0


def cmd_lockup_build(args: argparse.Namespace) -> int:
    lockup_path = Path(args.spec)
    try:
        raw = json.loads(lockup_path.read_text(encoding="utf-8"))
        spec = LockupSpec.model_validate(raw)
        compiled = compile_lockup(spec, base_dir=lockup_path.parent)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Lockup error: {exc}", file=sys.stderr)
        return 1

    metrics = analyze_compiled(compiled)
    out_dir = Path(args.out_dir) if args.out_dir else lockup_path.parent / "out" / lockup_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    lockup_svg = out_dir / "lockup.svg"
    clearspace_svg = out_dir / "lockup-clearspace.svg"
    logo_svg = out_dir / "logo.svg"
    metrics_file = out_dir / "metrics.json"
    spec_file = out_dir / "spec.json"
    meta_file = out_dir / "meta.json"

    lockup_svg.write_text(compiled.svg_markup, encoding="utf-8")
    clearspace_svg.write_text(compiled.clearspace_svg_markup, encoding="utf-8")
    logo_svg.write_text(compiled.svg_markup, encoding="utf-8")
    render_inspection_sheet(compiled).save(out_dir / "sheet.png", format="PNG")
    metrics_file.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")
    spec_file.write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )
    meta_file.write_text(
        json.dumps(
            {
                "name": spec.name,
                "concept": f"Lockup ({spec.layout})",
                "canvas_size": spec.canvas_size,
                "gap_svg": round(compiled.gap_svg, 2),
                "clearspace_svg": round(compiled.clearspace_svg, 2),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "svg": str(lockup_svg),
                "clearspace_svg": str(clearspace_svg),
                "metrics": str(metrics_file),
                "gap_svg": round(compiled.gap_svg, 2),
                **metrics.to_dict(),
            },
            indent=2,
        )
    )
    return 0


def cmd_icons_build(args: argparse.Namespace) -> int:
    icons_path = Path(args.spec)
    try:
        raw = json.loads(icons_path.read_text(encoding="utf-8"))
        spec = IconSetSpec.model_validate(raw)
        compiled = compile_icon_set(spec, base_dir=icons_path.parent)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Icons error: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else icons_path.parent / "out" / icons_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_file = out_dir / "icons-sheet.png"
    compiled.sheet_image.save(sheet_file, format="PNG")

    summary: list[dict] = []
    for icon in compiled.icons:
        svg_file = out_dir / f"{icon.id}.svg"
        svg_file.write_text(icon.svg_markup, encoding="utf-8")
        summary.append(
            {
                "id": icon.id,
                "svg": str(svg_file),
                **icon.metrics.to_dict(),
            }
        )

    metrics_file = out_dir / "metrics.json"
    metrics_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "sheet": str(sheet_file),
                "metrics": str(metrics_file),
                "icons": summary,
            },
            indent=2,
        )
    )
    return 0


def cmd_pattern_build(args: argparse.Namespace) -> int:
    pat_path = Path(args.spec)
    try:
        raw = json.loads(pat_path.read_text(encoding="utf-8"))
        spec = PatternSpec.model_validate(raw)
        compiled = compile_pattern(spec)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"Pattern error: {exc}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else pat_path.parent / "out" / pat_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    tile_file = out_dir / "tile.svg"
    pattern_file = out_dir / "pattern.svg"
    spec_file = out_dir / "spec.json"

    tile_file.write_text(compiled.tile_svg_markup, encoding="utf-8")
    pattern_file.write_text(compiled.pattern_svg_markup, encoding="utf-8")
    spec_file.write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "tile_svg": str(tile_file),
                "pattern_svg": str(pattern_file),
                "tile_width_px": compiled.tile_width_px,
                "tile_height_px": compiled.tile_height_px,
            },
            indent=2,
        )
    )
    return 0


def _extract_accent_from_spec(spec_data: dict) -> str | None:
    fill = spec_data.get("post", {}).get("fill")
    if isinstance(fill, str) and fill.lower() not in {"#000000", "#111111", "#ffffff"}:
        return fill
    if isinstance(fill, dict):
        for stop in fill.get("stops", []):
            c = str(stop.get("color", "")).lower()
            if c and c not in {"#000000", "#111111", "#ffffff"}:
                return c
    return None


SCHEMA_MODELS = {
    "icons": IconSetSpec,
    "kit": KitSpec,
    "lockup": LockupSpec,
    "manifest": BrandManifest,
    "mark": MarkSpec,
    "pattern": PatternSpec,
    "sweep": SweepSpec,
    "tokens": TokensSpec,
    "wordmark": WordmarkSpec,
}


def _default_font_dirs() -> list[Path]:
    home = Path.home()
    candidates = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".local" / "share" / "fonts",
        home / ".fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        home / "Library" / "Fonts",
        Path("C:/Windows/Fonts"),
    ]
    return [p for p in candidates if p.is_dir()]


def discover_system_fonts(
    font_dirs: list[Path] | None = None,
    query: str | None = None,
) -> list[Path]:
    """Return sorted .ttf and .otf font paths from standard OS font directories."""
    dirs = _default_font_dirs() if font_dirs is None else [p for p in font_dirs if p.is_dir()]
    needle = query.strip().lower() if query else ""
    found: set[Path] = set()
    for base in dirs:
        try:
            for path in base.rglob("*"):
                if path.is_file() and path.suffix.lower() in {".ttf", ".otf"}:
                    if not needle or needle in str(path).lower():
                        found.add(path)
        except OSError:
            continue
    return sorted(found, key=lambda p: str(p).lower())


def cmd_schema(args: argparse.Namespace) -> int:
    model = SCHEMA_MODELS[args.engine]
    print(json.dumps(model.model_json_schema(), indent=2))
    return 0


def cmd_wordmark_fonts(args: argparse.Namespace) -> int:
    fonts = discover_system_fonts(query=args.query)
    if args.json:
        print(json.dumps([str(p) for p in fonts], indent=2))
    else:
        for font in fonts:
            print(font)
    return 0


def cmd_mockup_list(_args: argparse.Namespace) -> int:
    for _tdir, manifest in discover_templates():
        print(f"{manifest.id:22s} [{manifest.category:9s}] {manifest.title} ({len(manifest.slots)} slot(s))")
    return 0


def cmd_mockup_build(args: argparse.Namespace) -> int:
    target = Path(args.target)
    spec_data: dict = {}
    if target.is_dir():
        svg_path = target / "logo.svg"
        if not svg_path.is_file():
            print(f"Mockup error: no logo.svg found in {target}", file=sys.stderr)
            return 1
        logo_svg = svg_path.read_text(encoding="utf-8")
        spec_file = target / "spec.json"
        if spec_file.is_file():
            spec_data = json.loads(spec_file.read_text(encoding="utf-8"))
        base_dir = target
    elif target.suffix.lower() == ".svg" and target.is_file():
        logo_svg = target.read_text(encoding="utf-8")
        base_dir = target.parent
    elif target.is_file():
        try:
            spec_data = json.loads(target.read_text(encoding="utf-8"))
            mark_spec = MarkSpec.model_validate(spec_data)
            logo_svg = compile_spec(mark_spec).svg_markup
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            print(f"Mockup error: {exc}", file=sys.stderr)
            return 1
        base_dir = target.parent
    else:
        print(f"Mockup error: target not found: {target}", file=sys.stderr)
        return 1

    tokens_data: dict = {}
    tokens_path = Path(args.tokens) if args.tokens else (base_dir / "tokens.spec.json")
    if tokens_path.is_file():
        try:
            tokens = TokensSpec.model_validate(json.loads(tokens_path.read_text(encoding="utf-8")))
            tokens_data = tokens.model_dump(mode="json")
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            print(f"Mockup tokens error: {exc}", file=sys.stderr)
            return 1

    accent = (
        args.accent
        or tokens_data.get("accent")
        or _extract_accent_from_spec(spec_data)
        or "#525252"
    )
    raw_concept = str(spec_data.get("concept") or "").strip()
    default_headline = raw_concept if raw_concept and len(raw_concept) <= 36 else "Precision built for scale."
    ctx = MockupContext(
        brand_name=args.brand_name or spec_data.get("name") or tokens_data.get("name") or "Brandspec",
        headline=args.headline or default_headline,
        tagline=args.tagline or "Deterministic identity across every surface.",
        website=args.website or "brandspec.com",
        accent=accent,
        surface_dark=tokens_data.get("bg_canvas", "#111318"),
        text_light=tokens_data.get("text_primary", "#f9fafb"),
    )

    only_ids = (
        {part.strip() for part in args.templates.split(",") if part.strip()}
        if args.templates
        else None
    )
    out_dir = Path(args.out_dir) if args.out_dir else (base_dir / "mockups")
    records = render_all_mockups(logo_svg, out_dir, ctx=ctx, only_ids=only_ids)
    (out_dir / "mockups.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out_dir": str(out_dir), "count": len(records), "mockups": records}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="brandspec",
        description="Deterministic brand specification compiler and visual audit CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_arch = sub.add_parser("archetypes", help="List bundled mark starter archetypes")
    p_arch.set_defaults(func=cmd_archetypes)

    p_init = sub.add_parser("init", help="Copy an archetype spec to a working spec.json")
    p_init.add_argument("archetype", help="Archetype name")
    p_init.add_argument("--out", default="spec.json", help="Destination JSON path")
    p_init.set_defaults(func=cmd_init)

    p_build = sub.add_parser("build", help="Compile spec.json into SVG, inspection sheet, and metrics")
    p_build.add_argument("spec", help="Path to spec.json")
    p_build.add_argument("--out-dir", help="Output directory")
    p_build.add_argument("--strict", action="store_true", help="Exit non-zero if quality metrics warn")
    p_build.set_defaults(func=cmd_build)

    p_check = sub.add_parser("check", help="Validate schema and quality metrics without writing files")
    p_check.add_argument("spec", help="Path to spec.json")
    p_check.set_defaults(func=cmd_check)

    p_schema = sub.add_parser("schema", help="Print JSON Schema for a brandspec spec type")
    p_schema.add_argument(
        "engine",
        choices=sorted(SCHEMA_MODELS),
        help="Spec engine name",
    )
    p_schema.set_defaults(func=cmd_schema)

    p_skill = sub.add_parser("install-skill", help="Install the bundled SKILL.md for an agent host")
    p_skill.add_argument(
        "--target",
        default="agents",
        help="Preset (agents, project, claude, cursor, codex, antigravity) or custom path",
    )
    p_skill.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing SKILL.md at the target location",
    )
    p_skill.set_defaults(func=cmd_install_skill)

    p_review = sub.add_parser("review", help="Start localhost visual review studio")
    p_review.add_argument("--dir", required=True, help="Compiled build or sweep directory")
    p_review.add_argument("--port", type=int, default=0, help="TCP port (0 for ephemeral)")
    p_review.add_argument("--open", action="store_true", help="Open browser automatically")
    p_review.add_argument(
        "--wait",
        action="store_true",
        help="Block until POST /api/review submits feedback and print JSON",
    )
    p_review.add_argument(
        "--timeout",
        type=int,
        default=900,
        help="Timeout in seconds for --wait mode (default 900)",
    )
    p_review.set_defaults(func=cmd_review)

    p_serve = sub.add_parser("serve", help="Serve compiled artifacts in localhost studio")
    p_serve.add_argument("--dir", required=True, help="Compiled build or sweep directory")
    p_serve.add_argument("--port", type=int, default=8420, help="TCP port (default 8420)")
    p_serve.add_argument("--open", action="store_true", help="Open browser automatically")
    p_serve.set_defaults(func=cmd_serve)

    p_sweep = sub.add_parser("sweep", help="Compile a bounded parameter sweep matrix")
    p_sweep.add_argument("spec", help="Base mark spec.json path")
    p_sweep.add_argument(
        "--set",
        action="append",
        default=[],
        help="Parameter axis path=v1,v2,... (repeatable, up to 3 axes)",
    )
    p_sweep.add_argument("--sweep", help="Optional sweep.json manifest path")
    p_sweep.add_argument("--out-dir", help="Output gallery directory")
    p_sweep.add_argument(
        "--max-variants",
        type=int,
        default=None,
        help="Maximum combinations allowed (default 24, max 64)",
    )
    p_sweep.add_argument(
        "--only-passed",
        action="store_true",
        help="Emit candidate subdirectories only for variants passing metrics",
    )
    p_sweep.add_argument(
        "--review",
        action="store_true",
        help="Launch brandspec review --wait on the generated gallery",
    )
    p_sweep.set_defaults(func=cmd_sweep)

    p_tokens = sub.add_parser("tokens", help="Validate and audit design token specifications")
    tokens_sub = p_tokens.add_subparsers(dest="tokens_command", required=True)
    p_tokens_check = tokens_sub.add_parser("check", help="Run WCAG 2.1 and APCA contrast audit")
    p_tokens_check.add_argument("spec", help="Path to tokens.spec.json")
    p_tokens_check.set_defaults(func=cmd_tokens_check)

    p_palette = sub.add_parser("palette", help="Extract deterministic color tokens from images")
    palette_sub = p_palette.add_subparsers(dest="palette_command", required=True)
    p_palette_ext = palette_sub.add_parser("extract", help="Extract palette tokens from image")
    p_palette_ext.add_argument("image", help="Path to reference image")
    p_palette_ext.add_argument("--colors", type=int, default=6, help="Palette color count (2-16)")
    p_palette_ext.add_argument("--out", help="Destination tokens.spec.json path")
    p_palette_ext.set_defaults(func=cmd_palette_extract)

    p_kit = sub.add_parser("kit", help="Export multi-format SVG, icon, and OG brand kits")
    kit_sub = p_kit.add_subparsers(dest="kit_command", required=True)
    p_kit_build = kit_sub.add_parser("build", help="Compile kit.spec.json into production assets")
    p_kit_build.add_argument("spec", help="Path to kit.spec.json")
    p_kit_build.add_argument("--out-dir", help="Output directory")
    p_kit_build.set_defaults(func=cmd_kit_build)

    p_wordmark = sub.add_parser("wordmark", help="Compile outlined vector wordmarks")
    wm_sub = p_wordmark.add_subparsers(dest="wordmark_command", required=True)
    p_wm_build = wm_sub.add_parser("build", help="Compile wordmark.spec.json to pure SVG paths")
    p_wm_build.add_argument("spec", help="Path to wordmark.spec.json")
    p_wm_build.add_argument("--out-dir", help="Output directory")
    p_wm_build.set_defaults(func=cmd_wordmark_build)
    p_wm_fonts = wm_sub.add_parser("fonts", help="List available .ttf and .otf system fonts")
    p_wm_fonts.add_argument("--query", help="Case-insensitive substring filter")
    p_wm_fonts.add_argument("--json", action="store_true", help="Output paths as a JSON array")
    p_wm_fonts.set_defaults(func=cmd_wordmark_fonts)

    p_lockup = sub.add_parser("lockup", help="Compose mark and wordmark lockups")
    lockup_sub = p_lockup.add_subparsers(dest="lockup_command", required=True)
    p_lockup_build = lockup_sub.add_parser("build", help="Compile lockup.spec.json with clearspace")
    p_lockup_build.add_argument("spec", help="Path to lockup.spec.json")
    p_lockup_build.add_argument("--out-dir", help="Output directory")
    p_lockup_build.set_defaults(func=cmd_lockup_build)

    p_icons = sub.add_parser("icons", help="Compile matched 24x24 icon sets")
    icons_sub = p_icons.add_subparsers(dest="icons_command", required=True)
    p_icons_build = icons_sub.add_parser("build", help="Compile icons.spec.json into SVGs and sheet")
    p_icons_build.add_argument("spec", help="Path to icons.spec.json")
    p_icons_build.add_argument("--out-dir", help="Output directory")
    p_icons_build.set_defaults(func=cmd_icons_build)

    p_pattern = sub.add_parser("pattern", help="Compile seamless tiling SVG patterns")
    pat_sub = p_pattern.add_subparsers(dest="pattern_command", required=True)
    p_pat_build = pat_sub.add_parser("build", help="Compile pattern.spec.json into tile and pattern SVGs")
    p_pat_build.add_argument("spec", help="Path to pattern.spec.json")
    p_pat_build.add_argument("--out-dir", help="Output directory")
    p_pat_build.set_defaults(func=cmd_pattern_build)

    p_mockup = sub.add_parser("mockup", help="Render brand marks onto perspective mockup scenes")
    mockup_sub = p_mockup.add_subparsers(dest="mockup_command", required=True)
    p_mockup_list = mockup_sub.add_parser("list", help="List available mockup scene templates")
    p_mockup_list.set_defaults(func=cmd_mockup_list)
    p_mockup_build = mockup_sub.add_parser("build", help="Composite mark onto mockup templates")
    p_mockup_build.add_argument("target", help="Compiled out dir, logo.svg, or mark spec.json")
    p_mockup_build.add_argument("--tokens", help="Optional tokens.spec.json path")
    p_mockup_build.add_argument("--brand-name", help="Brand display name for layouts")
    p_mockup_build.add_argument("--headline", help="Primary billboard/banner headline")
    p_mockup_build.add_argument("--tagline", help="Secondary tagline")
    p_mockup_build.add_argument("--website", help="Display website URL")
    p_mockup_build.add_argument("--accent", help="Accent hex color (#RRGGBB)")
    p_mockup_build.add_argument("--templates", help="Comma-separated template IDs to render")
    p_mockup_build.add_argument("--out-dir", help="Output directory")
    p_mockup_build.set_defaults(func=cmd_mockup_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
