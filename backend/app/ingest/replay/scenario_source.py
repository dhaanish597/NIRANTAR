"""Reads a scenario JSON file and replays it on a ScenarioClock (BUILD_PLAN.md task 0.9).

This is what powers "Run Case Study": every value in every yielded frame is exactly what's on
disk in the scenario file, merged with that frame's `defaults` — nothing here is randomised,
interpolated, or otherwise invented (CLAUDE.md rule 13, determinism).
"""
from __future__ import annotations

import asyncio
import bisect
import json
from datetime import datetime
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


def _nearest_frame_index(frames: list, to: datetime) -> int:
    """Index of the first frame at-or-after `to` (bisect on the sorted frame timestamps
    `scripts/validate_scenario.py` already requires); clamped to the last frame if `to` is past
    the scenario's final frame."""
    times = [f.t for f in frames]
    index = bisect.bisect_left(times, to)
    return min(index, len(frames) - 1)


class ScenarioSource:
    """DataSource implementation that replays a ScenarioFile on a ScenarioClock.

    `realtime=True` (default) sleeps between frames scaled by `clock.speed_factor`, so a browser
    watching this animate sees it unfold the way a judge would. `realtime=False` advances the
    clock and yields as fast as possible — used by tests and the determinism check (BUILD_PLAN.md
    task 4.11), where wall-clock pacing would only slow things down without proving anything.

    Replay controls (BUILD_PLAN.md task 4.7 — pause / resume / speed / scrub to timestamp /
    restart), all safe to call from another task/coroutine while `frames()` is actively iterating:

    - `pause()` / `resume()`: `frames()` blocks (via an `asyncio.Event`) before yielding the next
      frame while paused, without ending iteration — the caller's `async for` just stalls, ready
      to continue the instant `resume()` is called.
    - `set_speed(x)`: mutates `self.clock.speed_factor` directly. `frames()` re-reads
      `clock.speed_factor` fresh on every iteration (not once at construction), so a change takes
      effect on the very next frame's pacing — no restart needed.
    - `seek(to)`: schedules a jump to the frame at-or-after `to`. Consumed by `frames()` just
      before it processes the next frame (so a seek issued mid-iteration takes effect on the very
      next step, forward OR backward), via `clock.seek()` (not `advance()`, which forbids moving
      backward — the right guard for ordinary playback, but wrong for scrubbing).
    - `restart()`: resets the clock to `start` (`ScenarioClock.reset()`), the frame pointer to 0,
      clears any pending seek, and un-pauses. Fully resets THIS object's iteration state so a
      fresh call to `frames()` replays from the very beginning with no residue from the previous
      run — proven byte-identical to a from-scratch `ScenarioSource` in
      `tests/test_ingest_replay.py`. Resetting *downstream* state (the `Pipeline`'s audit hash
      chain) is the caller's job — see `api/state.py`'s `AppState`, which owns the `Pipeline`.
    """

    def __init__(self, scenario: ScenarioFile, clock: ScenarioClock, *, realtime: bool = True):
        self.scenario = scenario
        self.clock = clock
        self.realtime = realtime
        self._provenance = _frame_provenance(scenario)
        self._frame_index = 0
        self._seek_index: int | None = None
        self._paused = asyncio.Event()
        self._paused.set()  # not paused by default

    @property
    def paused(self) -> bool:
        return not self._paused.is_set()

    def pause(self) -> None:
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    def set_speed(self, speed_factor: float) -> None:
        if speed_factor <= 0:
            raise ValueError(f"speed_factor must be > 0, got {speed_factor}")
        self.clock.speed_factor = speed_factor

    def seek(self, to: datetime) -> None:
        """Scrub to the frame at-or-after `to`. Takes effect the next time `frames()` checks for
        a pending seek, i.e. just before it yields its next frame — safe to call concurrently
        while `frames()` is iterating in another task, unlike mutating `_frame_index` directly."""
        self._seek_index = _nearest_frame_index(self.scenario.frames, to)

    def restart(self) -> None:
        """Reset to the very beginning — see the class docstring's `restart()` note."""
        self.clock.reset()
        self._frame_index = 0
        self._seek_index = None
        self._paused.set()

    async def frames(self) -> AsyncIterator[ObservationFrame]:
        self._frame_index = 0
        while self._frame_index < len(self.scenario.frames):
            await self._paused.wait()

            jumped = False
            if self._seek_index is not None:
                self._frame_index = self._seek_index
                self._seek_index = None
                jumped = True

            frame = self.scenario.frames[self._frame_index]

            if self.realtime:
                real_seconds = (frame.t - self.clock.now()).total_seconds() / self.clock.speed_factor
                if real_seconds > 0:
                    await asyncio.sleep(real_seconds)

            # seek() can jump the clock backward (scrubbing to an earlier point) — advance()
            # forbids that by design (it's the right guard for ordinary forward playback), so a
            # frame reached via a seek uses the unconstrained seek() instead; every other frame
            # still goes through advance()'s "never move backward" invariant.
            if jumped:
                self.clock.seek(frame.t)
            else:
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
            self._frame_index += 1
