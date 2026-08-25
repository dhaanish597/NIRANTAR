#!/usr/bin/env python
"""Load an AOI's static data (terrain grid + exposure layers) into PostGIS (BUILD_PLAN.md task
1.5). Idempotent per AOI: each table gets `DELETE FROM <table> WHERE aoi_id = :aoi_id` followed
by a fresh insert, inside one transaction — re-running never duplicates rows and never touches
other AOIs' data. This is the "delete-then-insert" style of idempotency (no DB-level unique
constraint enforcing it) — good enough for re-running a static-data build, not a substitute for
real upsert semantics if this table ever takes concurrent/incremental writes later.

Reads `DATABASE_URL` from `.env` (see .env.example) — this is infra config, not a domain
constant, so it does NOT live in backend/app/config.py alongside the AOI registry.

Requires backend/requirements-db.txt (sqlalchemy + geoalchemy2 + psycopg2-binary), kept out of
requirements-geo.txt so people not touching the DB don't need psycopg2's native build.

SCOPE CUT, flagged not silently dropped (CLAUDE.md §10): CLAUDE.md's stack table calls for a
SQLite fallback for a laptop-only demo. This script targets PostGIS only — SQLite's spatial
support (SpatiaLite) is a real additional native-binary dependency, and Docker Desktop is now
confirmed working (Required_by_me.md), so the fallback path isn't blocking anything right now.
Deferred, not forgotten — flagged here and in Required_by_me.md.

All geometries are reprojected to EPSG:4326 before loading. AOIs use different UTM zones for
their own terrain math (config.py) — a shared multi-AOI table needs one common storage CRS, and
4326 is PostGIS's conventional default for that.

Usage:
    python scripts/load_db.py --aoi aizawl
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import geopandas as gpd  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import Engine, create_engine, inspect, text  # noqa: E402

from app.config import get_aoi  # noqa: E402

# Exposure layers to load, in (gpkg layer name, DB table name) pairs — same name today, kept as
# pairs in case a table needs to diverge from its source layer name later.
EXPOSURE_LAYERS = [
    ("villages", "villages"),
    ("shelters", "shelters"),
    ("hospitals", "hospitals"),
    ("bridges", "bridges"),
]


def _get_database_url() -> str:
    load_dotenv(REPO_ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set — copy .env.example to .env and fill it in "
            "(see Required_by_me.md for the Docker Desktop / postgis container setup)"
        )
    return url


def get_engine() -> Engine:
    return create_engine(_get_database_url())


def ensure_postgis_extension(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))


def load_table(engine: Engine, gdf: gpd.GeoDataFrame, table_name: str, aoi_id: str) -> int:
    """Deletes this AOI's existing rows (if the table already exists) then inserts `gdf` fresh.
    Returns the row count inserted."""
    inspector = inspect(engine)
    if inspector.has_table(table_name):
        with engine.begin() as conn:
            conn.execute(text(f'DELETE FROM "{table_name}" WHERE aoi_id = :aoi_id'), {"aoi_id": aoi_id})

    # to_postgis's if_exists="append" creates the table (via the same pandas.to_sql machinery)
    # if it doesn't exist yet — no separate CREATE TABLE step needed on first run.
    gdf.to_postgis(table_name, engine, if_exists="append", index=False)
    return len(gdf)


def load_aoi(aoi_id: str) -> None:
    aoi = get_aoi(aoi_id)
    engine = get_engine()

    print("Ensuring PostGIS extension is enabled ...")
    ensure_postgis_extension(engine)

    cells_path = REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
    if not cells_path.is_file():
        raise FileNotFoundError(
            f"{cells_path} not found — run `python scripts/build_grid.py --aoi {aoi_id}` first"
        )
    print(f"Reading {cells_path} ...")
    cells = gpd.read_file(cells_path).to_crs(epsg=4326)
    cells["aoi_id"] = aoi_id
    print(f"Loading {len(cells)} cells into 'cells' ...")
    load_table(engine, cells, "cells", aoi_id)

    exposure_path = REPO_ROOT / "data" / "static" / aoi_id / "exposure.gpkg"
    if not exposure_path.is_file():
        print(
            f"WARNING: {exposure_path} not found — skipping exposure layers "
            f"(run `python scripts/fetch_exposure.py --aoi {aoi_id}` first)"
        )
    else:
        for layer_name, table_name in EXPOSURE_LAYERS:
            gdf = gpd.read_file(exposure_path, layer=layer_name).to_crs(epsg=4326)
            gdf["aoi_id"] = aoi_id
            print(f"Loading {len(gdf)} rows into '{table_name}' ...")
            load_table(engine, gdf, table_name, aoi_id)

    print(f"Done loading AOI {aoi_id!r}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()
    load_aoi(args.aoi)


if __name__ == "__main__":
    main()
