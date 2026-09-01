from datetime import datetime, timezone

from app.commander.store import CommanderStore
from app.core.clock import ScenarioClock
from app.schemas.commander import CommanderRoute, SavedRoutePlanCreate
from app.schemas.decision import EvacuationRoute


def _plan() -> SavedRoutePlanCreate:
    route = EvacuationRoute(
        village_id="v1",
        shelter_id="s1",
        shelter_name="Shelter 1",
        geometry={"type": "LineString", "coordinates": [[92.7, 23.7], [92.8, 23.8]]},
        distance_m=1000,
        est_walk_minutes=15,
        shelter_capacity_ok=True,
    )
    return SavedRoutePlanCreate(
        name="Primary route",
        aoi_id="aizawl",
        village_id="v1",
        routes=[CommanderRoute(route_rank=1, route=route, safety_reason="Lowest route risk")],
    )


def test_store_uses_injected_clock_and_deterministic_identifier(tmp_path):
    instant = datetime(2024, 5, 28, 3, 0, tzinfo=timezone.utc)
    clock = ScenarioClock(instant, instant)

    first = CommanderStore(tmp_path / "first.sqlite3", clock=clock).save(_plan())
    second = CommanderStore(tmp_path / "second.sqlite3", clock=clock).save(_plan())

    assert first.created_at == instant
    assert first.id == second.id
