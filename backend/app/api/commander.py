from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.ratelimit import rate_limit
from app.commander.service import answer
from app.commander.store import CommanderStore
from app.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL, NVIDIA_TIMEOUT_SECONDS
from app.schemas.commander import CommanderChatRequest, CommanderChatResponse, SavedRoutePlan, SavedRoutePlanCreate

router = APIRouter(prefix="/api/commander")


@router.post(
    "/chat",
    response_model=CommanderChatResponse,
    # FastAPI does not infer this from the `rate_limit` dependency (it only documents what the
    # route itself declares), so a client reading the OpenAPI schema would otherwise not know a
    # 429 is possible. Declared explicitly for the same reason the limiter exists: this route
    # spends real money per call and its caller should be able to see the contract.
    responses={429: {"description": "Rate limit exceeded — see the Retry-After header."}},
)
async def commander_chat(
    body: CommanderChatRequest,
    request: Request,
    _limit: None = Depends(rate_limit("commander_chat")),
):
    state = request.app.state.app_state
    api_key = None if state.mode.state.mode.value == "replay" else NVIDIA_API_KEY
    return await answer(body, state.latest_tick, api_key=api_key, model=NVIDIA_MODEL, base_url=NVIDIA_BASE_URL, timeout=NVIDIA_TIMEOUT_SECONDS)


@router.get("/saved-routes", response_model=list[SavedRoutePlan])
async def list_saved_routes(request: Request):
    return request.app.state.commander_store.list()


@router.post("/saved-routes", response_model=SavedRoutePlan)
async def save_route_plan(body: SavedRoutePlanCreate, request: Request):
    return request.app.state.commander_store.save(body)
