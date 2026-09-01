from __future__ import annotations

import base64
import json
import math
import re
import uuid
from datetime import datetime, timedelta

import httpx

from app.citizen_reports.images import DecodedImage, score_image_quality
from app.citizen_reports.store import CitizenReportStore
from app.config import AoiConfig
from app.schemas.citizen_report import AgentTrace, CitizenReport, CitizenReportCategory, CitizenReportSubmit
from app.schemas.tick import TickResult

STEPS = ["Ingestion", "Classification", "Dedup", "Hotspot", "Forecast", "Urgency", "Recommendation"]
CATEGORY_KEYWORDS: dict[CitizenReportCategory, tuple[str, ...]] = {
    "Slope crack": ("crack", "fissure", "split", "slope opening"),
    "Blocked road": ("blocked road", "road blocked", "cannot pass", "traffic stopped"),
    "Rockfall or debris": ("rockfall", "rocks", "debris", "mudslide", "landslide"),
    "Water seepage": ("seepage", "water", "spring", "leak", "saturated"),
    "Retaining wall damage": ("retaining wall", "wall damage", "bulging wall", "collapsed wall"),
    "Other": (),
}


class CitizenReportWorkflow:
    def __init__(
        self,
        store: CitizenReportStore,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout: float,
    ):
        self.store = store
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout

    async def submit(
        self,
        body: CitizenReportSubmit,
        *,
        image: DecodedImage,
        aoi: AoiConfig,
        now: datetime,
        latest_tick: TickResult | None,
    ) -> CitizenReport:
        outside_aoi = not _inside_bbox(body.lon, body.lat, aoi.bbox)

        report_id = f"report-{uuid.uuid4()}"
        traces: list[AgentTrace] = []

        def trace(step: str, detail: str, source: str = "deterministic") -> None:
            traces.append(
                AgentTrace(
                    step_name=step,
                    step_order=STEPS.index(step) + 1,
                    detail=detail,
                    source=source,
                    created_at=now,
                )
            )

        quality = score_image_quality(image)
        dimensions = (
            f"{image.width}x{image.height}" if image.width is not None and image.height is not None else "unknown dimensions"
        )
        trace(
            "Ingestion",
            f"Accepted geotagged {image.mime_type} photo ({dimensions}, {len(image.data)} bytes) "
            f"{'outside' if outside_aoi else 'inside'} the configured {aoi.name} AOI; "
            f"quality score {quality:.2f}. {'Retained for officer triage.' if outside_aoi else ''}",
        )

        classification = await self._classify(body, image)
        category = classification["category"]
        severity = classification["severity"]
        relevance = classification["relevance_score"]
        source = classification["source"]
        reasoning = classification["reasoning"]
        trace(
            "Classification",
            f"Classified as {category}, severity {severity}/5, relevance {relevance:.2f}. {reasoning}",
            "nvidia" if source == "nvidia" else "deterministic",
        )

        existing = self.store.list(aoi_id=body.aoi_id)
        duplicate = _find_duplicate(existing, category, body.lat, body.lon, now)
        duplicate_of = duplicate.id if duplicate else None
        trace(
            "Dedup",
            f"Likely duplicate of {duplicate.id}; matching open report is within 250 m and 72 hours."
            if duplicate
            else "No open report of the same class was found within 250 m in the last 72 hours.",
        )

        recent_nearby = [
            report
            for report in existing
            if report.created_at >= now - timedelta(days=7)
            and _haversine_km(body.lat, body.lon, report.lat, report.lon) <= 2.0
        ]
        hotspot_count = len(recent_nearby) + 1
        trace(
            "Hotspot",
            f"Found {hotspot_count} citizen report(s) within 2 km during the last 7 days, including this report.",
        )

        recent_aoi = [report for report in existing if report.created_at >= now - timedelta(days=14)]
        forecast_next_7_days = max(1, round((len(recent_aoi) / 14.0) * 7.0))
        trace(
            "Forecast",
            f"Simple recurrence projection estimates {forecast_next_7_days} report(s) in the AOI over the next 7 days; this is workload planning, not a landslide forecast.",
        )

        aoi_max_p_fail = None
        if latest_tick and latest_tick.aoi_id == body.aoi_id and latest_tick.cell_risks:
            aoi_max_p_fail = max(risk.p_fail for risk in latest_tick.cell_risks)
        urgency = _urgency_score(
            severity=severity,
            relevance=relevance,
            quality=quality,
            hotspot_count=hotspot_count,
            aoi_max_p_fail=aoi_max_p_fail,
            duplicate=duplicate is not None,
        )
        risk_detail = (
            f"current AOI maximum P_fail {aoi_max_p_fail:.2f}"
            if aoi_max_p_fail is not None
            else "no current AOI risk tick available"
        )
        trace(
            "Urgency",
            f"Urgency score {urgency}/100 from severity, evidence quality/relevance, local recurrence, duplicate status, and {risk_detail}.",
        )

        recommendation = _recommendation(category, urgency, quality, relevance, duplicate_of, hotspot_count)
        trace("Recommendation", recommendation)

        report = CitizenReport(
            id=report_id,
            aoi_id=body.aoi_id,
            category=category,
            citizen_selected_category=body.category,
            description=body.description.strip(),
            lat=body.lat,
            lon=body.lon,
            accuracy_m=body.accuracy_m,
            image_url=f"/api/citizen-reports/{report_id}/image",
            image_mime_type=image.mime_type,
            image_width=image.width,
            image_height=image.height,
            image_size_bytes=len(image.data),
            quality_score=quality,
            relevance_score=relevance,
            severity=severity,
            classification_source=source,
            classification_reasoning=reasoning,
            duplicate_of=duplicate_of,
            hotspot_count=hotspot_count,
            forecast_next_7_days=forecast_next_7_days,
            current_aoi_max_p_fail=aoi_max_p_fail,
            urgency_score=urgency,
            recommendation=recommendation,
            created_at=now,
            updated_at=now,
            agent_traces=traces,
        )
        return self.store.save(report, image.data, image.extension)

    async def _classify(self, body: CitizenReportSubmit, image: DecodedImage) -> dict:
        if self.api_key:
            result = await self._classify_with_nvidia(body, image)
            if result is not None:
                return result
        return _fallback_classification(body)

    async def _classify_with_nvidia(self, body: CitizenReportSubmit, image: DecodedImage) -> dict | None:
        prompt = (
            "Inspect this citizen-submitted landslide-hazard photo. Return JSON only with keys "
            "category, severity, relevance_score, reasoning. category must be one of: "
            f"{', '.join(CATEGORY_KEYWORDS)}. severity is 1-5. relevance_score is 0-1. "
            "Reject unrelated/spam imagery with low relevance. Do not infer an exact landslide time. "
            f"Citizen selected {body.category}. Note: {body.description or '(none)'}"
        )
        encoded = base64.b64encode(image.data).decode("ascii")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{image.mime_type};base64,{encoded}"},
                                    },
                                ],
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 300,
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                match = re.search(r"\{.*\}", content, flags=re.DOTALL)
                parsed = json.loads(match.group(0) if match else content)
                category = parsed.get("category")
                if category not in CATEGORY_KEYWORDS:
                    return None
                return {
                    "category": category,
                    "severity": max(1, min(5, int(parsed.get("severity", 3)))),
                    "relevance_score": round(max(0.0, min(1.0, float(parsed.get("relevance_score", 0.5)))), 3),
                    "reasoning": str(parsed.get("reasoning") or "Vision model classification."),
                    "source": "nvidia",
                }
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return None


