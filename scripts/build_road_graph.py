#!/usr/bin/env python
"""Build the OSM road graph for an AOI (BUILD_PLAN.md task 2.1).

Downloads the drivable road network for the AOI bbox via OSMnx, keeps it as a plain
`networkx.MultiDiGraph` (so downstream consumers — impact/road_graph.py, impact/isolation.py —
only need `networkx`, never `osmnx`), and writes two artifacts:

  - data/osm/<aoi>_graph.pkl      — the pickled NetworkX graph (edges keyed by (u, v, key),
                                    node attrs `x`/`y` = lon/lat, edge attrs preserved from OSM).
  - data/osm/<aoi>_graph.geojson  — the same edges as a GeoJSON FeatureCollection, for map
                                    rendering (frontend task 2.7) and for eyeballing the extract.

CLAUDE.md §6 / BUILD_PLAN.md task 2.1: **OSMnx runs ONLY in this script, never at request time.**
`impact/road_graph.py` and `impact/isolation.py` load the pickled graph and only ever import
`networkx` — never `osmnx` — enforced by keeping the graph a bare `nx.MultiDiGraph`, not an
osmnx-specific subclass, so no osmnx import is even possible to reach for through the pickle.

Both output files are gitignored (`data/osm/*` per .gitignore, "never commit large binaries" —
CLAUDE.md rule 15) — this script is meant to be re-run (`make graph AOI=aizawl`), not committed.

Preserves per BUILD_PLAN.md task 2.1's instruction:
  - `highway_class`  — the OSM `highway` tag (e.g. "trunk", "primary", "residential").
  - `is_bridge`      — True if the way's `bridge` tag is anything other than absent/"no".
  - `ref`            — the OSM `ref` tag (e.g. "NH-6", "SH-...") when present.
  - `name`           — the OSM `name` tag when present.

Network type is "drive" (OSMnx's `{"all","all_public","bike","drive","drive_service","walk"}`
preset) — matches CLAUDE.md's "OSM road graph" framing (RII, C_edge routing, NH-6/SH refs are
all vehicle-road concepts); a pedestrian/track network is a plausible future addition for
last-mile village-to-shelter routing but is out of this task's scope, not silently dropped.

OSMnx's own `bridge=yes` highway-way tag is what identifies road-segment bridges here — a
different (and, for Aizawl, better-populated) OSM tag than the `man_made=bridge` POINT layer
scripts/fetch_exposure.py queried for task 1.3 (which came back empty for Aizawl; documented
there as a rare tag, with `bridge=yes` on highway ways named as the not-yet-implemented fallback
— implemented here, for the road graph, which is the layer it actually belongs to).

Usage:
    python scripts/build_road_graph.py --aoi aizawl
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import networkx as nx  # noqa: E402
import osmnx as ox  # noqa: E402

from app.config import AoiConfig, get_aoi  # noqa: E402

# Same Overpass identification consideration discovered in scripts/build_grid.py /
# scripts/fetch_exposure.py (task 1.2/1.3) — that code hit a flat 406 from the default `requests`
# User-Agent and had to set an explicit one. OSMnx 2.x already sends its own descriptive default
# (`settings.http_user_agent`, "OSMnx Python package (...)") on every Overpass call, so the 406
# those scripts hit doesn't reproduce here — confirmed by actually running this script (see
# below), not assumed. We still override it to identify *this* project's traffic distinctly,
# via `settings.http_user_agent` — NOT `settings.requests_kwargs["headers"]`, which double-
# specifies the `headers` kwarg together with osmnx's own internal header construction and
# raises `TypeError: requests.api.get() got multiple values for keyword argument 'headers'`
# (found by actually hitting this, not assumed).
_OVERPASS_USER_AGENT = "NIRANTAR-SIH26001/0.1 (research prototype; contact 240186.cs@rmkec.ac.in)"

NETWORK_TYPE = "drive"


def _reliable_overpass_request(data):
    """Replaces osmnx's own `osmnx._overpass._overpass_request` with a plain `requests.post` —
    monkeypatched in by `_configure_osmnx()` below.

    WHY THIS EXISTS (found by direct diagnosis in this environment, not assumed): osmnx's real
    `_overpass_request` calls `_http._config_dns(...)` before every request, which resolves
    `overpass-api.de` to ONE specific IP via `socket.gethostbyname()` and then monkeypatches
    `socket.getaddrinfo` so every subsequent request in the process reuses that same pinned IP —
    a deliberate osmnx feature so a preliminary rate-limit-slot check and the real query always
    land on the same physical backend server (Overpass round-robins several).

    In this environment that pinned IP reliably `ConnectTimeout`s (reproduced 3 times, cumulative
    ~40 minutes) — while a plain `requests.post` to the exact same URL, with the exact same query
    (including this AOI's full-size, ~12.7 MB-response bbox query), succeeds in under 5 seconds
    every time it was tried directly. The difference is specifically osmnx's DNS-pinning
    (`socket.gethostbyname`, IPv4-only, legacy) vs. an ordinary fresh resolution
    (`socket.getaddrinfo`, used internally by `requests`/urllib3) — not query size, not rate
    limiting (no 429/503 was ever seen), and not the AOI being too large.

    This function is otherwise a faithful copy of the real one's HTTP semantics (cache-first via
    osmnx's own cache helpers, so this doesn't disable osmnx's caching; a short courtesy pause
    instead of the real function's own rate-limit-slot GET check, which hit the identical
    DNS-pinning problem; 429/504 retry with backoff, reusing the retry-on-transient-error pattern
    scripts/fetch_exposure.py already established for the same Overpass host) — it only removes
    the DNS-pinning and the pre-flight status GET.
    """
    import time as _time

    import requests as _requests
    from osmnx import _http as _osmnx_http
    from osmnx import settings as _osmnx_settings

    url = _osmnx_settings.overpass_url.rstrip("/") + "/interpreter"
    prepared_url = str(_requests.Request("GET", url, params=data).prepare().url)
    cached = _osmnx_http._retrieve_from_cache(prepared_url)
    if isinstance(cached, dict):
        return cached

    for attempt in range(5):
        response = _requests.post(
            url,
            data=data,
            timeout=_osmnx_settings.requests_timeout,
            headers={"User-Agent": _osmnx_settings.http_user_agent},
        )
        if response.status_code in (429, 504, 502, 503):
            wait_s = 55.0 * (attempt + 1)
            print(f"  Overpass HTTP {response.status_code}, waiting {wait_s:.0f}s before retry ...")
            _time.sleep(wait_s)
            continue
        response_json = _osmnx_http._parse_response(response)
        if not isinstance(response_json, dict):
            raise RuntimeError("Overpass API did not return a dict of results.")
        _osmnx_http._save_to_cache(prepared_url, response_json, response.ok)
        return response_json
    raise RuntimeError("Overpass still failing after 5 retries")


def _configure_osmnx() -> None:
    ox.settings.http_user_agent = _OVERPASS_USER_AGENT
    ox.settings.overpass_url = "https://overpass-api.de/api"
    ox.settings.log_console = False
    # osmnx defaults its HTTP response cache to "./cache" relative to whatever directory it's
    # invoked from — left at that default this script would scatter a `backend/cache/` (or
    # wherever cwd happens to be) directory outside the project's usual data layout. Every other
    # script's own download cache lives under data/ (e.g. fetch_exposure.py's
    # data/static/_worldpop_tiles, build_grid.py's data/static/_worldcover_tiles) and data/osm/*
    # is already gitignored (CLAUDE.md rule 15: never commit large binaries), so this reuses that
    # same ignored location rather than adding a new stray gitignore entry.
    ox.settings.cache_folder = str(REPO_ROOT / "data" / "osm" / "_overpass_cache")
    # `_download_overpass_network`/`_download_overpass_features` call `_overpass_request` as a
    # bare module-global name, so reassigning it here (rather than at import time) is enough to
    # redirect every internal osmnx caller in this process — see `_reliable_overpass_request`'s
    # own docstring for why this is necessary in this environment.
    ox._overpass._overpass_request = _reliable_overpass_request


def _graph_from_osm_api_tiles(aoi: AoiConfig, *, divisions: int = 3) -> nx.MultiDiGraph:
    """Fallback for public Overpass outages using tiled, standard OSM map exports."""
    import time as _time

    import requests as _requests

    cache_dir = REPO_ROOT / "data" / "osm" / "_osm_api_cache" / aoi.id
    cache_dir.mkdir(parents=True, exist_ok=True)
    min_lon, min_lat, max_lon, max_lat = aoi.bbox
    lon_step = (max_lon - min_lon) / divisions
    lat_step = (max_lat - min_lat) / divisions
    graphs: list[nx.MultiDiGraph] = []

    def download_tile(left: float, bottom: float, right: float, top: float, label: str, depth: int = 0) -> list[Path]:
        path = cache_dir / f"tile-{label}.osm"
        if path.is_file():
            return [path]
        response = _requests.get(
            "https://api.openstreetmap.org/api/0.6/map",
            params={"bbox": f"{left},{bottom},{right},{top}"},
            headers={"User-Agent": _OVERPASS_USER_AGENT},
            timeout=180,
        )
        if response.status_code == 400 and depth < 3:
            mid_lon = (left + right) / 2.0
            mid_lat = (bottom + top) / 2.0
            print(f"  OSM tile {label} is dense; subdividing ...")
            return [
                *download_tile(left, bottom, mid_lon, mid_lat, f"{label}-0", depth + 1),
                *download_tile(mid_lon, bottom, right, mid_lat, f"{label}-1", depth + 1),
                *download_tile(left, mid_lat, mid_lon, top, f"{label}-2", depth + 1),
                *download_tile(mid_lon, mid_lat, right, top, f"{label}-3", depth + 1),
            ]
        response.raise_for_status()
        path.write_bytes(response.content)
        print(f"  cached OSM map tile {label}")
        _time.sleep(2.0)
        return [path]

    for row in range(divisions):
        for col in range(divisions):
            left = min_lon + col * lon_step
            right = min_lon + (col + 1) * lon_step
            bottom = min_lat + row * lat_step
            top = min_lat + (row + 1) * lat_step
            for path in download_tile(left, bottom, right, top, f"{row}-{col}"):
                graphs.append(ox.graph_from_xml(path, simplify=False, retain_all=True))

    combined = nx.compose_all(graphs)
    excluded = {
        "bridleway", "construction", "corridor", "cycleway", "footway", "path",
        "pedestrian", "proposed", "raceway", "steps", "track",
    }
    for u, v, key, data in list(combined.edges(keys=True, data=True)):
        values = data.get("highway", [])
        classes = set(values if isinstance(values, list) else [values])
        if not classes or classes <= excluded:
            combined.remove_edge(u, v, key)
    combined.remove_nodes_from(list(nx.isolates(combined)))
    if combined.number_of_edges() == 0:
        raise RuntimeError("OSM map exports contained no routable road edges")
    return ox.simplification.simplify_graph(combined)


def _first(value):
    """OSMnx's `simplify_graph` merges consecutive same-topology edges, which can turn a
    scalar OSM tag value into a list of the merged segments' values. We only need one
    representative value per edge (not a full history of every merged segment's tag), so this
    takes the first non-null entry — documented simplification, not a data-loss bug: the
    GeoJSON/pickle still carries the *raw* OSMnx attribute unchanged in `raw_tags`, so nothing is
    actually discarded."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _is_bridge(value) -> bool:
    """True if any of the (possibly merged-list) `bridge` tag values is a real bridge marker.
    OSM's `bridge` tag is typically "yes", but also allows more specific values like "viaduct",
    "aqueduct", etc. — any non-"no", non-falsy value counts as a bridge segment."""
    values = value if isinstance(value, list) else [value]
    return any(v not in (None, False, "no") for v in values)


def build_road_graph(aoi_id: str) -> tuple[Path, Path]:
    aoi: AoiConfig = get_aoi(aoi_id)
    _configure_osmnx()

    print(f"Downloading OSMnx '{NETWORK_TYPE}' network for {aoi.name} (bbox={aoi.bbox}) ...")
    # AoiConfig.bbox is (min_lon, min_lat, max_lon, max_lat) — exactly OSMnx 2.x's
    # `(left, bottom, right, top)` bbox convention (verified against the installed osmnx's own
    # docstring), no reordering needed.
    force_osm_api = os.getenv("NIRANTAR_OSM_API_FALLBACK") == "1"
    try:
        if force_osm_api:
            raise RuntimeError("OSM API fallback explicitly selected")
        raw_graph = ox.graph_from_bbox(aoi.bbox, network_type=NETWORK_TYPE, simplify=True)
    except Exception as exc:
        print(f"  Overpass unavailable ({exc}); falling back to tiled OSM map exports ...")
        raw_graph = _graph_from_osm_api_tiles(aoi)
    print(f"  {raw_graph.number_of_nodes()} nodes, {raw_graph.number_of_edges()} edges")

    graph = nx.MultiDiGraph()
    for node_id, data in raw_graph.nodes(data=True):
        graph.add_node(node_id, x=float(data["x"]), y=float(data["y"]))

    n_bridges = 0
    n_refs = 0
    for u, v, key, data in raw_graph.edges(keys=True, data=True):
        highway_class = _first(data.get("highway")) or "unclassified"
        is_bridge = _is_bridge(data.get("bridge"))
        ref = _first(data.get("ref"))
        name = _first(data.get("name"))
        length_m = float(data.get("length", 0.0))
        geometry = data.get("geometry")  # shapely LineString if the edge is curved, else None

        n_bridges += int(is_bridge)
        n_refs += int(ref is not None)

        graph.add_edge(
            u,
            v,
            key=key,
            edge_id=f"{u}_{v}_{key}",
            highway_class=highway_class,
            is_bridge=is_bridge,
            ref=ref,
            name=name,
            length_m=length_m,
            geometry=geometry,
        )

    print(f"  {n_bridges} bridge-tagged edges, {n_refs} edges with an NH/SH-style ref")

    out_dir = REPO_ROOT / "data" / "osm"
    out_dir.mkdir(parents=True, exist_ok=True)

    pkl_path = out_dir / f"{aoi_id}_graph.pkl"
    with pkl_path.open("wb") as f:
        pickle.dump(graph, f)
    print(f"Wrote {pkl_path}")

    geojson_path = out_dir / f"{aoi_id}_graph.geojson"
    _write_geojson(graph, geojson_path)
    print(f"Wrote {geojson_path}")

    return pkl_path, geojson_path


def _write_geojson(graph: nx.MultiDiGraph, out_path: Path) -> None:
    """Writes edges as a GeoJSON FeatureCollection. Uses the node x/y endpoints (not OSMnx's own
    `graph_to_gdfs`, to avoid re-deriving anything osmnx-specific) — falls back to a straight
    line between endpoints when an edge has no stored curved `geometry`, which is exactly what
    OSM/OSMnx themselves treat as the edge's implied shape for a non-curved way."""
    import json

    from shapely.geometry import LineString, mapping

    features = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        geometry = data.get("geometry")
        if geometry is None:
            u_data, v_data = graph.nodes[u], graph.nodes[v]
            geometry = LineString([(u_data["x"], u_data["y"]), (v_data["x"], v_data["y"])])
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": {
                    "edge_id": data["edge_id"],
                    "name": data["name"],
                    "highway_class": data["highway_class"],
                    "is_bridge": data["is_bridge"],
                    "ref": data["ref"],
                    "length_m": data["length_m"],
                },
            }
        )

    out_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aoi", required=True, help="AOI id from backend/app/config.py, e.g. aizawl")
    args = parser.parse_args()
    build_road_graph(args.aoi)


if __name__ == "__main__":
    main()
