# Aizawl terrain-susceptibility model — evaluation report

Model version: `xgb-terrain-v1` | AOI: `aizawl` | seed: `42`

## 0. Read this first

BUILD_PLAN.md's own risk register anticipated this outcome: *"Landslide inventory too sparse to train a credible model... Ship the threshold engine [`risk/thresholds.py`, task 1.11, the published NE Himalaya I-D/E-D rainfall curves] as the primary if ML underperforms; present ML as an enhancement layer with measured numbers."* That is exactly the situation below: **56 labeled cells (14 positive, 42 negative) from one AOI** is not enough data to support a headline accuracy claim, and this report does not make one. `risk/thresholds.py` — a physically-grounded, published, cited formula — remains the credible primary signal; this XGBoost model is an honestly-scoped exploratory layer fused with it (task 1.19), not a replacement.

**This model is terrain-only.** No verified per-cell historical rainfall or soil-moisture time series exists yet (task 1.6/1.7's IMERG/SMAP backfill remains blocked on Earthdata GES DISC authorization — see `Required_by_me.md`), so LHASA v2's dynamic features are genuinely absent from this artifact, not defaulted to a placeholder. At inference (`risk/model.py`), the live rainfall signal still reaches the system through `risk/thresholds.py`'s exceedance ratio and the task-1.19 fusion rule — the *deployed* system is not purely static even though this trained artifact is.

## 1. Data provenance and source counts

- Raw COOLR export (global scope): **14,753 rows**
- India rows: **1,741**
- NER rows (8 states): **504** — Manipur 102, Assam 94, Nagaland 91, Arunachal Pradesh 74, Sikkim 56, Mizoram 41, Meghalaya 38, Tripura 8
- Within the Aizawl AOI bounding box: **19**
- Trusted `location_accuracy` (exact/1km/5km — see task 1.12's recorded distribution for why coarser rows are excluded): **17**
- Aizawl terrain grid: **2,912 cells** (212 with no valid DEM pixel, excluded entirely; 1619 within the task-1.13 spatial buffer of the Aizawl-2024 anchors, excluded from negative sampling only — see `ml/negative_sampling.py`)
- **GSI Bhukosh (lithology) join: not attempted this pass** — task 1.4 is deliberately deferred by prior user decision (see BUILD_PLAN.md). `lithology_class` is included as an explicit 100%-missing feature (see below), not silently omitted.

- Final labeled training table: **56 cells** (14 positive, 42 negative, 3.0:1 ratio)

## 2. Single-AOI and cell-level scope (say this before a judge asks)

Only Aizawl has a built terrain grid (`data/static/aizawl/cells.gpkg`) — no other AOI has task 1.2's grid yet, so nothing below validates against Manipur, Kerala, or Sikkim terrain; this is an Aizawl-only susceptibility model. Spatial cross-validation is therefore leave-one-**quadrant**-out (NW/NE/SW/SE by median centroid of the labeled cells), not leave-one-**district**-out — there is no second district to hold out. This is a real spatial split (nearby cells never appear in both train and test within a fold) but a materially weaker one than "by district" implies, and every fold is tiny (12-16 cells). Treat every metric below as illustrative, not a stable estimate.

Sampling is also at the **cell level**, not the **cell-day** level BUILD_PLAN.md's task 1.14 literally asks for — there is no verified per-day rainfall history for any Aizawl cell yet, so "no recorded failure" is evaluated statically per cell, not dynamically per cell-day.

## 3. Out-of-fold metrics

- **AUC-ROC: 0.696** (n=56, out-of-fold across 4 spatial-quadrant folds)
- **PR-AUC (average precision): 0.500** (baseline for a random classifier at this class balance is 0.250)

For plain-language reference: an AUC-ROC of 0.696 means, informally, that a randomly chosen failed cell scored higher than a randomly chosen non-failed cell about 70% of the time in held-out spatial folds — meaningfully better than a coin flip (50%), nowhere near a number to lead a pitch with given the n.

## 4. Calibration

Presented as a table, not a plotted curve — this is a committed markdown document, and 56 points split across a handful of bins is better read as numbers than as a sparse scatter plot.

| Predicted p_fail bin | n | mean predicted | observed rate |
|---|---|---|---|
| (-0.001, 0.25] | 45 | 0.146 | 0.200 |
| (0.25, 0.5] | 5 | 0.344 | 0.200 |
| (0.5, 0.75] | 6 | 0.541 | 0.667 |

## 5. Confusion matrix at three operating thresholds

| Threshold | TP | FP | FN | TN |
|---|---|---|---|---|
| 0.30 | 5 | 5 | 9 | 37 |
| 0.50 | 4 | 2 | 10 | 40 |
| 0.70 | 0 | 0 | 14 | 42 |

## 6. False-alarm-cost table

BUILD_PLAN.md asks for "alarms/season vs. missed events" — that literal framing assumes a per-day/per-season time series this cell-level dataset does not have (see §2). Reinterpreted honestly at the granularity this data actually supports: **cells flagged** (out of all 56 labeled cells) vs. **known historical events missed** (false negatives among the 14 positive cells), at each candidate operating threshold.

| Threshold | Cells flagged | % of labeled cells flagged | Known events caught | Known events missed |
|---|---|---|---|---|
| 0.30 | 10 | 17.9% | 5/14 | 9/14 |
| 0.50 | 6 | 10.7% | 4/14 | 10/14 |
| 0.70 | 0 | 0.0% | 0/14 | 14/14 |

Lower thresholds catch more known events at the cost of flagging more cells (higher false-alarm rate); this is precisely the tradeoff the false-alarm-cost slider (BUILD_PLAN.md task 5.6) is meant to expose to a DDMA officer, once wired to these numbers rather than a placeholder.

## 7. Fusion with the threshold engine (task 1.19)

`risk/fusion.py` combines this model's `p_fail` with `risk/thresholds.py`'s I-D/E-D exceedance ratio via `max(p_fail, min(1.0, exceedance_ratio))` — whichever signal is more concerned wins. Rationale: for a life-safety system, under-alerting is the costlier error, and `max` stays fully explainable to a judge ("whichever method is more concerned wins") without requiring a justification for arbitrary blend weights. Given how little labeled data underwrites this model (§0), the threshold engine — a published, cited formula — should be treated as the load-bearing half of that `max` in practice, not a fallback used to allay some hypothetical model failure.

## 8. Feature set actually used

`elevation_m`, `elevation_min_m`, `elevation_max_m`, `slope_mean_deg`, `slope_max_deg`, `twi_mean`, `relief_m`, `dist_to_road_m`, `plan_curvature`, `profile_curvature`, `dist_to_fault_km`, `lithology_class`, `aspect_sin`, `aspect_cos`, `land_cover_tree_cover`, `land_cover_shrubland`, `land_cover_grassland`, `land_cover_cropland`, `land_cover_built_up`, `land_cover_bare_sparse_vegetation`, `land_cover_snow_ice`, `land_cover_water`, `land_cover_herbaceous_wetland`, `land_cover_mangroves`, `land_cover_moss_lichen`

`lithology_class`, `plan_curvature`, `profile_curvature`, `dist_to_fault_km` are 100% missing this pass (task 1.2's documented scope cuts + task 1.4's deferral) — included per the task 1.15 ruling so XGBoost's native missing-value handling can use them the moment they land, without a retrain-time schema change. They contribute zero information in the model evaluated above; a retrain once lithology lands is a documented follow-up, not an afterthought.

## 9. Reproducing this report

```
cd backend
.venv/Scripts/python.exe -m ml.build_inventory
.venv/Scripts/python.exe -m ml.train --aoi aizawl
.venv/Scripts/python.exe -m ml.evaluate --aoi aizawl
```
