"""LIVE ⇄ REPLAY state machine (BUILD_PLAN.md task 0.7).

ModeMachine is deliberately clock- and datasource-ignorant: it only tracks and publishes
ModeState. Swapping the actual Clock/DataSource pair when mode changes is done by whatever wires
the pipeline together (api/), which reads scenario config to build a ScenarioClock — mode.py has
no file I/O and no knowledge of scenario JSON shape, which keeps it trivially unit-testable.
"""
from __future__ import annotations

from datetime import datetime

from app.core.bus import Bus, Topic
from app.schemas.mode import ModeState, RunMode


class ModeError(Exception):
    """Raised on an invalid transition, e.g. pause() while not in REPLAY."""


class ModeMachine:
    def __init__(self, bus: Bus):
        self._bus = bus
        self._state = ModeState(mode=RunMode.LIVE, scenario_id=None, scenario_time=None)

    @property
    def state(self) -> ModeState:
        return self._state

    async def start_replay(
        self, scenario_id: str, *, speed_factor: float = 1.0, scenario_time: datetime | None = None
    ) -> ModeState:
        """Enter REPLAY. Calling this again while already replaying switches scenarios."""
        if speed_factor <= 0:
            raise ValueError(f"speed_factor must be > 0, got {speed_factor}")
        self._state = ModeState(
            mode=RunMode.REPLAY,
            scenario_id=scenario_id,
            scenario_time=scenario_time,
            speed_factor=speed_factor,
            paused=False,
        )
        await self._publish()
        return self._state

    async def pause(self) -> ModeState:
        self._require_replay("pause")
        self._state = self._state.model_copy(update={"paused": True})
        await self._publish()
        return self._state

    async def resume(self) -> ModeState:
        self._require_replay("resume")
        self._state = self._state.model_copy(update={"paused": False})
        await self._publish()
        return self._state

    async def set_speed(self, speed_factor: float) -> ModeState:
        self._require_replay("set_speed")
        if speed_factor <= 0:
            raise ValueError(f"speed_factor must be > 0, got {speed_factor}")
        self._state = self._state.model_copy(update={"speed_factor": speed_factor})
        await self._publish()
        return self._state

    async def stop_replay(self) -> ModeState:
        """Return to LIVE. A no-op transition (still publishes) if already LIVE."""
        self._state = ModeState(mode=RunMode.LIVE, scenario_id=None, scenario_time=None)
        await self._publish()
        return self._state

    def update_scenario_time(self, t: datetime) -> ModeState:
        """Called once per tick during replay to keep ModeState.scenario_time current.

        Does NOT publish to the bus — every TickResult already carries `t` on its own broadcast
        (see schemas/tick.py), so publishing here too would just double the traffic for no new
        information. Only real mode *transitions* go on Topic.MODE.
        """
        if self._state.mode is RunMode.REPLAY:
            self._state = self._state.model_copy(update={"scenario_time": t})
        return self._state

    def _require_replay(self, action: str) -> None:
        if self._state.mode is not RunMode.REPLAY:
            raise ModeError(f"cannot {action}(): not currently in REPLAY mode")

    async def _publish(self) -> None:
        await self._bus.publish(Topic.MODE, self._state)
