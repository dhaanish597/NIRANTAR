"""SHAP explanations, top-4 contributing features in plain language (BUILD_PLAN.md task 1.18).

Uses `shap.TreeExplainer` against the same Booster `risk/model.py` (task 1.17) loads. SHAP values
are computed in the model's **raw margin (log-odds) units**, not probability units — this is
`shap.TreeExplainer`'s default and standard practice for explaining a gradient-boosted tree
ensemble; SHAP values are additive in margin space (they sum to the difference from the base
margin), not in probability space, so converting per-feature contributions to "probability
points" would misrepresent how the additive decomposition actually works. The sign and relative
ranking are what's reported — a positive contribution pushed the cell toward failure, a negative
one pushed it away — not a claim of "+X percentage points of literal probability."

**Feature groups, not raw columns:** several raw feature columns decompose one physical quantity
(`aspect_sin`/`aspect_cos` are a circular encoding of one aspect value; the eleven `land_cover_*`
columns are a one-hot encoding of one land-cover class). Reporting each raw column as its own
"top feature" would be confusing and double-count a single real-world driver — this module sums
SHAP values within each documented group before ranking, so "slope aspect" or "land cover" appears
once, not fragmented across its encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import shap

from app.risk.model import RiskModel
from app.schemas.risk import Attribution

_COMPASS_DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _compass(aspect_deg: float) -> str:
    idx = int(((aspect_deg % 360) + 22.5) // 45) % 8
    return _COMPASS_DIRECTIONS[idx]


@dataclass(frozen=True)
class FeatureGroup:
    key: str
    columns: list[str]
    label: Callable[[pd.Series], str]


FEATURE_GROUPS: list[FeatureGroup] = [
    FeatureGroup("elevation", ["elevation_m"], lambda row: f"elevation ({row['elevation_m']:.0f} m)"),
    FeatureGroup(
        "elevation_range",
        ["elevation_min_m", "elevation_max_m"],
        lambda row: f"elevation range ({row['elevation_min_m']:.0f}-{row['elevation_max_m']:.0f} m)",
    ),
    FeatureGroup("slope_mean", ["slope_mean_deg"], lambda row: f"average slope ({row['slope_mean_deg']:.0f}°)"),
    FeatureGroup("slope_max", ["slope_max_deg"], lambda row: f"maximum slope ({row['slope_max_deg']:.0f}°)"),
    FeatureGroup("twi", ["twi_mean"], lambda row: f"topographic wetness index ({row['twi_mean']:.1f})"),
    FeatureGroup("relief", ["relief_m"], lambda row: f"relief / elevation range in cell ({row['relief_m']:.0f} m)"),
    FeatureGroup(
        "aspect",
        ["aspect_sin", "aspect_cos"],
        lambda row: f"slope aspect ({_compass(np.degrees(np.arctan2(row['aspect_sin'], row['aspect_cos'])))}-facing)",
    ),
    FeatureGroup(
        "dist_to_road", ["dist_to_road_m"], lambda row: f"distance to nearest road ({row['dist_to_road_m']:.0f} m)"
    ),
    FeatureGroup(
        "land_cover",
        [],  # patched in by _build_feature_groups() once the real land_cover_* columns are known
        lambda row: "land cover",
    ),
    FeatureGroup(
        "plan_curvature",
        ["plan_curvature"],
        lambda row: "plan curvature (not yet computed — see BUILD_PLAN.md task 1.2)",
    ),
    FeatureGroup(
        "profile_curvature",
        ["profile_curvature"],
        lambda row: "profile curvature (not yet computed — see BUILD_PLAN.md task 1.2)",
    ),
    FeatureGroup(
        "dist_to_fault",
        ["dist_to_fault_km"],
        lambda row: "distance to nearest fault (not yet computed — see BUILD_PLAN.md task 1.2)",
    ),
    FeatureGroup(
        "lithology",
        ["lithology_class"],
        lambda row: "lithology / rock type (not yet available — see BUILD_PLAN.md task 1.4, deferred)",
    ),
]


def _build_feature_groups(all_columns: list[str]) -> list[FeatureGroup]:
    """Patches in the real land_cover_* column list (risk/features.py's LAND_COVER_CLASSES) and
    drops any group whose declared columns aren't actually present (keeps this module correct if
    the feature set ever changes without a matching edit here)."""
    land_cover_cols = [c for c in all_columns if c.startswith("land_cover_")]
    groups = []
    for g in FEATURE_GROUPS:
        cols = land_cover_cols if g.key == "land_cover" else g.columns
        cols = [c for c in cols if c in all_columns]
        if cols:
            groups.append(FeatureGroup(g.key, cols, g.label))
    return groups


def _land_cover_label(row: pd.Series, land_cover_cols: list[str]) -> str:
    active = [c[len("land_cover_") :] for c in land_cover_cols if row.get(c, 0) == 1.0]
    cls = active[0] if active else "unknown"
    return f"land cover ({cls.replace('_', ' ')})"


def compute_shap_margin(model: RiskModel, X: pd.DataFrame) -> np.ndarray:
    """Raw SHAP values (margin/log-odds units, see module docstring), shape (n_rows, n_features),
    column order matching `X.columns`."""
    explainer = shap.TreeExplainer(model.booster)
    explanation = explainer(X)
    return np.asarray(explanation.values)


def attributions_for_rows(X: pd.DataFrame, shap_values: np.ndarray, *, top_n: int = 4) -> list[list[Attribution]]:
    """One `Attribution` list per row of `X`, top `top_n` feature GROUPS by absolute contribution."""
    groups = _build_feature_groups(list(X.columns))
    col_index = {c: i for i, c in enumerate(X.columns)}

    results: list[list[Attribution]] = []
    for row_i in range(len(X)):
        row = X.iloc[row_i]
        row_shap = shap_values[row_i]

        group_contribs: list[tuple[FeatureGroup, float]] = []
        for g in groups:
            total = float(sum(row_shap[col_index[c]] for c in g.columns))
            group_contribs.append((g, total))

        total_abs = sum(abs(c) for _, c in group_contribs) or 1.0  # avoid div-by-zero if all-zero
        group_contribs.sort(key=lambda gc: abs(gc[1]), reverse=True)

        attributions = []
        for g, contrib in group_contribs[:top_n]:
            if g.key == "land_cover":
                plain = _land_cover_label(row, g.columns)
            else:
                plain = g.label(row)
            attributions.append(
                Attribution(
                    feature=g.key,
                    plain_language=plain,
                    contribution=contrib,
                    display_pct=100.0 * contrib / total_abs,
                )
            )
        results.append(attributions)
    return results


def explain_cells(model: RiskModel, cell_ids: list[str], *, top_n: int = 4) -> dict[str, list[Attribution]]:
    """Convenience entry point: top-N attributions for a batch of already-matched cell_ids (see
    `RiskModel.predict_batch`'s `unmatched_cell_ids` — callers should filter to matched ids first,
    same as `risk/model.py` does for prediction)."""
    if not cell_ids:
        return {}
    X = model.terrain_by_cell.loc[cell_ids]
    shap_values = compute_shap_margin(model, X)
    per_row = attributions_for_rows(X, shap_values, top_n=top_n)
    return dict(zip(cell_ids, per_row))
