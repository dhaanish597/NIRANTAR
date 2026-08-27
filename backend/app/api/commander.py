from __future__ import annotations

from fastapi import APIRouter, Request

from app.commander.service import answer
from app.commander.store import CommanderStore
from app.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL, NVIDIA_TIMEOUT_SECONDS
from app.schemas.commander import CommanderChatRequest, CommanderChatResponse, SavedRoutePlan, SavedRoutePlanCreate

router = APIRouter(prefix="/api/commander")


@router.post("/chat", response_model=CommanderChatResponse)
async def commander_chat(body: CommanderChatRequest, request: Request):
    state = request.app.state.app_state
    return await answer(body, state.latest_tick, api_key=NVIDIA_API_KEY, model=NVIDIA_MODEL, base_url=NVIDIA_BASE_URL, timeout=NVIDIA_TIMEOUT_SECONDS)


@router.get("/saved-routes", response_model=list[SavedRoutePlan])
async def list_saved_routes(request: Request):
    return request.app.state.commander_store.list()


@router.post("/saved-routes", response_model=SavedRoutePlan)
async def save_route_plan(body: SavedRoutePlanCreate, request: Request):
    return request.app.state.commander_store.save(body)
