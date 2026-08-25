"""The DataSource protocol (BUILD_PLAN.md task 0.9). See docs/ARCHITECTURE.md §3.

Two implementations: ingest/live/ (stubbed in Phase 0) and ingest/replay/scenario_source.py
(reads a scenario JSON). Nothing above this layer knows or cares which one is active — that
choice is made by whatever wires the pipeline together based on ModeState (CLAUDE.md §2). This
file itself must never import from risk/, impact/, decision/, dissemination/, or audit/.
"""
from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from app.schemas.ingest import ObservationFrame


@runtime_checkable
class DataSource(Protocol):
    def frames(self) -> AsyncIterator[ObservationFrame]:
        """Yield observation frames in timestamp order.

        A live source never returns (it keeps producing frames as time passes); a replay source
        ends once it has yielded its scenario's last frame.
        """
        ...
