"""Phase 2 TDD Suite: True Neuro-Symbolic Agent Orchestrator, GraphRAG & Citation Guardrail.

Directly enforces the 5 Rules from the HackerRank Orchestrate Retrospective:
1. Production system prompts (`app/agents/prompts.py`) with explicit Role Assignment, Temporal/Physics
   Constraints, Refusal Conditions (`INSUFFICIENT_GRAPH_EVIDENCE`), and JSON Output Schemas.
2. Formal `@tool` JSON-schema registry (`app/agents/tools.py`) wrapping deterministic engines.
3. HybridCypherRetriever (`app/graph/hybrid_retriever.py`) combining lexical + semantic retrieval
   with 1-3 hop subgraph expansion and filtering out `PLAUSIBILITY_REJECTED` / `SUPERSEDED` nodes.
4. Set-Membership Post-Generation Guardrail (`app/agents/verifier_gate.py`) that strips any
   hallucinated `node_id` not present in the retrieved Neo4j `allowed_node_ids` set.
5. Bounded multi-turn `OrchestratorAgent` (`while turn < max_turns:`) with Fast vs Reasoning
   Model Routing, Multi-Agent Handoffs, and non-zero `UsageTelemetryTracker` metrics.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / "data" / "seed_bundle"


class TestPhase2AgentOrchestrator(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.graph.neo4j_client import GraphStoreManager
        from scripts.build_multiplex_seed_bundle import build_multiplex_bundle
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        if not (BUNDLE_DIR / "nodes.json").is_file():
            build_multiplex_bundle(["chennai", "wayanad", "aizawl"], BUNDLE_DIR)
        cls.store = GraphStoreManager(uri="", user="neo4j", password="")
        seed_nirantar_knowledge_graph(BUNDLE_DIR, cls.store)

    def test_01_system_prompts_have_role_constraints_refusal_and_schemas(self) -> None:
        from app.agents.prompts import (
            FIELD_INTAKE_TRIAGE_PROMPT,
            GRAPHRAG_INVESTIGATOR_PROMPT,
            ORCHESTRATOR_SYSTEM_PROMPT,
            ROBOTICS_MISSION_PLANNER_PROMPT,
            get_all_agent_prompts,
        )

        prompts = get_all_agent_prompts()
        self.assertEqual(len(prompts), 4)
        for name, text in prompts.items():
            self.assertGreater(len(text), 350, f"Prompt {name} is too short; must be rich and structured")
            self.assertIn("ROLE", text)
            self.assertIn("CONSTRAINTS", text)
            self.assertIn("REFUSAL", text)
            self.assertIn("OUTPUT_SCHEMA", text)
        self.assertIn("INSUFFICIENT_GRAPH_EVIDENCE", GRAPHRAG_INVESTIGATOR_PROMPT)
        self.assertIn("PLAUSIBILITY_REJECTED", FIELD_INTAKE_TRIAGE_PROMPT)
        self.assertIn("CoE-AWRDS", ROBOTICS_MISSION_PLANNER_PROMPT)
        self.assertIn("DDMA", ORCHESTRATOR_SYSTEM_PROMPT)

    def test_02_formal_tool_registry_exposes_seven_json_schema_tools(self) -> None:
        from app.agents.tools import get_registered_agent_tools

        tools = get_registered_agent_tools(self.store)
        expected_names = {
            "query_cascading_blast_radius_tool",
            "discover_topological_chokepoints_tool",
            "compute_risk_budgeted_route_tool",
            "hybrid_graphrag_retrieve_tool",
            "verify_citizen_report_physics_tool",
            "plan_uav_usv_verification_mission_tool",
            "synthesize_sarvam_vernacular_advisory_tool",
        }
        self.assertEqual(set(tools.keys()), expected_names)
        for tool_name, tool_def in tools.items():
            self.assertEqual(tool_def.name, tool_name)
            self.assertTrue(len(tool_def.description) > 30)
            self.assertEqual(tool_def.parameters_schema.get("type"), "object")
            self.assertIn("properties", tool_def.parameters_schema)
            self.assertIn("required", tool_def.parameters_schema)

    def test_03_hybrid_cypher_retriever_expands_three_hop_subgraph(self) -> None:
        from app.graph.hybrid_retriever import HybridCypherGraphRetriever

        retriever = HybridCypherGraphRetriever(self.store)
        sub = retriever.retrieve_subgraph(
            query_text="Which ICU hospital near Velachery 33kV substation is at cascade risk?",
            aoi_id="chennai",
            top_k=5,
        )
        self.assertGreater(len(sub.allowed_node_ids), 3)
        self.assertIn("SUB-CHENNAI-33KV-01", sub.allowed_node_ids)
        self.assertIn("HOSP-CHENNAI-CARE-01", sub.allowed_node_ids)
        self.assertGreater(len(sub.explicit_edge_paths), 0)

    def test_04_verifier_gate_blocks_hallucinated_node_ids(self) -> None:
        from app.agents.verifier_gate import (
            CommanderCopilotResponse,
            EvidenceCitation,
            TacticalRecommendation,
            verify_and_gate_copilot_output,
        )

        # Case A: Valid citations subset of allowed_node_ids -> kept intact
        valid_rec = TacticalRecommendation(
            priority_rank=1,
            action_type="SANDBAG_CHOKEPOINT",
            target_node_id="CUL-CHENNAI-01",
            recommendation_text="Clear box culvert CUL-CHENNAI-01 to protect SUB-CHENNAI-33KV-01.",
            survival_window_hrs=3.18,
            citations=[
                EvidenceCitation(
                    node_id="SUB-CHENNAI-33KV-01",
                    node_label="Substation",
                    edge_path="FloodZone:FZ-CHENNAI-01-[INUNDATES]->Substation:SUB-CHENNAI-33KV-01",
                    confidence_score=0.96,
                    observed_at="2026-10-26T12:00:00Z",
                )
            ],
        )
        # Case B: Hallucinated node_id "HOSP-FAKE-999" -> must be stripped by verifier gate
        hallucinated_rec = TacticalRecommendation(
            priority_rank=2,
            action_type="EVACUATE_ICU",
            target_node_id="HOSP-FAKE-999",
            recommendation_text="Evacuate non-existent hospital HOSP-FAKE-999.",
            survival_window_hrs=1.0,
            citations=[
                EvidenceCitation(
                    node_id="HOSP-FAKE-999",
                    node_label="Hospital",
                    edge_path="Substation:SUB-FAKE-[POWERS]->Hospital:HOSP-FAKE-999",
                    confidence_score=0.99,
                    observed_at="2026-10-26T12:00:00Z",
                )
            ],
        )
        raw_resp = CommanderCopilotResponse(
            status="EVIDENCE_BACKED",
            executive_sitrep="Sitrep with one valid and one hallucinated recommendation.",
            recommendations=[valid_rec, hallucinated_rec],
            verified_subgraph_node_count=4,
        )
        gated = verify_and_gate_copilot_output(
            raw_resp,
            allowed_node_ids={"FZ-CHENNAI-01", "SUB-CHENNAI-33KV-01", "CUL-CHENNAI-01", "HOSP-CHENNAI-CARE-01"},
        )
        self.assertEqual(len(gated.recommendations), 1)
        self.assertEqual(gated.recommendations[0].target_node_id, "CUL-CHENNAI-01")
        self.assertEqual(gated.unverified_citations_blocked, 1)

        # Case C: All recommendations hallucinated -> status transitions to GUARDRAIL_REDACTED
        all_bad = CommanderCopilotResponse(
            status="EVIDENCE_BACKED",
            executive_sitrep="Bad sitrep",
            recommendations=[hallucinated_rec],
            verified_subgraph_node_count=2,
        )
        redacted = verify_and_gate_copilot_output(
            all_bad, allowed_node_ids={"SUB-CHENNAI-33KV-01"}
        )
        self.assertEqual(redacted.status, "GUARDRAIL_REDACTED")
        self.assertEqual(len(redacted.recommendations), 0)

    def test_05_orchestrator_runs_bounded_multi_turn_loop_and_records_telemetry(self) -> None:
        from app.agents.orchestrator import OrchestratorAgent
        from app.agents.telemetry import UsageTelemetryTracker

        tracker = UsageTelemetryTracker()
        agent = OrchestratorAgent(
            graph_store=self.store,
            telemetry=tracker,
            max_iterations=5,
        )
        response = asyncio.run(
            agent.run_commander_investigation(
                query="Which ICU hospital is at highest cascade risk in Chennai, what choke point must SDRF clear, and what is the safest evacuation route?",
                aoi_id="chennai",
            )
        )
        self.assertEqual(response.status, "EVIDENCE_BACKED")
        self.assertGreaterEqual(len(response.recommendations), 2)
        self.assertGreaterEqual(len(response.agent_traces), 3)
        # Verify multi-agent handoffs and model routing occurred inside the bounded loop
        agents_invoked = {trace["agent_role"] for trace in response.agent_traces}
        self.assertIn("IntakeRouterAgent", agents_invoked)
        self.assertIn("GraphInvestigatorAgent", agents_invoked)
        self.assertIn("VerifierGateAgent", agents_invoked)
        # Verify non-zero telemetry was recorded
        summary = tracker.summary()
        self.assertGreater(summary["total_calls"], 0)
        self.assertGreater(summary["total_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
