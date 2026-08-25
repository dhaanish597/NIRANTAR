"""Contract test for scripts/load_db.py's pure logic (BUILD_PLAN.md task 1.5). No live database —
the actual PostGIS load is verified by manually running the script against the real docker-compose
postgis container (see CLAUDE.md §12 session log), same reasoning as test_build_grid.py /
test_fetch_dem.py for network-dependent scripts.

Skipped entirely if requirements-db.txt isn't installed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("geoalchemy2")
pytest.importorskip("psycopg2")
pytest.importorskip("geopandas")

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "load_db.py"


def _load_load_db():
    spec = importlib.util.spec_from_file_location("load_db", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["load_db"] = module
    spec.loader.exec_module(module)
    return module


load_db = _load_load_db()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestGetDatabaseUrl:
    def test_raises_if_unset(self, monkeypatch, tmp_path):
        # Point load_dotenv at an empty temp file so a real local .env can't leak into this test.
        monkeypatch.setattr(load_db, "REPO_ROOT", tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(RuntimeError, match="DATABASE_URL not set"):
            load_db._get_database_url()

    def test_reads_from_environment(self, monkeypatch, tmp_path):
        monkeypatch.setattr(load_db, "REPO_ROOT", tmp_path)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
        assert load_db._get_database_url() == "postgresql://u:p@localhost:5432/db"


class TestExposureLayers:
    def test_covers_all_four_categories(self):
        names = {layer for layer, _table in load_db.EXPOSURE_LAYERS}
        assert names == {"villages", "shelters", "hospitals", "bridges"}
