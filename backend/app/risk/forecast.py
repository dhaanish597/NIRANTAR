"""Five-day forecast adapter over the current risk/impact snapshot.

There is no forward rainfall provider in the running application yet. Until one is wired in,
this adapter deliberately labels its deterministic rainfall outlook FALLBACK. It preserves the
latest spatial risk snapshot and evolves it with a smooth, date-seeded rainfall outlook; a future
weather adapter can replace ``rainfall_outlook`` without changing the API or frontend.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.clock import LiveClock
from app.schemas.forecast import ForecastArea, RiskForecast, RiskForecastDay
from app.schemas.impact import RoadSegmentRisk, SettlementPriority, VillageIsolation
from app.schemas.risk import CellRisk
from app.schemas.tick import TickResult

FORECAST_TIMEZONE = ZoneInfo("Asia/Kolkata")
_RAINFALL_TREND = (1.0, 1.14, 0.96, 0.74, 0.56)


def forecast_dates(now: datetime | None = None) -> list[date]:
    current = (now or LiveClock().now()).astimezone(FORECAST_TIMEZONE).date()
    return [current + timedelta(days=offset) for offset in range(5)]


def _label(day: date, offset: int) -> str:
    return ("Today" if offset == 0 else "Tomorrow" if offset == 1 else day.strftime("%a")).upper()


def _level(probability: float) -> str:
    if probability >= 0.75:
        return "VERY HIGH"
    if probability >= 0.5:
        return "HIGH"
    if probability >= 0.25:
        return "MODERATE"
    return "LOW"


def _base_rainfall(tick: TickResult | None) -> float:
    if not tick or not tick.cell_risks:
        return 4.0
    # Threshold exceedance is the current pipeline's rainfall-derived signal. A modest daily
    # rainfall proxy keeps the fallback tied to the observed risk rather than a random number.
    return max(1.0, sum(max(0.0, cell.threshold_exceedance) for cell in tick.cell_risks) / len(tick.cell_risks) * 24.0)


def _evolve_cells(cells: list[CellRisk], factor: float) -> list[CellRisk]:
    result = []
    for cell in cells:
        probability = min(1.0, max(0.0, cell.p_fail * (0.72 + 0.28 * factor)))
        result.append(cell.model_copy(update={"p_fail": probability, "confidence": 1.0 - abs(probability - 0.5) * 2}))
    return result


def _evolve_roads(roads: list[RoadSegmentRisk], factor: float) -> list[RoadSegmentRisk]:
    result = []
    for road in roads:
        probability = min(1.0, max(0.0, road.p_blocked * (0.72 + 0.28 * factor)))
        result.append(road.model_copy(update={"p_blocked": probability, "severed": probability >= 0.7}))
    return result


def _evolve_isolations(isolations: list[VillageIsolation], factor: float) -> list[VillageIsolation]:
    return [village.model_copy(update={"p_isolated": min(1.0, village.p_isolated * (0.72 + 0.28 * factor)), "isolated_now": village.p_isolated * (0.72 + 0.28 * factor) >= 0.7}) for village in isolations]


def _evolve_priorities(priorities: list[SettlementPriority], cells: list[CellRisk]) -> list[SettlementPriority]:
    risk = max((cell.p_fail for cell in cells), default=0.0)
    return [
        priority.model_copy(
            update={
                "eps": min(
                    1.0,
                    max(0.0, priority.eps - priority.components.get("p_fail", 0.0) * 0.35 + risk * 0.35),
                )
            }
        )
        for priority in priorities
    ]


def build_forecast(location_id: str, location: str, tick: TickResult | None, *, now: datetime | None = None) -> RiskForecast:
    dates = forecast_dates(now)
    base_rain = _base_rainfall(tick)
    base_cells = tick.cell_risks if tick else []
    base_roads = tick.road_risks if tick else []
    base_isolations = tick.isolations if tick else []
    base_priorities = tick.priorities if tick else []
    days: list[RiskForecastDay] = []
    for offset, day in enumerate(dates):
        factor = _RAINFALL_TREND[offset]
        cells = _evolve_cells(base_cells, factor)
        roads = _evolve_roads(base_roads, factor)
        isolations = _evolve_isolations(base_isolations, factor)
        priorities = _evolve_priorities(base_priorities, cells)
        probability = max((cell.p_fail for cell in cells), default=min(0.85, 0.18 + 0.12 * factor))
        rainfall = round(base_rain * factor, 1)
        driver = "Heavy rainfall" if factor >= 1.0 else "Antecedent rainfall and terrain susceptibility" if factor >= 0.8 else "High terrain susceptibility"
        explanation = (f"Risk elevated primarily due to forecast rainfall ({rainfall:.1f} mm) and terrain susceptibility." if factor >= 0.8 else f"Risk decreasing as forecast rainfall falls to {rainfall:.1f} mm, while terrain susceptibility persists.")
        areas = [ForecastArea(id=cell.cell_id, name=cell.cell_id, risk_probability=cell.p_fail, risk_level=_level(cell.p_fail)) for cell in cells]
        days.append(RiskForecastDay(date=day, day_label=_label(day, offset), risk_level=_level(probability), risk_probability=probability, rainfall_mm=rainfall, confidence=max((cell.confidence for cell in cells), default=0.45), primary_driver=driver, explanation=explanation, affected_villages=sum(1 for item in isolations if item.p_isolated >= 0.5), affected_road_segments=sum(1 for item in roads if item.p_blocked >= 0.5), cell_risks=cells, road_risks=roads, isolations=isolations, priorities=priorities, areas=areas))
    return RiskForecast(location=location, location_id=location_id, generated_at=(now or LiveClock().now()), source="FALLBACK", forecast=days)
