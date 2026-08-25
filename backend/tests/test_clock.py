"""Contract test for core/clock.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import Clock, LiveClock, ScenarioClock

UTC = timezone.utc


def test_live_clock_is_live_and_reads_wall_time():
    clock = LiveClock()
    assert clock.is_live is True
    before = datetime.now(UTC)
    reading = clock.now()
    after = datetime.now(UTC)
    assert before <= reading <= after


def test_live_clock_satisfies_protocol():
    assert isinstance(LiveClock(), Clock)


def test_live_clock_advance_is_a_noop_that_still_returns_now():
    clock = LiveClock()
    reading = clock.advance(to=datetime(2020, 1, 1, tzinfo=UTC))  # target is ignored
    assert reading >= datetime.now(UTC) - timedelta(seconds=1)


class TestScenarioClock:
    def make(self, **overrides) -> ScenarioClock:
        defaults = dict(
            start=datetime(2024, 5, 26, 0, 0, tzinfo=UTC),
            end=datetime(2024, 5, 28, 18, 0, tzinfo=UTC),
            speed_factor=3600.0,
        )
        defaults.update(overrides)
        return ScenarioClock(**defaults)

    def test_starts_at_start_and_is_not_live(self):
        clock = self.make()
        assert clock.is_live is False
        assert clock.now() == clock.start

    def test_satisfies_protocol(self):
        assert isinstance(self.make(), Clock)

    def test_advance_to_explicit_timestamp_is_deterministic(self):
        clock = self.make()
        target = clock.start + timedelta(hours=6)
        result = clock.advance(to=target)
        assert result == target
        assert clock.now() == target

    def test_advance_without_target_steps_by_default_increment(self):
        clock = self.make()
        result = clock.advance()
        assert result == clock.start + timedelta(minutes=1)

    def test_advance_clamps_to_end(self):
        clock = self.make()
        far_future = clock.end + timedelta(days=10)
        result = clock.advance(to=far_future)
        assert result == clock.end
        assert clock.finished is True

    def test_advance_backward_raises(self):
        clock = self.make()
        clock.advance(to=clock.start + timedelta(hours=1))
        with pytest.raises(ValueError):
            clock.advance(to=clock.start)

    def test_reset_returns_to_start(self):
        clock = self.make()
        clock.advance(to=clock.end)
        assert clock.finished is True
        result = clock.reset()
        assert result == clock.start
        assert clock.finished is False

    def test_rejects_naive_datetimes(self):
        with pytest.raises(ValueError):
            ScenarioClock(start=datetime(2024, 1, 1), end=datetime(2024, 1, 2), speed_factor=1.0)

    def test_rejects_end_before_start(self):
        with pytest.raises(ValueError):
            self.make(end=self.make().start - timedelta(days=1))

    def test_rejects_non_positive_speed_factor(self):
        with pytest.raises(ValueError):
            self.make(speed_factor=0.0)

    def test_two_scenario_clocks_advanced_identically_are_deterministic(self):
        """Replay determinism (CLAUDE.md rule 13) starts here: same inputs, same clock state."""
        a, b = self.make(), self.make()
        for hours in (1, 2, 5, 10):
            target = a.start + timedelta(hours=hours)
            assert a.advance(to=target) == b.advance(to=target)
