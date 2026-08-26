"""NASA GPM IMERG rainfall adapter (BUILD_PLAN.md task 1.6). Computes rain_1h/6h/24h/72h and
antecedent_7d/15d/30d per cell from IMERG "Early Run" half-hourly precipitation granules.

STATUS, read before touching this file: the HDF5-parsing internals (`_read_granule_precip`)
are written against NASA's PUBLISHED IMERG file specification and the widely-documented
`/Grid/precipitation` layout used by essentially every third-party IMERG tool — they are NOT
yet verified against a real downloaded granule's actual bytes. That verification is blocked on
one thing: real granule downloads currently return NASA's generic GES DISC web-app shell (HTML,
HTTP 200) instead of file bytes, because this Earthdata account hasn't yet completed GES DISC's
one-time "authorize this application" step — confirmed via the NASA Earthdata Forum thread on
exactly this symptom ("HTTP Basic: Access denied" / wrong-body-on-200), not assumed. See
Required_by_me.md for the one-time browser action needed. Once that's done, re-run this module
against a real granule and fix `_read_granule_precip` if the real structure differs — there's a
runtime magic-byte + variable-existence check below specifically so that mismatch fails loudly
instead of silently producing wrong numbers.

Access mechanism (the parts that ARE verified against real requests this session):
- Granule URL pattern and the current file-naming convention (`.../GPM_3IMERGHHE.07/{year}/
  {doy:03d}/3B-HHR-E.MS.MRG.3IMERG.{YYYYMMDD}-S{start}-E{end}.{minute_of_day:04d}.V07C.HDF5`) —
  confirmed by fetching a real GES DISC directory listing for today and reading real filenames
  out of it, not guessed.
- `requests` (like curl) drops the `Authorization` header on a cross-host redirect by default;
  GES DISC downloads redirect through `urs.earthdata.nasa.gov` and back, so a plain
  `requests.get(url, auth=(...))` silently 401s. `_EarthdataSession` below re-attaches the header
  when the redirect stays within the Earthdata/EOSDIS host family — the same fix `curl
  --location-trusted` provides, and NASA's own Earthdata Login tutorials document this same
  Session-subclass pattern for exactly this reason.

Resolution honesty: IMERG's native grid is 0.1 degree (~10 km). Aizawl's whole AOI is ~25 km
across, so it is covered by only a handful of distinct IMERG pixels — most of the 2,912 analysis
cells share an identical value with their neighbours. This module reflects that reality rather
than hiding it: it fetches/caches a per-PIXEL time series (a handful of columns, not 2,912), and
maps each cell to its containing pixel. This is not a compromise on accuracy — sampling all 2,912
cells independently from a 10 km grid would not be more accurate, only more expensive to store.

Antecedent-window definition (an engineering choice, not a cited formula — none of CLAUDE.md's
reference formulae define "antecedent rainfall" precisely, and BUILD_PLAN.md's task text doesn't
either): antecedent_Nd is total precipitation (mm) summed over the trailing N*24 hours ending at
the tick's timestamp, same trailing-window convention as rain_1h/6h/24h/72h. TODO(verify): revisit
if the ML feature work (task 1.15) wants a decayed/weighted antecedent index instead of a flat sum.

Cold-start honesty: a live system starting today has no rainfall history. `antecedent_30d` and
even `rain_72h` are genuinely incomplete until this adapter has been running (or been backfilled)
long enough to have real data spanning that window. Every ObservationFrame's `provenance` dict
carries `history_complete_from` (the earliest timestamp actually backed by real cached data) so
nothing downstream mistakes a short cache for a genuine 30-day antecedent total.

NOT wired into ingest/factory.py's LIVE branch yet — CLAUDE.md's own Current State notes already
flag that wiring real adapters + the real cell grid into the live pipeline is a Phase 1C/2
integration step, not a per-adapter one (the synthetic 3x3 stub grid is still what LIVE mode uses
today). This module is written, tested, and runnable standalone; the wiring is deliberately out
of scope here.

Usage (standalone):
    python -m app.ingest.live.imerg --aoi aizawl --backfill-hours 6
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402
from app.core.clock import Clock, LiveClock  # noqa: E402
from app.ingest.live.earthdata_common import EarthdataSession as _EarthdataSession  # noqa: E402
from app.ingest.live.earthdata_common import HDF5_MAGIC  # noqa: E402
from app.schemas.ingest import CellObservation, ObservationFrame  # noqa: E402

IMERG_BASE_URL = "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHHE.07"
IMERG_GRANULE_MINUTES = 30
IMERG_GRID_DEG = 0.1  # native IMERG pixel size
# Public IMERG spec (see module docstring) — NOT yet confirmed against a real downloaded file.
IMERG_HDF5_GROUP = "Grid"
IMERG_PRECIP_VAR = "precipitation"  # V07 name; V06 tools call this "precipitationCal" instead
IMERG_FILL_VALUE = -9999.9

GRANULE_CACHE_DIR = REPO_ROOT / "data" / "static" / "_imerg_granules"
# `_EarthdataSession`/`HDF5_MAGIC` moved to earthdata_common.py (task 1.7, shared with smap.py)
# and re-imported above under their original names — this module's own tests reference both names
# directly on `imerg` and were re-run unchanged after the extraction (see earthdata_common.py's
# module docstring).

FEATURE_WINDOWS_HOURS = {
    "rain_1h": 1,
    "rain_6h": 6,
    "rain_24h": 24,
    "rain_72h": 72,
    "antecedent_7d": 7 * 24,
    "antecedent_15d": 15 * 24,
    "antecedent_30d": 30 * 24,
}


# =============================================================================================
# Granule URL / cache path (pure, no network — see TestGranuleNaming)
# =============================================================================================
def granule_half_hour_start(dt: datetime) -> datetime:
    """Floors `dt` (UTC) to the start of its containing 30-minute IMERG granule."""
    if dt.tzinfo is None:
        raise ValueError("granule_half_hour_start requires a timezone-aware datetime")
    minute = 0 if dt.minute < 30 else 30
    return dt.astimezone(timezone.utc).replace(minute=minute, second=0, microsecond=0)


def granule_url(half_hour_start: datetime) -> str:
    start = half_hour_start
    end = start + timedelta(minutes=IMERG_GRANULE_MINUTES) - timedelta(seconds=1)
    minute_of_day = start.hour * 60 + start.minute
    doy = start.timetuple().tm_yday
    filename = (
        f"3B-HHR-E.MS.MRG.3IMERG.{start:%Y%m%d}"
        f"-S{start:%H%M%S}-E{end:%H%M%S}.{minute_of_day:04d}.V07C.HDF5"
    )
    return f"{IMERG_BASE_URL}/{start:%Y}/{doy:03d}/{filename}"


def granule_cache_path(half_hour_start: datetime, cache_dir: Path = GRANULE_CACHE_DIR) -> Path:
    return cache_dir / f"{half_hour_start:%Y%m%dT%H%M}.HDF5"


# =============================================================================================
# Download (real cross-host-redirect Basic Auth fix — see earthdata_common.py / module docstring)
# =============================================================================================
def download_granule(
    half_hour_start: datetime,
    username: str,
    password: str,
    cache_dir: Path = GRANULE_CACHE_DIR,
) -> Path:
    """Downloads (if not already cached) one half-hour granule. Raises RuntimeError with a clear,
    actionable message if the response isn't real HDF5 bytes (e.g. the GES DISC app-authorization
    HTML shell this session actually hit — see module docstring) rather than silently caching it."""
    dest = granule_cache_path(half_hour_start, cache_dir)
    if dest.is_file():
        return dest

    cache_dir.mkdir(parents=True, exist_ok=True)
    url = granule_url(half_hour_start)
    session = _EarthdataSession(username, password)
    response = session.get(url, timeout=180)
    response.raise_for_status()

    if not response.content.startswith(HDF5_MAGIC):
        raise RuntimeError(
            f"Response for {url} is not an HDF5 file (got {len(response.content)} bytes not "
            f"starting with the HDF5 magic number). This is the exact symptom of a NASA Earthdata "
            f"account that hasn't authorized the GES DISC application yet - see Required_by_me.md."
        )

    dest.write_bytes(response.content)
    return dest


# =============================================================================================
# HDF5 parsing + zonal extraction to IMERG pixels (see module docstring re: verification status)
# =============================================================================================
def read_granule_precip_mm(granule_path: Path, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    """Reads one granule's precipitation (mm, accumulated over the half hour) for pixels
    overlapping `bbox`. Returns a DataFrame with columns pixel_id, lon, lat, precip_mm.

    pixel_id is a stable string key ("lon_lat", pixel-centre coordinates) so the same physical
    pixel gets the same id across every granule and across a script restart.
    """
    import h5py  # local import: only needed by this function, keeps module import cheap for tests

    min_lon, min_lat, max_lon, max_lat = bbox
    with h5py.File(granule_path, "r") as f:
        grid = f[IMERG_HDF5_GROUP]
        if IMERG_PRECIP_VAR not in grid:
            raise RuntimeError(
                f"{granule_path}: expected variable '{IMERG_HDF5_GROUP}/{IMERG_PRECIP_VAR}' not "
                f"found (has: {list(grid.keys())}). The public IMERG spec this was written "
                f"against may not match this file's actual structure — see module docstring; "
                f"this is exactly the mismatch the docstring warns is unverified."
            )
        lon = grid["lon"][:]
        lat = grid["lat"][:]
        # Public IMERG spec: precipitation is (time=1, lon, lat) — NOT the more common
        # (time, lat, lon) order. Squeeze the length-1 time axis.
        precip = np.asarray(grid[IMERG_PRECIP_VAR][0, :, :])  # (lon, lat), mm/hr rate

    lon_mask = (lon >= min_lon) & (lon <= max_lon)
    lat_mask = (lat >= min_lat) & (lat <= max_lat)
    if not lon_mask.any() or not lat_mask.any():
        raise ValueError(f"{granule_path}: no IMERG pixel overlaps bbox {bbox}")

    lon_idx = np.where(lon_mask)[0]
    lat_idx = np.where(lat_mask)[0]
    rows = []
    for li in lon_idx:
        for la in lat_idx:
            rate_mm_hr = precip[li, la]
            if rate_mm_hr == IMERG_FILL_VALUE:
                continue
            depth_mm = float(rate_mm_hr) * (IMERG_GRANULE_MINUTES / 60.0)
            rows.append(
                {
                    "pixel_id": f"{lon[li]:.2f}_{lat[la]:.2f}",
                    "lon": float(lon[li]),
                    "lat": float(lat[la]),
                    "precip_mm": max(depth_mm, 0.0),
                }
            )
    return pd.DataFrame(rows, columns=["pixel_id", "lon", "lat", "precip_mm"])


# =============================================================================================
# Cell -> pixel mapping (real Aizawl cell centroids, not the synthetic stub grid)
# =============================================================================================
def assign_cells_to_pixels(cells_gpkg_path: Path, imerg_grid_deg: float = IMERG_GRID_DEG) -> pd.DataFrame:
    """Maps each real cell_id (from data/static/<aoi>/cells.gpkg) to the pixel_id of the IMERG
    pixel whose centre is nearest its centroid. Returns columns cell_id, pixel_id."""
    import geopandas as gpd  # local import — see read_granule_precip_mm's note

    cells = gpd.read_file(cells_gpkg_path)
    centroids_wgs84 = cells.geometry.centroid.to_crs(epsg=4326) if cells.crs != "EPSG:4326" else cells.geometry.centroid

    def nearest_pixel_id(lon: float, lat: float) -> str:
        pixel_lon = round(lon / imerg_grid_deg) * imerg_grid_deg
        pixel_lat = round(lat / imerg_grid_deg) * imerg_grid_deg
        return f"{pixel_lon:.2f}_{pixel_lat:.2f}"

    return pd.DataFrame(
        {
            "cell_id": cells["cell_id"].values,
            "pixel_id": [nearest_pixel_id(pt.x, pt.y) for pt in centroids_wgs84],
        }
    )


# =============================================================================================
# Persistent per-pixel time series + rolling-window features
# =============================================================================================
def append_timeseries(new_rows: pd.DataFrame, t: datetime, store_path: Path) -> None:
    """Appends `new_rows` (pixel_id, precip_mm) timestamped `t` to the persistent CSV store.
    A plain append-only CSV, not a proper time-series DB — a documented, acceptable-for-this-scale
    simplification (a handful of pixels x 30-min cadence is small; see module docstring)."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    to_write = new_rows[["pixel_id", "precip_mm"]].copy()
    to_write.insert(0, "timestamp", t.astimezone(timezone.utc).isoformat())
    header = not store_path.is_file()
    to_write.to_csv(store_path, mode="a", header=header, index=False)


