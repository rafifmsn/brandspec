"""Deterministic WCAG 2.1 contrast ratio and APCA Lc auditing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .schema import TokensSpec


@dataclass(frozen=True)
class PairContrastResult:
    name: str
    role: str
    fg: str
    bg: str
    wcag_ratio: float
    apca_lc: float
    min_wcag_required: float
    passed: bool


@dataclass(frozen=True)
class ContrastReport:
    passed: bool
    pairs: list[PairContrastResult]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pairs": [asdict(p) for p in self.pairs],
            "warnings": self.warnings,
        }


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    return (
        int(cleaned[0:2], 16),
        int(cleaned[2:4], 16),
        int(cleaned[4:6], 16),
    )


def _linearize_channel(c: int) -> float:
    s = c / 255.0
    if s <= 0.04045:
        return s / 12.92
    return ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance in [0.0, 1.0]."""
    r, g, b = hex_to_rgb(hex_color)
    return (
        0.2126 * _linearize_channel(r)
        + 0.7152 * _linearize_channel(g)
        + 0.0722 * _linearize_channel(b)
    )


def wcag_contrast_ratio(fg: str, bg: str) -> float:
    """Compute WCAG 2.1 contrast ratio between fg and bg hex colors."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


def apca_contrast_lc(fg: str, bg: str) -> float:
    """Compute APCA Lc contrast value (signed) using standard W3 0.0.98G-4g constants."""
    def _y_apca(hex_val: str) -> float:
        r, g, b = hex_to_rgb(hex_val)
        y = (
            0.2126729 * ((r / 255.0) ** 2.4)
            + 0.7151522 * ((g / 255.0) ** 2.4)
            + 0.0721750 * ((b / 255.0) ** 2.4)
        )
        if y < 0.022:
            y += (0.022 - y) ** 1.414
        return y

    y_txt = _y_apca(fg)
    y_bg = _y_apca(bg)
    if abs(y_bg - y_txt) < 0.0005:
        return 0.0

    if y_bg > y_txt:
        sapc = ((y_bg ** 0.56) - (y_txt ** 0.57)) * 1.14
        lc = 0.0 if sapc < 0.1 else (sapc - 0.027) * 100.0
    else:
        sapc = ((y_bg ** 0.65) - (y_txt ** 0.62)) * 1.14
        lc = 0.0 if sapc > -0.1 else (sapc + 0.027) * 100.0
    return round(lc, 1)


def audit_tokens_contrast(spec: TokensSpec) -> ContrastReport:
    """Audit all primary token pairs and declared surface pairs for AA contrast."""
    checks: list[tuple[str, str, str, str]] = [
        ("text_primary_on_canvas", "text", spec.text_primary, spec.bg_canvas),
        ("text_primary_on_surface", "text", spec.text_primary, spec.bg_surface),
        ("text_secondary_on_surface", "text", spec.text_secondary, spec.bg_surface),
        ("mark_dark_on_canvas", "mark", spec.mark_dark, spec.bg_canvas),
        ("mark_light_on_white", "mark", spec.mark_light, "#ffffff"),
    ]
    for name, pair in sorted(spec.surfaces.items()):
        checks.append((f"surface.{name}", pair.role, pair.fg, pair.bg))

    results: list[PairContrastResult] = []
    warnings: list[str] = []
    for name, role, fg, bg in checks:
        min_req = 4.5 if role == "text" else 3.0
        ratio = wcag_contrast_ratio(fg, bg)
        lc = apca_contrast_lc(fg, bg)
        passed = ratio >= min_req
        if not passed:
            warnings.append(
                f"{name} ({fg} on {bg}) WCAG ratio {ratio:.2f} < {min_req:.1f} AA ({role})"
            )
        results.append(
            PairContrastResult(
                name=name,
                role=role,
                fg=fg,
                bg=bg,
                wcag_ratio=ratio,
                apca_lc=lc,
                min_wcag_required=min_req,
                passed=passed,
            )
        )

    return ContrastReport(
        passed=len(warnings) == 0,
        pairs=results,
        warnings=warnings,
    )
