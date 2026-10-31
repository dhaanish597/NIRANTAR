"""Phase 4 TDD tests: IIIT Delhi CoE-AWRDS Robotics Loop, UN SDG 6/11/13 Metrics & Multiplex API Endpoints."""
from __future__ import annotations

import asyncio
from pathlib import Path
import unittest

from app.graph.neo4j_client import GraphStoreManager


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPhase4CoeAwrdsRobotics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manager = GraphStoreManager.from_seed_bundle(REPO_ROOT / "data" / "seed_bundle")

    def test_01_generate_uav_usv_mission_order_produces_valid_geojson_waypoints(self) -> None:
        from app.robotics.coe_awrds import CoeAwrdsRoboticsCoordinator

        coordinator = CoeAwrdsRoboticsCoordinator(self.manager)
        mission = coordinator.generate_uav_usv_mission_order(
            aoi_id="chennai",
            target_node_id="CUL-CHENNAI-01",
            platform_type="USV_SONAR",
        )
        self.assertEqual(mission.action_type, "DEPLOY_UAV_USV")
        self.assertEqual(mission.platform_type, "USV_SONAR")
        self.assertEqual(mission.target_node_id, "CUL-CHENNAI-01")
        self.assertEqual(mission.waypoints_geojson["type"], "FeatureCollection")
        self.assertGreaterEqual(len(mission.waypoints_geojson["features"]), 3)
        self.assertIn("CoE-AWRDS", mission.knowledge_partner_tag)

    def test_02_ingest_robotic_sensor_reading_mutates_graph_and_triggers_recompute(self) -> None:
        from app.robotics.coe_awrds import CoeAwrdsRoboticsCoordinator

        coordinator = CoeAwrdsRoboticsCoordinator(self.manager)
        telemetry_res = coordinator.ingest_robotic_sensor_reading(
            mission_id="MSN-AWRDS-001",
            target_node_id="CUL-CHENNAI-01",
            platform_type="USV_SONAR",
            measured_water_depth_m=0.22,
            blockage_pct=12.0,
            structural_integrity_score=0.94,
            observed_at_iso="2026-10-26T15:10:00Z",
        )
        self.assertEqual(telemetry_res["status"], "TELEMETRY_INGESTED")
        updated_node = self.manager.get_node("CUL-CHENNAI-01")
        self.assertIsNotNone(updated_node)
        self.assertAlmostEqual(float(updated_node["water_depth_m"]), 0.22, places=2)
        self.assertAlmostEqual(float(updated_node["blockage_pct"]), 12.0, places=1)
        self.assertTrue(updated_node["robotic_verified"])

    def test_03_compute_sdg_resilience_scorecard_quantifies_sdg6_sdg11_sdg13(self) -> None:
        from app.robotics.coe_awrds import CoeAwrdsRoboticsCoordinator

        coordinator = CoeAwrdsRoboticsCoordinator(self.manager)
        scorecard = coordinator.compute_sdg_resilience_metrics(
            aoi_id="chennai",
            trigger_node_id="FZ-CHENNAI-01",
            mitigated_node_ids=["SUB-CHENNAI-33KV-01", "CUL-CHENNAI-01"],
        )
        self.assertGreater(scorecard.sdg6_potable_water_person_hours_saved, 1000)
        self.assertGreater(scorecard.sdg11_isolated_residents_reconnected, 200)
        self.assertGreater(scorecard.sdg13_cascade_lead_time_gain_minutes, 30.0)
        self.assertIn("SDG 6", scorecard.summary_narrative)
        self.assertIn("SDG 11", scorecard.summary_narrative)
        self.assertIn("SDG 13", scorecard.summary_narrative)

    def test_04_multiplex_api_endpoints_return_dynamic_grid_and_graphrag_payloads(self) -> None:
        from app.api.multiplex import (
            CascadeRequest,
            RoboticsMissionRequest,
            get_aoi_dynamic_grid,
            get_multiplex_chokepoints,
            post_multiplex_cascade,
            post_robotics_mission,
        )

        grid_res = asyncio.run(get_aoi_dynamic_grid("chennai"))
        self.assertEqual(grid_res["aoi_id"], "chennai")
        self.assertGreater(grid_res["cell_count"], 20)

        cascade_res = asyncio.run(
            post_multiplex_cascade(CascadeRequest(trigger_node_id="FZ-CHENNAI-01", max_hops=3))
        )
        self.assertEqual(cascade_res["trigger_node_id"], "FZ-CHENNAI-01")
        self.assertGreater(len(cascade_res["impacted_assets"]), 3)

        cp_res = asyncio.run(get_multiplex_chokepoints("chennai", top_k=3))
        self.assertEqual(len(cp_res["chokepoints"]), 3)

        msn_res = asyncio.run(
            post_robotics_mission(
                RoboticsMissionRequest(
                    aoi_id="chennai",
                    target_node_id="CUL-CHENNAI-01",
                    platform_type="USV_SONAR",
                )
            )
        )
        self.assertEqual(msn_res["action_type"], "DEPLOY_UAV_USV")


if __name__ == "__main__":
    unittest.main()
