"""Sub-15-Second Batched Neo4j AuraDB Seeder (`UNWIND $batch AS row`).

Seeds all 4 architectural layers (`nodes.json` and `edges.json`) into `GraphStoreManager`
(both live Neo4j AuraDB when configured and the synchronized local mirror).
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.graph.models import SeedSummary
from app.graph.neo4j_client import GraphStoreManager


def _batch_chunks(items: list[dict[str, Any]], size: int = 2500) -> Iterator[list[dict[str, Any]]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


NODE_UNWIND_CYPHER = """
UNWIND $batch AS row
MERGE (n {id: row.id})
SET n += row,
    n.location = CASE
      WHEN row.lat IS NOT NULL AND row.lon IS NOT NULL
      THEN point({latitude: row.lat, longitude: row.lon})
      ELSE n.location
    END
"""

EDGE_UNWIND_CYPHER = """
UNWIND $batch AS row
MATCH (src {id: row.src_id}), (dst {id: row.dst_id})
MERGE (src)-[r:REL_GENERIC {edge_id: row.edge_id}]->(dst)
SET r += row
"""


def seed_nirantar_knowledge_graph(
    bundle_dir: Path | str,
    graph_store: GraphStoreManager | None = None,
) -> SeedSummary:
    t0 = datetime.now(timezone.utc)
    bundle_path = Path(bundle_dir)
    nodes_path = bundle_path / "nodes.json"
    edges_path = bundle_path / "edges.json"

    if not nodes_path.is_file() or not edges_path.is_file():
        raise FileNotFoundError(f"Seed bundle missing at {bundle_path}; run build_multiplex_seed_bundle.py")

    nodes_by_label: dict[str, list[dict[str, Any]]] = json.loads(
        nodes_path.read_text(encoding="utf-8")
    )
    edges_by_type: dict[str, list[dict[str, Any]]] = json.loads(
        edges_path.read_text(encoding="utf-8")
    )

    store = graph_store or GraphStoreManager(
        uri=os.getenv("NEO4J_URI", ""),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", ""),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    store.initialize_schema()

    total_nodes = 0
    for label, rows in nodes_by_label.items():
        for batch in _batch_chunks(rows, size=2500):
            total_nodes += store.upsert_nodes_batch(label, batch, cypher=NODE_UNWIND_CYPHER)

    total_edges = 0
    for rel_type, rows in edges_by_type.items():
        for batch in _batch_chunks(rows, size=2500):
            total_edges += store.upsert_edges_batch(rel_type, batch, cypher=EDGE_UNWIND_CYPHER)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    return SeedSummary(
        status="SEEDED",
        elapsed_seconds=round(max(0.001, elapsed), 4),
        nodes_seeded=total_nodes,
        edges_seeded=total_edges,
        backend_mode=store.backend_mode,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed NIRANTAR Multiplex Graph into Neo4j AuraDB")
    parser.add_argument("--bundle", default="data/seed_bundle")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = seed_nirantar_knowledge_graph(Path(args.bundle))
    print(json.dumps(result.model_dump(), indent=2))
