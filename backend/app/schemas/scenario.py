"""Minimal Phase 0 subset of the scenario file contract (BUILD_PLAN.md Appendix B).

Only the fields ingest/replay/scenario_source.py actually needs to drive a replay. Appendix B
also defines `ground_truth` and `narration` (used by the Phase 4 Counterfactual Scorecard and
on-screen captions) — those are intentionally NOT modelled here yet; task 4.1 finalizes the full
schema and a validator script. Do not extend this file speculatively ahead of that task.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class ScenarioClockConfig(BaseModel):
    start: datetime
    end: datetime
    frame_interval_minutes: int = Field(gt=0)
    default_speed_factor: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "ScenarioClockConfig":
        if self.end < self.start:
            raise ValueError(f"clock.end ({self.end}) is before clock.start ({self.start})")
        return self


class ScenarioFrame(BaseModel):
    t: datetime
    # Each entry is {"cell_id": "...", <numeric field overrides>}. Kept loosely typed here —
    # app.ingest.replay.scenario_source merges these with `defaults` and constructs a validated
    # CellObservation per cell, which is where the real enforcement happens.
    cells: list[dict[str, object]] = Field(default_factory=list)
    defaults: dict[str, object] = Field(default_factory=dict)


class ScenarioFile(BaseModel):
    id: str
    aoi_id: str
    held_out_of_training: bool
    provenance: dict[str, object]
    clock: ScenarioClockConfig
    frames: list[ScenarioFrame]

    @model_validator(mode="after")
    def _has_frames(self) -> "ScenarioFile":
        if not self.frames:
            raise ValueError(f"scenario {self.id!r} has no frames")
        return self
