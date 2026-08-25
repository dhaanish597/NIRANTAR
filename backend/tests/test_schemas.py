"""Contract test for backend/app/schemas/ (CLAUDE.md rule 12 / §10 "write at least one test per
module that proves the contract holds"). Not exhaustive — just proves every schema in the spine
can be constructed with valid data and rejects the domain's stated invariants (p_fail, p_isolated,
p_blocked, confidence, soil_moisture all live in [0,1] per CLAUDE.md §4 glossary).
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas import (
    ActionCard,
    Attribution,
    AuditEvent,
    CellObservation,
    CellRisk,
    EvacuationRoute,
    ModeState,
    ObservationFrame,
    RoadSegmentRisk,
    RunMode,
    RunoutEnvelope,
    SettlementPriority,
    TickResult,
    VillageIsolation,
)

NOW = datetime(2024, 5, 28, 6, 0, tzinfo=timezone.utc)


def make_cell_observation(**overrides) -> CellObservation:
    defaults = dict(
        cell_id="aizawl_0412",
        rain_1h=2.1,
        rain_6h=8.0,
        rain_24h=40.0,
        rain_72h=120.0,
        antecedent_7d=60.0,
        antecedent_15d=100.0,
        antecedent_30d=180.0,
        soil_moisture=0.31,
        insar_velocity_mm_yr=None,
        source="scenario:_smoke",
        is_reconstructed=True,
    )
    defaults.update(overrides)
    return CellObservation(**defaults)


def make_cell_risk(**overrides) -> CellRisk:
    defaults = dict(
        cell_id="aizawl_0412",
        p_fail=0.42,
        threshold_exceedance=0.8,
        confidence=0.6,
        attributions=[
            Attribution(
                feature="rain_72h",
                plain_language="72-hour rainfall",
                contribution=0.38,
                display_pct=38.0,
            )
        ],
        model_version="stub-0.0.1",
    )
    defaults.update(overrides)
    return CellRisk(**defaults)


class TestModeState:
    def test_valid_replay_state(self):
        state = ModeState(
            mode=RunMode.REPLAY,
            scenario_id="_smoke",
            scenario_time=NOW,
            speed_factor=3600.0,
            paused=False,
        )
        assert state.mode is RunMode.REPLAY

    def test_speed_factor_must_be_positive(self):
        with pytest.raises(ValidationError):
            ModeState(mode=RunMode.LIVE, scenario_id=None, scenario_time=None, speed_factor=0.0)


class TestIngest:
    def test_valid_observation_frame(self):
        frame = ObservationFrame(
            t=NOW,
            aoi_id="aizawl",
            cells=[make_cell_observation()],
            provenance={"confidence": "fabricated"},
        )
        assert frame.cells[0].is_reconstructed is True

    def test_soil_moisture_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            make_cell_observation(soil_moisture=1.4)

    def test_negative_rainfall_rejected(self):
        with pytest.raises(ValidationError):
            make_cell_observation(rain_1h=-1.0)


class TestRisk:
    def test_valid_cell_risk(self):
        risk = make_cell_risk()
        assert 0.0 <= risk.p_fail <= 1.0

    def test_p_fail_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            make_cell_risk(p_fail=1.2)


class TestImpact:
    def test_valid_impact_objects(self):
        envelope = RunoutEnvelope(
            source_cell_id="aizawl_0412",
            geometry={"type": "Polygon", "coordinates": []},
            p_fail=0.7,
            method="stub-fixed-angle",
        )
        road = RoadSegmentRisk(
            edge_id="nh6_hunthar_1",
            name="NH-6",
            highway_class="trunk",
            is_bridge=False,
            p_blocked=0.65,
            severed=False,
            contributing_cells=["aizawl_0412"],
        )
        village = VillageIsolation(
            village_id="v_hunthar",
            name="Hunthar",
            population=1200,
            p_isolated=0.55,
            isolated_now=False,
            alternate_route_exists=True,
            est_duration_hours=None,
            severed_links=[],
        )
        priority = SettlementPriority(
            village_id="v_hunthar",
            eps=0.71,
            tier="P2",
            components={"p_fail": 0.42, "pop": 0.3, "rii": 0.55, "shelter": 0.1},
        )
        assert envelope.p_fail == 0.7
        assert road.severed is False
        assert village.population == 1200
        assert priority.tier == "P2"

    def test_p_blocked_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            RoadSegmentRisk(
                edge_id="x",
                name=None,
                highway_class="trunk",
                is_bridge=False,
                p_blocked=1.5,
                severed=False,
                contributing_cells=[],
            )


class TestDecision:
    def test_valid_action_card_without_route(self):
        card = ActionCard(
            alert_id="alert-1",
            village_id="v_hunthar",
            stage="ORANGE",
            headline="Evacuation Ready",
            reason_plain="Rising rainfall on slopes above Hunthar",
            shelter_name="Hunthar Community Hall",
            route=None,
            roads_to_avoid=["NH-6 near Hunthar"],
            what_to_carry=["ID", "medicines", "torch"],
            contact="DDMA Aizawl",
            issued_at=NOW,
            valid_until=NOW,
            safe_window_hours=(2.0, 6.0),
            translations={},
            audio_urls={},
        )
        assert card.route is None
        assert card.safe_window_hours == (2.0, 6.0)

    def test_valid_evacuation_route(self):
        route = EvacuationRoute(
            village_id="v_hunthar",
            shelter_id="shelter-1",
            shelter_name="Hunthar Community Hall",
            geometry={"type": "LineString", "coordinates": []},
            distance_m=800.0,
            est_walk_minutes=12,
            avoided_roads=["NH-6 near Hunthar"],
            shelter_capacity_ok=True,
        )
        assert route.shelter_capacity_ok is True


class TestAudit:
    def test_valid_audit_event(self):
        event = AuditEvent(
            event_id="evt-1",
            alert_id="alert-1",
            kind="AI_FLAGGED",
            actor="system",
            t=NOW,
            payload={"cell_id": "aizawl_0412"},
            input_hash="deadbeef",
            prev_hash="0" * 64,
            hash="cafef00d",
        )
        assert event.kind == "AI_FLAGGED"

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValidationError):
            AuditEvent(
                event_id="evt-1",
                alert_id="alert-1",
                kind="NOT_A_REAL_KIND",
                actor="system",
                t=NOW,
                payload={},
                input_hash="x",
                prev_hash="x",
                hash="x",
            )


class TestTick:
    def test_valid_empty_tick(self):
        tick = TickResult(t=NOW, mode=RunMode.REPLAY, scenario_id="_smoke", aoi_id="aizawl")
        assert tick.cell_risks == []
        assert tick.is_reconstructed is False

    def test_tick_round_trips_through_json(self):
        tick = TickResult(
            t=NOW,
            mode=RunMode.REPLAY,
            scenario_id="_smoke",
            aoi_id="aizawl",
            cell_risks=[make_cell_risk()],
            is_reconstructed=True,
        )
        payload = tick.model_dump_json()
        restored = TickResult.model_validate_json(payload)
        assert restored == tick
