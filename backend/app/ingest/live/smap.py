"""NASA SMAP surface soil moisture adapter (BUILD_PLAN.md task 1.7). Populates
`CellObservation.soil_moisture` from the SMAP Enhanced L3 Radiometer Global and Polar Grid Daily
9 km EASE-Grid Soil Moisture product (short_name `SPL3SMP_E`).

UI LABEL REQUIREMENT (CLAUDE.md honesty rule 5 — read this before wiring anything downstream):
every UI surface that shows this value MUST label it "surface proxy (top 5 cm)". This is a
radiometric retrieval of the TOP of the soil column, not pore-water pressure — frame it as NASA's
own operational LHASA v2 does: a surrogate, fused with antecedent rainfall (`imerg.py`), never
presented alone as "soil wetness" without that caveat. `CellObservation.soil_moisture`'s own
schema comment already says "surface proxy, 0-1" (`schemas/ingest.py`) — this note exists so
whoever wires the frontend (a later phase) does not have to go find that comment first.

STATUS, read before touching this file: like `imerg.py` before its GES DISC authorization landed,
this module's HDF5-parsing internals (`read_granule_soil_moisture`) are written against NASA's
PUBLICLY DOCUMENTED product structure — the NSIDC "SMAP Enhanced L3 Radiometer Global and Polar
Grid Daily 9 km EASE-Grid Soil Moisture, Version 5" User Guide (O'Neill et al. 2021,
https://nsidc.org/sites/default/files/spl3smp_e-v005-userguide.pdf, fetched and read in full this
session) — NOT yet verified against a real downloaded granule's actual bytes. Real network access
to both the granule host (`n5eil01u.ecs.nsidc.org`) and the CMR search API
(`cmr.earthdata.nasa.gov`) was attempted from this sandboxed environment and refused outright
(`ECONNREFUSED`) — a stricter block than `imerg.py`'s original session hit (that one reached GES
DISC and got a wrong-body HTML shell; this one couldn't open a TCP connection to NSIDC at all).
This is the anticipated "real download verification is blocked here" case the task brief called
out, not a code defect — the runtime magic-byte + variable-existence checks below exist for
exactly this reason: once network access + this Earthdata account's access to NSIDC DAAC is
confirmed working, re-run this module against a real granule and fix `read_granule_soil_moisture`
if the real structure differs.

What IS confirmed against real, cited public documentation this session (not guessed):
- Product identity: `SPL3SMP_E`, current collection version "006" per the NSIDC landing page
  (https://nsidc.org/data/spl3smp_e/versions/6) — data from 2023-12-04 onward are served under
  this version; the v005 User Guide (still the most recent one with full field documentation
  publicly available) covers 2015-03-31 to 2023-12-02. TODO(verify): the v006 landing page was not
  read field-by-field in this session (only its existence/version number/coverage-date confirmed
  via search) — assumed here that v006 is a forward-processing continuation with the same internal
  HDF5 group/field layout as v005 (NSIDC's normal convention for a minor reprocessing version
  bump), not independently confirmed field-by-field.
- File naming convention: `SMAP_L3_SM_P_E_yyyymmdd_RLVvvv_NNN.h5`, e.g.
  `SMAP_L3_SM_P_E_20150403_R17400_001.h5` (User Guide, Table 3) — the `RLVvvv` composite release
  ID is NOT something this module hardcodes or guesses; see "granule discovery" below.
- HDF5 group layout: `Soil_Moisture_Retrieval_Data_AM` / `_PM` (global) — this module only reads
  the global groups, not `_Polar_AM`/`_Polar_PM` (Aizawl is nowhere near either pole, so the polar
  Lambert-azimuthal grid is irrelevant here). PM-group field names carry a `_pm` suffix (User
  Guide §1.2.3 and Appendix note) — e.g. `soil_moisture_pm`, not a separate `soil_moisture` in a
  differently-named group.
  Each daily granule already contains BOTH the AM (descending, ~6am LST) and PM (ascending, ~6pm
  LST) passes composited together (User Guide §1.4.4) — one granule per UTC day, not two.
- Field names read: `soil_moisture` (Float32, m3/m3, valid range 0.02-soil_porosity, fill
  -9999.0) — this is the GENERIC field name, internally linked to whichever algorithm is the
  current baseline; since Version 5 (Oct 2021) that baseline is DCA (Dual Channel Algorithm), so
  `soil_moisture` and `soil_moisture_dca` are the same values (User Guide §1.1, "Table 2: Pointer
  Elements and Corresponding Variables"). `retrieval_qual_flag` (Uint16, fill 65534) — bit 0 = 0
  means "recommended quality" (User Guide Table A-2 / Table 6). `latitude`/`longitude` (Float32,
  degrees, fill -9999.0) — PER-CELL 2-D arrays (NOT a pair of 1-D coordinate vectors the way
  IMERG's regular lat/lon grid works — EASE-Grid 2.0 is an equal-AREA, not equal-ANGLE, projection,
  so a grid cell's lon/lat cannot be recovered by simple row/column rounding the way
  `imerg.py::assign_cells_to_pixels` does). This is why this module's own cell-to-pixel mapping
  (`assign_cells_to_pixels` below) needs an actual read granule's lon/lat arrays as input, unlike
  IMERG's analytic version.
- Resolution honesty: native footprint ~36 km, interpolated (Backus-Gilbert) onto a 9 km EASE-Grid
  2.0 posting (User Guide §1.3.2) — i.e. even the "9 km" grid does not mean 9 km independent
  information content. Aizawl's ~25 km AOI likely maps onto a small handful of distinct 9 km
  pixels, the same resolution-mismatch spirit `imerg.py` documents for its 0.1deg IMERG pixels —
  not independently confirmed with real data this session (blocked, see above), but recorded here
  so nobody mistakes a handful of pixels reused across ~2,912 cells for a modelling bug later.

Granule discovery (a deliberate departure from imerg.py's approach, not an oversight): imerg.py
could hardcode its granule URL because task 1.6's session fetched a REAL GES DISC directory
listing and read a real filename out of it. That path is closed here (network blocked, see
above), and more importantly the `RLVvvv` composite release ID in SMAP's filename is not something
a client should hardcode even when it CAN reach the server — NSIDC's own guidance for
machine-readable programmatic discovery is NASA's Common Metadata Repository (CMR) granule search
API (https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html, fetched this session),
which is UNAUTHENTICATED for search (only the actual granule download needs Earthdata Login) and
returns the real current filename/URL for a given short_name+version+date+bbox rather than a
client having to guess the release id. `find_granule_download_url` below queries CMR; the ESIP
FedSearch "data" relation convention (`rel` ending in `/data#` carries the direct HTTPS download
href) is a documented, real convention (see `extract_data_download_url`'s own docstring for the
citation), not invented.

Not wired into ingest/factory.py's LIVE branch — same documented reason imerg.py gives (Phase
1C/2 integration step, not a per-adapter one): a live source that ONLY carries soil_moisture (with
rain_* fields all left at the placeholder 0.0, mirroring imerg.py's own placeholder
`soil_moisture=None`) is not something the live pipeline should actually run as-is; a future task
must fuse imerg.py + smap.py (+ eventually insar.py) into one CellObservation stream per tick.

Usage (standalone):
    python -m app.ingest.live.smap --aoi aizawl --backfill-days 3
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlencode

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

# ---- Product identity (see module docstring for the citation on each of these) -----------------
SMAP_SHORT_NAME = "SPL3SMP_E"
SMAP_VERSION = "006"  # TODO(verify): assumed field-layout-compatible with the v005 User Guide

CMR_GRANULE_SEARCH_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
# ESIP Federated Search convention: a granule's downloadable-data link has a `rel` ending in this
# suffix (both /1.0/ and /1.1/ namespace versions appear in the wild) — see
# extract_data_download_url()'s own docstring for the citation.
CMR_DATA_LINK_REL_SUFFIX = "/data#"

SMAP_GROUP_BY_PASS = {
    "AM": "Soil_Moisture_Retrieval_Data_AM",
    "PM": "Soil_Moisture_Retrieval_Data_PM",
}
SMAP_SOIL_MOISTURE_FIELD = "soil_moisture"  # generic pointer -> *_dca (baseline algorithm, v5+)
SMAP_QUAL_FLAG_FIELD = "retrieval_qual_flag"
SMAP_FILL_VALUE = -9999.0
SMAP_QUAL_RECOMMENDED_BIT = 0  # bit0 == 0 -> "recommended quality" (User Guide Table A-2)

GRANULE_CACHE_DIR = REPO_ROOT / "data" / "static" / "_smap_granules"

# How far back to look for the most recent published daily granule if "today" isn't out yet — SMAP
# L3 products have real processing latency (User Guide §1.4.3 points at NSIDC's own latency FAQ,
# which this session did not separately fetch — TODO(verify) the exact figure). This lookback
# window is an engineering default, not a cited latency number, mirroring imerg.py's own
# documented-assumption style for its ~4h IMERG latency handling.
DEFAULT_MAX_LOOKBACK_DAYS = 5


# =============================================================================================
# Granule discovery via CMR (pure query-building — see TestCmrQueryBuilding; the actual network
# call + response parsing are split apart so parsing logic is unit-testable against a synthetic
# fixture without hitting CMR, same split imerg.py uses between granule_url() and download_granule())
# =============================================================================================
def granule_day_bounds(date: datetime) -> tuple[datetime, datetime]:
    """Floors `date` (must be timezone-aware) to its containing UTC calendar day and returns
    (day_start, day_end) — the daily granule's temporal coverage window."""
    if date.tzinfo is None:
        raise ValueError("granule_day_bounds requires a timezone-aware datetime")
    day_start = date.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
    return day_start, day_end


