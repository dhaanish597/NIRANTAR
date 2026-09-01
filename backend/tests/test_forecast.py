from datetime import datetime, timezone

from app.risk.forecast import build_forecast, forecast_dates
from app.schemas.forecast import RiskForecast


def test_forecast_has_five_consecutive_local_dates_across_year_boundary():
    now = datetime(2026, 12, 31, 18, 30, tzinfo=timezone.utc)
    dates = forecast_dates(now)
    assert len(dates) == 5
    assert [item.isoformat() for item in dates] == [
        "2027-01-01", "2027-01-02", "2027-01-03", "2027-01-04", "2027-01-05"
    ]


def test_forecast_contract_is_exactly_five_and_deterministic_without_tick():
    now = datetime(2026, 2, 27, 12, tzinfo=timezone.utc)
    first = build_forecast("aizawl", "Aizawl, Mizoram", None, now=now)
    second = build_forecast("aizawl", "Aizawl, Mizoram", None, now=now)
    assert len(first.forecast) == 5
    assert first.forecast[0].date.isoformat() == "2026-02-27"
    assert [day.date for day in first.forecast] == [day.date for day in second.forecast]
    assert [day.risk_probability for day in first.forecast] == [day.risk_probability for day in second.forecast]
    assert RiskForecast.model_validate(first.model_dump())
    assert first.source == "FALLBACK"
