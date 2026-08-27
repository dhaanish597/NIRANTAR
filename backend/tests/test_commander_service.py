from datetime import datetime, timezone

import pytest

from app.commander.service import answer, verified_routes
from app.schemas.commander import CommanderChatRequest
from app.schemas.decision import ActionCard, EvacuationRoute
from app.schemas.tick import TickResult
from app.schemas.mode import RunMode


def tick_with_routes() -> TickResult:
    def card(shelter: str) -> ActionCard:
        return ActionCard(alert_id="a", village_id="v1", stage="ORANGE", headline="h", reason_plain="r", shelter_name=shelter, route=EvacuationRoute(village_id="v1", shelter_id=shelter, shelter_name=shelter, geometry={"type": "LineString", "coordinates": [[92.7, 23.7], [92.8, 23.8]]}, distance_m=1000, est_walk_minutes=15, shelter_capacity_ok=True), contact="c", issued_at=datetime.now(timezone.utc), valid_until=datetime.now(timezone.utc))
    return TickResult(t=datetime.now(timezone.utc), mode=RunMode.LIVE, aoi_id="aizawl", new_action_cards=[card("s1"), card("s2"), card("s3"), card("s1")])


def test_verified_routes_are_distinct_and_capped_at_three():
    routes = verified_routes(tick_with_routes(), "v1")
    assert len(routes) == 3
    assert [item.route_rank for item in routes] == [1, 2, 3]
    assert [item.route.shelter_id for item in routes] == ["s1", "s2", "s3"]


@pytest.mark.asyncio
async def test_chat_without_key_uses_structured_fallback():
    response = await answer(CommanderChatRequest(message="show safe routes"), tick_with_routes(), api_key=None, model="test", base_url="http://localhost", timeout=1)
    assert response.source == "fallback"
    assert len(response.routes) == 3
    assert "verified" in response.answer.lower()
