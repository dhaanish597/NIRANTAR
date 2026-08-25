"""Contract tests for ml/holdout.py (BUILD_PLAN.md task 1.13 — P0 correctness requirement).

CLAUDE.md honesty rule 2: "Any scenario replay event must be excluded from model training data."
These tests prove `exclude_held_out()` actually removes leaked rows and `assert_no_leakage()`
actually raises when it should — not just that the module imports cleanly.
"""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from ml import holdout  # noqa: E402


def _row(lat, lon, dt, state):
    return {"latitude": lat, "longitude": lon, "event_dt": dt, "admin_division_name": state}


class TestHaversine:
    def test_zero_distance_for_identical_point(self):
        assert holdout.haversine_km(23.7, 92.7, 23.7, 92.7) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_order_of_magnitude(self):
        # Aizawl (23.7307N, 92.7173E) to Guwahati (26.14N, 91.74E, per CLAUDE.md §4) is a real,
        # well-known ~280 km road distance — great-circle should be in the same ballpark (less,
        # since it's a straight line, but not wildly off).
        km = holdout.haversine_km(23.7307, 92.7173, 26.14, 91.74)
        assert 200 < km < 320

    def test_vectorized_over_series(self):
        lats = pd.Series([23.70, 23.70, 30.0])
        lons = pd.Series([92.71, 92.71, 90.0])
        km = holdout.haversine_km(23.70, 92.71, lats, lons)
        assert isinstance(km, pd.Series)
        assert km.iloc[0] == pytest.approx(0.0, abs=1e-6)
        assert km.iloc[1] == pytest.approx(0.0, abs=1e-6)
        assert km.iloc[2] > 100


class TestExcludeHeldOut:
    def test_removes_row_inside_aizawl_anchor_buffer(self):
        # Well within 10km of the Aizawl quarry-collapse anchor (23.70, 92.71), and within 30
        # days of 2024-05-28.
        df = pd.DataFrame(
            [
                _row(23.705, 92.715, "2024-05-20", "Mizoram"),  # should be excluded
                _row(23.705, 92.715, "2015-01-01", "Mizoram"),  # same place, way outside date buffer
                _row(10.0, 80.0, "2024-05-28", "Tamil Nadu"),  # far away, same date
            ]
        )
        clean = holdout.exclude_held_out(df)
        assert len(clean) == 2
        remaining_dates = set(clean["event_dt"])
        assert "2024-05-20" not in remaining_dates

    def test_removes_row_via_coarse_state_date_fallback_for_no_anchor_event(self):
        # sikkim-glof-2023 has no anchor coordinate — falls back to state+date only.
        df = pd.DataFrame(
            [
                _row(27.5, 88.6, "2023-10-04", "Sikkim"),  # same state, same date -> excluded
                _row(27.5, 88.6, "2010-01-01", "Sikkim"),  # same state, far outside date buffer -> kept
                _row(27.5, 88.6, "2023-10-04", "Assam"),  # same date, different state -> kept
            ]
        )
        clean = holdout.exclude_held_out(df)
        assert len(clean) == 2

    def test_untouched_rows_pass_through_unchanged(self):
        df = pd.DataFrame([_row(23.0, 91.0, "2019-06-01", "Tripura")])
        clean = holdout.exclude_held_out(df)
        assert len(clean) == 1


class TestAssertNoLeakage:
    def test_raises_on_leaked_data(self):
        df = pd.DataFrame([_row(23.70, 92.71, "2024-05-28", "Mizoram")])
        with pytest.raises(holdout.LeakageError):
            holdout.assert_no_leakage(df)

    def test_passes_on_clean_data(self):
        df = pd.DataFrame([_row(10.0, 80.0, "2019-01-01", "Tamil Nadu")])
        holdout.assert_no_leakage(df)  # must not raise

    def test_exclude_then_assert_is_idempotent(self):
        """The documented belt-and-suspenders pattern: exclude, then assert. If exclude works,
        assert must never fire on its own output."""
        df = pd.DataFrame(
            [
                _row(23.705, 92.715, "2024-05-20", "Mizoram"),
                _row(24.9786, 93.5027, "2022-07-01", "Manipur"),
                _row(11.5034, 76.1347, "2024-08-01", "Kerala"),
                _row(23.0, 91.0, "2019-06-01", "Tripura"),
            ]
        )
        clean = holdout.exclude_held_out(df)
        holdout.assert_no_leakage(clean)  # must not raise
        assert len(clean) == 1  # only the untouched Tripura row survives


class TestHeldOutEventsTable:
    def test_covers_all_four_scenario_events(self):
        ids = {e.id for e in holdout.HELD_OUT_EVENTS}
        # aizawl-2024 has two anchor rows (quarry collapse + Hunthar/NH-6) for the same event.
        assert "aizawl-2024" in ids
        assert any(e.id.startswith("aizawl-2024") for e in holdout.HELD_OUT_EVENTS)
        assert "tupul-2022" in ids
        assert "wayanad-2024" in ids
        assert "sikkim-glof-2023" in ids

    def test_every_event_has_a_documented_anchor_source(self):
        for event in holdout.HELD_OUT_EVENTS:
            assert event.anchor_source, f"{event.id} missing anchor_source documentation"


def test_real_ner_inventory_holdout_smoke():
    """Real-data smoke test against the committed inventory, if present (skips otherwise)."""
    inv_path = holdout.REPO_ROOT / "data" / "static" / "ner_inventory.csv"
    if not inv_path.is_file():
        pytest.skip("data/static/ner_inventory.csv not built yet")
    df = pd.read_csv(inv_path)
    clean = holdout.exclude_held_out(df)
    assert len(clean) <= len(df)
    holdout.assert_no_leakage(clean)
