"""Deterministic Post-Generation Set-Membership Guardrail (`verifier_gate.py`).

Enforces the formal anti-hallucination post-condition:
  forall c in Citations(Output), c.node_id in V_retrieved and rec.target_node_id in V_retrieved.
Any recommendation citing an unverified or hallucinated infrastructure ID is deterministically
stripped and logged before reaching the DEOC Commander UI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class EvidenceCitation:
    node_id: str
    node_label: str
    edge_path: str
    confidence_score: float
    observed_at: str

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TacticalRecommendation:
    priority_rank: int
    action_type: Literal[
        "SANDBAG_CHOKEPOINT",
        "EVACUATE_ICU",
        "REROUTE_FUEL",
        "DEPLOY_UAV_USV",
        "HOLD_AND_VERIFY",
    ]
    target_node_id: str
    recommendation_text: str
    survival_window_hrs: float
    citations: list[EvidenceCitation] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CommanderCopilotResponse:
    status: Literal[
        "EVIDENCE_BACKED",
        "INSUFFICIENT_GRAPH_EVIDENCE",
        "GUARDRAIL_REDACTED",
    ]
    executive_sitrep: str
    recommendations: list[TacticalRecommendation]
    verified_subgraph_node_count: int
    unverified_citations_blocked: int = 0
    agent_traces: list[dict[str, Any]] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def verify_and_gate_copilot_output(
    llm_response: CommanderCopilotResponse,
    allowed_node_ids: set[str],
    allowed_edge_paths: set[str] | None = None,
) -> CommanderCopilotResponse:
    verified_recs: list[TacticalRecommendation] = []
    blocked_count = 0

    for rec in llm_response.recommendations:
        cited_ids = {c.node_id for c in rec.citations} | {rec.target_node_id}
        if not cited_ids.issubset(allowed_node_ids) or len(rec.citations) == 0:
            blocked_count += 1
            continue
        if allowed_edge_paths:
            invalid_edge = any(
                c.edge_path not in allowed_edge_paths and "->" not in c.edge_path
                for c in rec.citations
            )
            if invalid_edge:
                blocked_count += 1
                continue
        verified_recs.append(rec)

    if blocked_count > 0 and not verified_recs:
        return CommanderCopilotResponse(
            status="GUARDRAIL_REDACTED",
            executive_sitrep=(
                "REFUSAL: The language model attempted to reference infrastructure node IDs "
                "not present in the verified Neo4j AuraDB subgraph. All unverified "
                "recommendations were deterministically blocked."
            ),
            recommendations=[],
            verified_subgraph_node_count=len(allowed_node_ids),
            unverified_citations_blocked=blocked_count,
            agent_traces=list(llm_response.agent_traces),
        )

    for idx, rec in enumerate(verified_recs, start=1):
        rec.priority_rank = idx

    return CommanderCopilotResponse(
        status=llm_response.status if verified_recs else "INSUFFICIENT_GRAPH_EVIDENCE",
        executive_sitrep=llm_response.executive_sitrep,
        recommendations=verified_recs,
        verified_subgraph_node_count=len(allowed_node_ids),
        unverified_citations_blocked=blocked_count,
        agent_traces=list(llm_response.agent_traces),
    )
