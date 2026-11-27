"""Tests for deterministic perspective mockup rendering, CLI, and Studio API."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
import threading
import urllib.request

from PIL import Image

from brandspec.cli import main
from brandspec.engines.mockup import MockupContext, discover_templates, render_all_mockups
from brandspec.studio.server import create_studio_server

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))


def _http_json(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_discover_builtin_mockup_templates() -> None:
    templates = discover_templates()
    ids = {manifest.id for _dir, manifest in templates}
    assert {
        "highway-billboard",
        "fence-billboard",
        "concourse-lightbox",
        "pole-banner",
        "stacked-cards",
        "concrete-card",
        "mailer-box",
        "matte-phone",
        "street-hoarding",
    }.issubset(ids)


def test_cli_mockup_list_and_build(tmp_path: Path) -> None:
    assert main(["mockup", "list"]) == 0

    build_dir = tmp_path / "mark"
    assert (
        main(["build", str(ARCHETYPES_DIR / "ribbon-weave.json"), "--out-dir", str(build_dir)])
        == 0
    )

    mockups_dir = tmp_path / "mockups-out"
    assert (
        main(
            [
                "mockup",
                "build",
                str(build_dir),
                "--brand-name",
                "Kinetix",
                "--headline",
                "Motion without friction.",
                "--accent",
                "#0f766e",
                "--templates",
                "stacked-cards,street-hoarding,matte-phone",
                "--out-dir",
                str(mockups_dir),
            ]
        )
        == 0
    )

    for tid in ("stacked-cards", "street-hoarding", "matte-phone"):
        out_img = mockups_dir / f"{tid}.jpg"
        assert out_img.is_file()
        with Image.open(out_img) as im:
            assert im.size[0] >= 1200

    index = json.loads((mockups_dir / "mockups.json").read_text(encoding="utf-8"))
    assert len(index) == 3


def test_studio_mockup_render_and_serving(tmp_path: Path) -> None:
    build_dir = tmp_path / "studio-mark"
    assert (
        main(["build", str(ARCHETYPES_DIR / "iso-impossible.json"), "--out-dir", str(build_dir)])
        == 0
    )

    server, _ = create_studio_server(build_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, session = _http_json(f"http://127.0.0.1:{port}/api/session")
        assert status == 200
        assert session["has_mockup_templates"] is True

        r_status, r_body = _http_json(
            f"http://127.0.0.1:{port}/api/mockups/render",
            method="POST",
            payload={
                "candidate_id": "default",
                "brand_name": "Vela",
                "headline": "Built for open water.",
                "website": "vela.studio",
                "accent": "#1d4ed8",
            },
        )
        assert r_status == 200
        assert len(r_body["mockups"]) >= 9
        first_url = r_body["mockups"][0]["url"]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{first_url}", timeout=10) as resp:
            assert resp.status == 200
            assert resp.headers.get("Content-Type") == "image/jpeg"
            assert len(resp.read()) > 10_000
    finally:
        server.shutdown()
        server.server_close()


def test_render_all_mockups_deterministic_with_gradient_mark(tmp_path: Path) -> None:
    svg_grad = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">'
        '<defs><linearGradient id="brand-fill" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#2563eb"/><stop offset="100%" stop-color="#06b6d4"/>'
        "</linearGradient></defs>"
        '<path d="M 200 200 L 800 200 L 800 800 L 200 800 Z" fill="url(#brand-fill)"/>'
        "</svg>"
    )
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    ctx = MockupContext(brand_name="Prism", accent="#2563eb")
    render_all_mockups(svg_grad, out1, ctx=ctx, only_ids={"concrete-card"})
    render_all_mockups(svg_grad, out2, ctx=ctx, only_ids={"concrete-card"})
    assert (out1 / "concrete-card.jpg").read_bytes() == (out2 / "concrete-card.jpg").read_bytes()
