"""XGBoost inference wrapper (BUILD_PLAN.md task 1.17).

Loads the artifact `ml/train.py` (task 1.15) wrote — `data/models/xgb_terrain_v1.json` (a raw
XGBoost Booster, not the sklearn wrapper — see that module's docstring for why) plus
`data/models/model_metadata.json` — and the AOI's terrain grid (`data/static/<aoi>/cells.gpkg`),
engineered through the SAME `app.risk.features.engineer_features()` training used (no train/serve
skew: one feature-engineering implementation, imported by both sides).

**`p_fail` on the returned `CellRisk` is the task-1.19 FUSED value** —
`risk/fusion.py`'s `max(ml_p_fail, capped threshold_exceedance)` — not the raw ML probability in
isolation. `threshold_exceedance` is still reported on `CellRisk` separately (per the Appendix A
schema) so a caller/UI can show both halves of the fusion, not just the combined result.

**Confidence** is a simple, honestly-labeled heuristic — 1 minus the normalized binary entropy of
the FUSED probability (confidence=1 at p=0 or p=1, confidence=0 at p=0.5). This is NOT a
statistical confidence interval; with only 56 labeled training cells (see `data/models/
eval_report.md`), a rigorous uncertainty quantification would itself be a false precision claim.
It answers "how decisive is the final reported number," nothing more.

**SHAP attributions (task 1.18) are included by default** — `predict_batch()` calls
`risk/explain.py`'s `explain_cells()` for the matched cells unless `include_attributions=False`;
they describe the ML model's raw margin contributions (see `risk/explain.py`), not the fused
probability, since SHAP's additive decomposition only applies to the model it was computed
against.

**Batched per-AOI**: `predict_cell_risks()` takes a whole `ObservationFrame`'s cells at once
(matching CLAUDE.md §5's "batched per-AOI" requirement) rather than one cell at a time — the
terrain grid and model are loaded once and reused across the batch.

**Not wired into `pipeline.py` this pass** — same documented pattern as `ingest/live/imerg.py`
(task 1.6): CLAUDE.md's Current State already flags that the live pipeline's cell_ids are still
the synthetic `aizawl_{row}{col}` stub convention, not the real `cells.gpkg` grid's
`aizawl_{row:03d}_{col:03d}` ids — wiring this into `pipeline.py` needs that convention unified
first, a separate Phase 1C/2 task, not part of 1.12-1.19.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import xgboost as xgb

from app.risk.features import engineer_features, feature_columns
from app.risk.fusion import fuse_p_fail
from app.risk.thresholds import threshold_exceedance_ratio
from app.schemas.ingest import CellObservation
from app.schemas.risk import CellRisk

REPO_ROOT = Path(__file__).resolve().parents[3]

MODEL_DIR = REPO_ROOT / "data" / "models"
MODEL_PATH = MODEL_DIR / "xgb_terrain_v1.json"
METADATA_PATH = MODEL_DIR / "model_metadata.json"


class ModelNotTrainedError(FileNotFoundError):
    """Raised when data/models/xgb_terrain_v1.json or model_metadata.json is missing — the
    actionable fix is always `python -m ml.train --aoi <aoi>`, not a silent fallback, since a
    silently-stubbed p_fail would be exactly the kind of unmeasured claim CLAUDE.md rule 1 bans."""


class RiskModel:
    """Holds one loaded Booster + its metadata + one AOI's engineered terrain feature table.
    Construct once per AOI and reuse — `load()` is the cheap path for repeated calls."""

    def __init__(self, booster: xgb.Booster, metadata: dict, terrain_by_cell: pd.DataFrame):
        self.booster = booster
        self.metadata = metadata
        self.terrain_by_cell = terrain_by_cell  # indexed by cell_id, columns = feature_columns()

    @property
    def model_version(self) -> str:
        return self.metadata["model_version"]

    @classmethod
    def load(cls, aoi_id: str) -> "RiskModel":
        if not MODEL_PATH.is_file() or not METADATA_PATH.is_file():
            raise ModelNotTrainedError(
                f"{MODEL_PATH} / {METADATA_PATH} not found — run `python -m ml.train --aoi {aoi_id}` "
                "first (see BUILD_PLAN.md task 1.15)."
            )
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

        booster = xgb.Booster()
        booster.load_model(str(MODEL_PATH))

        cells_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
        if not cells_path.is_file():
            raise FileNotFoundError(
                f"{cells_path} not found — run `python scripts/build_grid.py --aoi {aoi_id}` first"
            )
        cells = gpd.read_file(cells_path)
        # Cells with no valid DEM pixel (task 1.2 — 212 of Aizawl's 2,912) carry entirely null
        # core terrain columns. XGBoost would still happily predict on them (native missing-value
        # handling), but a "confident-looking" p_fail for a cell we structurally have zero real
        # terrain data about is exactly the kind of unearned-precision claim CLAUDE.md rule 6
        # warns against — dropped here so they behave like any other unmatched cell_id (reported,
        # not fabricated a risk value), consistent with ml/negative_sampling.py excluding the same
        # cells "from everything."
        has_terrain = cells["slope_mean_deg"].notna() & cells["elevation_m"].notna()
        cells = cells[has_terrain]
        cells = engineer_features(cells)
        terrain_by_cell = cells.set_index("cell_id")[feature_columns()]

        return cls(booster, metadata, terrain_by_cell)

    def predict_batch(
        self, observations: list[CellObservation], *, include_attributions: bool = True
    ) -> tuple[list[CellRisk], list[str]]:
        """Returns (risks, unmatched_cell_ids). A cell_id with no terrain row (e.g. an AOI whose
        grid doesn't cover it, a no-valid-DEM-pixel cell, or a stub/synthetic cell_id — see module
        docstring) is skipped, not fabricated a p_fail; its id is reported in `unmatched_cell_ids`
        so a caller can log it.

        `CellRisk.p_fail` is the task-1.19 FUSED value (`risk/fusion.py`'s
        `max(ml_p_fail, capped threshold_exceedance)`), not the raw ML probability — see
        `risk/fusion.py`'s docstring for the one-sentence rationale. `confidence` describes the
        decisiveness of this final, fused value (the number actually shown alongside it), not the
        ML model in isolation.

        `include_attributions=False` skips the SHAP computation (task 1.18) — useful for callers
        that only need p_fail/threshold_exceedance and want to avoid the extra cost."""
        if not observations:
            return [], []

        obs_by_id = {obs.cell_id: obs for obs in observations}
        matched_ids = [cid for cid in obs_by_id if cid in self.terrain_by_cell.index]
        unmatched_ids = [cid for cid in obs_by_id if cid not in self.terrain_by_cell.index]

        if not matched_ids:
            return [], unmatched_ids

        X = self.terrain_by_cell.loc[matched_ids]
        dmatrix = xgb.DMatrix(X, feature_names=list(X.columns))
        ml_p_fail_raw = self.booster.predict(dmatrix)

        attributions_by_cell: dict[str, list] = {}
        if include_attributions:
            # Local import — app.risk.explain imports RiskModel from this module, so importing it
            # at module scope here would be circular. A function-local import is the standard,
            # narrow way around a two-module mutual dependency like this one.
            from app.risk.explain import explain_cells

            attributions_by_cell = explain_cells(self, matched_ids)

        risks: list[CellRisk] = []
        for cell_id, ml_p_fail in zip(matched_ids, ml_p_fail_raw):
            obs = obs_by_id[cell_id]
            exceedance = threshold_exceedance_ratio(obs)
            fused_p_fail = fuse_p_fail(float(ml_p_fail), float(exceedance))
            risks.append(
                CellRisk(
                    cell_id=cell_id,
                    p_fail=fused_p_fail,
                    threshold_exceedance=float(exceedance),
                    confidence=_confidence_from_probability(fused_p_fail),
                    attributions=attributions_by_cell.get(cell_id, []),
                    model_version=self.model_version,
                )
            )
        return risks, unmatched_ids


def _confidence_from_probability(p: float) -> float:
    """1 - normalized binary entropy. confidence=1 at p in {0,1} (maximally decisive), confidence=0
    at p=0.5 (maximally undecided). A simple heuristic, not a statistical confidence interval —
    see module docstring."""
    eps = 1e-9
    p_clamped = min(max(p, eps), 1.0 - eps)
    entropy_bits = -(p_clamped * math.log2(p_clamped) + (1 - p_clamped) * math.log2(1 - p_clamped))
    return 1.0 - entropy_bits  # entropy_bits in [0, 1] for a binary variable


_MODEL_CACHE: dict[str, RiskModel] = {}


def get_model(aoi_id: str) -> RiskModel:
    """Process-wide cache — avoids re-reading cells.gpkg/the model file on every tick."""
    if aoi_id not in _MODEL_CACHE:
        _MODEL_CACHE[aoi_id] = RiskModel.load(aoi_id)
    return _MODEL_CACHE[aoi_id]


def predict_cell_risks(observations: list[CellObservation], aoi_id: str) -> list[CellRisk]:
    """The module-level convenience entry point BUILD_PLAN.md task 1.17 describes: batched
    inference for one AOI's worth of observations in one call."""
    model = get_model(aoi_id)
    risks, _unmatched = model.predict_batch(observations)
    return risks
