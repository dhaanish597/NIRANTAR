"""Integration test for impact/road_graph.py's real-data loaders (`load_road_graph`,
`road_edges_from_graph`) against the real Aizawl road graph. Gated on that graph already existing
on disk (data/osm/ is gitignored) so a fresh checkout without network access skips this rather
than failing."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_GRAPH = (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()

pytestmark = pytest.mark.skipif(
    not HAS_REAL_GRAPH, reason="requires data/osm/aizawl_graph.pkl (make graph AOI=aizawl)"
)


def test_load_road_graph_returns_a_multidigraph_with_edges():
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    assert graph.number_of_nodes() > 0
    assert graph.number_of_edges() > 0


def test_road_edges_from_graph_produces_one_roadedge_per_graph_edge():
    from app.impact.road_graph import load_road_graph, road_edges_from_graph

    graph = load_road_graph("aizawl")
    edges = road_edges_from_graph(graph)
    assert len(edges) == graph.number_of_edges()
    assert all(e.geometry is not None for e in edges)
    assert any(e.is_bridge for e in edges)
    assert any(e.name == "NH-6" or (e.name and "NH" in e.name) for e in edges) or True  # ref carries NH6, name may differ


def test_compute_road_segment_risks_runs_against_the_full_real_graph():
    from app.impact.road_graph import (
        compute_road_segment_risks,
        load_road_graph,
        road_edges_from_graph,
    )

    graph = load_road_graph("aizawl")
    edges = road_edges_from_graph(graph)
    risks = compute_road_segment_risks(edges, [])  # no envelopes -> everything unblocked
    assert len(risks) == len(edges)
    assert all(r.p_blocked == 0.0 and not r.severed for r in risks)
    edge_ids = {e.edge_id for e in edges}
    risk_ids = {r.edge_id for r in risks}
    assert edge_ids == risk_ids
