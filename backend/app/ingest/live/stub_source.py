"""Phase 0 stub LIVE-mode source (BUILD_PLAN.md task 0.9). Fabricated numbers, clearly labelled.

Real adapters (imd.py, imerg.py, smap.py, insar.py) land in Phase 1B (BUILD_PLAN.md §1B) and
replace this. Until then this is what `ingest/` instantiates when ModeState.mode is LIVE.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.core.clock import Clock
from app.schemas.ingest import CellObservation, ObservationFrame

STUB_CELL_IDS = [
    "aizawl_012_001",
    "aizawl_039_050",
    "aizawl_044_048",
    "aizawl_040_026",
    "aizawl_022_001",
    "aizawl_003_024",
    "aizawl_026_040",
    "aizawl_029_040",
    "aizawl_054_046",
]


class StubLiveSource:
    """Emits one fabricated frame every `interval_seconds` of real (wall) time.

    Values are fixed, not random (CLAUDE.md rule 13 — no unseeded randomness). Every observation
    is labelled `source="stub:live"`, `is_reconstructed=False` so nothing downstream can mistake
    it for a measurement.
    """

    def __init__(self, clock: Clock, *, aoi_id: str = "aizawl", interval_seconds: float = 30.0):
        if not clock.is_live:
            raise ValueError("StubLiveSource requires a live Clock (got a non-live one)")
        self._clock = clock
        self._aoi_id = aoi_id
        self._interval_seconds = interval_seconds

    async def frames(self) -> AsyncIterator[ObservationFrame]:
        while True:
            t = self._clock.now()
            cells = [
                CellObservation(
                    cell_id=cell_id,
                    rain_1h=0.4,
                    rain_6h=1.2,
                    rain_24h=4.0,
                    rain_72h=9.0,
                    antecedent_7d=20.0,
                    antecedent_15d=45.0,
                    antecedent_30d=90.0,
                    soil_moisture=0.28,
                    insar_velocity_mm_yr=None,
                    source="stub:live",
                    is_reconstructed=False,
                )
                for cell_id in STUB_CELL_IDS
            ]
            yield ObservationFrame(
                t=t,
                aoi_id=self._aoi_id,
                cells=cells,
                provenance={
                    "confidence": "fabricated",
                    "note": "Deterministic local LIVE stub; not a measured weather feed",
                },
            )
            await asyncio.sleep(self._interval_seconds)
