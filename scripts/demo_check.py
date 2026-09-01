#!/usr/bin/env python
"""Deterministic SIH preflight for models, scenarios, data, and replay."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ingest.replay.scenario_source import ScenarioSource, build_scenario_clock, load_scenario
from app.pipeline import Pipeline
from app.schemas.mode import RunMode
from app.risk.model import get_model


def _pass(label: str) -> None:
    print(f"[PASS] {label}")


def _fail(label: str, reason: str) -> None:
    print(f"[FAIL] {label}: {reason}")


def _required_files() -> list[tuple[str, Path]]:
    files = [("model", REPO_ROOT / "data/models/xgb_terrain_v1.json"),
             ("model metadata", REPO_ROOT / "data/models/model_metadata.json")]
    for aoi in ("aizawl", "wayanad", "tupul"):
        files.extend([
            (f"{aoi} DEM", REPO_ROOT / f"data/static/{aoi}/dem.tif"),
            (f"{aoi} cells", REPO_ROOT / f"data/static/{aoi}/cells.gpkg"),
            (f"{aoi} exposure", REPO_ROOT / f"data/static/{aoi}/exposure.gpkg"),
            (f"{aoi} road graph", REPO_ROOT / f"data/osm/{aoi}_graph.pkl"),
            (f"{aoi} offline tiles", REPO_ROOT / f"data/tiles/{aoi}.pmtiles"),
            (f"{aoi} hillshade", REPO_ROOT / f"data/tiles/{aoi}-hillshade.png"),
        ])
    return files


def _scenario_hash(scenario_id: str, ticks: list) -> str:
    payload = [tick.model_dump(mode="json") for tick in ticks]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def _run_frames(scenario_id: str, limit: int | None = None) -> list:
    scenario = load_scenario(REPO_ROOT / f"data/scenarios/{scenario_id}.json")
    source = ScenarioSource(scenario, build_scenario_clock(scenario), realtime=False)
    pipeline = Pipeline()
    ticks = []
    async for frame in source.frames():
        ticks.append(pipeline.process(frame, mode=RunMode.REPLAY, scenario_id=scenario.id))
        if limit is not None and len(ticks) >= limit:
            break
    return ticks


async def main() -> int:
    print("ICONIX DEMO CHECK")
    print("=" * 28)
    failures = 0

    missing = [(label, path) for label, path in _required_files() if not path.is_file() or path.stat().st_size == 0]
    if missing:
        failures += 1
        _fail("required artifacts", "; ".join(f"{label}: {path}" for label, path in missing))
    else:
        _pass("model, scenarios, geographic data, offline map")

    try:
        model = get_model("aizawl")
        metadata = model.metadata
        expected = set(metadata.get("feature_columns", []))
        actual = set(model.terrain_by_cell.columns)
        if expected and expected != actual:
            raise RuntimeError(f"feature schema mismatch: metadata={sorted(expected)} loaded={sorted(actual)}")
    except Exception as exc:
        failures += 1
        _fail("model load/schema", str(exc))
    else:
        _pass("model load/schema")

    try:
        for scenario_id in ("aizawl-2024", "wayanad-2024", "tupul-2022"):
            scenario = load_scenario(REPO_ROOT / f"data/scenarios/{scenario_id}.json")
            if not scenario.frames:
                raise RuntimeError(f"{scenario_id} has no frames")
        _pass("scenario validation")
    except Exception as exc:
        failures += 1
        _fail("scenario validation", str(exc))

    try:
        a = await _run_frames("_smoke")
        b = await _run_frames("_smoke")
        if _scenario_hash("_smoke", a) != _scenario_hash("_smoke", b):
            raise RuntimeError("identical replay hashes differ")
        _pass("deterministic replay")
    except Exception as exc:
        failures += 1
        _fail("deterministic replay", str(exc))

    try:
        smoke = await _run_frames("_smoke")
        if len(smoke) != 10 or not smoke[-1].cell_risks:
            raise RuntimeError(f"expected 10 smoke ticks with risk output, got {len(smoke)}")
        _pass("Aizawl smoke")
    except Exception as exc:
        failures += 1
        _fail("Aizawl smoke", str(exc))

    for scenario_id in ("wayanad-2024", "tupul-2022"):
        try:
            ticks = await _run_frames(scenario_id, limit=1)
            if not ticks or not ticks[0].cell_risks:
                raise RuntimeError("first replay tick has no risk output")
            _pass(f"{scenario_id} smoke")
        except Exception as exc:
            failures += 1
            _fail(f"{scenario_id} smoke", str(exc))

    # Guard the replay code and frontend configuration against accidental external dependencies.
    scan_paths = [REPO_ROOT / "backend/app/ingest/replay", REPO_ROOT / "frontend/src/components/MapView.tsx"]
    forbidden = re.compile(r"https?://(?!127\.0\.0\.1|localhost)")
    hits = []
    for root in scan_paths:
        paths = [root] if root.is_file() else list(root.rglob("*.py"))
        for path in paths:
            for line_no, line in enumerate(path.read_text(encoding="utf-8"), 1):
                if forbidden.search(line):
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")
    if hits:
        failures += 1
        _fail("no replay network dependency", ", ".join(hits))
    else:
        _pass("no replay network dependency")

    if failures:
        print(f"RESULT: NOT READY ({failures} check(s) failed)")
        return 1
    print("RESULT: READY")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
