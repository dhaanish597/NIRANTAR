"""The /ws/ticks WebSocket hub (BUILD_PLAN.md task 0.11). Every connected client receives every
TickResult broadcast on Topic.TICK, and every Announcement broadcast on Topic.DISSEMINATION —
still ONE WebSocket endpoint (the stack table's "one channel, /ws/ticks"), multiplexed by message
shape on the wire: a bare TickResult JSON object for a tick, `{"type": "announcement", "data":
{...}}` for an announcement. TickResult has no `type` field, so this is an unambiguous
discriminator — see frontend/src/lib/ws.ts's matching parse.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.bus import Topic
from app.schemas.tick import TickResult

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/ticks")
async def ws_ticks(websocket: WebSocket) -> None:
    await websocket.accept()
    app_state = websocket.app.state.app_state
    try:
        async with (
            app_state.bus.subscribe(Topic.TICK) as tick_queue,
            app_state.bus.subscribe(Topic.DISSEMINATION) as announcement_queue,
        ):
            pending = {
                asyncio.ensure_future(tick_queue.get()): tick_queue,
                asyncio.ensure_future(announcement_queue.get()): announcement_queue,
            }
            try:
                while True:
                    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        queue = pending.pop(task)
                        message = task.result()
                        if isinstance(message, TickResult):
                            await websocket.send_text(message.model_dump_json())
                        else:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "announcement",
                                        "data": message.model_dump(mode="json"),
                                    }
                                )
                            )
                        pending[asyncio.ensure_future(queue.get())] = queue
            finally:
                # Whatever is still in `pending` on the way out (WebSocketDisconnect, any other
                # exception, or the task being cancelled on server shutdown) is a scheduled
                # `queue.get()` Task that will now never resolve — the `async with` above only
                # unsubscribes the queue from the Bus, it does NOT cancel outstanding Tasks
                # created via `asyncio.ensure_future`. Left uncancelled, each disconnect leaks up
                # to 2 pending Tasks (visible as "Task was destroyed but it is pending!" on GC) —
                # real, unbounded resource growth across reconnects in a long-running demo
                # session. Cancel every remaining task and await it so it unwinds immediately
                # rather than lingering for the garbage collector.
                for task in pending:
                    task.cancel()
                for task in pending:
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
    except WebSocketDisconnect:
        logger.info("client disconnected from /ws/ticks")
