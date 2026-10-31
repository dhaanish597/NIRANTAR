"""Neo4j AuraDB Cypher Data Definition Language (DDL) for the 4-Layer Multiplex Graph.

Defines:
- 17 uniqueness constraints across all 4 architectural layers
- 6 spatial POINT indexes (WGS-84 SRID 4326)
- 4 operational state & temporal RANGE indexes
- 1 Lucene BM25 FULLTEXT index (`sitrep_fulltext_idx`)
- 1 768-dimensional cosine VECTOR index (`sitrep_vector_idx`)
"""
from __future__ import annotations

CONSTRAINTS_DDL: tuple[str, ...] = (
    "CREATE CONSTRAINT watershed_id_unique IF NOT EXISTS FOR (w:MicroWatershed) REQUIRE w.watershed_id IS UNIQUE",
    "CREATE CONSTRAINT drain_id_unique IF NOT EXISTS FOR (d:DrainageNode) REQUIRE d.drain_id IS UNIQUE",
    "CREATE CONSTRAINT floodzone_id_unique IF NOT EXISTS FOR (f:FloodZone) REQUIRE f.zone_id IS UNIQUE",
    "CREATE CONSTRAINT junction_osmid_unique IF NOT EXISTS FOR (j:RoadJunction) REQUIRE j.osmid IS UNIQUE",
    "CREATE CONSTRAINT segment_id_unique IF NOT EXISTS FOR (r:RoadSegment) REQUIRE r.segment_id IS UNIQUE",
    "CREATE CONSTRAINT bridge_id_unique IF NOT EXISTS FOR (b:Bridge) REQUIRE b.bridge_id IS UNIQUE",
    "CREATE CONSTRAINT culvert_id_unique IF NOT EXISTS FOR (c:Culvert) REQUIRE c.culvert_id IS UNIQUE",
    "CREATE CONSTRAINT substation_id_unique IF NOT EXISTS FOR (s:Substation) REQUIRE s.substation_id IS UNIQUE",
    "CREATE CONSTRAINT water_id_unique IF NOT EXISTS FOR (w:WaterFacility) REQUIRE w.water_id IS UNIQUE",
    "CREATE CONSTRAINT tower_id_unique IF NOT EXISTS FOR (t:TelecomTower) REQUIRE t.tower_id IS UNIQUE",
    "CREATE CONSTRAINT hospital_id_unique IF NOT EXISTS FOR (h:Hospital) REQUIRE h.hospital_id IS UNIQUE",
    "CREATE CONSTRAINT shelter_id_unique IF NOT EXISTS FOR (sh:ReliefShelter) REQUIRE sh.shelter_id IS UNIQUE",
    "CREATE CONSTRAINT depot_id_unique IF NOT EXISTS FOR (dp:SupplyDepot) REQUIRE dp.depot_id IS UNIQUE",
    "CREATE CONSTRAINT report_id_unique IF NOT EXISTS FOR (cr:CitizenReport) REQUIRE cr.report_id IS UNIQUE",
    "CREATE CONSTRAINT sensor_id_unique IF NOT EXISTS FOR (sr:SensorReading) REQUIRE sr.reading_id IS UNIQUE",
    "CREATE CONSTRAINT unit_id_unique IF NOT EXISTS FOR (ru:ResponderUnit) REQUIRE ru.unit_id IS UNIQUE",
    "CREATE CONSTRAINT order_id_unique IF NOT EXISTS FOR (ao:ActionOrder) REQUIRE ao.order_id IS UNIQUE",
)

POINT_INDEXES_DDL: tuple[str, ...] = (
    "CREATE POINT INDEX junction_loc_idx IF NOT EXISTS FOR (j:RoadJunction) ON (j.location)",
    "CREATE POINT INDEX drain_loc_idx IF NOT EXISTS FOR (d:DrainageNode) ON (d.location)",
    "CREATE POINT INDEX substation_loc_idx IF NOT EXISTS FOR (s:Substation) ON (s.location)",
    "CREATE POINT INDEX hospital_loc_idx IF NOT EXISTS FOR (h:Hospital) ON (h.location)",
    "CREATE POINT INDEX shelter_loc_idx IF NOT EXISTS FOR (sh:ReliefShelter) ON (sh.location)",
    "CREATE POINT INDEX report_loc_idx IF NOT EXISTS FOR (cr:CitizenReport) ON (cr.location)",
)

RANGE_INDEXES_DDL: tuple[str, ...] = (
    "CREATE INDEX junction_passable_idx IF NOT EXISTS FOR (j:RoadJunction) ON (j.is_passable, j.elev_m)",
    "CREATE INDEX rel_connects_passable_idx IF NOT EXISTS FOR ()-[r:CONNECTS_TO]-() ON (r.is_passable, r.dynamic_cost_s)",
    "CREATE INDEX substation_status_idx IF NOT EXISTS FOR (s:Substation) ON (s.status)",
    "CREATE INDEX report_state_time_idx IF NOT EXISTS FOR (cr:CitizenReport) ON (cr.verification_state, cr.observed_at)",
)

FULLTEXT_AND_VECTOR_DDL: tuple[str, ...] = (
    (
        "CREATE FULLTEXT INDEX sitrep_fulltext_idx IF NOT EXISTS "
        "FOR (n:CitizenReport|ActionOrder|Substation|Hospital|ReliefShelter) "
        "ON EACH [n.raw_transcript, n.english_translation, n.rationale, n.name]"
    ),
    (
        "CREATE VECTOR INDEX sitrep_vector_idx IF NOT EXISTS "
        "FOR (cr:CitizenReport) ON (cr.embedding) "
        "OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}"
    ),
)


def get_all_ddl_statements() -> list[str]:
    return [
        *CONSTRAINTS_DDL,
        *POINT_INDEXES_DDL,
        *RANGE_INDEXES_DDL,
        *FULLTEXT_AND_VECTOR_DDL,
    ]
