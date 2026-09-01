"""Contract test for ingest/live/stub_source.py."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import geopandas as gpd
from pathlib import Path

from app.core.clock import LiveClock, ScenarioClock
from app.ingest.base import DataSource
from app.ingest.live.stub_source import STUB_CELL_IDS, StubLiveSource


async def test_stub_live_source_satisfies_data_source_protocol():
    source = StubLiveSource(LiveClock())
    assert isinstance(source, DataSource)


async def test_first_frame_is_immediate_and_labelled_fabricated_live():
    source = StubLiveSource(LiveClock(), interval_seconds=999.0)  # never actually waited on
    gen = source.frames()
    frame = await gen.__anext__()  # first item only — yielded before any sleep
    assert frame.aoi_id == "aizawl"
    assert {c.cell_id for c in frame.cells} == set(STUB_CELL_IDS)
    assert all(c.source == "stub:live" for c in frame.cells)
    assert all(c.is_reconstructed is False for c in frame.cells)
    assert "not a measured weather feed" in frame.provenance["note"]


def test_stub_cell_ids_join_the_real_aizawl_grid():
    cells_path = Path(__file__).resolve().parents[2] / "data" / "static" / "aizawl" / "cells.gpkg"
    if not cells_path.is_file():
        pytest.skip("requires built Aizawl grid")
    real_ids = set(gpd.read_file(cells_path, columns=["cell_id"])["cell_id"])
    assert set(STUB_CELL_IDS) <= real_ids


async def test_rejects_a_non_live_clock():
    clock = ScenarioClock(
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, tzinfo=timezone.utc),
        speed_factor=1.0,
    )
    with pytest.raises(ValueError):
        StubLiveSource(clock)
