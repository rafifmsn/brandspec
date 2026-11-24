"""CLI entrypoint for logo-mod."""

from __future__ import annotations

import argparse
from importlib import resources
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .compiler import compile_spec
from .inspect import analyze_compiled, render_inspection_sheet
from .schema import LogoSpec


def _find_archetypes_dir() -> Path:
    pkg_dir = Path(str(resources.files("logo_mod").joinpath("archetypes")))
    if pkg_dir.is_dir():
        return pkg_dir
    cwd_dir = Path.cwd() / "archetypes"
    if cwd_dir.is_dir():
        return cwd_dir
    raise FileNotFoundError("Could not locate archetypes directory.")


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


def _load_spec(spec_path: Path) -> LogoSpec:
    raw = json.loads(spec_path.read_text(encoding="utf-8"))
    return LogoSpec.model_validate(raw)


def cmd_build(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    try:
        spec = _load_spec(spec_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Spec error: {exc}", file=sys.stderr)
        return 1

    compiled = compile_spec(spec)
    metrics = analyze_compiled(compiled)
    sheet = render_inspection_sheet(compiled)

    out_dir = Path(args.out_dir) if args.out_dir else spec_path.parent / "out" / spec_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    svg_file = out_dir / "logo.svg"
    sheet_file = out_dir / "sheet.png"
    metrics_file = out_dir / "metrics.json"
    locked_spec = out_dir / "spec.json"

    svg_file.write_text(compiled.svg_markup, encoding="utf-8")
    sheet.save(sheet_file, format="PNG")
    metrics_file.write_text(json.dumps(metrics.to_dict(), indent=2) + "\n", encoding="utf-8")
    locked_spec.write_text(
        json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "svg": str(svg_file),
                "sheet": str(sheet_file),
                "metrics": str(metrics_file),
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="logo-mod",
        description="Deterministic Logo Modernism vector compiler and inspection CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_arch = sub.add_parser("archetypes", help="List available Logo Modernism starter archetypes")
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
