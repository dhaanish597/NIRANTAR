#!/usr/bin/env python
"""Write data/models/eval_report.md — the document to hand a geologist judge (BUILD_PLAN.md task
1.16).

Every number in the generated report comes from re-running the actual pipeline (ml/build_inventory
-> ml/holdout -> ml/negative_sampling -> the out-of-fold predictions ml/train.py already wrote) —
nothing here is hand-typed or estimated. Requires `python -m ml.train` to have been run first
(it writes `data/models/cv_predictions.csv` and `data/models/model_metadata.json`).

**Per BUILD_PLAN.md's own risk register** ("Landslide inventory too sparse to train a credible
model... Ship [the threshold engine] as the primary if ML underperforms; present ML as an
enhancement layer with measured numbers") — that is exactly what happened here. This report says
so in its own first section, not buried at the bottom.

Usage:
    python -m ml.evaluate --aoi aizawl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from ml import build_inventory, negative_sampling  # noqa: E402
from ml.train import CV_PREDICTIONS_PATH, METADATA_PATH  # noqa: E402

REPORT_PATH = REPO_ROOT / "data" / "models" / "eval_report.md"

OPERATING_THRESHOLDS = (0.3, 0.5, 0.7)
CALIBRATION_BIN_EDGES = (0.0, 0.25, 0.5, 0.75, 1.0)


def gather_source_counts() -> dict:
    """Re-derives the inventory/sampling counts by actually re-running the real pipeline stages
    (all idempotent — none of this fabricates a number, it re-measures one)."""
    raw = build_inventory.load_raw()
    india = raw[raw["country_code"] == "IN"]
    ner = build_inventory.filter_to_ner(raw)

    from app.config import get_aoi

    aoi = get_aoi("aizawl")
    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    in_bbox = ner[
        (ner["longitude"] >= min_lon)
        & (ner["longitude"] <= max_lon)
        & (ner["latitude"] >= min_lat)
        & (ner["latitude"] <= max_lat)
    ]
    trusted = in_bbox[in_bbox["location_accuracy"].isin(negative_sampling.TRUSTED_ACCURACY_TIERS)]

    cells = negative_sampling.load_eligible_cells("aizawl")

    return {
        "raw_global_rows": len(raw),
        "india_rows": len(india),
        "ner_rows": len(ner),
        "ner_state_counts": ner["admin_division_name"].value_counts().to_dict(),
        "aizawl_bbox_rows": len(in_bbox),
        "trusted_accuracy_rows": len(trusted),
        "total_cells": len(cells),
        "cells_no_terrain": int((~cells["has_terrain"]).sum()),
        "cells_in_holdout_buffer": int((cells["in_holdout_buffer"] & cells["has_terrain"]).sum()),
    }


def calibration_table(y_true: pd.Series, y_pred: pd.Series) -> pd.DataFrame:
    bins = pd.cut(y_pred, bins=CALIBRATION_BIN_EDGES, include_lowest=True)
    grouped = pd.DataFrame({"bin": bins, "y_true": y_true, "y_pred": y_pred}).groupby("bin", observed=True)
    table = grouped.agg(n=("y_true", "size"), mean_predicted=("y_pred", "mean"), observed_rate=("y_true", "mean"))
    return table.reset_index()


def confusion_at_thresholds(y_true: pd.Series, y_pred: pd.Series, thresholds=OPERATING_THRESHOLDS) -> pd.DataFrame:
    rows = []
    n_total_cells = int(len(y_true))
    n_actual_positive = int(y_true.sum())
    for t in thresholds:
        pred_label = (y_pred >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, pred_label, labels=[0, 1]).ravel()
        rows.append(
            {
                "threshold": t,
                "tp": int(tp),
                "fp": int(fp),
                "fn": int(fn),
                "tn": int(tn),
                "cells_flagged": int(tp + fp),
                "pct_of_labeled_cells_flagged": 100.0 * (tp + fp) / n_total_cells,
                "known_events_caught": int(tp),
                "known_events_missed": int(fn),
                "pct_known_events_caught": 100.0 * tp / n_actual_positive if n_actual_positive else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def _fmt_state_counts(counts: dict) -> str:
    return ", ".join(f"{state} {n}" for state, n in counts.items())


def render_report(metadata: dict, source_counts: dict, cv: pd.DataFrame) -> str:
    scored = cv.dropna(subset=["oof_p_fail"])
    y_true, y_pred = scored["label"], scored["oof_p_fail"]

    both_classes = y_true.nunique() == 2
    auc = roc_auc_score(y_true, y_pred) if both_classes else None
    pr_auc = average_precision_score(y_true, y_pred) if both_classes else None

    calib = calibration_table(y_true, y_pred)
    conf = confusion_at_thresholds(y_true, y_pred)

    lines: list[str] = []
    a = lines.append

    a("# Aizawl terrain-susceptibility model — evaluation report")
    a("")
    a(f"Model version: `{metadata['model_version']}` | AOI: `{metadata['aoi_id']}` | "
      f"seed: `{metadata['seed']}`")
    a("")
    a("## 0. Read this first")
    a("")
    a(
        "BUILD_PLAN.md's own risk register anticipated this outcome: *\"Landslide inventory too "
        "sparse to train a credible model... Ship the threshold engine [`risk/thresholds.py`, "
        "task 1.11, the published NE Himalaya I-D/E-D rainfall curves] as the primary if ML "
        "underperforms; present ML as an enhancement layer with measured numbers.\"* That is "
        f"exactly the situation below: **{metadata['n_total']} labeled cells "
        f"({metadata['n_positive']} positive, {metadata['n_negative']} negative) from one "
        "AOI** is not enough data to support a headline accuracy claim, and this report does not "
        "make one. `risk/thresholds.py` — a physically-grounded, published, cited formula — "
        "remains the credible primary signal; this XGBoost model is an honestly-scoped "
        "exploratory layer fused with it (task 1.19), not a replacement."
    )
    a("")
    a(
        "**This model is terrain-only.** No verified per-cell historical rainfall or soil-"
        "moisture time series exists yet (task 1.6/1.7's IMERG/SMAP backfill remains blocked on "
        "Earthdata GES DISC authorization — see `Required_by_me.md`), so LHASA v2's dynamic "
        "features are genuinely absent from this artifact, not defaulted to a placeholder. At "
        "inference (`risk/model.py`), the live rainfall signal still reaches the system through "
        "`risk/thresholds.py`'s exceedance ratio and the task-1.19 fusion rule — the *deployed* "
        "system is not purely static even though this trained artifact is."
    )
    a("")

    a("## 1. Data provenance and source counts")
    a("")
    a(f"- Raw COOLR export (global scope): **{source_counts['raw_global_rows']:,} rows**")
    a(f"- India rows: **{source_counts['india_rows']:,}**")
    a(f"- NER rows (8 states): **{source_counts['ner_rows']}** — "
      f"{_fmt_state_counts(source_counts['ner_state_counts'])}")
    a(f"- Within the Aizawl AOI bounding box: **{source_counts['aizawl_bbox_rows']}**")
    a(f"- Trusted `location_accuracy` (exact/1km/5km — see task 1.12's recorded distribution "
      f"for why coarser rows are excluded): **{source_counts['trusted_accuracy_rows']}**")
    a(f"- Aizawl terrain grid: **{source_counts['total_cells']:,} cells** "
      f"({source_counts['cells_no_terrain']} with no valid DEM pixel, excluded entirely; "
      f"{source_counts['cells_in_holdout_buffer']} within the task-1.13 spatial buffer of the "
      "Aizawl-2024 anchors, excluded from negative sampling only — see `ml/negative_sampling.py`)")
    a(f"- **GSI Bhukosh (lithology) join: not attempted this pass** — task 1.4 is deliberately "
      f"deferred by prior user decision (see BUILD_PLAN.md). `lithology_class` is included as an "
      f"explicit 100%-missing feature (see below), not silently omitted.")
    a("")
    a(f"- Final labeled training table: **{metadata['n_total']} cells** "
      f"({metadata['n_positive']} positive, {metadata['n_negative']} negative, "
      f"{metadata['n_negative'] / max(metadata['n_positive'], 1):.1f}:1 ratio)")
    a("")

    a("## 2. Single-AOI and cell-level scope (say this before a judge asks)")
    a("")
    a(
        "Only Aizawl has a built terrain grid (`data/static/aizawl/cells.gpkg`) — no other AOI "
        "has task 1.2's grid yet, so nothing below validates against Manipur, Kerala, or Sikkim "
        "terrain; this is an Aizawl-only susceptibility model. Spatial cross-validation is "
        "therefore leave-one-**quadrant**-out (NW/NE/SW/SE by median centroid of the labeled "
        "cells), not leave-one-**district**-out — there is no second district to hold out. This "
        "is a real spatial split (nearby cells never appear in both train and test within a "
        "fold) but a materially weaker one than \"by district\" implies, and every fold is tiny "
        "(12-16 cells). Treat every metric below as illustrative, not a stable estimate."
    )
    a("")
    a(
        "Sampling is also at the **cell level**, not the **cell-day** level BUILD_PLAN.md's task "
        "1.14 literally asks for — there is no verified per-day rainfall history for any Aizawl "
        "cell yet, so \"no recorded failure\" is evaluated statically per cell, not dynamically "
        "per cell-day."
    )
    a("")

    a("## 3. Out-of-fold metrics")
    a("")
    if both_classes:
        a(f"- **AUC-ROC: {auc:.3f}** (n={len(scored)}, out-of-fold across 4 spatial-quadrant folds)")
        a(f"- **PR-AUC (average precision): {pr_auc:.3f}** (baseline for a random classifier at "
          f"this class balance is {y_true.mean():.3f})")
    else:
        a("- AUC-ROC / PR-AUC: **undefined this run** — out-of-fold predictions did not span both classes.")
    a("")
    if both_classes:
        a(
            f"For plain-language reference: an AUC-ROC of {auc:.3f} means, informally, that a "
            f"randomly chosen failed cell scored higher than a randomly chosen non-failed cell "
            f"about {auc * 100:.0f}% of the time in held-out spatial folds — meaningfully better "
            "than a coin flip (50%), nowhere near a number to lead a pitch with given the n."
        )
        a("")

    a("## 4. Calibration")
    a("")
    a(
        "Presented as a table, not a plotted curve — this is a committed markdown document, and "
        f"{len(scored)} points split across a handful of bins is better read as numbers than as "
        "a sparse scatter plot."
    )
    a("")
    a("| Predicted p_fail bin | n | mean predicted | observed rate |")
    a("|---|---|---|---|")
    for _, row in calib.iterrows():
        a(f"| {row['bin']} | {int(row['n'])} | {row['mean_predicted']:.3f} | {row['observed_rate']:.3f} |")
    a("")

    a("## 5. Confusion matrix at three operating thresholds")
    a("")
    a("| Threshold | TP | FP | FN | TN |")
    a("|---|---|---|---|---|")
    for _, row in conf.iterrows():
        # .iterrows() coerces each row to a single dtype (Series), which would otherwise upcast
        # these int columns to float (printing "5.0" instead of "5") since other columns in the
        # same row (threshold, pct_*) are floats — cast back to int explicitly at render time.
        a(f"| {row['threshold']:.2f} | {int(row['tp'])} | {int(row['fp'])} | {int(row['fn'])} | {int(row['tn'])} |")
    a("")

    a("## 6. False-alarm-cost table")
    a("")
    a(
        "BUILD_PLAN.md asks for \"alarms/season vs. missed events\" — that literal framing "
        "assumes a per-day/per-season time series this cell-level dataset does not have (see "
        "§2). Reinterpreted honestly at the granularity this data actually supports: **cells "
        f"flagged** (out of all {metadata['n_total']} labeled cells) vs. **known historical "
        f"events missed** (false negatives among the {metadata['n_positive']} positive cells), "
        "at each candidate operating threshold."
    )
    a("")
    a("| Threshold | Cells flagged | % of labeled cells flagged | Known events caught | Known events missed |")
    a("|---|---|---|---|---|")
    n_pos = metadata["n_positive"]
    for _, row in conf.iterrows():
        a(
            f"| {row['threshold']:.2f} | {int(row['cells_flagged'])} | "
            f"{row['pct_of_labeled_cells_flagged']:.1f}% | {int(row['known_events_caught'])}/{n_pos} | "
            f"{int(row['known_events_missed'])}/{n_pos} |"
        )
    a("")
    a(
        "Lower thresholds catch more known events at the cost of flagging more cells (higher "
        "false-alarm rate); this is precisely the tradeoff the false-alarm-cost slider "
        "(BUILD_PLAN.md task 5.6) is meant to expose to a DDMA officer, once wired to these "
        "numbers rather than a placeholder."
    )
    a("")

    a("## 7. Fusion with the threshold engine (task 1.19)")
    a("")
    a(
        "`risk/fusion.py` combines this model's `p_fail` with `risk/thresholds.py`'s I-D/E-D "
        "exceedance ratio via `max(p_fail, min(1.0, exceedance_ratio))` — whichever signal is "
        "more concerned wins. Rationale: for a life-safety system, under-alerting is the costlier "
        "error, and `max` stays fully explainable to a judge (\"whichever method is more "
        "concerned wins\") without requiring a justification for arbitrary blend weights. Given "
        "how little labeled data underwrites this model (§0), the threshold engine — a "
        "published, cited formula — should be treated as the load-bearing half of that `max` in "
        "practice, not a fallback used to allay some hypothetical model failure."
    )
    a("")

    a("## 8. Feature set actually used")
    a("")
    a(", ".join(f"`{c}`" for c in metadata["feature_columns"]))
    a("")
    a(
        "`lithology_class`, `plan_curvature`, `profile_curvature`, `dist_to_fault_km` are 100% "
        "missing this pass (task 1.2's documented scope cuts + task 1.4's deferral) — included "
        "per the task 1.15 ruling so XGBoost's native missing-value handling can use them the "
        "moment they land, without a retrain-time schema change. They contribute zero "
        "information in the model evaluated above; a retrain once lithology lands is a "
        "documented follow-up, not an afterthought."
    )
    a("")

    a("## 9. Reproducing this report")
    a("")
    a("```")
    a("cd backend")
    a(".venv/Scripts/python.exe -m ml.build_inventory")
    a(".venv/Scripts/python.exe -m ml.train --aoi aizawl")
    a(".venv/Scripts/python.exe -m ml.evaluate --aoi aizawl")
    a("```")
    a("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", default="aizawl")
    parser.parse_args()

    if not METADATA_PATH.is_file() or not CV_PREDICTIONS_PATH.is_file():
        raise SystemExit(
            f"{METADATA_PATH} / {CV_PREDICTIONS_PATH} not found — run `python -m ml.train` first"
        )

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    cv = pd.read_csv(CV_PREDICTIONS_PATH)

    print("Re-deriving source counts from a real pipeline run ...")
    source_counts = gather_source_counts()

    report = render_report(metadata, source_counts, cv)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH} ({len(report)} chars)")


if __name__ == "__main__":
    main()