def _fallback_classification(body: CitizenReportSubmit) -> dict:
    text = body.description.lower()
    category = body.category
    for candidate, keywords in CATEGORY_KEYWORDS.items():
        if keywords and any(keyword in text for keyword in keywords):
            category = candidate
            break
    severe_words = ("urgent", "collapsed", "people trapped", "impassable", "large crack", "active rockfall")
    mild_words = ("small", "minor", "hairline", "slow seepage")
    severity = 5 if any(word in text for word in severe_words) else 2 if any(word in text for word in mild_words) else 3
    relevance = 0.78 if category != "Other" else (0.5 if text else 0.25)
    return {
        "category": category,
        "severity": severity,
        "relevance_score": relevance,
        "reasoning": "NVIDIA vision was unavailable; deterministic category and hazard-language checks were used.",
        "source": "fallback",
    }


def _inside_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def _find_duplicate(
    reports: list[CitizenReport],
    category: CitizenReportCategory,
    lat: float,
    lon: float,
    now: datetime,
) -> CitizenReport | None:
    candidates = [
        report
        for report in reports
        if report.category == category
        and report.status not in {"actioned", "dismissed"}
        and report.created_at >= now - timedelta(hours=72)
        and _haversine_km(lat, lon, report.lat, report.lon) <= 0.25
    ]
    return min(candidates, key=lambda report: _haversine_km(lat, lon, report.lat, report.lon), default=None)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _urgency_score(
    *,
    severity: int,
    relevance: float,
    quality: float,
    hotspot_count: int,
    aoi_max_p_fail: float | None,
    duplicate: bool,
) -> int:
    score = severity * 10
    score += round(relevance * 12)
    score += round(quality * 8)
    score += min(15, max(0, hotspot_count - 1) * 3)
    if aoi_max_p_fail is not None:
        score += round(aoi_max_p_fail * 20)
    if duplicate:
        score -= 8
    return max(0, min(100, score))


def _recommendation(
    category: CitizenReportCategory,
    urgency: int,
    quality: float,
    relevance: float,
    duplicate_of: str | None,
    hotspot_count: int,
) -> str:
    if relevance < 0.35 or quality < 0.25:
        return "Hold for manual evidence review; the photo quality or hazard relevance is too low for operational use."
    if duplicate_of:
        return f"Link this evidence to {duplicate_of} and verify whether conditions have worsened before dispatching another team."
    if urgency >= 70:
        action = "restrict access and dispatch an immediate field verification"
        if category == "Blocked road":
            action = "verify the closure immediately and update DDMA routing/road-isolation inputs"
        return f"High-priority DDMA review: {action}. Human authorisation is required before public action."
    if urgency >= 45 or hotspot_count >= 4:
        return "Prioritise field verification during the current operational shift and compare the location with the live risk map."
    return "Acknowledge the citizen report and queue it for routine field verification; do not alter alerts until an officer confirms it."
