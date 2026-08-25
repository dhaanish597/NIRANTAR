"""Mode & time contracts. See docs/ARCHITECTURE.md §4.1.

RunMode / ModeState are produced and owned by core/mode.py. Nothing outside core/mode.py and
core/clock.py should construct a ModeState directly.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"


class ModeState(BaseModel):
    mode: RunMode
    scenario_id: str | None = None
    scenario_time: datetime | None = None
    speed_factor: float = Field(default=1.0, gt=0.0)
    paused: bool = False
