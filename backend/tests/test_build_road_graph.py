"""Contract test for scripts/build_road_graph.py (BUILD_PLAN.md task 2.1).

Pure-logic tests only (no network) for `_first`/`_is_bridge`/`_write_geojson`'s geometry
fallback, same pattern as tests/test_build_grid.py. The real OSMnx/Overpass download is verified
by actually running the script against the real Aizawl AOI (see CLAUDE.md §12 session log) — a
real integration check below is gated on that output already existing on disk, so CI in a fresh
checkout (data/osm/ gitignored) skips it rather than depending on Overpass being reachable.
"""
from __future__ import annotations

import importlib.util
import pickle
import sys
from pathlib import Path

import pytest

pytest.importorskip("networkx")
pytest.importorskip("osmnx")

import networkx as nx  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_road_graph.py"


def _load_build_road_graph():
    spec = importlib.util.spec_from_file_location("build_road_graph", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_road_graph"] = module
    spec.loader.exec_module(module)
    return module


brg = _load_build_road_graph()


def test_script_exists():
    assert SCRIPT_PATH.is_file()


class TestFirst:
    def test_scalar_passes_through(self):
        assert brg._first("trunk") == "trunk"

    def test_none_passes_through(self):
        assert brg._first(None) is None

    def test_list_takes_first_element(self):
        assert brg._first(["primary", "secondary"]) == "primary"

    def test_empty_list_gives_none(self):
        assert brg._first([]) is None


class TestIsBridge:
    def test_none_is_not_a_bridge(self):
        assert brg._is_bridge(None) is False

    def test_no_string_is_not_a_bridge(self):
        assert brg._is_bridge("no") is False

    def test_yes_string_is_a_bridge(self):
        assert brg._is_bridge("yes") is True

    def test_other_bridge_subtype_counts(self):
        assert brg._is_bridge("viaduct") is True

    def test_list_with_any_bridge_value_counts(self):
        assert brg._is_bridge(["no", "yes"]) is True

    def test_list_of_all_no_is_not_a_bridge(self):
        assert brg._is_bridge(["no", "no"]) is False

    def test_empty_list_is_not_a_bridge(self):
        assert brg._is_bridge([]) is False


class TestWriteGeojson:
    def test_falls_back_to_straight_line_when_no_curved_geometry(self, tmp_path):
        g = nx.MultiDiGraph()
        g.add_node(1, x=0.0, y=0.0)
        g.add_node(2, x=1.0, y=1.0)
        g.add_edge(
            1, 2, key=0, edge_id="1_2_0", highway_class="residential", is_bridge=False,
            ref=None, name=None, length_m=100.0, geometry=None,
        )
        out_path = tmp_path / "test.geojson"
        brg._write_geojson(g, out_path)

        import json

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        feature = data["features"][0]
        assert feature["geometry"]["type"] == "LineString"
        assert feature["geometry"]["coordinates"] == [[0.0, 0.0], [1.0, 1.0]]
        assert feature["properties"]["edge_id"] == "1_2_0"
        assert feature["properties"]["highway_class"] == "residential"
        assert feature["properties"]["is_bridge"] is False

    def test_uses_stored_curved_geometry_when_present(self, tmp_path):
        from shapely.geometry import LineString

        g = nx.MultiDiGraph()
        g.add_node(1, x=0.0, y=0.0)
        g.add_node(2, x=2.0, y=2.0)
        curved = LineString([(0.0, 0.0), (1.0, 0.5), (2.0, 2.0)])
        g.add_edge(
            1, 2, key=0, edge_id="e1", highway_class="trunk", is_bridge=True,
            ref="NH-6", name="Test Road", length_m=250.0, geometry=curved,
        )
        out_path = tmp_path / "test2.geojson"
        brg._write_geojson(g, out_path)

        import json

        data = json.loads(out_path.read_text(encoding="utf-8"))
        coords = data["features"][0]["geometry"]["coordinates"]
        assert len(coords) == 3  # the curved geometry's 3 vertices, not a 2-point straight line
        assert data["features"][0]["properties"]["ref"] == "NH-6"
        assert data["features"][0]["properties"]["is_bridge"] is True


HAS_REAL_GRAPH = (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()


@pytest.mark.skipif(not HAS_REAL_GRAPH, reason="requires data/osm/aizawl_graph.pkl (make graph AOI=aizawl)")
class TestRealAizawlGraph:
    """Sanity checks against the actual Aizawl OSMnx extract (built and verified live this
    session — CLAUDE.md §12: 3,622 nodes, 8,808 edges, 50 bridge-tagged edges, 336 NH/SH-ref
    edges, NH6/NH2/NH108 all present as real `ref` values)."""

    def test_unpickles_as_a_plain_multidigraph_no_osmnx_needed(self):
        with (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").open("rb") as f:
            g = pickle.load(f)
        assert type(g) is nx.MultiDiGraph  # exactly nx's own class, not an osmnx subclass
        assert g.number_of_nodes() > 0
        assert g.number_of_edges() > 0

    def test_nh6_is_present_as_a_real_ref(self):
        with (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").open("rb") as f:
            g = pickle.load(f)
        refs = {data.get("ref") for _, _, data in g.edges(data=True) if data.get("ref")}
        assert "NH6" in refs

    def test_every_edge_has_a_stable_edge_id_and_required_fields(self):
        with (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").open("rb") as f:
            g = pickle.load(f)
        for u, v, key, data in g.edges(keys=True, data=True):
            assert data["edge_id"] == f"{u}_{v}_{key}"
            assert isinstance(data["highway_class"], str)
            assert isinstance(data["is_bridge"], bool)
            assert isinstance(data["length_m"], float)

    def test_some_edges_are_bridge_tagged(self):
        with (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").open("rb") as f:
            g = pickle.load(f)
        assert any(data["is_bridge"] for _, _, data in g.edges(data=True))
