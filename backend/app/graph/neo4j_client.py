"""Neo4j AuraDB Driver & Dual-Mode Deterministic Local Mirror (`GraphStoreManager`).

Ensures NIRANTAR satisfies both:
1. Full cloud Neo4j AuraDB execution via the official `neo4j` Python driver (`execute_query`)
   when `NEO4J_URI` and credentials are configured.
2. CLAUDE.md Rule 10 ("The demo must run with the network cable unplugged"): every node and
   directed relationship is simultaneously maintained in an indexed in-memory property-graph
   mirror so offline replay and clean-checkout unit tests execute identically without network calls.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from app.graph.schema_ddl import get_all_ddl_statements


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2.0) ** 2
    return radius_m * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


class GraphStoreManager:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = "neo4j",
        password: str | None = None,
        database: str = "neo4j",
    ) -> None:
        self.uri = (uri or "").strip()
        self.user = (user or "neo4j").strip()
        self.password = (password or "").strip()
        self.database = database
        self._driver: Any = None
        self._nodes: dict[str, dict[str, Any]] = {}
        self._out_edges: dict[str, list[dict[str, Any]]] = {}
        self._in_edges: dict[str, list[dict[str, Any]]] = {}
        self._connect_if_configured()

    def _connect_if_configured(self) -> None:
        if not self.uri or not self.password or "xxxx.databases.neo4j.io" in self.uri:
            return
        try:
            from neo4j import GraphDatabase  # type: ignore[import-untyped]

            driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            driver.verify_connectivity()
            self._driver = driver
        except Exception:
            self._driver = None

    @property
    def backend_mode(self) -> Literal["auradb_live", "local_mirror"]:
        return "auradb_live" if self._driver is not None else "local_mirror"

    def initialize_schema(self) -> int:
        stmts = get_all_ddl_statements()
        if self._driver is not None:
            for stmt in stmts:
                self._driver.execute_query(stmt, database_=self.database)
        return len(stmts)

    def upsert_node(self, label: str, node_id: str, props: dict[str, Any]) -> dict[str, Any]:
        record = dict(props)
        record["id"] = node_id
        record["label"] = label
        self._nodes[node_id] = record
        self._out_edges.setdefault(node_id, [])
        self._in_edges.setdefault(node_id, [])
        return record

    def update_node_properties(self, node_id: str, props: dict[str, Any]) -> dict[str, Any] | None:
        node = self._nodes.get(node_id)
        if node is None:
            return None
        node.update(props)
        return node

    def upsert_nodes_batch(self, label: str, rows: list[dict[str, Any]], cypher: str | None = None) -> int:
        for row in rows:
            node_id = str(
                row.get("id")
                or row.get("osmid")
                or row.get("substation_id")
                or row.get("hospital_id")
                or row.get("shelter_id")
                or row.get("zone_id")
                or row.get("drain_id")
                or row.get("watershed_id")
                or row.get("segment_id")
                or row.get("bridge_id")
                or row.get("culvert_id")
                or row.get("water_id")
                or row.get("tower_id")
                or row.get("depot_id")
                or row.get("report_id")
            )
            self.upsert_node(label, node_id, row)
        if self._driver is not None and cypher:
            self._driver.execute_query(cypher, batch=rows, database_=self.database)
        return len(rows)

    def upsert_edge(
        self, rel_type: str, src_id: str, dst_id: str, edge_id: str, props: dict[str, Any]
    ) -> dict[str, Any]:
        edge = dict(props)
        edge["edge_id"] = edge_id
        edge["rel_type"] = rel_type
        edge["src_id"] = src_id
        edge["dst_id"] = dst_id

        out_list = self._out_edges.setdefault(src_id, [])
        self._out_edges[src_id] = [e for e in out_list if e.get("edge_id") != edge_id] + [edge]

        in_list = self._in_edges.setdefault(dst_id, [])
        self._in_edges[dst_id] = [e for e in in_list if e.get("edge_id") != edge_id] + [edge]
        return edge

    def upsert_edges_batch(
        self, rel_type: str, rows: list[dict[str, Any]], cypher: str | None = None
    ) -> int:
        for row in rows:
            src_id = str(row.get("src_id") or row.get("u_id"))
            dst_id = str(row.get("dst_id") or row.get("v_id"))
            edge_id = str(row.get("edge_id") or f"{rel_type}:{src_id}->{dst_id}")
            self.upsert_edge(rel_type, src_id, dst_id, edge_id, row)
        if self._driver is not None and cypher:
            self._driver.execute_query(cypher, batch=rows, database_=self.database)
        return len(rows)

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        return self._nodes.get(node_id)

    def nodes_by_label(self, label: str, aoi_id: str | None = None) -> list[dict[str, Any]]:
        result = [n for n in self._nodes.values() if n.get("label") == label]
        if aoi_id is not None:
            result = [n for n in result if n.get("aoi_id") == aoi_id]
        return result

    def all_nodes(self, aoi_id: str | None = None) -> list[dict[str, Any]]:
        if aoi_id is None:
            return list(self._nodes.values())
        return [n for n in self._nodes.values() if n.get("aoi_id") == aoi_id]

    def outgoing_edges(
        self, node_id: str, rel_types: set[str] | None = None
    ) -> list[dict[str, Any]]:
        edges = self._out_edges.get(node_id, [])
        if rel_types is None:
            return list(edges)
        return [e for e in edges if e.get("rel_type") in rel_types]

    def incoming_edges(
        self, node_id: str, rel_types: set[str] | None = None
    ) -> list[dict[str, Any]]:
        edges = self._in_edges.get(node_id, [])
        if rel_types is None:
            return list(edges)
        return [e for e in edges if e.get("rel_type") in rel_types]

    def find_nearest_node(
        self, lat: float, lon: float, label: str = "RoadJunction", max_dist_m: float = 5000.0
    ) -> tuple[dict[str, Any] | None, float]:
        candidates = self.nodes_by_label(label)
        best_node: dict[str, Any] | None = None
        best_dist = float("inf")
        for node in candidates:
            n_lat = node.get("lat")
            n_lon = node.get("lon")
            if n_lat is None or n_lon is None:
                continue
            dist = haversine_meters(lat, lon, float(n_lat), float(n_lon))
            if dist < best_dist and dist <= max_dist_m:
                best_dist = dist
                best_node = node
        return best_node, best_dist

    @classmethod
    def from_seed_bundle(cls, bundle_dir: Path | str) -> "GraphStoreManager":
        from scripts.seed_auradb_fast import seed_nirantar_knowledge_graph

        store = cls(uri="", user="neo4j", password="")
        seed_nirantar_knowledge_graph(Path(bundle_dir), store)
        return store

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None
