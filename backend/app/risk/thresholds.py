"""NE Himalaya rainfall intensity-duration and event-duration thresholds (BUILD_PLAN.md task
1.11). This is the physically-grounded baseline risk signal — the fallback if the ML model
(Phase 1C, risk/model.py) underperforms, and reportedly what GSI itself uses operationally
(BUILD_PLAN.md risk register: "Ship it as the primary if ML underperforms").

Two published threshold curves (CLAUDE.md §4 — cite these in the UI/docs, a geologist judge will
ask about them first):
    Intensity-Duration: I = 5.8294 * D^-0.4141   (I mm/h, D hours)
    Event-Duration:      E = -11.10 + 0.62 * D    (E mm, valid 24 < D < 1440 h)

CellObservation (schemas/ingest.py) doesn't track storm "duration" as its own variable — it only
carries four fixed accumulation windows (rain_1h/6h/24h/72h). So both curves are evaluated at
each of those windows and the *maximum* resulting exceedance ratio is reported: the most
threshold-exceeding way of reading the current accumulation. That choice of windows and of taking
the max — not the two formulas themselves — is our own engineering decision, not a cited figure;
say so if a judge asks why these four windows specifically.
"""
from __future__ import annotations

from app.schemas.ingest import CellObservation

# The four accumulation windows CellObservation actually carries.
_WINDOWS_HOURS = (1.0, 6.0, 24.0, 72.0)


def intensity_duration_threshold_mm_per_hr(duration_hours: float) -> float:
    """I = 5.8294 * D^-0.4141 (NE Himalaya, CLAUDE.md §4)."""
    return 5.8294 * duration_hours**-0.4141


def event_duration_threshold_mm(duration_hours: float) -> float | None:
    """E = -11.10 + 0.62 * D (NE Himalaya, CLAUDE.md §4).

    Only valid for 24 < D < 1440 h — returns None outside that range rather than extrapolating a
    published formula past its documented validity.
    """
    if not (24 < duration_hours < 1440):
        return None
    return -11.10 + 0.62 * duration_hours


def _window_rainfall_mm(obs: CellObservation, duration_hours: float) -> float:
    by_window = {1.0: obs.rain_1h, 6.0: obs.rain_6h, 24.0: obs.rain_24h, 72.0: obs.rain_72h}
    return by_window[duration_hours]


def threshold_exceedance_ratio(obs: CellObservation) -> float:
    """max(observed / threshold) across the I-D curve (all four windows) and the E-D curve
    (windows where it's valid — only the 72h window, of our four, falls in 24 < D < 1440).

    A ratio >= 1.0 means observed rainfall at that accumulation window meets or exceeds the
    published threshold for that duration. Always >= 0.0; unbounded above.
    """
    ratios: list[float] = []

    for duration in _WINDOWS_HOURS:
        observed_mm = _window_rainfall_mm(obs, duration)

        observed_intensity = observed_mm / duration  # mm/h average over the window
        id_threshold = intensity_duration_threshold_mm_per_hr(duration)
        ratios.append(observed_intensity / id_threshold)

        ed_threshold = event_duration_threshold_mm(duration)
        if ed_threshold is not None and ed_threshold > 0:
            ratios.append(observed_mm / ed_threshold)

    return max(ratios)
