"""decision/window.py — BUILD_PLAN.md task 2.6: the safe evacuation window.

CLAUDE.md §4 glossary is explicit and non-negotiable: "Safe evacuation window — Estimated time
until critical risk. **Never** call this 'time to landslide' — we do not predict exact timing."
Every string this module produces is checked (see tests/test_window.py) to never contain that
forbidden phrase, the same style of structural enforcement `tests/test_no_wallclock.py` already
uses for rule 14.

WHAT THIS MODULE DOES: fits a simple linear trend through a short recent history of
`risk/thresholds.py`'s threshold-exceedance ratio (observed rainfall / published I-D or E-D
threshold — 1.0 means the published threshold is met) and projects forward to the point that
trend would cross `config.WINDOW_CRITICAL_EXCEEDANCE_RATIO`. This is exactly the "rising trend
toward exceedance is your signal" instruction in BUILD_PLAN.md task 2.6 — the physically-grounded
threshold engine (task 1.11) already IS the fallback risk signal CLAUDE.md's risk register names,
so building the window projection on top of its output (rather than re-deriving a new trend model
against raw rainfall) keeps this consistent with the rest of the risk stack.

WHY A LINEAR TREND, NOT SOMETHING FANCIER: with no forecast rainfall model of our own (IMD
nowcasts are task 1.8, circuit-broken/P1) and no calibrated event dataset large enough to fit
anything more sophisticated (see ml/train.py's own 56-row honesty note), a plain least-squares
extrapolation of the *observed* trend is the most defensible thing that doesn't overclaim. It is
an engineering heuristic, not a validated forecast model — the `basis` string on every
`SafeWindowEstimate` says so explicitly, and `confidence` is a heuristic goodness-of-fit measure
(same "decisive vs. undecided" honesty framing risk/model.py's own `confidence` field uses), not a
statistical prediction interval.

Pure function over a plain time series (`WindowObservation`) — no LIVE/REPLAY awareness
(CLAUDE.md §2), no clock.now() call of its own (rule 14: `datetime.now()` is banned outside
core/clock.py). The reference "now" instant is a required, caller-supplied argument (a real
pipeline would pass `clock.now()`; tests pass a fixed timestamp), never read internally — which is
exactly what "build and test this as a pure function over a time series" (BUILD_PLAN.md task 2.6)
means in practice, and it's what lets this be exercised standalone with `datetime` fixtures only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config import (
    WINDOW_CRITICAL_EXCEEDANCE_RATIO,
    WINDOW_IMMEDIATE_UPPER_HOURS,
    WINDOW_MARGIN_FRACTION,
    WINDOW_MAX_FORECAST_HOURS,
    WINDOW_MIN_MARGIN_HOURS,
    WINDOW_MIN_TREND_POINTS,
)
from app.risk.thresholds import threshold_exceedance_ratio
from app.schemas.ingest import CellObservation


@dataclass(frozen=True)
class WindowObservation:
    """One point in the exceedance-ratio trajectory this module fits a trend against."""

    t: datetime
    exceedance_ratio: float


@dataclass(frozen=True)
class SafeWindowEstimate:
    """`hours` matches `ActionCard.safe_window_hours`'s exact shape — a range, never a point
    estimate (CLAUDE.md's own phrasing) — or `None` when no defensible window can be estimated at
    all (too little data, a flat/falling trend, or a projected crossing beyond the forecast
    horizon: see module docstring). `confidence` is a heuristic in [0, 1], always 0.0 when `hours`
    is `None` — there is nothing to be confident about. `basis` is a short, honest, plain-language
    statement of how the number was produced, for the explainability panel (BUILD_PLAN.md task
    5.7) and for a judge who asks "how did you get this."
    """

    hours: tuple[float, float] | None
    confidence: float
    basis: str


def exceedance_trajectory(
    timed_observations: list[tuple[datetime, CellObservation]],
) -> list[WindowObservation]:
    """Convenience wrapper turning a (timestamp, CellObservation) history into the
    `WindowObservation` trajectory `estimate_safe_window` consumes, via risk/thresholds.py's real
    I-D/E-D exceedance-ratio engine (task 1.11) — the "you have risk/thresholds.py's exceedance
    ratio available" signal BUILD_PLAN.md task 2.6 points at. Not sorted here — callers are
    expected to supply their own history in chronological order, same as `estimate_safe_window`
    itself requires (documented there)."""
    return [
        WindowObservation(t=t, exceedance_ratio=threshold_exceedance_ratio(obs))
        for t, obs in timed_observations
    ]


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Ordinary least squares y = a + b*x. Returns (a, b, r_squared). Callers guarantee len(xs) >=
    2 and not all x identical (checked by `estimate_safe_window` before calling this)."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    s_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    s_xx = sum((x - mean_x) ** 2 for x in xs)
    b = s_xy / s_xx
    a = mean_y - b * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot == 0.0:
        # Every y identical: a perfectly flat trend fits itself perfectly (r_squared=1) but that
        # is a meaningless "goodness of fit" for a flat line with no variance to explain — report
        # 0.0 rather than a misleadingly confident 1.0.
        r_squared = 0.0
    else:
        ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
        r_squared = max(0.0, 1.0 - ss_res / ss_tot)
    return a, b, r_squared


def estimate_safe_window(
    observations: list[WindowObservation],
    *,
    now: datetime | None = None,
    critical_ratio: float = WINDOW_CRITICAL_EXCEEDANCE_RATIO,
    min_points: int = WINDOW_MIN_TREND_POINTS,
    forecast_horizon_hours: float = WINDOW_MAX_FORECAST_HOURS,
    margin_fraction: float = WINDOW_MARGIN_FRACTION,
    min_margin_hours: float = WINDOW_MIN_MARGIN_HOURS,
    immediate_upper_hours: float = WINDOW_IMMEDIATE_UPPER_HOURS,
) -> SafeWindowEstimate:
    """`observations` must be sorted ascending by `.t` (chronological trajectory) — the caller's
    responsibility, same as `ingest/replay/scenario_source.py` requires sorted scenario frames.

    `now` defaults to the last observation's own timestamp (the most recent reading IS "now" if
    the caller doesn't supply a distinct reference instant) — this is never a wall-clock read
    (rule 14); a real pipeline caller passes `clock.now()` explicitly.
    """
    if not observations:
        return SafeWindowEstimate(hours=None, confidence=0.0, basis="no observations supplied")

    last = observations[-1]
    reference_t = now if now is not None else last.t

    if last.exceedance_ratio >= critical_ratio:
        return SafeWindowEstimate(
            hours=(0.0, immediate_upper_hours),
            confidence=1.0,
            basis=(
                f"observed exceedance ratio {last.exceedance_ratio:.2f} is already at or above "
                f"the critical ratio {critical_ratio:g} — this is a current reading, not a "
                "projection: act now rather than wait for a projected crossing."
            ),
        )

    if len(observations) < min_points:
        return SafeWindowEstimate(
            hours=None,
            confidence=0.0,
            basis=(
                f"only {len(observations)} observation(s) available; at least {min_points} are "
                "needed to fit a defensible trend, so no window is projected."
            ),
        )

    t0 = observations[0].t
    xs = [(o.t - t0).total_seconds() / 3600.0 for o in observations]
    ys = [o.exceedance_ratio for o in observations]

    if xs[-1] == xs[0]:
        return SafeWindowEstimate(
            hours=None, confidence=0.0, basis="all observations share the same timestamp; cannot fit a trend"
        )

    a, b, r_squared = _linear_fit(xs, ys)

    if b <= 0:
        return SafeWindowEstimate(
            hours=None,
            confidence=0.0,
            basis=(
                "the recent exceedance-ratio trend is flat or falling; no threshold crossing is "
                "projected"
            ),
        )

    x_now = (reference_t - t0).total_seconds() / 3600.0
    x_cross = (critical_ratio - a) / b
    hours_until_cross = x_cross - x_now

    if hours_until_cross <= 0:
        # The fitted trend already implies critical risk as of `now`, even though the last actual
        # observation hadn't itself reached the critical ratio — treat as imminent rather than
        # reporting a nonsensical negative lead time.
        return SafeWindowEstimate(
            hours=(0.0, immediate_upper_hours),
            confidence=max(0.0, min(r_squared, 0.95)),
            basis=(
                "the fitted rainfall trend projects the critical exceedance ratio has already "
                "been reached as of the reference time — treat as imminent."
            ),
        )

    if hours_until_cross > forecast_horizon_hours:
        return SafeWindowEstimate(
            hours=None,
            confidence=0.0,
            basis=(
                f"projected crossing is {hours_until_cross:.0f}h away, beyond the "
                f"{forecast_horizon_hours:g}h forecast horizon this trend is trusted over; not "
                "reported, to avoid a false sense of precision at that range."
            ),
        )

    margin_hours = max(margin_fraction * hours_until_cross, min_margin_hours)
    lower = max(0.0, hours_until_cross - margin_hours)
    upper = hours_until_cross + margin_hours

    # Heuristic confidence: goodness of fit (r_squared), damped a little by how few points backed
    # it — never a statistical guarantee, documented as such in `basis`. Never reported as 1.0 for
    # a genuine projection (only the "already critical" / literal-reading branches above use 1.0,
    # because those aren't projections at all).
    point_count_factor = min(1.0, len(observations) / (min_points + 2))
    confidence = max(0.0, min(0.95, r_squared * point_count_factor))

    return SafeWindowEstimate(
        hours=(lower, upper),
        confidence=confidence,
        basis=(
            f"linear trend over the last {len(observations)} exceedance-ratio observations "
            f"(fit R²={r_squared:.2f}) projects crossing the critical ratio "
            f"{critical_ratio:g} in roughly {hours_until_cross:.1f}h — an extrapolation of "
            "the current rainfall trend, not a fixed prediction."
        ),
    )
