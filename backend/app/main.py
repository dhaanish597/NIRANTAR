"""FastAPI app entrypoint (BUILD_PLAN.md task 0.11). Wires api/ routers and the /ws/ticks hub
onto one AppState instance. See docs/ARCHITECTURE.md §3 for what each module owns.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.commander import router as commander_router
from app.api.state import AppState
from app.ws.hub import router as ws_router

DEV_ORIGINS = [
    "http://localhost:5173",  # Vite dev server, CLAUDE.md §8
    "http://127.0.0.1:5173",
]


def _origins_from_env() -> list[str]:
    """Origins from `ALLOWED_ORIGINS`, a comma-separated list. Trailing slashes are stripped
    because a browser's `Origin` header never has one, and `https://x.dev` != `https://x.dev/`
    for CORSMiddleware — a mismatch here surfaces as an opaque CORS failure in the browser with
    nothing in the server log, which is a miserable thing to debug from a deployed frontend.
    """
    raw = os.getenv("ALLOWED_ORIGINS", "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


# Dev origins are always allowed (additive, never a replacement): a laptop running `make dev`
# against the deployed backend is a legitimate setup, and no public client can forge an Origin of
# localhost. Production origins come from the environment so that deploying the frontend does not
# require editing this file — the frontend's host is a deployment detail, not an app constant.
ALLOWED_ORIGINS = [*DEV_ORIGINS, *_origins_from_env()]

# Vite hops to 5174/5175/... whenever 5173 is already taken (a second checkout, a stale process).
# Allowing any localhost port stops a port hop from silently breaking every API call with an
# opaque CORS error. Gated off when NIRANTAR_ENV=production: it is a dev convenience, and a
# deployed service has no reason to accept origin `http://localhost:*` from a stranger's browser.
ALLOWED_ORIGIN_REGEX: str | None = (
    None
    if os.getenv("NIRANTAR_ENV", "").strip().lower() == "production"
    else r"^http://(localhost|127\.0\.0\.1):\d+$"
)


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