def compute_rolling_features(
    timeseries: pd.DataFrame, now: datetime, windows_hours: dict[str, int] = FEATURE_WINDOWS_HOURS
) -> tuple[dict[str, dict[str, float]], datetime | None]:
    """From a long-format (timestamp, pixel_id, precip_mm) DataFrame, computes trailing-window
    sums per pixel_id for every feature in `windows_hours`.

    Returns (features_by_pixel, earliest_timestamp) — `features_by_pixel[pixel_id][feature_name]`,
    and the earliest timestamp actually present in the store (used to report `history_complete_from`
    in ObservationFrame.provenance — see module docstring's cold-start honesty note).
    """
    if timeseries.empty:
        return {}, None

    ts = timeseries.copy()
    ts["timestamp"] = pd.to_datetime(ts["timestamp"], utc=True)
    earliest = ts["timestamp"].min().to_pydatetime()

    features: dict[str, dict[str, float]] = {pixel_id: {} for pixel_id in ts["pixel_id"].unique()}
    for feature_name, hours in windows_hours.items():
        cutoff = now - timedelta(hours=hours)
        window = ts[ts["timestamp"] >= cutoff]
        sums = window.groupby("pixel_id")["precip_mm"].sum()
        for pixel_id in features:
            features[pixel_id][feature_name] = float(sums.get(pixel_id, 0.0))

    return features, earliest


