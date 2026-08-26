"""IMD (India Meteorological Department) public API adapter (BUILD_PLAN.md task 1.8) — district
nowcast + district warnings for the AOI's district. Explicitly SUPPLEMENTARY, not critical path:
IMERG is the primary rainfall source (CLAUDE.md's own risk register), IMD is corroborating
context, and BUILD_PLAN.md itself warns "Expect IP-whitelisting friction" — hence the circuit
breaker this whole module is built around (see `CircuitBreaker` below).

STATUS, read before touching this file: real network access to `api.imd.gov.in` was attempted
from this sandboxed environment and refused outright, the same way `smap.py`'s session couldn't
reach NSIDC/CMR either (see that module's docstring) — and separately, IMD API access itself has
not yet been requested for this project at all (Required_by_me.md, task 1.8's own checklist item
is unchecked). So nothing here has been run against a real response, by design and as expected —
this module is real, tested code against the MOST DEFENSIBLE structure this session could find
publicly cited, with every field-name/auth assumption marked TODO(verify) rather than guessed
silently, per this task's own brief.

What IS confirmed against real, cited public documentation this session (not guessed) — fetched
and read from `https://api.imd.gov.in/public/api_reference.html` (IMD's own API reference page):
- Base URL: `https://api.imd.gov.in/api/v1`.
- District-wise Nowcast: `GET /districtnowcast` (optional `?id=<district id>`; omitting `id`
  returns all districts as a list — used here instead of guessing a numeric district id, see
  "Endpoint strategy" below). Documented fields: `Station`, `Date`, `Cat1`-`Cat19` (nowcast hazard
  category codes), `message` (plain-language text), `toi` (time of issue, HHmm), `Vupto` (valid
  until, HHmm), `color` (1-4).
- District-wise Warnings: `GET /districtwarning` (optional `?id=<district object id>`). Documented
  fields: `Obj_id`, `Date`, `UTC`, `District`, `Day_1`..`Day_5` (warning codes), `Day1_Color`..
  `Day5_Color` (1-4 codes).
- Several OTHER endpoints on this exact same API surface (cyclone_track, cyclone_wind, sunmoon)
  are documented with a `{status, message, totalCount, data: [...]}` envelope. districtnowcast/
  districtwarning's own field list (above) reads as a flat per-record shape, consistent with being
  the CONTENTS of that same envelope's `data` array — `extract_records()` below assumes this
  envelope convention holds across the whole gateway (a real, cited pattern from the SAME
  documentation page, not invented), but falls back to treating a bare top-level JSON array as the
  record list too, in case districtnowcast/districtwarning specifically don't use the envelope.
  TODO(verify) once a real response can be inspected.

What is genuinely NOT confirmed (marked TODO(verify) at the point of use, per this task's brief,
rather than guessed silently):
- Authentication mechanism. No public page this session could reach documents the header/query-
  param name for the API key ("IMD API Management" in search results points at a standard APIM-
  style gateway product, which commonly uses an `X-Api-Key`-style header — used here as the most
  defensible default, not a confirmed fact). See `build_auth_headers()`.
- The exact `District`/`Station` name string IMD uses for Aizawl (casing, whether it's "Aizawl" or
  something like "Aizawl Dist" or a full "Aizawl, Mizoram" form). See
  `AoiConfig.imd_district_name` (backend/app/config.py) and `resolve_district_name()` below.
- Whether `id` really means "omit it for all districts" for BOTH endpoints, or whether one of them
  requires it. Documented as optional for both on the reference page; this module always omits it
  and filters client-side by district name instead of guessing a numeric id (BUILD_PLAN.md
  explicitly bans inventing figures/ids we can't cite).
- Exact rate limits / IP-whitelisting behaviour beyond BUILD_PLAN's own "expect friction" warning.

Deliberate scope ruling (flag this prominently — see the task brief's own instruction to call out
IMD-format rulings): this module does NOT implement a `DataSource`/`frames()` wrapper the way
imerg.py/smap.py do. Their payloads map cleanly onto existing `CellObservation` fields
(rain_*, soil_moisture); IMD's payload (categorical nowcast hazard codes, per-day warning colour
codes) has NO corresponding field on `CellObservation`, and inventing one (or stuffing formatted
strings into `ObservationFrame.provenance`, which is free-form `dict[str, str]` but meant for
metadata like source/resolution, not primary content) would be exactly the kind of schema-avoidance
CLAUDE.md rule 12 warns against ("change the schema first, then the producers, then the
consumers"). Wiring IMD data into the product needs a real schema decision (most likely a new
"official advisory" concept under decision/ or dissemination/, echoing scenario files' existing
`ground_truth.official_warnings` shape) that is out of this task's scope — this module instead
exposes a small, well-tested, circuit-breaker-protected CLIENT (`fetch_district_nowcast`,
`fetch_district_warning`) that a future task can wire in once that schema exists.

Usage (standalone):
    python -m app.ingest.live.imd --aoi aizawl
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, TypeVar

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import requests  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402
from app.core.clock import LiveClock  # noqa: E402

T = TypeVar("T")

IMD_BASE_URL = "https://api.imd.gov.in/api/v1"
IMD_DISTRICT_NOWCAST_PATH = "/districtnowcast"
IMD_DISTRICT_WARNING_PATH = "/districtwarning"

# Fields a matched record must have to be trusted (see module docstring's citation). A record that
# superficially matches our district but is MISSING these is treated as a format mismatch (raises
# IMDResponseFormatError, counts as a circuit-breaker failure) — not silently accepted as partial
# data, per this task's own "fails closed rather than silently parsing garbage" instruction.
DISTRICT_NOWCAST_REQUIRED_FIELDS = ("Station", "Date", "message", "color")
DISTRICT_WARNING_REQUIRED_FIELDS = ("District", "Date", "Day_1")

DEFAULT_TIMEOUT_SECONDS = 15.0


# =============================================================================================
# Exceptions — one clean type for callers to catch (see call_with_breaker)
# =============================================================================================
class IMDResponseFormatError(Exception):
    """The response was received but doesn't match the documented shape this module was written
    against (module docstring). Deliberately distinct from requests.RequestException so tests can
    tell "network/HTTP problem" apart from "wrong format" — both are treated the same way by
    call_with_breaker (both count as a circuit-breaker failure), but keeping them distinct
    exception types costs nothing and helps anyone debugging a real failure later."""


class IMDUnavailableError(Exception):
    """Raised by call_with_breaker for BOTH "the breaker is open, request not even attempted" and
    "the request was attempted and failed" — callers (the CLI entry point, and any future
    pipeline integration) should catch exactly this one type and treat it as "no IMD data this
    tick," never let it propagate up and stall anything. IMD is supplementary, not critical path
    (CLAUDE.md's own risk register / Required_by_me.md)."""


# =============================================================================================
# Circuit breaker (BUILD_PLAN.md task 1.8) — no existing library found in
# backend/requirements*.txt (checked: fastapi/pydantic/uvicorn/websockets/python-dotenv/pytest/
# httpx/rasterio/shapely/geopandas/pyproj/requests/scipy/h5py/sqlalchemy/geoalchemy2/psycopg2/
# scikit-learn/xgboost/shap/networkx/osmnx/lxml — none provide one), so this is a small
# hand-written one rather than pulling in a new dependency for ~30 lines of logic.
# =============================================================================================
class CircuitState(str, Enum):
    CLOSED = "closed"  # normal — requests allowed
    OPEN = "open"  # >= failure_threshold consecutive failures — requests short-circuited
    HALF_OPEN = "half_open"  # cooldown elapsed — exactly one trial request is allowed through


class CircuitBreaker:
    """Stateless with respect to wall time BY DESIGN: every method takes `now` explicitly instead
    of holding a Clock. This means CLAUDE.md rule 14 (datetime.now() banned outside
    core/clock.py) is trivially satisfied — this class never reads time itself — and the breaker
    is easy to unit-test without any Clock plumbing at all. Callers (the CLI entry point here, and
    any future pipeline integration) pass `clock.now()` at the call site, same as every other
    non-core module in this repo.

    CLOSED -> OPEN after `failure_threshold` consecutive failures. OPEN -> HALF_OPEN once
    `cooldown_seconds` have elapsed since the circuit opened (computed on read, not by a timer).
    HALF_OPEN allows exactly one trial request through (via allow_request/record_*): success ->
    CLOSED, failure -> OPEN again (and the cooldown restarts from that failure's `now`).
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 300.0):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be > 0")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._opened_at: datetime | None = None

    def state(self, now: datetime) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        elapsed = (now - self._opened_at).total_seconds()
        return CircuitState.HALF_OPEN if elapsed >= self.cooldown_seconds else CircuitState.OPEN

    def allow_request(self, now: datetime) -> bool:
        return self.state(now) != CircuitState.OPEN

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self, now: datetime) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            # (Re)opens and restarts the cooldown — covers both the CLOSED->OPEN transition and a
            # failed HALF_OPEN trial re-opening the circuit.
            self._opened_at = now


def call_with_breaker(breaker: CircuitBreaker, now: datetime, fn: Callable[[], T]) -> T:
    """Runs `fn()` through `breaker`. Raises IMDUnavailableError immediately (no network call
    attempted at all) if the breaker is OPEN; otherwise calls `fn()` and records success/failure
    on the breaker, wrapping any (requests.RequestException | IMDResponseFormatError) as
    IMDUnavailableError so every caller has exactly one exception type to catch. `fn()` returning
    a plain value (including None, e.g. "well-formed response, our district just wasn't in it
    today") counts as a SUCCESS — the API and the response format both worked; a missing district
    is not a format failure (see resolve_district_name/parse_district_* docstrings)."""
    if not breaker.allow_request(now):
        raise IMDUnavailableError(
            f"circuit breaker {breaker.state(now).value}; skipping IMD request without a network call"
        )
    try:
        result = fn()
    except (requests.RequestException, IMDResponseFormatError) as exc:
        breaker.record_failure(now)
        raise IMDUnavailableError(f"IMD request failed: {exc}") from exc
    else:
        breaker.record_success()
        return result


# =============================================================================================
# Auth (see module docstring — genuinely unconfirmed, marked TODO(verify) rather than guessed
# silently, per this task's own brief)
# =============================================================================================
def build_auth_headers(api_key: str) -> dict[str, str]:
    """TODO(verify): api.imd.gov.in's exact API-key delivery mechanism (header vs query param,
    exact name) is not confirmed by any public documentation this session could reach — see module
    docstring. `X-Api-Key` is used as the most defensible default (a common convention for this
    style of API-management gateway product), not a confirmed fact. If real calls 401/403 once IMD
    access is granted (Required_by_me.md), this is the one function to fix."""
    return {"X-Api-Key": api_key}


# =============================================================================================
# Response envelope + record parsing (pure — see TestExtractRecords / TestParseDistrict*)
# =============================================================================================
def extract_records(payload: object) -> list[dict]:
    """Normalizes a decoded JSON response into a flat list of per-district record dicts. Accepts
    (in priority order): a bare top-level JSON array; a `{..., "data": [...]}` envelope (the shape
    confirmed for other endpoints on this same API — see module docstring); a single bare record
    dict (e.g. what a real `?id=` filtered request might return, unwrapped). Raises
    IMDResponseFormatError for anything else — an unrecognized envelope IS a format mismatch, not
    silently treated as "zero records"."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        if any(key in payload for key in ("Station", "District", "Obj_id")):
            return [payload]
    raise IMDResponseFormatError(
        f"unrecognized IMD API response envelope (type={type(payload).__name__}); expected a "
        f"JSON array, a {{'data': [...]}} envelope, or a single district record dict"
    )


def resolve_district_name(aoi: AoiConfig) -> str:
    """`aoi.imd_district_name` if set (task 1.8's own config addition — see config.py), else a
    best-effort derivation from `aoi.name` (e.g. "Aizawl, Mizoram" -> "Aizawl"). Both are
    TODO(verify) against a real IMD response — see module docstring."""
    if aoi.imd_district_name:
        return aoi.imd_district_name
    return aoi.name.split(",")[0].strip()


def parse_district_nowcast(records: list[dict], district_name: str) -> dict | None:
    """Finds the record for `district_name` (case-insensitive exact match against `Station`).
    Returns None if no record matches — a well-formed response simply not covering our district
    today is NOT a format error (does not count as a circuit-breaker failure; see
    call_with_breaker's docstring) and is not itself proof `district_name` is wrong. Raises
    IMDResponseFormatError only if a MATCHING record is missing expected fields — that pattern
    really would mean the documented structure doesn't match reality."""
    target = district_name.strip().lower()
    for record in records:
        if str(record.get("Station", "")).strip().lower() == target:
            missing = [f for f in DISTRICT_NOWCAST_REQUIRED_FIELDS if f not in record]
            if missing:
                raise IMDResponseFormatError(
                    f"districtnowcast record for {district_name!r} is missing expected field(s) "
                    f"{missing}: keys present = {sorted(record.keys())}"
                )
            return record
    return None


def parse_district_warning(records: list[dict], district_name: str) -> dict | None:
    """Same contract as parse_district_nowcast, against the `District` field."""
    target = district_name.strip().lower()
    for record in records:
        if str(record.get("District", "")).strip().lower() == target:
            missing = [f for f in DISTRICT_WARNING_REQUIRED_FIELDS if f not in record]
            if missing:
                raise IMDResponseFormatError(
                    f"districtwarning record for {district_name!r} is missing expected field(s) "
                    f"{missing}: keys present = {sorted(record.keys())}"
                )
            return record
    return None


# =============================================================================================
# Network calls
# =============================================================================================
def _request_json(path: str, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> object:
    headers = build_auth_headers(api_key)
    response = requests.get(f"{IMD_BASE_URL}{path}", headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_district_nowcast(
    district_name: str, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict | None:
    """Fetches ALL districts' nowcasts (no `?id=`, see module docstring's "Endpoint strategy") and
    returns just `district_name`'s record, or None if not present this tick."""
    payload = _request_json(IMD_DISTRICT_NOWCAST_PATH, api_key, timeout=timeout)
    return parse_district_nowcast(extract_records(payload), district_name)


def fetch_district_warning(
    district_name: str, api_key: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict | None:
    """Same as fetch_district_nowcast, against the districtwarning endpoint."""
    payload = _request_json(IMD_DISTRICT_WARNING_PATH, api_key, timeout=timeout)
    return parse_district_warning(extract_records(payload), district_name)


def main() -> None:
    import os

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()

    api_key = os.environ.get("IMD_API_KEY")
    if not api_key:
        raise RuntimeError("IMD_API_KEY not set in .env (see Required_by_me.md — IMD access not yet requested)")

    aoi = get_aoi(args.aoi)
    district = resolve_district_name(aoi)
    breaker = CircuitBreaker()
    # CLAUDE.md rule 14 (datetime.now() banned outside core/clock.py) applies here too — go
    # through LiveClock like every other CLI entry point in this repo.
    now = LiveClock().now()

    try:
        nowcast = call_with_breaker(breaker, now, lambda: fetch_district_nowcast(district, api_key))
        print(f"districtnowcast[{district}]: {nowcast if nowcast is not None else '(no record this tick)'}")
    except IMDUnavailableError as exc:
        print(f"districtnowcast[{district}]: unavailable ({exc})")

    try:
        warning = call_with_breaker(breaker, now, lambda: fetch_district_warning(district, api_key))
        print(f"districtwarning[{district}]: {warning if warning is not None else '(no record this tick)'}")
    except IMDUnavailableError as exc:
        print(f"districtwarning[{district}]: unavailable ({exc})")


if __name__ == "__main__":
    main()
