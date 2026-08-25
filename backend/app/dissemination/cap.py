"""dissemination/cap.py — build a standards-conformant CAP 1.2 (OASIS Common Alerting Protocol)
XML document from an `ActionCard` (BUILD_PLAN.md task 3.4).

This is the artifact that proves "we integrate with SACHET's rails, we don't replace it"
(CLAUDE.md rule 8): NDMA's SACHET platform ingests CAP 1.2 alerts and fans them out over its own
channels (C-DOT cell broadcast, telecom SMS gateways, the SACHET app, RSS, etc — see
docs/reference/SIH26001_Technical_Architecture_Reference.md). We produce one conformant CAP
<alert> document per ActionCard; we do not build, and this module must never be read as claiming
to build, a replacement telecom alerting pipe. `dissemination/channels.py` (task 3.5) models the
*next* hop after a CAP document like this leaves our system — and everything there is explicitly
SIMULATED, never a live send.

Validated in `tests/test_cap.py` against the real OASIS CAP 1.2 XSD, cached locally at
`tests/fixtures/CAP-v1.2.xsd` (fetched once from
https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.xsd — a public, versioned, non-project-
sensitive standard; caching it is explicitly sanctioned for this task rather than re-fetching it
on every test run, which would also violate CLAUDE.md rule 10 for anything on a demo-adjacent
path).

This is a pure function: identical `ActionCard` in -> byte-identical XML out (CLAUDE.md rule 13).
No wall-clock reads, no randomness — every timestamp in the document comes from a field already
on the card.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from lxml import etree

from app.decision.escalation import STAGE_LABELS
from app.schemas.decision import ActionCard

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

# A plain, non-domain-shaped identifier for the CAP `sender` field — deliberately NOT formatted
# like a real government email/domain. We are a partner feed into SACHET, not SACHET itself and
# not NDMA (CLAUDE.md rule 8) — the sender string must never look like it originated from the
# national system.
DEFAULT_SENDER = "sih26001-ner-landslide-ews"

# Landslide has no dedicated CAP category; "Geo" (geophysical — the closest published fit,
# commonly used for landslide/seismic events in real-world CAP feeds) plus "Safety" (every card
# here is evacuation guidance, not a bare hazard notice) is our own pairing, not a cited profile.
_CATEGORIES: tuple[str, ...] = ("Geo", "Safety")
_EVENT = "Landslide"

# stage -> (urgency, severity, certainty, responseType...). CAP has no built-in notion of our
# four-stage escalation ladder, so this mapping is our own engineering decision — loosely modelled
# on how US NWS/IPAWS profiles fold watch/warning language onto CAP's three severity axes, not a
# copied standard. Document this if a judge asks why these particular triples.
_STAGE_CAP_FIELDS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "GREEN": ("Future", "Minor", "Possible", ("Monitor",)),
    "YELLOW": ("Expected", "Moderate", "Likely", ("Prepare", "Monitor")),
    "ORANGE": ("Expected", "Severe", "Likely", ("Prepare",)),
    "RED": ("Immediate", "Extreme", "Observed", ("Evacuate",)),
}


def _cap_datetime(dt: datetime) -> str:
    """Format per the CAP 1.2 XSD's `sent`/`effective`/`onset`/`expires` pattern:
    `\\d\\d\\d\\d-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d[-,+]\\d\\d:\\d\\d` — whole seconds only (no
    fractional part), and a colon-separated `+HH:MM`/`-HH:MM` offset (Python's `%z` gives `+HHMM`
    with no colon, so we splice one in)."""
    if dt.tzinfo is None:
        raise ValueError("CAP requires a timezone-aware datetime; got a naive one")
    text = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return f"{text[:-2]}:{text[-2:]}"


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    child = etree.SubElement(parent, f"{{{CAP_NS}}}{tag}")
    if text is not None:
        child.text = text
    return child


def _value_pair(parent: etree._Element, tag: str, name: str, value: str) -> etree._Element:
    """`<parameter>`, `<geocode>`, and `<eventCode>` are all the same
    `{valueName, value}` shape in the CAP 1.2 XSD."""
    block = _el(parent, tag)
    _el(block, "valueName", name)
    _el(block, "value", value)
    return block


def _instruction_text(card: ActionCard) -> str:
    parts = [f"Go to {card.shelter_name}."]
    if card.roads_to_avoid:
        parts.append("Avoid: " + ", ".join(card.roads_to_avoid) + ".")
    if card.what_to_carry:
        parts.append("Carry: " + ", ".join(card.what_to_carry) + ".")
    return " ".join(parts)


def _write_common_info_fields(
    info: etree._Element,
    *,
    language: str,
    urgency: str,
    severity: str,
    certainty: str,
    response_types: tuple[str, ...],
) -> None:
    _el(info, "language", language)
    for cat in _CATEGORIES:
        _el(info, "category", cat)
    _el(info, "event", _EVENT)
    for rt in response_types:
        _el(info, "responseType", rt)
    _el(info, "urgency", urgency)
    _el(info, "severity", severity)
    _el(info, "certainty", certainty)


def _write_area(info: etree._Element, card: ActionCard) -> None:
    # TODO(verify): ActionCard carries no village polygon/point geometry yet (that lives in
    # data/static/<aoi>/exposure.gpkg per BUILD_PLAN.md task 1.3, not on this schema) — so `area`
    # can only identify the village by id today, not draw its real boundary. Once impact/decision
    # carries village geometry through to ActionCard/EvacuationRoute, replace this geocode-only
    # placeholder with a real <polygon> or <circle>.
    area = _el(info, "area")
    _el(area, "areaDesc", f"Village {card.village_id}")
    _value_pair(area, "geocode", "village_id", card.village_id)


def build_cap_alert(card: ActionCard, *, sender: str = DEFAULT_SENDER) -> bytes:
    """Build one CAP 1.2 `<alert>` document (as UTF-8 XML bytes) from an `ActionCard`.

    Emits one primary `<info>` block in English plus one additional `<info>` block per language
    present in `card.translations` (each carrying that language's translated headline, and a
    `<resource>` link to the matching pre-generated TTS audio in `card.audio_urls`, if present —
    BUILD_PLAN.md task 3.9's audio is exactly what such a `<resource>` would point at).
    """
    if card.stage not in _STAGE_CAP_FIELDS:
        raise ValueError(f"unknown ActionCard.stage {card.stage!r}")
    urgency, severity, certainty, response_types = _STAGE_CAP_FIELDS[card.stage]

    alert = etree.Element(f"{{{CAP_NS}}}alert", nsmap={None: CAP_NS})
    _el(alert, "identifier", card.alert_id)
    _el(alert, "sender", sender)
    _el(alert, "sent", _cap_datetime(card.issued_at))
    _el(alert, "status", "Actual")
    _el(alert, "msgType", "Alert")
    _el(alert, "scope", "Public")
    # What CLAUDE.md rule 8 ("we are a partner to the national system, never a replacement")
    # looks like on the wire: an explicit, human-readable note on every alert we emit.
    _el(
        alert,
        "note",
        "Generated by the NER Landslide Early Warning & Risk Monitoring System (SIH26001) "
        "for ingestion into NDMA SACHET. This system is a data/decision partner to SACHET, "
        "not a replacement alerting authority.",
    )

    info = _el(alert, "info")
    _write_common_info_fields(
        info,
        language="en-US",
        urgency=urgency,
        severity=severity,
        certainty=certainty,
        response_types=response_types,
    )

    _el(info, "effective", _cap_datetime(card.issued_at))
    if card.safe_window_hours is not None:
        onset = card.issued_at + timedelta(hours=card.safe_window_hours[0])
        _el(info, "onset", _cap_datetime(onset))
    _el(info, "expires", _cap_datetime(card.valid_until))

    _el(info, "senderName", "NER Landslide Early Warning & Risk Monitoring System (SIH26001)")
    _el(info, "headline", card.headline)
    _el(info, "description", card.reason_plain)
    _el(info, "instruction", _instruction_text(card))
    _el(info, "contact", card.contact)

    _value_pair(info, "parameter", "stage", f"{card.stage} ({STAGE_LABELS[card.stage]})")
    _value_pair(info, "parameter", "shelter_name", card.shelter_name)
    if card.roads_to_avoid:
        _value_pair(info, "parameter", "roads_to_avoid", "; ".join(card.roads_to_avoid))
    if card.safe_window_hours is not None:
        lo, hi = card.safe_window_hours
        _value_pair(info, "parameter", "safe_window_hours", f"{lo}-{hi}")

    _write_area(info, card)

    for lang, text in card.translations.items():
        t_info = _el(alert, "info")
        _write_common_info_fields(
            t_info,
            language=lang,
            urgency=urgency,
            severity=severity,
            certainty=certainty,
            response_types=response_types,
        )
        _el(t_info, "headline", text)
        audio_url = card.audio_urls.get(lang)
        if audio_url:
            resource = _el(t_info, "resource")
            _el(
                resource,
                "resourceDesc",
                "Voice alert audio (pre-generated TTS; BUILD_PLAN.md task 3.9)",
            )
            _el(resource, "mimeType", "audio/mpeg")
            _el(resource, "uri", audio_url)
        _write_area(t_info, card)

    return etree.tostring(alert, xml_declaration=True, encoding="UTF-8", pretty_print=True)
