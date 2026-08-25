"""Phase 0 risk stub (BUILD_PLAN.md task 0.10). Deterministic fake p_fail as a linear function of
rain_1h — clearly fabricated, not a model. Real threshold-exceedance engine + XGBoost model land
in Phase 1C (BUILD_PLAN.md §1C) and this file goes away; risk/thresholds.py, risk/model.py, and
risk/explain.py replace it without any change to CellRisk (schemas/risk.py) or to callers.
"""
from __future__ import annotations

from app.schemas.ingest import ObservationFrame
from app.schemas.risk import Attribution, CellRisk

MODEL_VERSION = "phase0-stub-fake-rain-linear"
# Fabricated: the rain_1h (mm/h) at which stub p_fail saturates to 1.0. Not derived from the
# real NE Himalaya I-D threshold (CLAUDE.md §4) — that's what Phase 1C implements for real.
RAIN_1H_SATURATION_MM = 30.0


def compute_cell_risks(frame: ObservationFrame) -> list[CellRisk]:
    return [
        CellRisk(
            cell_id=cell.cell_id,
            p_fail=(p_fail := min(1.0, max(0.0, cell.rain_1h / RAIN_1H_SATURATION_MM))),
            threshold_exceedance=p_fail,  # same fake number; Phase 1 computes this for real
            confidence=0.5,  # fixed — Phase 0 has no calibration to report
            attributions=[
                Attribution(
                    feature="rain_1h",
                    plain_language="1-hour rainfall (Phase 0 stub — not a real attribution)",
                    contribution=p_fail,
                    display_pct=round(p_fail * 100, 1),
                )
            ],
            model_version=MODEL_VERSION,
        )
        for cell in frame.cells
    ]
