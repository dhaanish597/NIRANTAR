"""Phase 0 impact stub (BUILD_PLAN.md task 0.10). One fixed village ("Hunthar (stub)") and one
fixed road ("NH-6 (stub)") so the map and priority list have something real to render. Real
runout/RII/EPS land in Phase 2 (BUILD_PLAN.md §Phase 2 — runout.py, road_graph.py, isolation.py,
priority.py) and this file goes away.

NOTE: RunoutEnvelope has no field on TickResult (schemas/tick.py, Appendix A) — it's computed
here and returned to the caller, but Phase 0's pipeline does not broadcast it over /ws/ticks.
Flagged as a plan gap rather than silently extending TickResult past what was reviewed; Phase 2
needs to decide how runout geometry actually reaches the frontend (a TickResult field vs. a
separate REST/tile layer).
"""
from __future__ import annotations

from app.schemas.impact import (
    RoadSegmentRisk,
    RunoutEnvelope,
    SettlementPriority,
    VillageIsolation,
)
from app.schemas.risk import CellRisk

STUB_VILLAGE_ID = "v_hunthar_stub"
STUB_ROAD_EDGE_ID = "nh6_hunthar_stub"
RUNOUT_TRIGGER_P_FAIL = 0.5  # fabricated — Phase 2 derives this from a real angle-of-reach model
SEVERANCE_P_BLOCKED = 0.9  # fabricated — Phase 2's road_graph.py sets this from real P_crit


def average_p_fail(cell_risks: list[CellRisk]) -> float:
    if not cell_risks:
        return 0.0
    return sum(r.p_fail for r in cell_risks) / len(cell_risks)


def compute_impact(
    cell_risks: list[CellRisk],
) -> tuple[
    list[RunoutEnvelope], list[RoadSegmentRisk], list[VillageIsolation], list[SettlementPriority]
]:
    avg = average_p_fail(cell_risks)

    envelopes = [
        RunoutEnvelope(
            source_cell_id=r.cell_id,
            geometry={"type": "Polygon", "coordinates": []},  # Phase 0: no real geometry yet
            p_fail=r.p_fail,
            method="phase0-stub-no-geometry",
        )
        for r in cell_risks
        if r.p_fail >= RUNOUT_TRIGGER_P_FAIL
    ]

    road = RoadSegmentRisk(
        edge_id=STUB_ROAD_EDGE_ID,
        name="NH-6",
        highway_class="trunk",
        is_bridge=False,
        p_blocked=avg,
        severed=avg >= SEVERANCE_P_BLOCKED,
        contributing_cells=[r.cell_id for r in cell_risks],
    )

    village = VillageIsolation(
        village_id=STUB_VILLAGE_ID,
        name="Hunthar (stub)",
        population=1200,  # fabricated — Phase 1 exposure data (scripts/fetch_exposure.py) replaces this
        p_isolated=avg,
        isolated_now=road.severed,
        alternate_route_exists=not road.severed,
        est_duration_hours=None,
        severed_links=[STUB_ROAD_EDGE_ID] if road.severed else [],
    )

    tier = "P1" if avg >= 0.75 else "P2" if avg >= 0.4 else "P3"
    priority = SettlementPriority(
        village_id=STUB_VILLAGE_ID,
        eps=avg,
        tier=tier,
        components={"p_fail": avg, "pop": 0.0, "rii": avg, "shelter": 0.0},
    )

    return envelopes, [road], [village], [priority]