def cmr_granule_search_url(
    date: datetime,
    bbox: tuple[float, float, float, float],
    short_name: str = SMAP_SHORT_NAME,
    version: str = SMAP_VERSION,
) -> str:
    """Builds the (unauthenticated — CMR search itself needs no Earthdata login, only the
    resulting granule download does) CMR granule-search query for the SPL3SMP_E daily composite
    granule covering `date`'s UTC calendar day over `bbox`. `bbox` uses this repo's
    (min_lon, min_lat, max_lon, max_lat) convention (AoiConfig.bbox), which is directly CMR's
    `west,south,east,north` bounding_box order — no reordering needed."""
    day_start, day_end = granule_day_bounds(date)
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "short_name": short_name,
        "version": version,
        "temporal": f"{day_start:%Y-%m-%dT%H:%M:%SZ},{day_end:%Y-%m-%dT%H:%M:%SZ}",
        "bounding_box": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "page_size": 5,
    }
    return f"{CMR_GRANULE_SEARCH_URL}?{urlencode(params)}"


def extract_data_download_url(cmr_json: dict) -> str | None:
    """Pure parser: given a decoded CMR `granules.json` response body, returns the first granule's
    direct HTTPS `.h5` download href, or None if no granule / no matching data link was found.

    CMR's granule JSON follows the ATOM-derived `feed.entry[].links[]` shape (CMR Search API docs,
    https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html, fetched this session); each
    link's `rel` follows the ESIP Federated Search convention where a downloadable-data link's
    `rel` ends in `/data#` (e.g. `http://esipfed.org/ns/fedsearch/1.1/data#`) as opposed to
    `/metadata#`, `/browse#`, or `/s3#` for the same granule's other links — real, documented ESIP
    FedSearch convention, not invented (see e.g. NSIDC/PO.DAAC Earthdata Cloud Cookbook tutorials
    using this exact `rel.endswith("/data#")` pattern to pick the HTTPS link out of a CMR result)."""
    entries = cmr_json.get("feed", {}).get("entry", [])
    for entry in entries:
        for link in entry.get("links", []):
            href = link.get("href", "")
            rel = link.get("rel", "")
            if rel.endswith(CMR_DATA_LINK_REL_SUFFIX) and href.endswith(".h5"):
                return href
    return None


