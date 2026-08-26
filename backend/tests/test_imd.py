"""Contract test for ingest/live/imd.py's pure logic and circuit breaker (BUILD_PLAN.md task
1.8). No real network access — api.imd.gov.in was unreachable from this sandboxed environment
this session, and IMD API access has not been granted for this project at all yet (see the
module's own docstring and Required_by_me.md) — so this exercises everything that CAN be verified
without it: response-envelope parsing against recorded fixtures, district record matching,
format-mismatch detection, and the circuit breaker's state machine end to end.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "app" / "ingest" / "live" / "imd.py"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
NOWCAST_FIXTURE = FIXTURES_DIR / "imd_districtnowcast_response.json"
WARNING_FIXTURE = FIXTURES_DIR / "imd_districtwarning_response.json"


def _load_imd():
    spec = importlib.util.spec_from_file_location("app.ingest.live.imd", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.ingest.live.imd"] = module
    spec.loader.exec_module(module)
    return module


imd = _load_imd()

T0 = datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc)


def test_module_exists():
    assert SCRIPT_PATH.is_file()


def test_recorded_fixtures_exist():
    assert NOWCAST_FIXTURE.is_file()
    assert WARNING_FIXTURE.is_file()


class TestBuildAuthHeaders:
    def test_returns_a_header_dict_carrying_the_key(self):
        headers = imd.build_auth_headers("secret123")
        assert "secret123" in headers.values()


class TestExtractRecords:
    def test_bare_array(self):
        records = imd.extract_records([{"Station": "Aizawl"}])
        assert records == [{"Station": "Aizawl"}]

    def test_envelope_with_data_list(self):
        payload = {"status": "Success", "data": [{"Station": "Aizawl"}, {"Station": "Lunglei"}]}
        assert len(imd.extract_records(payload)) == 2

    def test_envelope_with_single_data_dict(self):
        payload = {"status": "Success", "data": {"Station": "Aizawl"}}
        assert imd.extract_records(payload) == [{"Station": "Aizawl"}]

    def test_bare_single_record_dict(self):
        payload = {"District": "Aizawl", "Date": "2026-08-26"}
        assert imd.extract_records(payload) == [payload]

    def test_recorded_nowcast_fixture_parses_to_three_records(self):
        payload = json.loads(NOWCAST_FIXTURE.read_text())
        assert len(imd.extract_records(payload)) == 3

    def test_unrecognized_envelope_raises_format_error(self):
        with pytest.raises(imd.IMDResponseFormatError):
            imd.extract_records({"totally": "unexpected"})

    def test_non_dict_non_list_raises_format_error(self):
        with pytest.raises(imd.IMDResponseFormatError):
            imd.extract_records("just a string, not real JSON structure")


class TestResolveDistrictName:
    def test_uses_configured_name_when_set(self):
        from app.config import AoiConfig

        aoi = AoiConfig(
            id="x", name="Somewhere, State", center_lat=0, center_lon=0,
            bbox=(0, 0, 1, 1), utm_epsg=32646, imd_district_name="Configured Name",
        )
        assert imd.resolve_district_name(aoi) == "Configured Name"

    def test_derives_from_aoi_name_when_unset(self):
        from app.config import AoiConfig

        aoi = AoiConfig(
            id="x", name="Aizawl, Mizoram", center_lat=0, center_lon=0,
            bbox=(0, 0, 1, 1), utm_epsg=32646,
        )
        assert imd.resolve_district_name(aoi) == "Aizawl"


class TestParseDistrictNowcast:
    @pytest.fixture
    def records(self):
        return imd.extract_records(json.loads(NOWCAST_FIXTURE.read_text()))

    def test_finds_matching_district_case_insensitively(self, records):
        record = imd.parse_district_nowcast(records, "aizawl")
        assert record is not None
        assert record["Station"] == "Aizawl"
        assert record["color"] == "3"

    def test_returns_none_for_unmatched_district_not_an_error(self, records):
        assert imd.parse_district_nowcast(records, "Not A Real District") is None

    def test_missing_required_field_raises_format_error(self):
        records = [{"Station": "Aizawl", "Date": "2026-08-26"}]  # missing message/color
        with pytest.raises(imd.IMDResponseFormatError, match="missing expected field"):
            imd.parse_district_nowcast(records, "Aizawl")


class TestParseDistrictWarning:
    @pytest.fixture
    def records(self):
        return imd.extract_records(json.loads(WARNING_FIXTURE.read_text()))

    def test_finds_matching_district(self, records):
        record = imd.parse_district_warning(records, "Aizawl")
        assert record is not None
        assert record["Day_1"] == "3"

    def test_returns_none_for_unmatched_district(self, records):
        assert imd.parse_district_warning(records, "Nowhereland") is None

    def test_missing_required_field_raises_format_error(self):
        records = [{"District": "Aizawl"}]  # missing Date/Day_1
        with pytest.raises(imd.IMDResponseFormatError, match="missing expected field"):
            imd.parse_district_warning(records, "Aizawl")


class TestFetchDistrictFunctions:
    def test_fetch_district_nowcast_end_to_end_against_fixture(self, monkeypatch):
        payload = json.loads(NOWCAST_FIXTURE.read_text())

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(imd.requests, "get", lambda url, headers, timeout: FakeResponse())
        result = imd.fetch_district_nowcast("Aizawl", "fake-key")
        assert result["Station"] == "Aizawl"

    def test_fetch_district_warning_end_to_end_against_fixture(self, monkeypatch):
        payload = json.loads(WARNING_FIXTURE.read_text())

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return payload

        monkeypatch.setattr(imd.requests, "get", lambda url, headers, timeout: FakeResponse())
        result = imd.fetch_district_warning("Aizawl", "fake-key")
        assert result["District"] == "Aizawl"

    def test_http_error_propagates_as_request_exception(self, monkeypatch):
        class FakeResponse:
            def raise_for_status(self):
                raise imd.requests.HTTPError("503 Service Unavailable")

        monkeypatch.setattr(imd.requests, "get", lambda url, headers, timeout: FakeResponse())
        with pytest.raises(imd.requests.HTTPError):
            imd.fetch_district_nowcast("Aizawl", "fake-key")


class TestCircuitBreaker:
    def test_starts_closed(self):
        breaker = imd.CircuitBreaker()
        assert breaker.state(T0) == imd.CircuitState.CLOSED
        assert breaker.allow_request(T0) is True

    def test_opens_after_threshold_consecutive_failures(self):
        breaker = imd.CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        breaker.record_failure(T0)
        assert breaker.state(T0) == imd.CircuitState.CLOSED
        breaker.record_failure(T0)
        assert breaker.state(T0) == imd.CircuitState.CLOSED
        breaker.record_failure(T0)
        assert breaker.state(T0) == imd.CircuitState.OPEN
        assert breaker.allow_request(T0) is False

    def test_success_resets_failure_count(self):
        breaker = imd.CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        breaker.record_failure(T0)
        breaker.record_failure(T0)
        breaker.record_success()
        breaker.record_failure(T0)
        # Only 1 consecutive failure since the reset — must still be closed.
        assert breaker.state(T0) == imd.CircuitState.CLOSED

    def test_transitions_to_half_open_after_cooldown(self):
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        breaker.record_failure(T0)
        assert breaker.state(T0) == imd.CircuitState.OPEN
        just_before = T0 + timedelta(seconds=59)
        assert breaker.state(just_before) == imd.CircuitState.OPEN
        just_after = T0 + timedelta(seconds=60)
        assert breaker.state(just_after) == imd.CircuitState.HALF_OPEN
        assert breaker.allow_request(just_after) is True

    def test_half_open_failure_reopens_and_restarts_cooldown(self):
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        breaker.record_failure(T0)
        half_open_at = T0 + timedelta(seconds=60)
        assert breaker.state(half_open_at) == imd.CircuitState.HALF_OPEN
        breaker.record_failure(half_open_at)  # the half-open trial fails
        assert breaker.state(half_open_at) == imd.CircuitState.OPEN
        # Cooldown restarted from half_open_at, not from the original T0.
        assert breaker.state(half_open_at + timedelta(seconds=59)) == imd.CircuitState.OPEN
        assert breaker.state(half_open_at + timedelta(seconds=60)) == imd.CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        breaker.record_failure(T0)
        half_open_at = T0 + timedelta(seconds=60)
        assert breaker.state(half_open_at) == imd.CircuitState.HALF_OPEN
        breaker.record_success()
        assert breaker.state(half_open_at) == imd.CircuitState.CLOSED

    def test_rejects_invalid_construction_args(self):
        with pytest.raises(ValueError):
            imd.CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError):
            imd.CircuitBreaker(cooldown_seconds=0)


class TestCallWithBreaker:
    def test_success_passes_through_and_records_success(self):
        breaker = imd.CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
        result = imd.call_with_breaker(breaker, T0, lambda: "ok")
        assert result == "ok"
        assert breaker.state(T0) == imd.CircuitState.CLOSED

    def test_none_result_counts_as_success_not_failure(self):
        """A well-formed-but-empty result (e.g. our district wasn't in today's response) must NOT
        trip the breaker — see call_with_breaker's own docstring on why this matters."""
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        result = imd.call_with_breaker(breaker, T0, lambda: None)
        assert result is None
        assert breaker.state(T0) == imd.CircuitState.CLOSED

    def test_request_exception_wrapped_and_recorded_as_failure(self):
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)

        def boom():
            raise imd.requests.ConnectionError("refused")

        with pytest.raises(imd.IMDUnavailableError):
            imd.call_with_breaker(breaker, T0, boom)
        assert breaker.state(T0) == imd.CircuitState.OPEN

    def test_format_error_wrapped_and_recorded_as_failure(self):
        """This is the task's own headline requirement: a WRONG FORMAT must open the breaker
        (fail closed) rather than being silently accepted."""
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)

        def bad_format():
            raise imd.IMDResponseFormatError("totally wrong shape")

        with pytest.raises(imd.IMDUnavailableError):
            imd.call_with_breaker(breaker, T0, bad_format)
        assert breaker.state(T0) == imd.CircuitState.OPEN

    def test_open_breaker_skips_the_call_entirely(self):
        breaker = imd.CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        breaker.record_failure(T0)
        assert breaker.state(T0) == imd.CircuitState.OPEN

        calls = []

        def should_not_run():
            calls.append(1)
            return "should not get here"

        with pytest.raises(imd.IMDUnavailableError, match="circuit breaker open"):
            imd.call_with_breaker(breaker, T0, should_not_run)
        assert calls == []  # fn() was never even invoked — no network call attempted

    def test_full_degrade_and_recover_cycle_against_fixture_and_fake_transport(self, monkeypatch):
        """End-to-end: repeated real (fake-transport) failures open the breaker; while open, no
        network call is attempted at all; after cooldown + a successful retry, service resumes."""
        breaker = imd.CircuitBreaker(failure_threshold=2, cooldown_seconds=100)
        call_count = {"n": 0}

        def flaky_get(url, headers, timeout):
            call_count["n"] += 1
            raise imd.requests.ConnectionError("simulated IP-whitelisting friction")

        monkeypatch.setattr(imd.requests, "get", flaky_get)

        for _ in range(2):
            with pytest.raises(imd.IMDUnavailableError):
                imd.call_with_breaker(
                    breaker, T0, lambda: imd.fetch_district_nowcast("Aizawl", "key")
                )
        assert breaker.state(T0) == imd.CircuitState.OPEN
        assert call_count["n"] == 2

        # While open: further ticks must not even attempt the network call.
        with pytest.raises(imd.IMDUnavailableError, match="circuit breaker open"):
            imd.call_with_breaker(breaker, T0 + timedelta(seconds=1), lambda: imd.fetch_district_nowcast("Aizawl", "key"))
        assert call_count["n"] == 2  # unchanged

        # After cooldown, service recovers (transport fixed) -> half-open trial succeeds -> closed.
        payload = json.loads(NOWCAST_FIXTURE.read_text())

        def healthy_get(url, headers, timeout):
            call_count["n"] += 1

            class FakeResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return payload

            return FakeResponse()

        monkeypatch.setattr(imd.requests, "get", healthy_get)
        recovered_at = T0 + timedelta(seconds=100)
        result = imd.call_with_breaker(
            breaker, recovered_at, lambda: imd.fetch_district_nowcast("Aizawl", "key")
        )
        assert result["Station"] == "Aizawl"
        assert breaker.state(recovered_at) == imd.CircuitState.CLOSED
