"""The only file in this repo allowed to call `datetime.now()` (CLAUDE.md rule 14).

Everything else calls `clock.now()`, where `clock` is either a LiveClock (wall time) or a
ScenarioClock (virtual time driven by a scenario file's frame timestamps). This is what lets
REPLAY be "a different Clock feeding the same pipeline" instead of a separate code path
(CLAUDE.md §2). tests/test_no_wallclock.py enforces the ban with an AST walk — do not delete it.

ScenarioClock intentionally does no sleeping/pacing itself: it is a pure, synchronous, easily
testable state holder. Real-time pacing between frames (using `speed_factor`) is the job of
ingest/replay/scenario_source.py, which calls `advance(to=frame.t)` as it walks the frame list.
Keeping the clock free of async/sleep is what makes replay determinism (CLAUDE.md rule 13)
straightforward to test: advancing a ScenarioClock in a unit test is instant.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Structural contract every clock implementation satisfies."""

    @property
    def is_live(self) -> bool: ...

    def now(self) -> datetime:
        """Current time as this clock sees it — wall clock or scenario virtual time."""
        ...

    def advance(self, to: datetime | None = None) -> datetime:
        """Move this clock's notion of "now" forward and return the new value.

        `to`: jump straight to this absolute timestamp (must not be earlier than the current
        time). If omitted, step forward by a small default increment. Live clocks ignore both
        the argument and the concept — wall time advances on its own.
        """
        ...


class LiveClock:
    """Wraps the real wall clock. The only place `datetime.now()` is called in this repo."""

    is_live = True

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def advance(self, to: datetime | None = None) -> datetime:
        # Wall-clock time advances whether we ask it to or not; `advance()` exists only so
        # callers can treat LiveClock and ScenarioClock identically.
        return self.now()


class ScenarioClock:
    """Virtual clock driven entirely by explicit `advance()` calls — no wall-clock reads.

    `speed_factor` (virtual seconds per real second) is stored here so ingest/replay/ has a
    single place to read it from, but this class never sleeps or reads real time itself.
    """

    is_live = False

    _DEFAULT_STEP = timedelta(minutes=1)

    def __init__(self, start: datetime, end: datetime, speed_factor: float = 1.0):
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("ScenarioClock requires timezone-aware start/end datetimes")
        if end < start:
            raise ValueError(f"end ({end}) is before start ({start})")
        if speed_factor <= 0:
            raise ValueError(f"speed_factor must be > 0, got {speed_factor}")

        self.start = start
        self.end = end
        self.speed_factor = speed_factor
        self._current = start

    def now(self) -> datetime:
        return self._current

    @property
    def finished(self) -> bool:
        return self._current >= self.end

    def advance(self, to: datetime | None = None) -> datetime:
        target = self._current + self._DEFAULT_STEP if to is None else to
        if target < self._current:
            raise ValueError(
                f"ScenarioClock cannot move backward ({target} < {self._current}); "
                "call reset() to restart a replay instead."
            )
        self._current = min(target, self.end)
        return self._current

    def reset(self) -> datetime:
        """Restart at `start`. Used when a replay is restarted (BUILD_PLAN.md task 4.7)."""
        self._current = self.start
        return self._current

    def seek(self, to: datetime) -> datetime:
        """Jump to an arbitrary timestamp within [start, end], forward OR backward.

        Unlike `advance()` (which enforces "never move backward" — the right invariant for
        ordinary frame-by-frame playback, where going backward would signal a real bug), `seek()`
        is the deliberate escape hatch for scrubbing a replay to an arbitrary point on its
        timeline (BUILD_PLAN.md task 4.7). Values outside [start, end] are clamped rather than
        raising, so a caller scrubbing slightly past either end of the scenario still lands
        somewhere valid instead of crashing the replay.
        """
        self._current = max(self.start, min(to, self.end))
        return self._current
