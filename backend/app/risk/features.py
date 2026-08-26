"""Shared feature engineering for the terrain-susceptibility model (CLAUDE.md §5 repo layout:
"risk/ <- features, thresholds, model (XGBoost), explain (SHAP)").

This is the ONE place the raw terrain columns from `data/static/<aoi>/cells.gpkg` (task 1.2) get
turned into the numeric feature vector XGBoost actually sees. Both `ml/train.py` (offline
training, task 1.15) and `risk/model.py` (online inference, task 1.17) import from here — a
model trained on one feature-engineering function and served with a different, subtly
inconsistent one is a classic and painful train/serve skew bug; there is exactly one
implementation, not two that are supposed to agree.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The terrain columns cells.gpkg actually carries (scripts/build_grid.py, task 1.2), including
# the four explicit-null columns (task 1.2's scope cuts + task 1.4's deferral) — kept as real
# feature inputs (see LAND_COVER_CLASSES / feature_columns() below for how they're encoded),
# not silently dropped.
TERRAIN_FEATURE_COLUMNS = [
    "elevation_m",
    "elevation_min_m",
    "elevation_max_m",
    "slope_mean_deg",
    "slope_max_deg",
    "twi_mean",
    "relief_m",
    "aspect_mean_deg",
    "dist_to_road_m",
    "land_cover_class",
    "plan_curvature",
    "profile_curvature",
    "dist_to_fault_km",
    "lithology_class",
]

# The full ESA WorldCover class set scripts/build_grid.py's LANDCOVER_CLASSES dict can produce —
# one-hot encoded rather than passed as a pandas categorical dtype so inference doesn't need to
# reconstruct training-time category codes; it just reindexes to this fixed list and fills
# missing indicators with 0.
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


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Adds aspect_sin/aspect_cos (circular encoding of aspect_mean_deg — 359deg and 1deg are
    nearly identical compass directions, which a raw degree value would hide from the model) and
    one-hot land-cover indicators. Casts the explicit-null columns to numeric NaN (they may arrive
    as Python `None`/object dtype from cells.gpkg). Returns a copy; does not mutate `df`."""
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
    """The final, ordered list of numeric columns fed to XGBoost — the exact column order the
    trained model's `data/models/model_metadata.json` records and inference must reproduce."""
    numeric = [c for c in TERRAIN_FEATURE_COLUMNS if c not in ("aspect_mean_deg", "land_cover_class")]
    return numeric + ["aspect_sin", "aspect_cos"] + [f"land_cover_{cls}" for cls in LAND_COVER_CLASSES]
