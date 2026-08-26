"""Integration test for impact/isolation.py's real-data loader (`build_isolation_inputs`) and the
full real-Aizawl pipeline (road graph + exposure data -> VillageIsolation per village). Gated on
the real road graph + exposure data already existing on disk (both gitignored) so a fresh
checkout without network access skips this rather than failing."""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HAS_REAL_GRAPH = (REPO_ROOT / "data" / "osm" / "aizawl_graph.pkl").is_file()
HAS_REAL_EXPOSURE = (REPO_ROOT / "data" / "static" / "aizawl" / "exposure.gpkg").is_file()

pytestmark = pytest.mark.skipif(
    not (HAS_REAL_GRAPH and HAS_REAL_EXPOSURE),
    reason="requires data/osm/aizawl_graph.pkl and data/static/aizawl/exposure.gpkg",
)


def test_build_isolation_inputs_resolves_every_real_village_and_three_targets_each():
    from app.impact.isolation import build_isolation_inputs
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    villages, targets_by_village = build_isolation_inputs("aizawl", graph)

    assert len(villages) == 11  # CLAUDE.md's Current State: 11 real Aizawl villages
    for village in villages:
        targets = targets_by_village[village.village_id]
        kinds = {t.kind for t in targets}
        assert "district_hq" in kinds
        # Aizawl has real hospitals(19)/shelters(7) per CLAUDE.md, so every village should
        # resolve one of each, not just the HQ.
        assert "hospital" in kinds
        assert "shelter" in kinds
        for target in targets:
            assert target.node_id in graph


def test_full_pipeline_produces_a_villageisolation_per_village_with_no_severed_edges():
    """No RunoutEnvelope/RoadSegmentRisk input in this test -> nothing should be severed, and
    every real village should show as NOT isolated (a real sanity check on the whole wiring, not
    just "it didn't crash")."""
    from app.impact.isolation import build_isolation_inputs, compute_all_village_isolations
    from app.impact.road_graph import load_road_graph

    graph = load_road_graph("aizawl")
    villages, targets_by_village = build_isolation_inputs("aizawl", graph)

    results = compute_all_village_isolations(villages, graph, {}, targets_by_village)
    assert len(results) == 11
    for r in results:
        assert r.isolated_now is False
        assert r.alternate_route_exists is True
        assert r.severed_links == []
        assert r.p_isolated == 0.0
