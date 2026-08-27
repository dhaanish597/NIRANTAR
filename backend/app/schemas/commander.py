from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.decision import EvacuationRoute


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class CommanderChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    village_id: str | None = None
    aoi_id: str | None = None


class CommanderRoute(BaseModel):
    route_rank: int = Field(ge=1, le=3)
    route: EvacuationRoute
    safety_reason: str
    risk_snapshot: list[str] = Field(default_factory=list)


class CommanderChatResponse(BaseModel):
    answer: str
    source: Literal["nvidia", "fallback"]
    routes: list[CommanderRoute] = Field(default_factory=list)
    context: dict[str, object] = Field(default_factory=dict)


class SavedRoutePlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aoi_id: str
    village_id: str
    routes: list[CommanderRoute] = Field(min_length=1, max_length=3)


class SavedRoutePlan(SavedRoutePlanCreate):
    id: str
    created_at: datetime