# =============================================================================================
# Orchestration
# =============================================================================================
def backfill_history(
    aoi: AoiConfig,
    username: str,
    password: str,
    hours: float,
    now: datetime,
    store_path: Path,
    cache_dir: Path = GRANULE_CACHE_DIR,
) -> int:
    """Fetches every granule from `hours` ago up to `now` and appends it to the persistent store.
    Idempotent: granule downloads are cached on disk, and re-appending an already-covered granule
    is avoided by skipping timestamps already present in `store_path`. Returns the count of new
    granules actually fetched."""
    already_covered: set[datetime] = set()
    if store_path.is_file():
        existing = pd.read_csv(store_path, usecols=["timestamp"])
        already_covered = set(pd.to_datetime(existing["timestamp"], utc=True).dt.to_pydatetime())

    start = granule_half_hour_start(now - timedelta(hours=hours))
    end = granule_half_hour_start(now)
    fetched = 0
    t = start
    while t <= end:
        if t.replace(tzinfo=timezone.utc) not in already_covered:
            try:
                granule_path = download_granule(t, username, password, cache_dir)
                rows = read_granule_precip_mm(granule_path, aoi.bbox)
                if not rows.empty:
                    append_timeseries(rows, t, store_path)
                fetched += 1
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    print(
                        f"Granule for {t.isoformat()} not yet published on GES DISC (IMERG ~4h latency); skipping."
                    )
                else:
                    raise
        t += timedelta(minutes=IMERG_GRANULE_MINUTES)
    return fetched


