"""Risk contracts. See docs/ARCHITECTURE.md §4.3.

Output of risk/. Phase 0: a deterministic fake function of rainfall. Phase 1: threshold-exceedance
engine + XGBoost, per BUILD_PLAN.md Phase 1C.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Attribution(BaseModel):
    feature: str
    plain_language: str  # "72-hour rainfall"
    contribution: float  # signed SHAP value
    display_pct: float


class CellRisk(BaseModel):
    # Appendix A names this field `model_version` exactly — not renaming it to dodge Pydantic's
    # reserved `model_` prefix warning; disabling the (inapplicable here) protection instead.
    model_config = ConfigDict(protected_namespaces=())

    cell_id: str
    p_fail: float = Field(ge=0.0, le=1.0)
    threshold_exceedance: float = Field(ge=0.0)  # observed / ID-curve threshold
    confidence: float = Field(ge=0.0, le=1.0)
    attributions: list[Attribution] = Field(default_factory=list)
    model_version: str
    geometry: dict | None = None
    terrain: dict[str, float | str | None] = Field(default_factory=dict)
