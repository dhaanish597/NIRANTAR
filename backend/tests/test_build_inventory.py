"""Contract tests for ml/build_inventory.py (BUILD_PLAN.md task 1.12).

Pure-logic tests run against a small synthetic DataFrame (no dependency on the real, gitignored
COOLR CSV being present). The real filtering run against the actual file is verified manually
(see CLAUDE.md §12 session log) since CI shouldn't depend on a manually-exported, gitignored raw
file being present on every machine.

Skipped entirely if pandas isn't installed (requirements-geo.txt's transitive dependency) — same
pattern as test_fetch_dem.py/test_build_grid.py for the geo stack.
"""
from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")

from ml import build_inventory  # noqa: E402


def _raw_row(**overrides):
    row = {
        "objectid": 1,
        "source_name": "COOLR",
        "event_id": 1000,
        "event_date": 1_600_000_000_000,  # epoch ms
        "event_title": "Test landslide",
        "location_description": "somewhere",
        "landslide_category": "landslide",
        "landslide_trigger": "downpour",
        "landslide_size": "medium",
        "landslide_setting": None,
        "fatality_count": 0.0,
        "injury_count": 0.0,
        "latitude": 23.7,
        "longitude": 92.7,
        "location_accuracy": "5km",
        "country_code": "IN",
        "admin_division_name": "Mizoram",
        "event_import_source": "GLC",
    }
    row.update(overrides)
    return row


def _raw_df(rows: list[dict]) -> "pd.DataFrame":
    return pd.DataFrame(rows)


class TestFilterToNer:
    def test_keeps_only_ner_states(self):
        df = _raw_df(
            [
                _raw_row(admin_division_name="Mizoram"),
                _raw_row(admin_division_name="Kerala"),  # India but not NER
                _raw_row(admin_division_name="Manipur"),
            ]
        )
        ner = build_inventory.filter_to_ner(df)
        assert set(ner["admin_division_name"]) == {"Mizoram", "Manipur"}

    def test_drops_non_india_rows(self):
        df = _raw_df(
            [
                _raw_row(country_code="IN", admin_division_name="Assam"),
                _raw_row(country_code="NP", admin_division_name="Assam"),  # spoofed state name, wrong country
            ]
        )
        ner = build_inventory.filter_to_ner(df)
        assert len(ner) == 1
        assert ner.iloc[0]["country_code"] == "IN"

    def test_drops_rows_with_no_coordinate(self):
        df = _raw_df(
            [
                _raw_row(latitude=23.7, longitude=92.7),
                _raw_row(latitude=None, longitude=92.7),
                _raw_row(latitude=23.7, longitude=None),
            ]
        )
        ner = build_inventory.filter_to_ner(df)
        assert len(ner) == 1

    def test_all_eight_ner_states_recognized(self):
        # Every state build_inventory.NER_STATES claims to keep must actually survive the filter.
        rows = [_raw_row(admin_division_name=s) for s in build_inventory.NER_STATES]
        ner = build_inventory.filter_to_ner(_raw_df(rows))
        assert len(ner) == len(build_inventory.NER_STATES)


class TestClean:
    def test_parses_event_date_to_datetime(self):
        ner = build_inventory.filter_to_ner(_raw_df([_raw_row(event_date=1_600_000_000_000)]))
        cleaned = build_inventory.clean(ner)
        assert pd.api.types.is_datetime64_any_dtype(cleaned["event_dt"])
        assert cleaned.loc[0, "event_dt"] == pd.Timestamp(1_600_000_000_000, unit="ms")

    def test_output_columns_are_stable(self):
        ner = build_inventory.filter_to_ner(_raw_df([_raw_row()]))
        cleaned = build_inventory.clean(ner)
        assert list(cleaned.columns) == build_inventory.OUTPUT_COLUMNS

    def test_sorted_by_event_dt(self):
        ner = build_inventory.filter_to_ner(
            _raw_df([_raw_row(event_date=2_000_000_000_000), _raw_row(event_date=1_000_000_000_000)])
        )
        cleaned = build_inventory.clean(ner)
        assert cleaned["event_dt"].is_monotonic_increasing


def test_load_raw_raises_actionable_error_when_missing(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match="manual Earthdata"):
        build_inventory.load_raw(missing)


def test_real_ner_inventory_file_if_present():
    """If the real filtered output already exists (i.e. someone ran the script for real), sanity
    check its shape — a light real-data smoke test, not a hard CI dependency (skips if absent)."""
    if not build_inventory.OUT_CSV.is_file():
        pytest.skip("data/static/ner_inventory.csv not built yet — run `python -m ml.build_inventory`")
    df = pd.read_csv(build_inventory.OUT_CSV)
    assert len(df) > 0
    assert set(df["admin_division_name"].unique()) <= set(build_inventory.NER_STATES)
    assert list(df.columns) == build_inventory.OUTPUT_COLUMNS
