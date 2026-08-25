"""Contract tests for dissemination/cap.py (BUILD_PLAN.md task 3.4).

Validates generated CAP <alert> documents against the real OASIS CAP 1.2 XSD, cached at
tests/fixtures/CAP-v1.2.xsd (fetched once from
https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.xsd -- a public, versioned OASIS
standard, not project-sensitive; see cap.py's module docstring).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from lxml import etree

from app.dissemination.cap import CAP_NS, DEFAULT_SENDER, build_cap_alert
from app.schemas.decision import ActionCard, EvacuationRoute

FIXTURES = Path(__file__).resolve().parent / "fixtures"
XSD_PATH = FIXTURES / "CAP-v1.2.xsd"

T0 = datetime(2026, 5, 28, 6, 0, tzinfo=timezone.utc)
IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(scope="module")
def cap_schema() -> etree.XMLSchema:
    assert XSD_PATH.is_file(), f"expected cached CAP 1.2 XSD at {XSD_PATH}"
    return etree.XMLSchema(etree.parse(str(XSD_PATH)))


def make_card(
    *,
    stage: str = "RED",
    issued_at: datetime = T0,
    translations: dict[str, str] | None = None,
    audio_urls: dict[str, str] | None = None,
    roads_to_avoid: list[str] | None = None,
    what_to_carry: list[str] | None = None,
    safe_window_hours=(0.0, 1.0),
) -> ActionCard:
    return ActionCard(
        alert_id=f"alert-v1-{stage.lower()}",
        village_id="v1",
        stage=stage,
        headline="Evacuate Now" if stage == "RED" else "Watch conditions",
        reason_plain="Rising rainfall over saturated slopes above the village.",
        shelter_name="Community Hall, Durtlang",
        route=EvacuationRoute(
            village_id="v1",
            shelter_id="shelter-1",
            shelter_name="Community Hall, Durtlang",
            geometry={"type": "LineString", "coordinates": [[92.71, 23.73], [92.72, 23.74]]},
            distance_m=1200.0,
            est_walk_minutes=18,
            avoided_roads=["NH-6"],
            shelter_capacity_ok=True,
        ),
        roads_to_avoid=roads_to_avoid if roads_to_avoid is not None else ["NH-6 (Hunthar)"],
        what_to_carry=what_to_carry if what_to_carry is not None else ["ID", "medicines", "torch"],
        contact="DDMA Aizawl: 1077",
        issued_at=issued_at,
        valid_until=issued_at + timedelta(hours=6),
        safe_window_hours=safe_window_hours,
        translations=translations if translations is not None else {},
        audio_urls=audio_urls if audio_urls is not None else {},
    )


def _validate(xml_bytes: bytes, schema: etree.XMLSchema) -> etree._ElementTree:
    doc = etree.fromstring(xml_bytes)
    is_valid = schema.validate(doc)
    assert is_valid, f"CAP XML failed XSD validation:\n{schema.error_log}"
    return doc


# --- core structural validity -------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["GREEN", "YELLOW", "ORANGE", "RED"])
def test_build_cap_alert_validates_against_real_xsd_for_every_stage(cap_schema, stage):
    xml_bytes = build_cap_alert(make_card(stage=stage))
    _validate(xml_bytes, cap_schema)


def test_alert_with_translations_and_audio_validates(cap_schema):
    card = make_card(
        translations={"mz": "Evakuashan tur - Chhuak ta", "hi": "अभी निकलें"},
        audio_urls={"mz": "data/audio/v1-red-mz.mp3", "hi": "data/audio/v1-red-hi.mp3"},
    )
    xml_bytes = build_cap_alert(card)
    doc = _validate(xml_bytes, cap_schema)
    info_blocks = doc.findall(f"{{{CAP_NS}}}info")
    # primary (en-US) + one per translation
    assert len(info_blocks) == 3


def test_alert_with_no_route_and_empty_lists_still_validates(cap_schema):
    card = make_card(roads_to_avoid=[], what_to_carry=[])
    xml_bytes = build_cap_alert(card)
    _validate(xml_bytes, cap_schema)


def test_alert_with_no_safe_window_validates(cap_schema):
    card = make_card(safe_window_hours=None)
    xml_bytes = build_cap_alert(card)
    doc = _validate(xml_bytes, cap_schema)
    info = doc.find(f"{{{CAP_NS}}}info")
    assert info.find(f"{{{CAP_NS}}}onset") is None  # only emitted when safe_window_hours is set


def test_timezone_other_than_utc_validates(cap_schema):
    card = make_card(issued_at=T0.astimezone(IST))
    xml_bytes = build_cap_alert(card)
    _validate(xml_bytes, cap_schema)


# --- field-level content checks -----------------------------------------------------------------


def test_identifier_sender_and_required_top_level_fields(cap_schema):
    card = make_card()
    doc = _validate(build_cap_alert(card), cap_schema)
    assert doc.findtext(f"{{{CAP_NS}}}identifier") == card.alert_id
    assert doc.findtext(f"{{{CAP_NS}}}sender") == DEFAULT_SENDER
    assert doc.findtext(f"{{{CAP_NS}}}status") == "Actual"
    assert doc.findtext(f"{{{CAP_NS}}}msgType") == "Alert"
    assert doc.findtext(f"{{{CAP_NS}}}scope") == "Public"


def test_note_field_names_sachet_and_partner_role(cap_schema):
    doc = _validate(build_cap_alert(make_card()), cap_schema)
    note = doc.findtext(f"{{{CAP_NS}}}note")
    assert "SACHET" in note
    assert "partner" in note.lower()


def test_sender_is_not_shaped_like_a_real_gov_domain():
    # CLAUDE.md rule 8: never look like we ARE SACHET/NDMA.
    assert "gov.in" not in DEFAULT_SENDER
    assert "ndma" not in DEFAULT_SENDER.lower()
    assert "sachet" not in DEFAULT_SENDER.lower()


@pytest.mark.parametrize(
    "stage,expected_urgency,expected_severity,expected_certainty",
    [
        ("GREEN", "Future", "Minor", "Possible"),
        ("YELLOW", "Expected", "Moderate", "Likely"),
        ("ORANGE", "Expected", "Severe", "Likely"),
        ("RED", "Immediate", "Extreme", "Observed"),
    ],
)
def test_stage_maps_to_expected_cap_severity_triple(
    cap_schema, stage, expected_urgency, expected_severity, expected_certainty
):
    doc = _validate(build_cap_alert(make_card(stage=stage)), cap_schema)
    info = doc.find(f"{{{CAP_NS}}}info")
    assert info.findtext(f"{{{CAP_NS}}}urgency") == expected_urgency
    assert info.findtext(f"{{{CAP_NS}}}severity") == expected_severity
    assert info.findtext(f"{{{CAP_NS}}}certainty") == expected_certainty


def test_red_stage_response_type_is_evacuate(cap_schema):
    doc = _validate(build_cap_alert(make_card(stage="RED")), cap_schema)
    info = doc.find(f"{{{CAP_NS}}}info")
    response_types = [e.text for e in info.findall(f"{{{CAP_NS}}}responseType")]
    assert "Evacuate" in response_types


def test_area_carries_village_id(cap_schema):
    doc = _validate(build_cap_alert(make_card()), cap_schema)
    area = doc.find(f"{{{CAP_NS}}}info/{{{CAP_NS}}}area")
    assert area.findtext(f"{{{CAP_NS}}}areaDesc") == "Village v1"
    geocode = area.find(f"{{{CAP_NS}}}geocode")
    assert geocode.findtext(f"{{{CAP_NS}}}valueName") == "village_id"
    assert geocode.findtext(f"{{{CAP_NS}}}value") == "v1"


def test_instruction_mentions_shelter_roads_and_items(cap_schema):
    doc = _validate(build_cap_alert(make_card()), cap_schema)
    instruction = doc.findtext(f"{{{CAP_NS}}}info/{{{CAP_NS}}}instruction")
    assert "Community Hall, Durtlang" in instruction
    assert "NH-6 (Hunthar)" in instruction
    assert "torch" in instruction


def test_translation_resource_links_to_matching_audio_url(cap_schema):
    card = make_card(
        translations={"mz": "Chhuak ta"},
        audio_urls={"mz": "data/audio/v1-red-mz.mp3"},
    )
    doc = _validate(build_cap_alert(card), cap_schema)
    info_blocks = doc.findall(f"{{{CAP_NS}}}info")
    mz_info = next(i for i in info_blocks if i.findtext(f"{{{CAP_NS}}}language") == "mz")
    resource = mz_info.find(f"{{{CAP_NS}}}resource")
    assert resource is not None
    assert resource.findtext(f"{{{CAP_NS}}}uri") == "data/audio/v1-red-mz.mp3"


def test_translation_without_audio_has_no_resource_block(cap_schema):
    card = make_card(translations={"as": "কিছু পাঠ"}, audio_urls={})
    doc = _validate(build_cap_alert(card), cap_schema)
    info_blocks = doc.findall(f"{{{CAP_NS}}}info")
    as_info = next(i for i in info_blocks if i.findtext(f"{{{CAP_NS}}}language") == "as")
    assert as_info.find(f"{{{CAP_NS}}}resource") is None


# --- error handling ------------------------------------------------------------------------------


def test_naive_datetime_rejected():
    card = make_card()
    card = card.model_copy(update={"issued_at": card.issued_at.replace(tzinfo=None)})
    with pytest.raises(ValueError):
        build_cap_alert(card)


def test_unknown_stage_rejected():
    card = ActionCard.model_construct(
        alert_id="bad",
        village_id="v1",
        stage="PURPLE",
        headline="?",
        reason_plain="?",
        shelter_name="?",
        route=None,
        roads_to_avoid=[],
        what_to_carry=[],
        contact="?",
        issued_at=T0,
        valid_until=T0 + timedelta(hours=1),
        safe_window_hours=None,
        translations={},
        audio_urls={},
    )
    with pytest.raises(ValueError):
        build_cap_alert(card)


# --- determinism (CLAUDE.md rule 13) --------------------------------------------------------------


def test_build_cap_alert_is_a_pure_function():
    card = make_card(translations={"mz": "x"}, audio_urls={"mz": "y.mp3"})
    assert build_cap_alert(card) == build_cap_alert(card)


def test_custom_sender_is_honoured(cap_schema):
    doc = _validate(build_cap_alert(make_card(), sender="custom-sender-id"), cap_schema)
    assert doc.findtext(f"{{{CAP_NS}}}sender") == "custom-sender-id"