class ImergLiveSource:
    """Live DataSource (BUILD_PLAN.md task 1.6) — polls for new IMERG granules on each tick,
    updates the persistent per-pixel time series, and yields real-cell ObservationFrames with
    `soil_moisture` / `insar_velocity_mm_yr` left None (tasks 1.7 / 1.9's job to fill)."""

    def __init__(
        self,
        clock: Clock,
        aoi_id: str,
        username: str,
        password: str,
        *,
        cells_gpkg_path: Path | None = None,
        store_path: Path | None = None,
        poll_interval_seconds: float = 60.0,
    ):
        if not clock.is_live:
            raise ValueError("ImergLiveSource requires a live Clock (got a non-live one)")
        self._clock = clock
        self._aoi = get_aoi(aoi_id)
        self._username = username
        self._password = password
        self._cells_gpkg_path = cells_gpkg_path or (
            REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
        )
        self._store_path = store_path or (
            REPO_ROOT / "data" / "static" / aoi_id / "imerg_pixel_timeseries.csv"
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._cell_to_pixel: pd.DataFrame | None = None

    def _load_cell_mapping(self) -> pd.DataFrame:
        if self._cell_to_pixel is None:
            self._cell_to_pixel = assign_cells_to_pixels(self._cells_gpkg_path)
        return self._cell_to_pixel

    async def frames(self) -> AsyncIterator[ObservationFrame]:
        import asyncio

        cell_to_pixel = self._load_cell_mapping()

        while True:
            now = self._clock.now()
            half_hour = granule_half_hour_start(now)
            try:
                granule_path = download_granule(half_hour, self._username, self._password)
                rows = read_granule_precip_mm(granule_path, self._aoi.bbox)
                if not rows.empty:
                    append_timeseries(rows, half_hour, self._store_path)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                # A missed granule degrades the feature set for this tick rather than stalling
                # the whole pipeline — same "circuit breaker" spirit as task 1.8's IMD adapter.
                print(f"ImergLiveSource: granule fetch failed ({exc}); yielding with stale cache")

            timeseries = (
                pd.read_csv(self._store_path) if self._store_path.is_file() else pd.DataFrame()
            )
            features_by_pixel, earliest = compute_rolling_features(timeseries, now)

            cells = []
            for _, row in cell_to_pixel.iterrows():
                pixel_features = features_by_pixel.get(row["pixel_id"], {})
                cells.append(
                    CellObservation(
                        cell_id=row["cell_id"],
                        rain_1h=pixel_features.get("rain_1h", 0.0),
                        rain_6h=pixel_features.get("rain_6h", 0.0),
                        rain_24h=pixel_features.get("rain_24h", 0.0),
                        rain_72h=pixel_features.get("rain_72h", 0.0),
                        antecedent_7d=pixel_features.get("antecedent_7d", 0.0),
                        antecedent_15d=pixel_features.get("antecedent_15d", 0.0),
                        antecedent_30d=pixel_features.get("antecedent_30d", 0.0),
                        soil_moisture=None,
                        insar_velocity_mm_yr=None,
                        source="imerg",
                        is_reconstructed=False,
                    )
                )

            yield ObservationFrame(
                t=now,
                aoi_id=self._aoi.id,
                cells=cells,
                provenance={
                    "source": "NASA GPM IMERG Early Run (GPM_3IMERGHHE.07)",
                    "resolution": "0.1 deg (~10 km) native, mapped onto 500 m analysis cells",
                    "history_complete_from": earliest.isoformat() if earliest else "no data yet",
                },
            )
            await asyncio.sleep(self._poll_interval_seconds)


def main() -> None:
    import os

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    parser.add_argument("--backfill-hours", type=float, default=6.0, help="Hours of history to backfill")
    args = parser.parse_args()

    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not username or not password:
        raise RuntimeError("EARTHDATA_USERNAME/EARTHDATA_PASSWORD not set in .env")

    aoi = get_aoi(args.aoi)
    store_path = REPO_ROOT / "data" / "static" / args.aoi / "imerg_pixel_timeseries.csv"
    # CLAUDE.md rule 14 (datetime.now() banned outside core/clock.py) applies to everything under
    # backend/app/, including this CLI entry point — go through LiveClock like everywhere else.
    now = LiveClock().now()
    count = backfill_history(aoi, username, password, args.backfill_hours, now, store_path)
    print(f"Fetched {count} new granule(s). Store: {store_path}")

    timeseries = pd.read_csv(store_path) if store_path.is_file() else pd.DataFrame()
    features, earliest = compute_rolling_features(timeseries, now)
    print(f"history_complete_from={earliest}")
    for pixel_id, feats in features.items():
        print(f"  pixel {pixel_id}: {feats}")


if __name__ == "__main__":
    main()
