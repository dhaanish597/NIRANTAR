"""Contract tests for ml/evaluate.py (BUILD_PLAN.md task 1.16)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("sklearn")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml import evaluate  # noqa: E402


def _cv_df():
    return pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(10)],
            "label": [1, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            "oof_p_fail": [0.9, 0.6, 0.2, 0.8, 0.4, 0.3, 0.1, 0.05, 0.02, 0.6],
        }
    )


class TestCalibrationTable:
    def test_bins_cover_all_rows(self):
        df = _cv_df()
        table = evaluate.calibration_table(df["label"], df["oof_p_fail"])
        assert table["n"].sum() == len(df)

    def test_mean_predicted_within_bin_range(self):
        df = _cv_df()
        table = evaluate.calibration_table(df["label"], df["oof_p_fail"])
        for _, row in table.iterrows():
            assert 0.0 <= row["mean_predicted"] <= 1.0


class TestConfusionAtThresholds:
    def test_higher_threshold_flags_fewer_or_equal_cells(self):
        df = _cv_df()
        conf = evaluate.confusion_at_thresholds(df["label"], df["oof_p_fail"], thresholds=(0.1, 0.5, 0.9))
        flagged = conf.set_index("threshold")["cells_flagged"]
        assert flagged.loc[0.1] >= flagged.loc[0.5] >= flagged.loc[0.9]

    def test_tp_plus_fn_equals_actual_positives(self):
        df = _cv_df()
        conf = evaluate.confusion_at_thresholds(df["label"], df["oof_p_fail"], thresholds=(0.5,))
        row = conf.iloc[0]
        assert row["tp"] + row["fn"] == int(df["label"].sum())

    def test_known_events_caught_matches_tp(self):
        df = _cv_df()
        conf = evaluate.confusion_at_thresholds(df["label"], df["oof_p_fail"], thresholds=(0.5,))
        row = conf.iloc[0]
        assert row["known_events_caught"] == row["tp"]


class TestRenderReport:
    def _metadata(self):
        return {
            "model_version": "xgb-terrain-v1",
            "aoi_id": "aizawl",
            "seed": 42,
            "n_total": 10,
            "n_positive": 3,
            "n_negative": 7,
            "feature_columns": ["slope_mean_deg", "elevation_m"],
        }

    def _source_counts(self):
        return {
            "raw_global_rows": 100,
            "india_rows": 10,
            "ner_rows": 5,
            "ner_state_counts": {"Mizoram": 5},
            "aizawl_bbox_rows": 3,
            "trusted_accuracy_rows": 2,
            "total_cells": 50,
            "cells_no_terrain": 1,
            "cells_in_holdout_buffer": 2,
        }

    def test_report_contains_no_literal_int_dot_zero_artifacts(self):
        """Regression guard for the iterrows-upcasts-ints-to-float formatting bug caught by
        actually reading the rendered output (e.g. 'TP | 5.0' instead of 'TP | 5')."""
        report = evaluate.render_report(self._metadata(), self._source_counts(), _cv_df())
        assert ".0 |" not in report
        assert "/14" not in report  # this fixture has 3 positives, not 14 — n must not be hardcoded

    def test_report_mentions_single_aoi_and_terrain_only_scope(self):
        report = evaluate.render_report(self._metadata(), self._source_counts(), _cv_df())
        assert "terrain-only" in report
        assert "single-AOI" in report or "Single-AOI" in report

    def test_report_includes_model_version_and_seed(self):
        report = evaluate.render_report(self._metadata(), self._source_counts(), _cv_df())
        assert "xgb-terrain-v1" in report
        assert "42" in report


def test_real_eval_report_if_present():
    if not evaluate.REPORT_PATH.is_file():
        pytest.skip("data/models/eval_report.md not generated yet — run `python -m ml.evaluate`")
    text = evaluate.REPORT_PATH.read_text(encoding="utf-8")
    assert "AUC-ROC" in text
    assert "single-AOI" in text or "Single-AOI" in text
    assert ".0 |" not in text  # the int-formatting regression, checked against the real file too
