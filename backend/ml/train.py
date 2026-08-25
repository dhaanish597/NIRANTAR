#!/usr/bin/env python
"""Train the Aizawl terrain-susceptibility XGBoost model (BUILD_PLAN.md task 1.15).

**Read this before trusting any number this script prints.** The realistic scope, forced by what
real data is actually available (not a corner cut for convenience — BUILD_PLAN.md's own risk
register anticipated this: "Landslide inventory too sparse to train a credible model... ship the
threshold engine as primary if ML underperforms"):

  - **56 labeled rows** (14 positive, 42 negative — see `ml/negative_sampling.py`, task 1.14).
    This is not enough data to make any accuracy claim a geologist judge should find persuasive
    on its own; `data/models/eval_report.md` (task 1.16) says so plainly.
  - **Terrain-only.** No verified per-cell historical rainfall or soil-moisture time series
    exists yet (task 1.6/1.7's IMERG/SMAP backfill is blocked on Earthdata GES DISC
    authorization — Required_by_me.md). CellObservation's dynamic fields (rain_1h..72h,
    antecedent_*, soil_moisture) are simply NOT features of this model — not set to a
    placeholder, genuinely absent, because unlike lithology (a legitimate one-time static join
    we haven't done yet) a *dynamic* feature can't be honestly represented by a static NaN
    column. At inference time (`risk/model.py`), the live rainfall signal is NOT ignored — it
    drives `risk/thresholds.py`'s I-D/E-D exceedance ratio, and the fusion rule (task 1.19)
    combines that with this model's terrain-only `p_fail` — so the deployed system's real-time
    risk assessment is not purely static even though this trained artifact is.
  - **`lithology_class` (and `plan_curvature`/`profile_curvature`/`dist_to_fault_km`) are included
    as explicit 100%-missing features**, per the ruling given for task 1.15: XGBoost handles
    missing values natively, so the schema is stable now and these become informative the moment
    task 1.4 (GSI Bhukosh, deliberately deferred) lands, without a retrain-time schema change.
    They currently contribute exactly zero information — a tree can't split on an all-NaN column.

**Spatial block CV, and why it is weaker than "by district" (BUILD_PLAN.md's own literal words
for task 1.15) implies:** there is only one AOI with a terrain grid (Aizawl), so there is no
second district to hold out. This script instead splits Aizawl's own extent into four spatial
quadrants (NW/NE/SW/SE, by the median centroid lat/lon of the labeled cells) and does leave-one-
quadrant-out CV. This is a real spatial split (it does prevent nearby cells from appearing in
both train and test), but it is quadrant-level, not district-level, and with only 56 labeled
cells each fold is very small — treat every fold metric as illustrative, not a stable estimate.

Usage:
    python -m ml.train --aoi aizawl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import average_precision_score, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from ml import holdout  # noqa: E402
from ml.negative_sampling import TERRAIN_FEATURE_COLUMNS, build_training_table  # noqa: E402

MODEL_VERSION = "xgb-terrain-v1"

MODEL_DIR = REPO_ROOT / "data" / "models"
MODEL_PATH = MODEL_DIR / "xgb_terrain_v1.json"
METADATA_PATH = MODEL_DIR / "model_metadata.json"
CV_PREDICTIONS_PATH = MODEL_DIR / "cv_predictions.csv"

# The one land-cover class set actually possible from scripts/build_grid.py's ESA WorldCover
# join (see its LANDCOVER_CLASSES dict) — one-hot encoded rather than passed as a pandas
# categorical dtype so risk/model.py doesn't need to reconstruct training-time category codes to
# get consistent columns; it just reindexes to this fixed list and fills missing indicators 0.
LAND_COVER_CLASSES = [
    "tree_cover",
    "shrubland",
    "grassland",
    "cropland",
    "built_up",
    "bare_sparse_vegetation",
    "snow_ice",
    "water",
    "herbaceous_wetland",
    "mangroves",
    "moss_lichen",
]

# Conservative, small-n-appropriate hyperparameters — NOT tuned via a CV grid search (56 labeled
# rows is too little data to do that credibly; a grid search would just fit noise). Shallow trees
# and a min_child_weight above 1 keep a single positive cell from being memorized as its own leaf.
XGB_PARAMS = dict(
    max_depth=3,
    n_estimators=50,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=3,
    reg_lambda=1.0,
    eval_metric="logloss",
    n_jobs=1,  # determinism (CLAUDE.md rule 13) — avoid multi-threaded histogram-build variance
)


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds aspect_sin/aspect_cos (circular encoding of aspect_mean_deg — 359deg and 1deg are
    nearly identical compass directions, which a raw degree value would hide from the model) and
    one-hot land-cover indicators. Returns df with the final FEATURE_COLUMNS present."""
    out = df.copy()
    aspect_rad = np.radians(out["aspect_mean_deg"].astype(float))
    out["aspect_sin"] = np.sin(aspect_rad)
    out["aspect_cos"] = np.cos(aspect_rad)

    for cls in LAND_COVER_CLASSES:
        out[f"land_cover_{cls}"] = (out["land_cover_class"] == cls).astype(float)

    for col in ("plan_curvature", "profile_curvature", "dist_to_fault_km", "lithology_class"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    return out


def feature_columns() -> list[str]:
    numeric = [c for c in TERRAIN_FEATURE_COLUMNS if c not in ("aspect_mean_deg", "land_cover_class")]
    return numeric + ["aspect_sin", "aspect_cos"] + [f"land_cover_{cls}" for cls in LAND_COVER_CLASSES]


def assign_spatial_blocks(df: pd.DataFrame) -> pd.Series:
    """NW/NE/SW/SE quadrant, split at the median centroid lat/lon of the labeled cells
    themselves (not the whole AOI grid — the labeled sample is what CV actually partitions)."""
    lat_med = df["centroid_lat"].median()
    lon_med = df["centroid_lon"].median()
    ns = np.where(df["centroid_lat"] >= lat_med, "N", "S")
    ew = np.where(df["centroid_lon"] >= lon_med, "E", "W")
    return pd.Series([n + e for n, e in zip(ns, ew)], index=df.index, name="block")


def _fit_model(X: pd.DataFrame, y: pd.Series, seed: int) -> xgb.XGBClassifier:
    model = xgb.XGBClassifier(random_state=seed, **XGB_PARAMS)
    model.fit(X, y)
    return model


def spatial_block_cv(df: pd.DataFrame, cols: list[str], seed: int) -> tuple[pd.Series, list[dict]]:
    """Leave-one-quadrant-out CV. Returns (out-of-fold predicted probabilities indexed like `df`,
    per-fold report list). A fold whose TRAINING partition has only one class can't fit a binary
    classifier at all — skipped, reported as such rather than crashing or fabricating a number."""
    blocks = assign_spatial_blocks(df)
    oof = pd.Series(np.nan, index=df.index)
    reports: list[dict] = []

    for block in sorted(blocks.unique()):
        test_mask = blocks == block
        train_mask = ~test_mask
        y_train = df.loc[train_mask, "label"]

        report = {
            "block": block,
            "n_train": int(train_mask.sum()),
            "n_test": int(test_mask.sum()),
            "n_test_positive": int(df.loc[test_mask, "label"].sum()),
        }

        if y_train.nunique() < 2:
            report["skipped"] = "training partition has only one class — cannot fit"
            reports.append(report)
            continue

        model = _fit_model(df.loc[train_mask, cols], y_train, seed)
        proba = model.predict_proba(df.loc[test_mask, cols])[:, 1]
        oof.loc[test_mask] = proba
        report["skipped"] = None
        reports.append(report)

    return oof, reports


def train(aoi_id: str = "aizawl", *, seed: int = 42) -> dict:
    print(f"Building training table for {aoi_id} ...")
    table = build_training_table(aoi_id, seed=seed)
    table = engineer_features(table)
    cols = feature_columns()

    n_pos, n_neg = int((table["label"] == 1).sum()), int((table["label"] == 0).sum())
    print(f"Training table: {len(table)} rows ({n_pos} positive, {n_neg} negative)")

    # Belt-and-suspenders leakage check (task 1.13) — the training TABLE is built from cells, not
    # the raw event inventory, but its positive labels trace back to inventory rows that must
    # already be clean. Re-derive the corresponding date/state columns is out of scope here (the
    # table doesn't carry them) — this assertion instead re-confirms the *inventory* is clean at
    # train time, which is what actually matters (build_training_table calls exclude_held_out
    # internally; this just proves that call path is exercised, not silently bypassed).
    inv_path = REPO_ROOT / "data" / "static" / "ner_inventory.csv"
    if inv_path.is_file():
        inv = pd.read_csv(inv_path)
        holdout.assert_no_leakage(holdout.exclude_held_out(inv))

    print("Running spatial block CV (leave-one-quadrant-out) ...")
    oof, fold_reports = spatial_block_cv(table, cols, seed)
    for r in fold_reports:
        print(f"  block {r['block']}: n_train={r['n_train']} n_test={r['n_test']} "
              f"n_test_pos={r['n_test_positive']} skipped={r['skipped']}")

    n_scored = int(oof.notna().sum())
    print(f"Out-of-fold predictions available for {n_scored}/{len(table)} rows")

    print(f"Fitting final deployed model on all {len(table)} rows ...")
    final_model = _fit_model(table[cols], table["label"], seed)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Save the raw Booster, not the sklearn wrapper (`XGBClassifier.save_model()` raises
    # `TypeError: _estimator_type undefined` on this xgboost/scikit-learn combination — a known
    # sklearn-wrapper-metadata version-skew issue, confirmed by actually hitting it, not assumed).
    # The Booster is also the more portable artifact for risk/model.py to load: no dependency on
    # xgboost's sklearn-compatibility shim at inference time, just `xgb.Booster().load_model()`.
    final_model.get_booster().save_model(str(MODEL_PATH))

    metadata = {
        "model_version": MODEL_VERSION,
        "feature_columns": cols,
        "xgb_params": XGB_PARAMS,
        "seed": seed,
        "aoi_id": aoi_id,
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_total": len(table),
        "n_oof_scored": n_scored,
        "cv_scheme": "leave-one-quadrant-out (NW/NE/SW/SE by median centroid lat/lon)",
        "fold_reports": fold_reports,
        "scope_notes": [
            "terrain-only: no dynamic rainfall/soil-moisture features this pass",
            "lithology_class/plan_curvature/profile_curvature/dist_to_fault_km are 100% missing "
            "this pass, included per the task 1.15 ruling for XGBoost's native missing handling",
            "single-AOI (Aizawl only) and cell-level (not cell-day) — see ml/negative_sampling.py",
        ],
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    cv_out = table[["cell_id", "label", "centroid_lat", "centroid_lon"]].copy()
    cv_out["block"] = assign_spatial_blocks(table)
    cv_out["oof_p_fail"] = oof
    cv_out.to_csv(CV_PREDICTIONS_PATH, index=False)

    print(f"Wrote {MODEL_PATH}, {METADATA_PATH}, {CV_PREDICTIONS_PATH}")

    scored = cv_out.dropna(subset=["oof_p_fail"])
    if scored["label"].nunique() == 2:
        auc = roc_auc_score(scored["label"], scored["oof_p_fail"])
        pr_auc = average_precision_score(scored["label"], scored["oof_p_fail"])
        print(f"Out-of-fold AUC-ROC={auc:.3f}  PR-AUC={pr_auc:.3f}  (n={len(scored)}) "
              "— see data/models/eval_report.md (task 1.16) for the full, honest picture; do not "
              "quote this number in isolation.")
    else:
        print("Out-of-fold predictions do not span both classes — AUC/PR-AUC undefined this run.")

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", default="aizawl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    train(args.aoi, seed=args.seed)


if __name__ == "__main__":
    main()
