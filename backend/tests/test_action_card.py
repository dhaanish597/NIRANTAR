"""Contract test for decision/action_card.py (BUILD_PLAN.md task 3.3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import ACTION_CARD_CONTACT_PLACEHOLDER, WHAT_TO_CARRY_CHECKLIST
from app.decision.action_card import (
    ALERT_WORTHY_STAGES,
    build_action_card,
    build_action_card_from_escalation,
)
from app.decision.escalation import EscalationStateMachine
from app.schemas.decision import EvacuationRoute
from app.schemas.risk import Attribution

T = datetime(2026, 5, 28, 3, 0, tzinfo=timezone.utc)


def make_route(**overrides) -> EvacuationRoute:
    defaults = dict(
        village_id="v1",
        shelter_id="s1",
        shelter_name="Community Hall Shelter",
        geometry={"type": "LineString", "coordinates": [[92.7, 23.7], [92.71, 23.71]]},
        distance_m=850.0,
        est_walk_minutes=12,
        avoided_roads=["NH6"],
        shelter_capacity_ok=True,
    )
    defaults.update(overrides)
    return EvacuationRoute(**defaults)


class TestBuildActionCard:
    def test_basic_fields_populated(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert card.village_id == "v1"
        assert card.stage == "RED"
        assert card.alert_id == f"card-v1-{T.isoformat()}"
        assert card.issued_at == T

    def test_headline_matches_stage(self):
        assert build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T).headline == "Evacuate Now"
        assert build_action_card(village_id="v1", stage="GREEN", p_fail=0.1, now=T).headline != "Evacuate Now"

    def test_valid_until_is_after_issued_at_and_uses_config_default(self):
        from app.config import ACTION_CARD_VALID_FOR_HOURS

        card = build_action_card(village_id="v1", stage="ORANGE", p_fail=0.6, now=T)
        assert card.valid_until == T + timedelta(hours=ACTION_CARD_VALID_FOR_HOURS)

    def test_valid_for_override_is_respected(self):
        card = build_action_card(village_id="v1", stage="ORANGE", p_fail=0.6, now=T, valid_for=timedelta(hours=2))
        assert card.valid_until == T + timedelta(hours=2)

    def test_never_calls_datetime_now_internally(self):
        # If this module called datetime.now() anywhere, issued_at would drift from the supplied
        # `now`. Calling twice with the same `now` a moment apart in wall-clock time must still
        # produce byte-identical issued_at/valid_until/alert_id (CLAUDE.md rule 13).
        card_a = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        card_b = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert card_a.issued_at == card_b.issued_at == T
        assert card_a.alert_id == card_b.alert_id

    def test_p_fail_out_of_range_raises(self):
        with pytest.raises(ValueError):
            build_action_card(village_id="v1", stage="RED", p_fail=1.5, now=T)

    def test_what_to_carry_defaults_to_config_checklist(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert card.what_to_carry == WHAT_TO_CARRY_CHECKLIST

    def test_what_to_carry_override_is_respected(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T, what_to_carry=["Torch"])
        assert card.what_to_carry == ["Torch"]

    def test_contact_defaults_to_placeholder_and_is_labelled_as_such(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert card.contact == ACTION_CARD_CONTACT_PLACEHOLDER
        assert "placeholder" in card.contact.lower()

    def test_contact_never_looks_like_a_real_phone_number(self):
        # Guards against ever silently swapping the honest placeholder for an invented digit
        # string (CLAUDE.md: never invent facts/figures).
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert not any(ch.isdigit() for ch in card.contact)

    def test_translations_and_audio_urls_default_empty(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T)
        assert card.translations == {}
        assert card.audio_urls == {}


class TestRouteWiring:
    def test_route_present_populates_shelter_and_roads(self):
        route = make_route()
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T, route=route)
        assert card.shelter_name == "Community Hall Shelter"
        assert card.roads_to_avoid == ["NH6"]
        assert card.route is route

    def test_route_none_produces_honest_fallback_not_a_fabricated_shelter(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T, route=None)
        assert card.route is None
        assert card.roads_to_avoid == []
        assert "no usable shelter" in card.shelter_name.lower()


class TestSafeWindowWiring:
    def test_safe_window_hours_passed_through_as_a_range(self):
        from app.decision.window import SafeWindowEstimate

        window = SafeWindowEstimate(hours=(1.0, 4.0), confidence=0.6, basis="test basis")
        card = build_action_card(village_id="v1", stage="ORANGE", p_fail=0.6, now=T, safe_window=window)
        assert card.safe_window_hours == (1.0, 4.0)

    def test_no_safe_window_supplied_is_none_not_fabricated(self):
        card = build_action_card(village_id="v1", stage="ORANGE", p_fail=0.6, now=T, safe_window=None)
        assert card.safe_window_hours is None

    def test_never_says_time_to_landslide_anywhere_on_the_card(self):
        from app.decision.window import SafeWindowEstimate

        window = SafeWindowEstimate(hours=(1.0, 4.0), confidence=0.6, basis="linear trend projection")
        card = build_action_card(
            village_id="v1", stage="ORANGE", p_fail=0.6, now=T, safe_window=window,
            attributions=[Attribution(feature="rain_72h", plain_language="72-hour rainfall", contribution=1.2, display_pct=38.0)],
        )
        haystack = " ".join(
            [card.headline, card.reason_plain, card.shelter_name, card.contact, *card.what_to_carry]
        ).lower()
        assert "time to landslide" not in haystack


class TestReasonPlain:
    def test_falls_back_to_generic_sentence_with_no_attributions(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.83, now=T, attributions=None)
        assert "83%" in card.reason_plain
        assert "Red Evacuate Now" in card.reason_plain

    def test_includes_top_attributions_when_supplied(self):
        attrs = [
            Attribution(feature="rain_72h", plain_language="72-hour rainfall", contribution=1.2, display_pct=38.0),
            Attribution(feature="slope_mean", plain_language="average slope (26°)", contribution=0.9, display_pct=21.0),
            Attribution(feature="elevation", plain_language="elevation (900 m)", contribution=0.1, display_pct=3.0),
        ]
        card = build_action_card(village_id="v1", stage="ORANGE", p_fail=0.62, now=T, attributions=attrs)
        assert "72-hour rainfall" in card.reason_plain
        assert "average slope" in card.reason_plain
        # top_n defaults to 2 -> the weakest (3%) attribution shouldn't be named
        assert "elevation" not in card.reason_plain

    def test_does_not_fabricate_a_driver_that_was_not_supplied(self):
        card = build_action_card(village_id="v1", stage="RED", p_fail=0.9, now=T, attributions=[])
        assert "rainfall" not in card.reason_plain.lower()


class TestAlertWorthyStages:
    def test_orange_and_red_are_alert_worthy(self):
        assert ALERT_WORTHY_STAGES == {"ORANGE", "RED"}

    def test_green_and_yellow_are_not(self):
        assert "GREEN" not in ALERT_WORTHY_STAGES
        assert "YELLOW" not in ALERT_WORTHY_STAGES


class TestBuildActionCardFromEscalation:
    def test_delegates_stage_to_the_real_escalation_state_machine(self):
        escalation = EscalationStateMachine()
        card = build_action_card_from_escalation(village_id="v1", p_fail=0.9, now=T, escalation=escalation)
        assert card.stage == "RED"
        assert escalation.current_stage("v1") == "RED"

    def test_upgrade_is_immediate_and_reflected_on_the_card(self):
        escalation = EscalationStateMachine()
        card1 = build_action_card_from_escalation(village_id="v1", p_fail=0.1, now=T, escalation=escalation)
        assert card1.stage == "GREEN"
        card2 = build_action_card_from_escalation(
            village_id="v1", p_fail=0.9, now=T + timedelta(hours=1), escalation=escalation
        )
        assert card2.stage == "RED"

    def test_downgrade_hysteresis_is_respected_not_reimplemented(self):
        # Drive to RED, then drop p_fail just below the raw red threshold (0.75) but still within
        # the hysteresis band (>= 0.65) -> escalation.py's own rule says stay at RED. If this
        # module reimplemented its own thresholds instead of calling escalation.py, this would
        # incorrectly show ORANGE.
        escalation = EscalationStateMachine()
        build_action_card_from_escalation(village_id="v1", p_fail=0.9, now=T, escalation=escalation)
        card = build_action_card_from_escalation(
            village_id="v1", p_fail=0.70, now=T + timedelta(hours=1), escalation=escalation
        )
        assert card.stage == "RED"

    def test_appends_a_real_escalated_audit_event(self):
        escalation = EscalationStateMachine()
        build_action_card_from_escalation(village_id="v1", p_fail=0.9, now=T, escalation=escalation)
        kinds = [e.kind for e in escalation.audit_log.for_alert("esc-v1")]
        assert kinds == ["ESCALATED"]

    def test_entity_id_override_keys_escalation_separately_from_village_id(self):
        escalation = EscalationStateMachine()
        build_action_card_from_escalation(
            village_id="v1", p_fail=0.9, now=T, escalation=escalation, entity_id="cell_aizawl_0101"
        )
        assert escalation.current_stage("cell_aizawl_0101") == "RED"
        assert escalation.current_stage("v1") == "GREEN"  # never observed under this key

    def test_extra_kwargs_pass_through_to_build_action_card(self):
        escalation = EscalationStateMachine()
        route = make_route()
        card = build_action_card_from_escalation(
            village_id="v1", p_fail=0.9, now=T, escalation=escalation, route=route
        )
        assert card.shelter_name == "Community Hall Shelter"
