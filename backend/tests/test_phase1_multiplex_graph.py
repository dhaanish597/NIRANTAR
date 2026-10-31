"""Phase 1 TDD Suite: Neo4j Multiplex Knowledge Graph, Seeder, GDS Choke Points & DEM Physics Gate.

Tests:
1. DDL schema completeness (17 constraints, POINT, RANGE, FULLTEXT, and 768-dim VECTOR indexes).
2. Sub-15s batched seeding and dual-mode GraphStoreManager (AuraDB + deterministic offline mirror).
3. 1-to-3 hop heterogeneous cascading blast radius & hospital ICU DG backup survival window math.
4. Tarjan articulation points, bridge edges, Brandes betweenness, PageRank, and risk-budgeted A* routing.
5. Topographic DEM hydrostatic gradient plausibility gate (spoof rejection) & temporal [:SUPERSEDES].
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "data" / "seed_bundle"


class TestPhase1MultiplexGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from scripts.build_multiplex_seed_bundle import build_multiplex_bundle

        if not (BUNDLE_DIR / "nodes.json").is_file():
            build_multiplex_bundle(["chennai", "wayanad", "aizawl"], BUNDLE_DIR)

    def test_01_schema_ddl_has_17_constraints_and_spatial_vector_indexes(self) -> None:
        from app.graph.schema_ddl import (
            CONSTRAINTS_DDL,
            FULLTEXT_AND_VECTOR_DDL,
            POINT_INDEXES_DDL,
            RANGE_INDEXES_DDL,
            get_all_ddl_statements,
        )

        self.assertEqual(len(CONSTRAINTS_DDL), 17)
        self.assertGreaterEqual(len(POINT_INDEXES_DDL), 6)
        self.assertGreaterEqual(len(RANGE_INDEXES_DDL), 4)
        self.assertEqual(len(FULLTEXT_AND_VECTOR_DDL), 2)
        all_stmts = get_all_ddl_statements()
        self.assertTrue(any("sitrep_vector_idx" in s and "768" in s for s in all_stmts))
        self.assertTrue(any("sitrep_fulltext_idx" in s for s in all_stmts))

    def test_02_fast_seeder_loads_multiplex_bundle_under_15_seconds(self) -> None:
        from app.graph.neo4j_client import GraphStoreManager
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        store = GraphStoreManager(uri="", user="neo4j", password="")
        summary = seed_nirantar_knowledge_graph(BUNDLE_DIR, store)
        self.assertEqual(summary.status, "SEEDED")
        self.assertLess(summary.elapsed_seconds, 15.0)
        self.assertGreaterEqual(summary.nodes_seeded, 150)
        self.assertGreaterEqual(summary.edges_seeded, 300)

    def test_03_three_hop_cascading_blast_radius_and_icu_survival_math(self) -> None:
        from app.graph.cascade_engine import (
            compute_cascading_blast_radius,
            compute_hospital_dg_survival_hours,
        )
        from app.graph.neo4j_client import GraphStoreManager
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        store = GraphStoreManager(uri="", user="neo4j", password="")
        seed_nirantar_knowledge_graph(BUNDLE_DIR, store)

        # Verify ICU DG backup formula: 165L / (0.28 L/kWh * 185 kW) - 0.0h = 3.185 hours
        rem_hrs = compute_hospital_dg_survival_hours(
            fuel_liters=165.0, icu_load_kw=185.0, elapsed_trip_hours=0.0, specific_consumption=0.28
        )
        self.assertAlmostEqual(rem_hrs, 3.19, places=1)

        # Trigger cascade from FloodZone FZ-CHENNAI-01 across 3 hops
        result = compute_cascading_blast_radius(store, trigger_node_id="FZ-CHENNAI-01", max_hops=3)
        self.assertEqual(result.trigger_node_id, "FZ-CHENNAI-01")
        hop_map = {item.asset_id: item.blast_radius_hop for item in result.impacted_assets}

        # Hop 1: SUB-CHENNAI-33KV-01 & CUL-CHENNAI-01
        self.assertEqual(hop_map.get("SUB-CHENNAI-33KV-01"), 1)
        self.assertEqual(hop_map.get("CUL-CHENNAI-01"), 1)
        # Hop 2: HOSP-CHENNAI-CARE-01, WTP-CHENNAI-01, TOW-CHENNAI-01
        self.assertEqual(hop_map.get("HOSP-CHENNAI-CARE-01"), 2)
        self.assertEqual(hop_map.get("WTP-CHENNAI-01"), 2)
        self.assertEqual(hop_map.get("TOW-CHENNAI-01"), 2)
        # Hop 3: SHEL-CHENNAI-01 (via WTP-CHENNAI-01) & HOSP-CHENNAI-GEN-02 (via SUB-CHENNAI-11KV-02)
        self.assertEqual(hop_map.get("SHEL-CHENNAI-01"), 3)
        self.assertGreaterEqual(result.total_critical_human_exposure, 350)

    def test_04_gds_chokepoints_and_risk_budgeted_astar_routing(self) -> None:
        from app.graph.gds_chokepoints import (
            compute_risk_budgeted_astar_route,
            discover_top_chokepoints,
        )
        from app.graph.neo4j_client import GraphStoreManager
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        store = GraphStoreManager(uri="", user="neo4j", password="")
        seed_nirantar_knowledge_graph(BUNDLE_DIR, store)

        chokepoints = discover_top_chokepoints(store, aoi_id="chennai", top_k=3)
        self.assertEqual(len(chokepoints), 3)
        self.assertTrue(any(cp.is_spof_articulation for cp in chokepoints))
        self.assertGreater(chokepoints[0].criticality_index, chokepoints[-1].criticality_index)

        # Route from SupplyDepot junction OSM-CHENNAI-001 to Hospital junction OSM-CHENNAI-017
        # Must automatically avoid flooded junction OSM-CHENNAI-008 (flood_depth_m = 1.25m >= 0.45m)
        route = compute_risk_budgeted_astar_route(
            store,
            source_osmid="OSM-CHENNAI-001",
            target_osmid="OSM-CHENNAI-017",
            vehicle_clearance_m=0.45,
        )
        self.assertTrue(route.reachable)
        self.assertNotIn("OSM-CHENNAI-008", route.route_junction_osmids)
        self.assertGreater(route.risk_adjusted_eta_seconds, 0.0)

    def test_05_dem_hydrostatic_plausibility_gate_and_temporal_supersession(self) -> None:
        from app.graph.neo4j_client import GraphStoreManager
        from app.graph.plausibility_gate import evaluate_dem_plausibility_and_supersede
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        store = GraphStoreManager(uri="", user="neo4j", password="")
        seed_nirantar_knowledge_graph(BUNDLE_DIR, store)
        t0 = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Spoofed report at high ridge peak OSM-CHENNAI-036 (elev ~44.5m) claiming 1.8m flood
        ridge_node = store.get_node("OSM-CHENNAI-036")
        self.assertIsNotNone(ridge_node)
        spoof_verdict = evaluate_dem_plausibility_and_supersede(
            store,
            report_id="REP-SPOOF-001",
            lat=ridge_node["lat"],
            lon=ridge_node["lon"],
            claimed_depth_m=1.80,
            reporter_role="CITIZEN",
            observed_at=t0,
        )
        self.assertEqual(spoof_verdict.verification_state, "PLAUSIBILITY_REJECTED")
        self.assertAlmostEqual(spoof_verdict.confidence_score, 0.05)
        self.assertIn("REJECTED_BY_DEM_PHYSICS", spoof_verdict.physics_audit_note)

        # 2. Valid citizen report at low-lying junction OSM-CHENNAI-008
        low_node = store.get_node("OSM-CHENNAI-008")
        valid_verdict = evaluate_dem_plausibility_and_supersede(
            store,
            report_id="REP-CITIZEN-002",
            lat=low_node["lat"],
            lon=low_node["lon"],
            claimed_depth_m=1.10,
            reporter_role="CITIZEN",
            observed_at=t0,
        )
        self.assertEqual(valid_verdict.verification_state, "PENDING")
        self.assertEqual(valid_verdict.physics_audit_note, "PASSED_DEM_GRADIENT_CHECK")

        # 3. Newer verified SDRF responder report at the same junction supersedes REP-CITIZEN-002
        sdrf_verdict = evaluate_dem_plausibility_and_supersede(
            store,
            report_id="REP-SDRF-003",
            lat=low_node["lat"],
            lon=low_node["lon"],
            claimed_depth_m=0.30,
            reporter_role="SDRF_RESPONDER",
            observed_at=t0 + timedelta(minutes=25),
        )
        self.assertEqual(sdrf_verdict.verification_state, "VERIFIED")
        self.assertIn("REP-CITIZEN-002", sdrf_verdict.superseded_report_ids)
        old_rep = store.get_node("REP-CITIZEN-002")
        self.assertEqual(old_rep["verification_state"], "SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
