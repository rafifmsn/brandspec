"""Tests for BrandSpec Studio HTTP server, inverse grid math, and --wait flow."""

from __future__ import annotations

from importlib import resources
import json
import math
from pathlib import Path
import threading
import urllib.error
import urllib.request

from brandspec.cli import main, run_studio_server
from brandspec.core.grid import GridSpec, canvas_to_grid, grid_to_xy, xy_to_grid
from brandspec.studio.server import create_studio_server

ARCHETYPES_DIR = Path(str(resources.files("brandspec").joinpath("engines/mark/archetypes")))


def _http_json(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def _http_status(url: str) -> int:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_session_discovers_single_and_multi_candidate_dirs(tmp_path: Path) -> None:
    single_dir = tmp_path / "single"
    assert (
        main(
            [
                "build",
                str(ARCHETYPES_DIR / "ribbon-weave.json"),
                "--out-dir",
                str(single_dir),
            ]
        )
        == 0
    )
    assert (single_dir / "meta.json").is_file()

    server, _ = create_studio_server(single_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, session = _http_json(f"http://127.0.0.1:{port}/api/session")
        assert status == 200
        assert len(session["candidates"]) == 1
        assert session["candidates"][0]["id"] == "default"
        assert session["candidates"][0]["meta"]["unit"] == 40.0
        assert _http_status(f"http://127.0.0.1:{port}/api/candidates/default/overlay.svg") == 200
        assert _http_status(f"http://127.0.0.1:{port}/") == 200
        assert _http_status(f"http://127.0.0.1:{port}/assets/studio.css") == 200
        assert _http_status(f"http://127.0.0.1:{port}/assets/studio.js") == 200

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as resp:
            html_text = resp.read().decode("utf-8")
        assert "<title>Brandspec</title>" in html_text
        assert "Brandspec</span>" in html_text

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/studio.css", timeout=5) as resp:
            css_text = resp.read().decode("utf-8")
        assert "monospace" not in css_text.lower()
        assert "tabular-nums" in css_text
        assert "flex-wrap: nowrap" in css_text

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/assets/studio.js", timeout=5) as resp:
            js_text = resp.read().decode("utf-8")
        assert "renumberPins" in js_text
        assert "nextPinId" not in js_text
        assert "isAwaitingAgent" in js_text
        assert session["awaiting_agent"] is False
    finally:
        server.shutdown()
        server.server_close()

    multi_dir = tmp_path / "multi"
    assert (
        main(["build", str(ARCHETYPES_DIR / "ribbon-weave.json"), "--out-dir", str(multi_dir / "01")])
        == 0
    )
    assert (
        main(["build", str(ARCHETYPES_DIR / "radial-vortex.json"), "--out-dir", str(multi_dir / "02")])
        == 0
    )
    server, _ = create_studio_server(multi_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, session = _http_json(f"http://127.0.0.1:{port}/api/session")
        assert status == 200
        assert [c["id"] for c in session["candidates"]] == ["01", "02"]
    finally:
        server.shutdown()
        server.server_close()


def test_post_review_writes_json_and_unblocks_wait(tmp_path: Path) -> None:
    build_dir = tmp_path / "mark"
    assert (
        main(["build", str(ARCHETYPES_DIR / "ribbon-weave.json"), "--out-dir", str(build_dir)]) == 0
    )

    def submit_when_ready(url: str, _state) -> None:
        def _post() -> None:
            status, body = _http_json(
                f"{url}api/review",
                method="POST",
                payload={
                    "status": "revise",
                    "selected_candidate": "default",
                    "summary": "Widen crossing gap",
                    "pins": [
                        {
                            "id": 1,
                            "candidate_id": "default",
                            "x_grid": -1.5,
                            "y_grid": 0.25,
                            "comment": "Increase halo to 0.45",
                        }
                    ],
                },
            )
            assert status == 200
            assert body["round"] == 1

        threading.Thread(target=_post, daemon=True).start()

    rc1 = run_studio_server(
        target_dir=build_dir,
        port=0,
        open_browser=False,
        wait=True,
        timeout=10,
        on_ready=submit_when_ready,
    )
    assert rc1 == 0
    review_v1 = json.loads((build_dir / "review.json").read_text(encoding="utf-8"))
    assert review_v1["round"] == 1
    assert review_v1["status"] == "revise"
    assert review_v1["pins"][0]["x_grid"] == -1.5

    def submit_round_two(url: str, _state) -> None:
        def _post() -> None:
            status, sess = _http_json(f"{url}api/session")
            assert status == 200
            assert sess["round"] == 2
            assert sess["latest_review"]["round"] == 1
            assert len(sess["round_groups"]) == 1
            assert sess["round_groups"][0]["round"] == 1
            assert sess["round_groups"][0]["candidates"][0]["id"] == "round-1/default"
            assert (
                _http_status(f"{url}api/rounds/round-1/default/logo.svg") == 200
            )
            assert (
                _http_status(f"{url}api/rounds/round-1/default/../secret.txt") in (403, 404)
            )

            status, body = _http_json(
                f"{url}api/review",
                method="POST",
                payload={
                    "status": "approve",
                    "selected_candidate": "default",
                    "summary": "Looks clean",
                    "pins": [],
                },
            )
            assert status == 200
            assert body["round"] == 2

        threading.Thread(target=_post, daemon=True).start()

    rc2 = run_studio_server(
        target_dir=build_dir,
        port=0,
        open_browser=False,
        wait=True,
        timeout=10,
        on_ready=submit_round_two,
    )
    assert rc2 == 0
    assert (build_dir / "review.round-1.json").is_file()
    review_v2 = json.loads((build_dir / "review.json").read_text(encoding="utf-8"))
    assert review_v2["round"] == 2
    assert review_v2["status"] == "approve"


def test_path_traversal_rejected_and_timeout_and_port_conflict(tmp_path: Path) -> None:
    build_dir = tmp_path / "mark"
    assert (
        main(["build", str(ARCHETYPES_DIR / "ribbon-weave.json"), "--out-dir", str(build_dir)]) == 0
    )
    (tmp_path / "secret.txt").write_text("do-not-leak", encoding="utf-8")

    server, _ = create_studio_server(build_dir, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        for bad in (
            "/api/candidates/default/../secret.txt",
            "/api/candidates/default/%2e%2e/secret.txt",
            "/api/candidates/..%2f/secret.txt",
            "/assets/../server.py",
        ):
            assert _http_status(f"http://127.0.0.1:{port}{bad}") in (403, 404)

        conflict_rc = run_studio_server(
            target_dir=build_dir,
            port=port,
            open_browser=False,
            wait=False,
            timeout=1,
        )
        assert conflict_rc == 1
    finally:
        server.shutdown()
        server.server_close()

    prior_review = {"schemaVersion": 1, "round": 1, "status": "revise", "pins": []}
    (build_dir / "review.json").write_text(json.dumps(prior_review), encoding="utf-8")
    timeout_rc = run_studio_server(
        target_dir=build_dir,
        port=0,
        open_browser=False,
        wait=True,
        timeout=1,
    )
    assert timeout_rc == 3
    assert json.loads((build_dir / "review.json").read_text(encoding="utf-8")) == prior_review


def test_inverse_grid_math_roundtrip() -> None:
    unit = 40.0
    affine = (2.5, 0.0, 0.0, 2.5, 500.0, 500.0)

    for grid_type, pt in (
        ("square", (-2.25, 1.75)),
        ("isometric", (1.5, -2.0)),
        ("polar", (2.4, 135.0)),
    ):
        grid = GridSpec(type=grid_type, divisions=8)
        x, y = grid_to_xy(pt, grid, unit)
        inv_a, inv_b = xy_to_grid((x, y), grid, unit)
        assert math.isclose(inv_a, pt[0], abs_tol=1e-3)
        assert math.isclose(inv_b, pt[1], abs_tol=1e-3)

        px = x * affine[0] + affine[4]
        py = y * affine[3] + affine[5]
        c_a, c_b = canvas_to_grid(px, py, affine, grid, unit)
        assert math.isclose(c_a, pt[0], abs_tol=1e-3)
        assert math.isclose(c_b, pt[1], abs_tol=1e-3)
