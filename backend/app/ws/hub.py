"""The /ws/ticks WebSocket hub (BUILD_PLAN.md task 0.11). Every connected client receives every
TickResult broadcast on Topic.TICK — one channel, no per-client filtering.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.bus import Topic

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/ticks")
async def ws_ticks(websocket: WebSocket) -> None:
    await websocket.accept()
    app_state = websocket.app.state.app_state
    try:
        async with app_state.bus.subscribe(Topic.TICK) as queue:
            while True:
                tick = await queue.get()
                await websocket.send_text(tick.model_dump_json())
    except WebSocketDisconnect:
        logger.info("client disconnected from /ws/ticks")
