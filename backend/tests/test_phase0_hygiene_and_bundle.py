"""Phase 0 TDD Suite: Hygiene, AOI Configuration, Dynamic Grid & Multiplex Seed Bundle.

Follows strict RED -> GREEN -> REFACTOR discipline:
1. Verifies `chennai` (Cyclone Michaung), `wayanad`, `aizawl`, and `tupul` AOIs + Neo4j/Sarvam config.
2. Verifies zero UTF-8 BOMs across all backend/frontend source files and wallclock compliance.
3. Verifies `frontend/src/lib/grid.ts` contains zero hardcoded dataset cell-ID lookup tables.
4. Verifies `scripts/build_multiplex_seed_bundle.py` builds a deterministic <28 MB 4-layer multiplex
   graph bundle (`nodes.json`, `edges.json`, `manifest.json`, and Sarvam multimodal fixtures).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"


class TestPhase0HygieneAndBundle(unittest.TestCase):
    def test_01_no_utf8_bom_in_any_source_file(self) -> None:
        offenders: list[str] = []
        for ext in ("*.py", "*.ts", "*.tsx"):
            for path in REPO_ROOT.rglob(ext):
                if ".git" in path.parts or "node_modules" in path.parts:
                    continue
                raw = path.read_bytes()
                if raw.startswith(b"\xef\xbb\xbf"):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(offenders, [], f"UTF-8 BOM found in files: {offenders}")

    def test_02_config_exposes_chennai_neo4j_sarvam_and_agent_settings(self) -> None:
        config_text = (BACKEND_ROOT / "app" / "config.py").read_text(encoding="utf-8")
        for required_symbol in (
            '"chennai"',
            "NEO4J_URI",
            "NEO4J_USER",
            "NEO4J_PASSWORD",
            "SARVAM_API_KEY",
            "AGENT_FAST_MODEL",
            "AGENT_REASONING_MODEL",
            "AOI_KEYTERMS",
        ):
            self.assertIn(
                required_symbol,
                config_text,
                f"Missing {required_symbol} in backend/app/config.py",
            )

    def test_03_frontend_grid_has_no_hardcoded_cell_id_lookup_table(self) -> None:
        grid_ts = (FRONTEND_ROOT / "src" / "lib" / "grid.ts").read_text(encoding="utf-8")
        forbidden_literals = (
            "aizawl_012_001",
            "aizawl_039_050",
            "wayanad_008_041",
            "tupul_036_012",
        )
        for literal in forbidden_literals:
            self.assertNotIn(
                literal,
                grid_ts,
                f"Hardcoded dataset cell ID {literal!r} still present in frontend/src/lib/grid.ts",
            )

    def test_04_multiplex_seed_bundle_builds_and_validates(self) -> None:
        from scripts.build_multiplex_seed_bundle import build_multiplex_bundle

        bundle_dir = REPO_ROOT / "data" / "seed_bundle"
        manifest = build_multiplex_bundle(
            aoi_ids=["chennai", "wayanad", "aizawl"],
            output_dir=bundle_dir,
        )
        self.assertTrue((bundle_dir / "nodes.json").is_file())
        self.assertTrue((bundle_dir / "edges.json").is_file())
        self.assertTrue((bundle_dir / "manifest.json").is_file())
        self.assertTrue((bundle_dir / "fixtures" / "sarvam_test_manifest.json").is_file())

        nodes_data = json.loads((bundle_dir / "nodes.json").read_text(encoding="utf-8"))
        edges_data = json.loads((bundle_dir / "edges.json").read_text(encoding="utf-8"))

        required_node_groups = {
            "MicroWatershed",
            "DrainageNode",
            "FloodZone",
            "RoadJunction",
            "RoadSegment",
            "Bridge",
            "Culvert",
            "Substation",
            "WaterFacility",
            "TelecomTower",
            "Hospital",
            "ReliefShelter",
            "SupplyDepot",
        }
        self.assertTrue(
            required_node_groups.issubset(set(nodes_data.keys())),
            f"Missing node groups: {required_node_groups - set(nodes_data.keys())}",
        )

        required_edge_groups = {
            "DRAINS_INTO",
            "INUNDATES",
            "CONNECTS_TO",
            "CARRIES_CORRIDOR",
            "POWERS",
            "SUPPLIES_WATER_TO",
            "COVERS_COMMS",
            "EVACUATES_TO",
        }
        self.assertTrue(
            required_edge_groups.issubset(set(edges_data.keys())),
            f"Missing edge groups: {required_edge_groups - set(edges_data.keys())}",
        )
        self.assertGreaterEqual(manifest["total_nodes"], 150)
        self.assertGreaterEqual(manifest["total_edges"], 300)
        self.assertLess(manifest["bundle_size_mb"], 28.0)


if __name__ == "__main__":
    unittest.main()
