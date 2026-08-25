"""The scenario file contract (BUILD_PLAN.md Appendix B, finalized by task 4.1).

Phase 0 (`_smoke.json`) only ever needed `id`, `aoi_id`, `held_out_of_training`, `provenance`,
`clock`, and `frames` to drive a replay — that subset is still exactly what
`ingest/replay/scenario_source.py` reads to run the pipeline. This task adds the rest of
Appendix B (`name`, `event_date`, `hazard_type`, `trigger`, `ground_truth`, `narration`) so a real
case-study file (aizawl-2024, wayanad-2024, tupul-2022) can carry the facts the Counterfactual
Lead-Time Scorecard (Phase 4 task 4.10) and the scenario-picker cards (task 4.8) need.

Backward compatibility with `_smoke.json` (which predates all of the above and MUST NOT be
edited, per this session's instructions) is why the new fields are optional at the schema level —
but `_real_events_carry_full_metadata` below then makes them mandatory the moment
`held_out_of_training` is True, which is every *real* scenario. `_smoke.json` sets
`held_out_of_training: false` precisely because it is fabricated, not a real event — so it is
exempt from that stricter rule without needing any change to the file itself.
"""
from __future__ import annotations

from datetime import date, datetime

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


class ProvenanceBlock(BaseModel):
    """Appendix B's `provenance` block. CLAUDE.md rules 2/3: every real scenario's `confidence`
    must be `"reconstructed"` (never presented as archived observation), with a `method` that
    names the actual technique used (see scripts/build_scenario.py for task 4.2's storm-profile
    disaggregation), real `sources`, and a `disclaimer` fit to show a judge on screen.
    `_smoke.json` uses `confidence: "fabricated"` instead — that is the one legitimate exception,
    since it is not a reconstruction of anything real.
    """

    confidence: str
    method: str
    sources: list[str] = Field(default_factory=list)
    disclaimer: str


class ScenarioFrame(BaseModel):
    t: datetime
    # Each entry is {"cell_id": "...", <numeric field overrides>}. Kept loosely typed here —
    # app.ingest.replay.scenario_source merges these with `defaults` and constructs a validated
    # CellObservation per cell, which is where the real enforcement happens.
    cells: list[dict[str, object]] = Field(default_factory=list)
    defaults: dict[str, object] = Field(default_factory=dict)


class GroundTruthFailure(BaseModel):
    t: datetime
    # Optional, NOT a schema default-to-zero: Appendix B's worked example has a real cited
    # coordinate for Aizawl's Melthum-Hlimen quarry collapse (23.70, 92.71), but docs/reference/
    # does not cite a precise point coordinate for every event (e.g. Wayanad's Mundakkai/
    # Chooralmala/Puthumala, or Tupul/Noney). CLAUDE.md: never invent a coordinate — so this is
    # None (and TODO(verify) noted in `note`) rather than a plausible-looking placeholder lat/lon.
    lat: float | None = None
    lon: float | None = None
    note: str
    # Free text, not int — CLAUDE.md rule: never assert a single invented death-toll figure.
    # "multiple", "27-34 (state total)", etc. are all legitimate values; a bare `27` is not,
    # unless a cited source actually gives that exact number for that specific failure.
    deaths_attributed: str


class GroundTruthRoadEvent(BaseModel):
    t: datetime
    road: str
    location: str
    effect: str
    consequence: str


class GroundTruthWarning(BaseModel):
    t: datetime
    issuer: str
    level: str
    spatial_scale: str
    note: str


class GroundTruthOutcome(BaseModel):
    # Always a string, never int — this is what lets Wayanad's "200-400+" survive as a range
    # instead of being silently coerced to one fabricated number (CLAUDE.md honesty rules).
    deaths: str
    source_note: str


class GroundTruth(BaseModel):
    failures: list[GroundTruthFailure] = Field(default_factory=list)
    road_events: list[GroundTruthRoadEvent] = Field(default_factory=list)
    official_warnings: list[GroundTruthWarning] = Field(default_factory=list)
    outcome: GroundTruthOutcome


class NarrationEntry(BaseModel):
    t: datetime
    text: str


class ScenarioFile(BaseModel):
    id: str
    aoi_id: str
    held_out_of_training: bool
    provenance: ProvenanceBlock
    clock: ScenarioClockConfig
    frames: list[ScenarioFrame]

    # Appendix B fields beyond Phase 0's minimal subset — optional so `_smoke.json` keeps
    # validating unmodified; required for any real (held-out) scenario, see the validator below.
    name: str | None = None
    event_date: date | None = None
    hazard_type: str | None = None
    trigger: str | None = None
    ground_truth: GroundTruth | None = None
    narration: list[NarrationEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_frames(self) -> "ScenarioFile":
        if not self.frames:
            raise ValueError(f"scenario {self.id!r} has no frames")
        return self

    @model_validator(mode="after")
    def _real_events_carry_full_metadata(self) -> "ScenarioFile":
        """`held_out_of_training: true` is the on-screen "held out of training" badge's source of
        truth (CLAUDE.md rule 2) — a scenario that claims that badge must actually be a
        documented real event, not a half-filled fixture. `_smoke.json` sets this False, so it
        never has to satisfy this rule.
        """
        if not self.held_out_of_training:
            return self

        missing = [
            field
            for field in ("name", "event_date", "hazard_type", "trigger")
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(
                f"scenario {self.id!r} has held_out_of_training=true (a real event) but is "
                f"missing required field(s) {missing}"
            )
        if self.ground_truth is None:
            raise ValueError(
                f"scenario {self.id!r} has held_out_of_training=true (a real event) but has no "
                "ground_truth block — required for the Counterfactual Lead-Time Scorecard"
            )
        return self
