"""Tests for api/ratelimit.py — the per-client limiter guarding the two endpoints that cost real
money or real CPU (`POST /api/commander/chat`, `POST /api/citizen-reports`).

Written for the first real deployment: the NVIDIA key is deployed to a publicly-reachable
backend, so "the limiter works" is a claim that has to be proven, not assumed. Everything here is
pure in-memory logic — no network, no data files — so it runs on a fresh checkout.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.api import ratelimit
from app.api.ratelimit import (
    SlidingWindowLimiter,
    client_identifier,
    get_limiter,
    rate_limit,
    reset_limiters,
)

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def make_limiter(limit: int = 3, window_seconds: float = 60.0) -> SlidingWindowLimiter:
    return SlidingWindowLimiter(
        limit=limit, window_seconds=window_seconds, max_tracked_clients=8
    )


# -------------------------------------------------------------------------------------------------
# SlidingWindowLimiter
# -------------------------------------------------------------------------------------------------


def test_allows_exactly_the_limit_then_rejects():
    limiter = make_limiter(limit=3)

    for i in range(3):
        allowed, retry_after = limiter.check("client-a", T0 + timedelta(seconds=i))
        assert allowed is True, f"request {i + 1} of 3 should have been allowed"
        assert retry_after == 0.0

    allowed, retry_after = limiter.check("client-a", T0 + timedelta(seconds=3))
    assert allowed is False
    assert retry_after > 0


def test_limits_are_per_client_not_global():
    """The whole point of keying by client: one abusive caller must not lock out everyone else."""
    limiter = make_limiter(limit=2)

    assert limiter.check("abuser", T0)[0] is True
    assert limiter.check("abuser", T0)[0] is True
    assert limiter.check("abuser", T0)[0] is False

    # A different client, same instant, is unaffected.
    assert limiter.check("villager", T0)[0] is True
    assert limiter.check("villager", T0)[0] is True


def test_window_slides_rather_than_resetting_on_a_fixed_boundary():
    """A fixed-window limiter would let 2x the quota through across a boundary. This one must not:
    with limit=2/60s, hits at t=0 and t=59 are still both in the window at t=60."""
    limiter = make_limiter(limit=2, window_seconds=60.0)

    assert limiter.check("c", T0)[0] is True
    assert limiter.check("c", T0 + timedelta(seconds=59))[0] is True
    # t=60: the t=0 hit is exactly at the cutoff (inclusive) and has expired, but t=59 has not.
    assert limiter.check("c", T0 + timedelta(seconds=60))[0] is True
    assert limiter.check("c", T0 + timedelta(seconds=60))[0] is False


def test_full_quota_recovers_after_the_window_passes():
    limiter = make_limiter(limit=2, window_seconds=30.0)

    assert limiter.check("c", T0)[0] is True
    assert limiter.check("c", T0)[0] is True
    assert limiter.check("c", T0)[0] is False

    assert limiter.check("c", T0 + timedelta(seconds=31))[0] is True


def test_a_rejected_request_does_not_extend_the_penalty():
    """Hammering while blocked must not push the recovery time further out — otherwise a client
    that retries politely-but-often never recovers, and `Retry-After` would be a lie."""
    limiter = make_limiter(limit=1, window_seconds=60.0)

    assert limiter.check("c", T0)[0] is True

    first_retry_after = limiter.check("c", T0 + timedelta(seconds=10))[1]
    later_retry_after = limiter.check("c", T0 + timedelta(seconds=40))[1]

    # Blocked at t=10 -> the t=0 hit frees a slot at t=60, so 50s remain.
    assert first_retry_after == pytest.approx(50.0)
    # Blocked at t=40 -> 20s remain. Strictly less: the deadline is fixed, it does not move.
    assert later_retry_after == pytest.approx(20.0)
    assert later_retry_after < first_retry_after

    # And the slot really is free once the deadline passes.
    assert limiter.check("c", T0 + timedelta(seconds=60))[0] is True


def test_retry_after_is_never_negative():
    limiter = make_limiter(limit=1, window_seconds=60.0)
    assert limiter.check("c", T0)[0] is True
    # A clock that jumped backwards must not produce a negative Retry-After header.
    allowed, retry_after = limiter.check("c", T0 - timedelta(seconds=5))
    assert allowed is False
    assert retry_after >= 0.0


def test_tracked_clients_stay_bounded():
    """A spray of distinct keys (e.g. forged X-Forwarded-For values) must not grow memory without
    limit on a 512 MB free instance."""
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60.0, max_tracked_clients=4)

    for i in range(50):
        limiter.check(f"spoofed-{i}", T0 + timedelta(seconds=i))

    assert len(limiter._hits) <= 4


def test_eviction_never_blocks_a_new_client():
    """Eviction forgets history; it must never cause a first-time caller to be rejected."""
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60.0, max_tracked_clients=2)

    for i in range(10):
        allowed, _ = limiter.check(f"client-{i}", T0 + timedelta(seconds=i))
        assert allowed is True, f"client-{i} was rejected on its first request"


def test_an_evicted_client_is_forgiven_not_punished():
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60.0, max_tracked_clients=2)

    assert limiter.check("a", T0)[0] is True
    assert limiter.check("a", T0)[0] is False  # a is now blocked

    # Push a and b out of the tracking table with fresh clients.
    for i in range(5):
        limiter.check(f"filler-{i}", T0 + timedelta(seconds=i))

    # "a" was evicted, so its history is gone — it gets a clean slate rather than staying blocked.
    assert limiter.check("a", T0 + timedelta(seconds=10))[0] is True


def test_reset_clears_history():
    limiter = make_limiter(limit=1)
    assert limiter.check("c", T0)[0] is True
    assert limiter.check("c", T0)[0] is False
    limiter.reset()
    assert limiter.check("c", T0)[0] is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0, "window_seconds": 60.0, "max_tracked_clients": 8},
        {"limit": -1, "window_seconds": 60.0, "max_tracked_clients": 8},
        {"limit": 1, "window_seconds": 0.0, "max_tracked_clients": 8},
        {"limit": 1, "window_seconds": -5.0, "max_tracked_clients": 8},
        {"limit": 1, "window_seconds": 60.0, "max_tracked_clients": 0},
    ],
)
def test_invalid_construction_is_rejected_loudly(kwargs):
    """A misconfigured limiter that silently allows everything (limit=0 -> "0 >= 0" -> always
    blocked; or a nonsense window) is worse than a crash at startup."""
    with pytest.raises(ValueError):
        SlidingWindowLimiter(**kwargs)


# -------------------------------------------------------------------------------------------------
# client_identifier
# -------------------------------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None, host: str | None = "10.0.0.1") -> None:
        self.headers = headers or {}
        self.client = _FakeClient(host) if host is not None else None


def test_client_identifier_prefers_the_rightmost_forwarded_hop():
    """Render appends the address it actually saw; anything to its left is caller-supplied and
    forgeable. Reading from the left (the common copy-paste) would make this limit bypassable."""
    request = _FakeRequest({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert client_identifier(request) == "203.0.113.9"


def test_client_identifier_tolerates_whitespace_and_empty_hops():
    request = _FakeRequest({"x-forwarded-for": " 1.2.3.4 ,, 203.0.113.9 ,"})
    assert client_identifier(request) == "203.0.113.9"


def test_client_identifier_falls_back_to_the_socket_peer():
    """Local dev and tests send no X-Forwarded-For at all."""
    assert client_identifier(_FakeRequest({})) == "10.0.0.1"
    assert client_identifier(_FakeRequest({"x-forwarded-for": "   "})) == "10.0.0.1"


def test_client_identifier_survives_a_missing_peer():
    """TestClient can present no client at all; that must be a key, not a crash."""
    assert client_identifier(_FakeRequest({}, host=None)) == "unknown"


# -------------------------------------------------------------------------------------------------
# Dependency wiring over real HTTP
# -------------------------------------------------------------------------------------------------


def build_app(bucket: str = "commander_chat") -> FastAPI:
    app = FastAPI()

    @app.post("/probe")
    async def probe(request: Request, _limit: None = Depends(rate_limit(bucket))):
        return {"ok": True}

    return app


def test_dependency_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_COMMANDER_CHAT_MAX", 2)
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_COMMANDER_CHAT_WINDOW_SECONDS", 60.0)
    reset_limiters()
    try:
        with TestClient(build_app()) as client:
            assert client.post("/probe").status_code == 200
            assert client.post("/probe").status_code == 200

            response = client.post("/probe")
            assert response.status_code == 429
            # A Retry-After a caller can act on, not just a bare rejection.
            assert int(response.headers["retry-after"]) >= 1
            assert "Rate limit exceeded" in response.json()["detail"]
    finally:
        reset_limiters()


def test_dependency_does_not_leak_between_buckets(monkeypatch):
    """Exhausting the commander budget must not block citizen photo uploads — two separate
    features with separate costs."""
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_COMMANDER_CHAT_MAX", 1)
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_CITIZEN_REPORT_MAX", 5)
    reset_limiters()
    try:
        with TestClient(build_app("commander_chat")) as client:
            assert client.post("/probe").status_code == 200
            assert client.post("/probe").status_code == 429

        with TestClient(build_app("citizen_report")) as client:
            assert client.post("/probe").status_code == 200
    finally:
        reset_limiters()


def test_master_switch_disables_limiting(monkeypatch):
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_COMMANDER_CHAT_MAX", 1)
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_ENABLED", False)
    reset_limiters()
    try:
        with TestClient(build_app()) as client:
            for _ in range(5):
                assert client.post("/probe").status_code == 200
    finally:
        reset_limiters()


def test_get_limiter_rejects_an_unknown_bucket():
    """A typo'd bucket name must fail at import/review time, not silently create an unlimited
    endpoint (which is exactly the failure this module exists to prevent)."""
    with pytest.raises(KeyError, match="unknown rate-limit bucket"):
        get_limiter("commnder_chat")


def test_get_limiter_is_a_singleton_per_bucket():
    reset_limiters()
    try:
        assert get_limiter("commander_chat") is get_limiter("commander_chat")
        assert get_limiter("commander_chat") is not get_limiter("citizen_report")
    finally:
        reset_limiters()


def test_get_limiter_uses_configured_values(monkeypatch):
    """Guards the bucket wiring itself: if the registry swapped two numbers, the deployment would
    enforce a limit nobody chose."""
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_CITIZEN_REPORT_MAX", 7)
    monkeypatch.setattr(ratelimit.app_config, "RATE_LIMIT_CITIZEN_REPORT_WINDOW_SECONDS", 120.0)
    reset_limiters()
    try:
        limiter = get_limiter("citizen_report")
        assert limiter.limit == 7
        assert limiter.window_seconds == 120.0
    finally:
        reset_limiters()


# -------------------------------------------------------------------------------------------------
# The guards are actually attached to the real routes
# -------------------------------------------------------------------------------------------------


def _iter_routes(app: FastAPI):
    """Flatten every real route in the app.

    `app.routes` alone is not enough in this FastAPI version: `include_router` wraps each router
    in an `_IncludedRouter` shim that has no `.path` and no `.dependant`, so the two routers this
    module cares about are invisible to a naive walk (they still resolve fine through
    `app.openapi()`, which is why that route table looked complete in the audit). Recursing into
    `original_router.routes` reaches the actual `APIRoute`s.
    """
    stack = list(app.routes)
    while stack:
        route = stack.pop()
        inner = getattr(route, "original_router", None)
        if inner is not None:
            stack.extend(getattr(inner, "routes", []))
        else:
            yield route


def _dependency_qualnames(route) -> set[str]:
    """Every callable in a route's dependency tree, by qualified name.

    Returns an empty set for routes that carry no dependency tree at all — FastAPI's own
    `/openapi.json`, `/docs` and `/redoc` are plain Starlette `Route`s with no `.dependant`.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set()

    names: set[str] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        if current.call is not None:
            names.add(getattr(current.call, "__qualname__", str(current.call)))
        stack.extend(current.dependencies)
    return names


