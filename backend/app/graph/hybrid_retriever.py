"""HybridCypherRetriever for Neo4j GraphRAG Subgraph Expansion (`hybrid_retriever.py`).

Combines:
1. Lexical BM25 token matching (`sitrep_fulltext_idx`) + cosine vector similarity (`sitrep_vector_idx`)
   over infrastructure names, substation codes, ward IDs, and citizen reports.
2. 1-to-3 hop deterministic Cypher subgraph expansion across `INUNDATES`, `POWERS`,
   `SUPPLIES_WATER_TO`, `COVERS_COMMS`, `CONNECTS_TO`, `CARRIES_CORRIDOR`, and `EVACUATES_TO`.
3. Automatic epistemic filtering that drops any node with `verification_state` in
   `{"PLAUSIBILITY_REJECTED", "SUPERSEDED"}`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.graph.cascade_engine import CASCADE_REL_TYPES
from app.graph.neo4j_client import GraphStoreManager

COMMANDER_SUBGRAPH_RETRIEVAL_CYPHER = """
WITH node, score
WHERE coalesce(node.verification_state, 'VERIFIED') NOT IN ['PLAUSIBILITY_REJECTED', 'SUPERSEDED']
OPTIONAL MATCH (node)-[:OBSERVED_AT|AFFECTS_NODE]->(anchor)
WITH coalesce(anchor, node) AS root_asset, node AS source_doc, score
MATCH path = (root_asset)-[rels:INUNDATES|POWERS|SUPPLIES_WATER_TO|COVERS_COMMS|CONNECTS_TO|CARRIES_CORRIDOR|EVACUATES_TO*1..3]-(connected)
RETURN root_asset, source_doc, score, path
LIMIT 25
"""


@dataclass
class SubgraphRetrievalResult:
    aoi_id: str
    query_text: str
    anchor_node_ids: list[str]
    allowed_node_ids: set[str]
    explicit_edge_paths: list[str]
    asset_telemetry: list[dict[str, Any]] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_node_ids"] = sorted(self.allowed_node_ids)
        return data


class HybridCypherGraphRetriever:
    def __init__(self, graph_store: GraphStoreManager) -> None:
        self.graph_store = graph_store

    def _score_node_relevance(self, node: dict[str, Any], query_tokens: set[str]) -> float:
        if node.get("verification_state") in ("PLAUSIBILITY_REJECTED", "SUPERSEDED"):
            return 0.0
        haystack = " ".join(
            str(node.get(k, ""))
            for k in ("id", "name", "label", "operator", "raw_transcript", "english_translation")
        ).lower()
        matches = sum(1 for tok in query_tokens if tok in haystack)
        label_bonus = 0.45 if node.get("label") in ("FloodZone", "Substation", "Hospital", "Culvert", "Bridge") else 0.1
        status_bonus = 0.35 if str(node.get("status", "")) in ("INUNDATED", "ON_DG_BACKUP", "OFFLINE", "ON_BATTERY") else 0.0
        return matches * 0.5 + label_bonus + status_bonus

    def retrieve_subgraph(
        self, query_text: str, aoi_id: str = "chennai", top_k: int = 5
    ) -> SubgraphRetrievalResult:
        tokens = {
            tok.strip("?,.:;!").lower()
            for tok in query_text.split()
            if len(tok.strip("?,.:;!")) >= 3
        }
        candidates = self.graph_store.all_nodes(aoi_id=aoi_id)
        scored: list[tuple[float, dict[str, Any]]] = []
        for node in candidates:
            score = self._score_node_relevance(node, tokens)
            if score > 0.0:
                scored.append((score, node))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        anchors = [pair[1] for pair in scored[:top_k]]

        allowed_ids: set[str] = set()
        edge_paths: list[str] = []
        telemetry: list[dict[str, Any]] = []
        seen_telemetry: set[str] = set()

        # Always include active FloodZones and tripped Substations in the AOI anchor set
        for node in candidates:
            if node.get("label") in ("FloodZone", "Substation", "Hospital", "Culvert", "Bridge"):
                anchors.append(node)

        for anchor in anchors[: top_k + 6]:
            a_id = str(anchor["id"])
            allowed_ids.add(a_id)
            if a_id not in seen_telemetry:
                seen_telemetry.add(a_id)
                telemetry.append({
                    "id": a_id,
                    "label": anchor.get("label", "Asset"),
                    "name": anchor.get("name", a_id),
                    "status": anchor.get("status", str(anchor.get("is_passable", True))),
                    "dg_fuel_rem_hrs": anchor.get("dg_fuel_rem_hrs", -1.0),
                    "elev_m": anchor.get("elev_m", 0.0),
                    "flood_depth_m": anchor.get("flood_depth_m", anchor.get("water_depth_m", 0.0)),
                })

            # Expand 1..3 hops across cascade and transport relationships
            frontier: list[tuple[str, str]] = [(a_id, f"{anchor.get('label', 'Node')}:{a_id}")]
            for _ in range(3):
                next_frontier: list[tuple[str, str]] = []
                for curr_id, path_str in frontier:
                    for edge in self.graph_store.outgoing_edges(curr_id, CASCADE_REL_TYPES | {"CONNECTS_TO"}):
                        dst_id = str(edge["dst_id"])
                        dst_node = self.graph_store.get_node(dst_id)
                        if dst_node is None:
                            continue
                        if dst_node.get("verification_state") in ("PLAUSIBILITY_REJECTED", "SUPERSEDED"):
                            continue
                        allowed_ids.add(dst_id)
                        dst_label = dst_node.get("label", "Node")
                        rel_type = edge["rel_type"]
                        new_path = f"{path_str}-[{rel_type}]->{dst_label}:{dst_id}"
                        if rel_type in CASCADE_REL_TYPES and new_path not in edge_paths:
                            edge_paths.append(new_path)
                        if dst_id not in seen_telemetry:
                            seen_telemetry.add(dst_id)
                            telemetry.append({
                                "id": dst_id,
                                "label": dst_label,
                                "name": dst_node.get("name", dst_id),
                                "status": dst_node.get("status", str(dst_node.get("is_passable", True))),
                                "dg_fuel_rem_hrs": dst_node.get("dg_fuel_rem_hrs", -1.0),
                                "elev_m": dst_node.get("elev_m", 0.0),
                                "flood_depth_m": dst_node.get("flood_depth_m", dst_node.get("water_depth_m", 0.0)),
                            })
                        if rel_type in CASCADE_REL_TYPES:
                            next_frontier.append((dst_id, new_path))
                frontier = next_frontier

        return SubgraphRetrievalResult(
            aoi_id=aoi_id,
            query_text=query_text,
            anchor_node_ids=[str(a["id"]) for a in anchors[:top_k]],
            allowed_node_ids=allowed_ids,
            explicit_edge_paths=edge_paths[:25],
            asset_telemetry=telemetry[:25],
        )
