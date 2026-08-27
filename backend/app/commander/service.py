from __future__ import annotations

from app.commander.llm import explain_with_nvidia, fallback_answer
from app.schemas.commander import CommanderChatRequest, CommanderChatResponse, CommanderRoute
from app.schemas.tick import TickResult


def verified_routes(tick: TickResult | None, village_id: str | None) -> list[CommanderRoute]:
    if tick is None:
        return []
    seen: set[tuple[str, str]] = set()
    result: list[CommanderRoute] = []
    for card in tick.new_action_cards:
        if village_id and card.village_id != village_id:
            continue
        if card.route is None:
            continue
        key = (card.village_id, card.route.shelter_id)
        if key in seen:
            continue
        seen.add(key)
        affected = ", ".join(card.roads_to_avoid or card.route.avoided_roads) or "none listed"
        result.append(CommanderRoute(route_rank=len(result) + 1, route=card.route, safety_reason="Uses the current risk-filtered route and avoids affected roads.", risk_snapshot=[f"Avoid: {affected}"]))
        if len(result) == 3:
            break
    return result


async def answer(request: CommanderChatRequest, tick: TickResult | None, *, api_key: str | None, model: str, base_url: str, timeout: float) -> CommanderChatResponse:
    routes = verified_routes(tick, request.village_id)
    priorities = tick.priorities if tick else []
    roads = tick.road_risks if tick else []
    context = {"aoi_id": request.aoi_id or (tick.aoi_id if tick else None), "priority_count": len(priorities), "p1_count": sum(x.tier == "P1" for x in priorities), "affected_road_count": sum(x.severed for x in roads), "route_count": len(routes), "routes": [x.model_dump(mode="json") for x in routes]}
    generated = await explain_with_nvidia(message=request.message, history=request.history, context=context, api_key=api_key, model=model, base_url=base_url, timeout=timeout)
    return CommanderChatResponse(answer=generated or fallback_answer(request.message, context, len(routes)), source="nvidia" if generated else "fallback", routes=routes, context=context)