def _route(app: FastAPI, path: str, method: str):
    for route in _iter_routes(app):
        if getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"no {method.upper()} route for {path}")


def test_expensive_routes_carry_a_rate_limit_dependency():
    """The unit tests above prove the limiter works; this proves it is WIRED UP. Asserted against
    the real dependency tree (not just the OpenAPI annotation), so deleting a `Depends(...)` line
    fails here instead of leaving every other test in this file green."""
    from app.main import create_app

    # realtime=False and no lifespan run: we only inspect the route table, never serve a request.
    app = create_app(realtime=False)

    expected = {
        "/api/commander/chat": "post",
        "/api/citizen-reports": "post",
    }
    for path, method in expected.items():
        qualnames = _dependency_qualnames(_route(app, path, method))
        assert any("rate_limit" in name for name in qualnames), (
            f"{method.upper()} {path} has no rate_limit dependency in its tree "
            f"(found: {sorted(qualnames)})"
        )
        # And the 429 it can raise is documented for clients.
        operation = app.openapi()["paths"][path][method]
        assert "429" in operation["responses"]


def test_rate_limited_routes_are_the_only_ones_with_a_rate_limit():
    """Limiting is a deliberate, narrow decision (see the module docstring) — a stray
    `Depends(rate_limit(...))` on a cheap read-only route would add a demo failure mode for no
    benefit, and would show up here."""
    from app.main import create_app

    app = create_app(realtime=False)
    limited = set()
    for route in _iter_routes(app):
        methods = getattr(route, "methods", None) or set()
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            if any("rate_limit" in name for name in _dependency_qualnames(route)):
                limited.add((route.path, method.lower()))

    assert limited == {
        ("/api/commander/chat", "post"),
        ("/api/citizen-reports", "post"),
    }
