"""FastAPI app entrypoint (BUILD_PLAN.md task 0.11). Wires api/ routers and the /ws/ticks hub
onto one AppState instance. See docs/ARCHITECTURE.md §3 for what each module owns.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.commander import router as commander_router
from app.api.state import AppState
from app.ws.hub import router as ws_router

ALLOWED_ORIGINS = [
    "http://localhost:5173",  # Vite dev server, CLAUDE.md §8
    "http://127.0.0.1:5173",
]
# Vite hops to 5174/5175/... whenever 5173 is already taken (a second checkout, a stale process),
# and there is no production deployment of this service — a real deploy would set explicit
# origins from the environment. Allow any localhost port in dev so a port hop doesn't silently
# break every API call with an opaque CORS error.
ALLOWED_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1):\d+$"


def create_app(*, realtime: bool = True, citizen_report_data_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.app_state = AppState(
            realtime=realtime,
            citizen_report_data_dir=citizen_report_data_dir,
        )
        app.state.app_state.start()  # begin the LIVE stub tick stream immediately
        yield
        await app.state.app_state.shutdown()

    app = FastAPI(title="NIRANTAR — NER Landslide Early Warning", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_origin_regex=ALLOWED_ORIGIN_REGEX,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(commander_router)
    app.include_router(ws_router)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/")
    async def root() -> dict:
        return {
            "service": "NIRANTAR",
            "description": "NER landslide early-warning decision and dissemination API",
            "status": "ok",
            "docs": "/docs",
            "health": "/healthz",
            "citizen_reports": "/api/citizen-reports",
        }

    return app


app = create_app()