def find_granule_download_url(
    date: datetime,
    bbox: tuple[float, float, float, float],
    timeout: float = 60.0,
) -> str:
    """Queries CMR for real, returns the direct download URL. Raises RuntimeError with the query
    URL included (so a human can paste it into a browser to see exactly what CMR said) if no
    granule is found for that day — the caller (`download_granule` / `find_latest_available_date`)
    decides whether that means "not published yet, try an earlier day" or a real failure."""
    url = cmr_granule_search_url(date, bbox)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    href = extract_data_download_url(response.json())
    if href is None:
        raise RuntimeError(
            f"No {SMAP_SHORT_NAME} granule found via CMR for {date.date()} over bbox {bbox} "
            f"(query: {url})"
        )
    return href


def find_latest_available_date(
    now: datetime,
    bbox: tuple[float, float, float, float],
    max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> datetime:
    """Tries `now`'s UTC day, then walks backward up to `max_lookback_days` looking for the first
    day CMR actually has a granule for — SMAP L3 has real processing latency (see module
    docstring), so "today" often has nothing yet. Raises RuntimeError if nothing is found in the
    whole window (a real outage / access problem, not ordinary latency)."""
    last_error: Exception | None = None
    for offset in range(max_lookback_days + 1):
        candidate = now - timedelta(days=offset)
        try:
            find_granule_download_url(candidate, bbox)
            return candidate
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            continue
    raise RuntimeError(
        f"No {SMAP_SHORT_NAME} granule found for any of the last {max_lookback_days + 1} day(s) "
        f"ending {now.date()} over bbox {bbox}; last error: {last_error}"
    )


# =============================================================================================
# Download (reuses imerg.py's cross-host-redirect Basic Auth fix — see earthdata_common.py)
# =============================================================================================
def granule_cache_path(date: datetime, cache_dir: Path = GRANULE_CACHE_DIR) -> Path:
    day_start, _ = granule_day_bounds(date)
    return cache_dir / f"{day_start:%Y-%m-%d}.h5"


def download_granule(
    date: datetime,
    bbox: tuple[float, float, float, float],
    username: str,
    password: str,
    cache_dir: Path = GRANULE_CACHE_DIR,
    timeout: float = 180.0,
) -> Path:
    """Downloads (if not already cached) the one daily granule covering `date`. Raises
    RuntimeError with a clear, actionable message if the response isn't real HDF5 bytes — same
    magic-byte-check pattern as imerg.py's `download_granule`, guarding against the equivalent of
    the wrong-body-on-200 GES DISC symptom task 1.6 actually hit."""
    dest = granule_cache_path(date, cache_dir)
    if dest.is_file():
        return dest

    cache_dir.mkdir(parents=True, exist_ok=True)
    href = find_granule_download_url(date, bbox)
    session = _EarthdataSession(username, password)
    response = session.get(href, timeout=timeout)
    response.raise_for_status()

    if not response.content.startswith(HDF5_MAGIC):
        raise RuntimeError(
            f"Response for {href} is not an HDF5 file (got {len(response.content)} bytes not "
            f"starting with the HDF5 magic number). This is the same class of symptom imerg.py's "
            f"module docstring documents for a NASA Earthdata account without the right DAAC "
            f"application authorized — see Required_by_me.md."
        )

    dest.write_bytes(response.content)
    return dest


# =============================================================================================
# HDF5 parsing (see module docstring re: verification status)
# =============================================================================================
def read_granule_soil_moisture(
    granule_path: Path,
    bbox: tuple[float, float, float, float],
    pass_name: str = "AM",
) -> pd.DataFrame:
    """Reads one pass group's (AM or PM) soil moisture for EASE-Grid cells overlapping `bbox`.
    Returns a DataFrame with columns pixel_id, lon, lat, soil_moisture, recommended_quality.

    pixel_id is `"ease_{row}_{col}"` — the array's own (row, col) indices, which for EASE-Grid 2.0
    ARE the stable identity of a physical grid cell (unlike a lon/lat string key, which would need
    float-rounding that risks instability at cell boundaries — not a risk worth taking here since
    the array indices are already exactly what's needed).

    Bbox + fill-value filtering is done as a vectorised numpy boolean mask BEFORE building the
    per-pixel row list, not as a nested Python loop over the full grid — the full global grid is
    ~1624x3856 (~6.3M cells; NSIDC User Guide Table 5), and a per-cell Python loop over that would
    be prohibitively slow. Only the (small, AOI-sized) set of masked-in indices is ever iterated in
    Python, the same "loop only over what bbox already narrowed down" spirit imerg.py's
    `read_granule_precip_mm` uses (that one gets to mask via cheap 1-D lon/lat vectors first
    because IMERG's grid is regular; this one masks via full 2-D lon/lat arrays because EASE-Grid
    2.0 is not a regular lon/lat grid — see module docstring)."""
    import h5py  # local import: only needed by this function, keeps module import cheap for tests

    if pass_name not in SMAP_GROUP_BY_PASS:
        raise ValueError(f"pass_name must be one of {sorted(SMAP_GROUP_BY_PASS)}, got {pass_name!r}")

    group_name = SMAP_GROUP_BY_PASS[pass_name]
    suffix = "_pm" if pass_name == "PM" else ""
    min_lon, min_lat, max_lon, max_lat = bbox

    with h5py.File(granule_path, "r") as f:
        if group_name not in f:
            raise RuntimeError(
                f"{granule_path}: expected group '{group_name}' not found (has: {list(f.keys())}). "
                f"The public SPL3SMP_E structure this was written against may not match this "
                f"file's actual structure — see module docstring; this is exactly the mismatch "
                f"the docstring warns is unverified."
            )
        group = f[group_name]
        field_names = {
            "soil_moisture": f"{SMAP_SOIL_MOISTURE_FIELD}{suffix}",
            "qual_flag": f"{SMAP_QUAL_FLAG_FIELD}{suffix}",
            "lat": f"latitude{suffix}",
            "lon": f"longitude{suffix}",
        }
        missing = [name for name in field_names.values() if name not in group]
        if missing:
            raise RuntimeError(
                f"{granule_path}: expected field(s) {missing} not found in group '{group_name}' "
                f"(has: {list(group.keys())}). Same unverified-structure caveat as above."
            )
        soil_moisture = np.asarray(group[field_names["soil_moisture"]][:], dtype=np.float64)
        qual_flag = np.asarray(group[field_names["qual_flag"]][:])
        lat = np.asarray(group[field_names["lat"]][:], dtype=np.float64)
        lon = np.asarray(group[field_names["lon"]][:], dtype=np.float64)

    if not (soil_moisture.shape == qual_flag.shape == lat.shape == lon.shape):
        raise RuntimeError(
            f"{granule_path}: field shape mismatch in group '{group_name}' "
            f"(soil_moisture={soil_moisture.shape}, qual_flag={qual_flag.shape}, "
            f"lat={lat.shape}, lon={lon.shape}) — real file structure differs from the documented "
            f"layout this was written against."
        )

    mask = (
        (soil_moisture != SMAP_FILL_VALUE)
        & (lat != SMAP_FILL_VALUE)
        & (lon != SMAP_FILL_VALUE)
        & (lon >= min_lon)
        & (lon <= max_lon)
        & (lat >= min_lat)
        & (lat <= max_lat)
    )
    row_idx, col_idx = np.where(mask)

    rows = [
        {
            "pixel_id": f"ease_{r}_{c}",
            "lon": float(lon[r, c]),
            "lat": float(lat[r, c]),
            "soil_moisture": float(soil_moisture[r, c]),
            "recommended_quality": (int(qual_flag[r, c]) & (1 << SMAP_QUAL_RECOMMENDED_BIT)) == 0,
        }
        for r, c in zip(row_idx, col_idx)
    ]
    return pd.DataFrame(
        rows, columns=["pixel_id", "lon", "lat", "soil_moisture", "recommended_quality"]
    )


def extract_pixel_readings(granule_path: Path, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    """Reads both AM and PM groups, returns one combined DataFrame with a `pass_name` column.
    Rows with `recommended_quality=False` are KEPT (not silently dropped) so `select_best_reading`
    can fall back to a lower-quality reading rather than report nothing at all — see its docstring."""
    frames = [
        read_granule_soil_moisture(granule_path, bbox, pass_name=pass_name).assign(pass_name=pass_name)
        for pass_name in ("AM", "PM")
    ]
    combined = pd.concat(frames, ignore_index=True)
    if combined.empty:
        combined = pd.DataFrame(
            columns=["pixel_id", "lon", "lat", "soil_moisture", "recommended_quality", "pass_name"]
        )
    return combined


# Priority order for select_best_reading: prefer AM (SMAP's descending pass, ~6am LST — the
# conventional reference pass for soil moisture validation/use in the literature) over PM, and
# prefer recommended-quality over not — but a lower-confidence reading beats no reading at all,
# which is why "not recommended" tiers are included rather than treated as equivalent to missing.
_PASS_QUALITY_PRIORITY: list[tuple[str, bool]] = [("AM", True), ("PM", True), ("AM", False), ("PM", False)]


def select_best_reading(readings: pd.DataFrame, pixel_id: str) -> dict | None:
    """Picks the single best available reading for `pixel_id` out of a combined AM+PM
    `extract_pixel_readings` DataFrame, per `_PASS_QUALITY_PRIORITY`. Returns None if `pixel_id`
    has no reading at all this granule (a genuinely missing retrieval — e.g. masked by cloud/snow/
    open-water/precipitation per the User Guide's surface-condition flags, see module docstring)."""
    subset = readings[readings["pixel_id"] == pixel_id]
    if subset.empty:
        return None
    for pass_name, want_recommended in _PASS_QUALITY_PRIORITY:
        match = subset[
            (subset["pass_name"] == pass_name) & (subset["recommended_quality"] == want_recommended)
        ]
        if not match.empty:
            row = match.iloc[0]
            return {
                "soil_moisture": float(row["soil_moisture"]),
                "pass_name": pass_name,
                "recommended_quality": bool(row["recommended_quality"]),
            }
    return None


# =============================================================================================
# Cell -> pixel mapping (needs a real read granule's lon/lat — see module docstring for why this
# can't be analytic the way imerg.py's version is)
# =============================================================================================
def assign_cells_to_pixels(cells_gpkg_path: Path, pixel_lookup: pd.DataFrame) -> pd.DataFrame:
    """Maps each real cell_id (from data/static/<aoi>/cells.gpkg) to the pixel_id of the nearest
    SMAP EASE-Grid pixel found in `pixel_lookup` (columns: pixel_id, lon, lat — typically the
    de-duplicated output of `extract_pixel_readings`/the persistent latest-cache CSV, task 1.10).
    Nearest-by-plain-Euclidean-degrees is an adequate approximation at this AOI's scale (~25 km
    across) with only a handful of candidate pixels — the same order of approximation
    imerg.py's simpler rounding-based version makes, just computed differently because EASE-Grid
    2.0's cells don't fall on a regular lon/lat grid (see module docstring)."""
    import geopandas as gpd  # local import — see read_granule_soil_moisture's note

    if pixel_lookup.empty:
        raise ValueError("pixel_lookup is empty — no SMAP pixels available to map cells onto")

    cells = gpd.read_file(cells_gpkg_path)
    centroids_wgs84 = (
        cells.geometry.centroid.to_crs(epsg=4326)
        if cells.crs != "EPSG:4326"
        else cells.geometry.centroid
    )
    pixel_lons = pixel_lookup["lon"].to_numpy()
    pixel_lats = pixel_lookup["lat"].to_numpy()
    pixel_ids = pixel_lookup["pixel_id"].to_numpy()

    def nearest_pixel_id(lon: float, lat: float) -> str:
        dist2 = (pixel_lons - lon) ** 2 + (pixel_lats - lat) ** 2
        return str(pixel_ids[int(np.argmin(dist2))])

    return pd.DataFrame(
        {
            "cell_id": cells["cell_id"].values,
            "pixel_id": [nearest_pixel_id(pt.x, pt.y) for pt in centroids_wgs84],
        }
    )


# =============================================================================================
# Persistent "latest known good" cache — soil moisture is used as a snapshot covariate (LHASA v2
# framing: fused with antecedent RAINFALL, not with antecedent soil moisture itself), unlike
# imerg.py's rolling-window rainfall features, so there is no reason to keep a full time series
# here — just the most recent reading per pixel, upserted, so a tick can still serve a (labelled)
# stale value if today's fetch fails or hasn't published yet (mirrors imerg.py's
# "yielding with stale cache" graceful-degradation pattern).
# =============================================================================================
LATEST_CACHE_COLUMNS = [
    "pixel_id",
    "lon",
    "lat",
    "date",
    "soil_moisture",
    "pass_name",
    "recommended_quality",
]


def update_latest_cache(readings: pd.DataFrame, date: datetime, store_path: Path) -> None:
    """Upserts one row per pixel_id (the `select_best_reading` winner for `date`) into the
    persistent CSV store, replacing any previous row for that pixel_id. A plain CSV rewrite, not
    an append-only log — acceptable at this scale (a handful of pixels), same "not a proper
    time-series DB, documented as fine at this size" judgment imerg.py's own docstring makes."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    date_str = granule_day_bounds(date)[0].date().isoformat()

    new_rows = []
    for pixel_id in readings["pixel_id"].unique():
        best = select_best_reading(readings, pixel_id)
        if best is None:
            continue
        pixel_row = readings[readings["pixel_id"] == pixel_id].iloc[0]
        new_rows.append(
            {
                "pixel_id": pixel_id,
                "lon": float(pixel_row["lon"]),
                "lat": float(pixel_row["lat"]),
                "date": date_str,
                **best,
            }
        )
    new_df = pd.DataFrame(new_rows, columns=LATEST_CACHE_COLUMNS)

    if store_path.is_file():
        existing = pd.read_csv(store_path)
        if not new_df.empty:
            existing = existing[~existing["pixel_id"].isin(new_df["pixel_id"])]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df
    combined.to_csv(store_path, index=False)


# =============================================================================================
# Orchestration
# =============================================================================================
def backfill_history(
    aoi: AoiConfig,
    username: str,
    password: str,
    days: int,
    now: datetime,
    store_path: Path,
    cache_dir: Path = GRANULE_CACHE_DIR,
) -> int:
    """Fetches every daily granule from `days` ago up to `now` and upserts it into the persistent
    latest-cache store. Idempotent: granule downloads are cached on disk; re-running for an
    already-cached day just re-reads the cached file rather than re-downloading. Returns the count
    of granules actually fetched-or-read (not the count of NEW downloads — unlike imerg.py's
    version, a day already present in the CSV cache still gets re-parsed here so its row reflects
    the latest `select_best_reading` logic if that logic has changed since the cache was written)."""
    fetched = 0
    for offset in range(days + 1):
        day = now - timedelta(days=offset)
        try:
            granule_path = download_granule(day, aoi.bbox, username, password, cache_dir)
            readings = extract_pixel_readings(granule_path, aoi.bbox)
            if not readings.empty:
                update_latest_cache(readings, day, store_path)
            fetched += 1
        except (requests.RequestException, RuntimeError) as exc:
            print(f"SMAP granule for {day.date()} unavailable ({exc}); skipping.")
    return fetched


class SmapLiveSource:
    """Live DataSource (BUILD_PLAN.md task 1.7) — polls for the latest published SMAP daily
    granule, updates the persistent per-pixel latest-cache, and yields real-cell ObservationFrames
    with `rain_*` fields left at the 0.0 placeholder (this is a soil-moisture-ONLY live source —
    see module docstring's "Not wired into ingest/factory.py" note for why, mirroring imerg.py's
    own `soil_moisture=None` placeholder in the opposite direction)."""

    def __init__(
        self,
        clock: Clock,
        aoi_id: str,
        username: str,
        password: str,
        *,
        cells_gpkg_path: Path | None = None,
        store_path: Path | None = None,
        poll_interval_seconds: float = 6 * 3600.0,  # engineering default, not a cited latency
    ):
        if not clock.is_live:
            raise ValueError("SmapLiveSource requires a live Clock (got a non-live one)")
        self._clock = clock
        self._aoi = get_aoi(aoi_id)
        self._username = username
        self._password = password
        self._cells_gpkg_path = cells_gpkg_path or (
            REPO_ROOT / "data" / "static" / aoi_id / "cells.gpkg"
        )
        self._store_path = store_path or (
            REPO_ROOT / "data" / "static" / aoi_id / "smap_soil_moisture_latest.csv"
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._cell_to_pixel: pd.DataFrame | None = None

    def _load_cell_mapping(self, latest: pd.DataFrame) -> pd.DataFrame | None:
        if self._cell_to_pixel is None and not latest.empty:
            pixel_lookup = latest[["pixel_id", "lon", "lat"]].drop_duplicates("pixel_id")
            self._cell_to_pixel = assign_cells_to_pixels(self._cells_gpkg_path, pixel_lookup)
        return self._cell_to_pixel

    async def frames(self) -> AsyncIterator[ObservationFrame]:
        import asyncio

        while True:
            now = self._clock.now()
            try:
                granule_path = download_granule(now, self._aoi.bbox, self._username, self._password)
                readings = extract_pixel_readings(granule_path, self._aoi.bbox)
                if not readings.empty:
                    update_latest_cache(readings, now, self._store_path)
            except (requests.RequestException, RuntimeError, ValueError) as exc:
                # A missed/not-yet-published granule degrades the feature set for this tick rather
                # than stalling the whole pipeline — same "circuit breaker" spirit as task 1.8's
                # IMD adapter, and the same fallback pattern imerg.py's ImergLiveSource uses.
                print(f"SmapLiveSource: granule fetch failed ({exc}); yielding with stale cache")

            latest = pd.read_csv(self._store_path) if self._store_path.is_file() else pd.DataFrame()
            cell_to_pixel = self._load_cell_mapping(latest)

            cells = []
            latest_by_pixel = (
                latest.drop_duplicates("pixel_id", keep="last").set_index("pixel_id")
                if not latest.empty
                else pd.DataFrame()
            )
            if cell_to_pixel is not None:
                for _, row in cell_to_pixel.iterrows():
                    soil_moisture = None
                    if row["pixel_id"] in latest_by_pixel.index:
                        soil_moisture = float(latest_by_pixel.loc[row["pixel_id"], "soil_moisture"])
                    cells.append(
                        CellObservation(
                            cell_id=row["cell_id"],
                            rain_1h=0.0,
                            rain_6h=0.0,
                            rain_24h=0.0,
                            rain_72h=0.0,
                            antecedent_7d=0.0,
                            antecedent_15d=0.0,
                            antecedent_30d=0.0,
                            soil_moisture=soil_moisture,
                            insar_velocity_mm_yr=None,
                            source="smap",
                            is_reconstructed=False,
                        )
                    )

            yield ObservationFrame(
                t=now,
                aoi_id=self._aoi.id,
                cells=cells,
                provenance={
                    "source": "NASA SMAP Enhanced L3 Radiometer (SPL3SMP_E, DCA baseline algorithm)",
                    "resolution": "9 km EASE-Grid 2.0 native (~36 km native footprint, "
                    "interpolated), mapped onto 500 m analysis cells",
                    "surface_proxy_note": (
                        "surface proxy (top 5 cm) - NOT pore-water pressure; fuse with antecedent "
                        "rainfall per NASA LHASA v2 framing (CLAUDE.md honesty rule 5)."
                    ),
                },
            )
            await asyncio.sleep(self._poll_interval_seconds)


def main() -> None:
    import os

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    parser.add_argument("--backfill-days", type=int, default=3, help="Days of history to backfill")
    args = parser.parse_args()

    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not username or not password:
        raise RuntimeError("EARTHDATA_USERNAME/EARTHDATA_PASSWORD not set in .env")

    aoi = get_aoi(args.aoi)
    store_path = REPO_ROOT / "data" / "static" / args.aoi / "smap_soil_moisture_latest.csv"
    # CLAUDE.md rule 14 (datetime.now() banned outside core/clock.py) applies here too — go
    # through LiveClock like every other CLI entry point in this repo (imerg.py's own docstring
    # flags this exact mistake having been caught once already; not repeating it).
    now = LiveClock().now()
    count = backfill_history(aoi, username, password, args.backfill_days, now, store_path)
    print(f"Fetched/read {count} day(s) of granules. Store: {store_path}")

    latest = pd.read_csv(store_path) if store_path.is_file() else pd.DataFrame()
    for _, row in latest.iterrows():
        print(f"  pixel {row['pixel_id']} ({row['date']}, {row['pass_name']}): {row['soil_moisture']}")


if __name__ == "__main__":
    main()
