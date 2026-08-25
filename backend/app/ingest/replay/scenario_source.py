"""Reads a scenario JSON file and replays it on a ScenarioClock (BUILD_PLAN.md task 0.9).

This is what powers "Run Case Study": every value in every yielded frame is exactly what's on
disk in the scenario file, merged with that frame's `defaults` — nothing here is randomised,
interpolated, or otherwise invented (CLAUDE.md rule 13, determinism).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from app.core.clock import ScenarioClock
from app.schemas.ingest import CellObservation, ObservationFrame
from app.schemas.scenario import ScenarioFile

REQUIRED_NUMERIC_FIELDS = (
    "rain_1h",
    "rain_6h",
    "rain_24h",
    "rain_72h",
    "antecedent_7d",
    "antecedent_15d",
    "antecedent_30d",
)


def load_scenario(path: str | Path) -> ScenarioFile:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioFile.model_validate(data)


def build_scenario_clock(scenario: ScenarioFile) -> ScenarioClock:
    return ScenarioClock(
        start=scenario.clock.start,
        end=scenario.clock.end,
        speed_factor=scenario.clock.default_speed_factor,
    )


def _frame_provenance(scenario: ScenarioFile) -> dict[str, str]:
    """ObservationFrame.provenance is `dict[str, str]` (Appendix A) — a compact per-frame stamp.

    Scenario-level provenance (Appendix B, `schemas.scenario.ProvenanceBlock`) carries richer
    structure (e.g. a list of sources), which wouldn't validate as dict[str, str]. We flatten just
    the parts worth repeating on every frame; the full block belongs on a scenario-metadata
    endpoint (`GET /api/scenarios`), not on every single frame.
    """
    raw = scenario.provenance
    return {
        "scenario_id": scenario.id,
        "confidence": raw.confidence,
        "disclaimer": raw.disclaimer,
    }


def _merged_cell_observation(
    cell_entry: dict[str, object],
    defaults: dict[str, object],
    *,
    scenario_id: str,
    frame_t: object,
) -> CellObservation:
    cell_id = cell_entry.get("cell_id")
    if not cell_id:
        raise ValueError(f"scenario {scenario_id!r} frame {frame_t}: cell entry missing cell_id")

    merged: dict[str, object] = {
        **defaults,
        **{k: v for k, v in cell_entry.items() if k != "cell_id"},
    }

    missing = [f for f in REQUIRED_NUMERIC_FIELDS if f not in merged]
    if missing:
        raise ValueError(
            f"scenario {scenario_id!r} frame {frame_t} cell {cell_id!r}: missing required "
            f"field(s) {missing} (not present in the cell entry or the frame's defaults)"
        )

    return CellObservation(
        cell_id=str(cell_id),
        rain_1h=merged["rain_1h"],
        rain_6h=merged["rain_6h"],
        rain_24h=merged["rain_24h"],
        rain_72h=merged["rain_72h"],
        antecedent_7d=merged["antecedent_7d"],
        antecedent_15d=merged["antecedent_15d"],
        antecedent_30d=merged["antecedent_30d"],
        soil_moisture=merged.get("soil_moisture"),
        insar_velocity_mm_yr=merged.get("insar_velocity_mm_yr"),
        source=f"scenario:{scenario_id}",
        is_reconstructed=True,
    )


class ScenarioSource:
    """DataSource implementation that replays a ScenarioFile on a ScenarioClock.

    `realtime=True` (default) sleeps between frames scaled by `clock.speed_factor`, so a browser
    watching this animate sees it unfold the way a judge would. `realtime=False` advances the
    clock and yields as fast as possible — used by tests and the determinism check (BUILD_PLAN.md
    task 4.11), where wall-clock pacing would only slow things down without proving anything.
    """

    def __init__(self, scenario: ScenarioFile, clock: ScenarioClock, *, realtime: bool = True):
        self.scenario = scenario
        self.clock = clock
        self.realtime = realtime
        self._provenance = _frame_provenance(scenario)

    async def frames(self) -> AsyncIterator[ObservationFrame]:
        for frame in self.scenario.frames:
            if self.realtime:
                real_seconds = (frame.t - self.clock.now()).total_seconds() / self.clock.speed_factor
                if real_seconds > 0:
                    await asyncio.sleep(real_seconds)

            self.clock.advance(to=frame.t)

            cells = [
                _merged_cell_observation(
                    cell_entry, frame.defaults, scenario_id=self.scenario.id, frame_t=frame.t
                )
                for cell_entry in frame.cells
            ]
            yield ObservationFrame(
                t=frame.t,
                aoi_id=self.scenario.aoi_id,
                cells=cells,
                provenance=self._provenance,
            )
