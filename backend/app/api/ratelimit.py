"""Per-client request limiting for the two endpoints that cost real money or real CPU.

**Why this exists.** Until this session the service had only ever run on `localhost`, where an
unthrottled endpoint costs nothing. It is now deployed to a publicly-reachable host with a real
`NVIDIA_API_KEY` in its environment (the user's explicit ruling: *"set ratelimit and then
deploy"*). `POST /api/commander/chat` spends money on every call and `POST /api/citizen-reports`
decodes an attacker-sized base64 body, so both are limited here. Every other route is cheap,
in-process and read-only against data already in memory — limiting those would add a failure mode
to the demo for no benefit, so it is deliberately not done.

**Why in-memory is sound here rather than a shortcut.** The deployment runs a *single* uvicorn
worker (Render free tier, one process — `render.yaml` sets no `--workers`), so one dict in one
process genuinely observes all traffic. A multi-worker or multi-instance deployment would need a
shared store (Redis or the Postgres already in the stack); this module would then keep the same
`check()` contract and swap its backing storage. That change is called out here rather than left
for a future reader to discover by being surprised.

**Honest limitation — this is abuse friction, not a security boundary.** The client key is
derived from `X-Forwarded-For`, which a determined attacker can vary to get a fresh bucket per
request. What this reliably stops is the realistic case: one script or one misbehaving client
hammering the key. A real deployment should additionally set a provider-level (Render/Cloudflare)
rate limit, which is enforced upstream of this process and cannot be spoofed from inside a
request. Both layers are cheap; only one of them is in this file.

CLAUDE.md rule 14 puts the wall clock behind `core/clock.py`, so `check()` takes `now` as an
argument instead of reading a clock itself — the caller (`rate_limit` below) passes
`LiveClock().now()`, which is also what makes the sliding-window logic directly testable.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Callable

from fastapi import HTTPException, Request

from app import config as app_config
from app.core.clock import LiveClock


class SlidingWindowLimiter:
    """Allow at most `limit` requests per `window_seconds` per client key.

    Sliding window (a deque of the timestamps that were allowed), not a fixed bucket: a fixed
    window lets a caller spend the whole quota at the end of one window and the whole quota again
    at the start of the next — 2x the intended rate, exactly at the boundary a script would find.
    The deque is pruned on every call, so a key's memory is bounded by `limit`, not by traffic.
    """

    def __init__(self, *, limit: int, window_seconds: float, max_tracked_clients: int) -> None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit!r}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be > 0, got {window_seconds!r}")
        if max_tracked_clients < 1:
            raise ValueError(f"max_tracked_clients must be >= 1, got {max_tracked_clients!r}")

        self._limit = limit
        self._window = timedelta(seconds=window_seconds)
        self._max_tracked_clients = max_tracked_clients
        self._hits: dict[str, deque[datetime]] = {}
        # A plain Lock, not an asyncio one: `check()` is a pure, microsecond-scale dict/deque
        # operation with no await inside, so holding a thread lock across it cannot stall the
        # event loop in any way an async lock would improve. It also keeps this class usable from
        # sync code (tests, a future non-async caller) without a second implementation.
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def window_seconds(self) -> float:
        return self._window.total_seconds()

    def check(self, key: str, now: datetime) -> tuple[bool, float]:
        """Record one request from `key` at `now`.

        Returns `(allowed, retry_after_seconds)`. On a rejection nothing is recorded, so a caller
        that keeps hammering does not extend its own penalty — the window drains on its original
        schedule and the client recovers `retry_after_seconds` from now, which is what the
        `Retry-After` header promises.
        """
        cutoff = now - self._window
        with self._lock:
            hits = self._hits.get(key)
            if hits is None:
                hits = self._hits[key] = deque()

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self._limit:
                # The oldest surviving hit is the one whose expiry frees the next slot.
                retry_after = (hits[0] + self._window - now).total_seconds()
                return False, max(retry_after, 0.0)

            hits.append(now)
            self._evict_if_over_capacity()
            return True, 0.0

    def _evict_if_over_capacity(self) -> None:
        """Keep the key count bounded. Caller already holds `self._lock`.

        Least-recently-active first: a client that has stopped calling is the cheapest history to
        forget, and forgetting it can only ever *loosen* the limit for that key — it can never
        cause a request to be rejected, so eviction is never a correctness hazard for anyone else.
        """
        if len(self._hits) <= self._max_tracked_clients:
            return
        while len(self._hits) > self._max_tracked_clients:
            oldest_key = min(self._hits, key=lambda k: self._hits[k][-1])
            del self._hits[oldest_key]

    def reset(self) -> None:
        """Forget every recorded hit. Used by tests; safe to call at any time."""
        with self._lock:
            self._hits.clear()


def client_identifier(request: Request) -> str:
    """Best-effort stable identity for the calling client.

    `X-Forwarded-For` is read from the **right**, not the left. Render terminates TLS at exactly
    one trusted proxy hop and appends the address it actually saw, so the rightmost entry is the
    one value in the header a client cannot forge — the leftmost is whatever the caller chose to
    send. (Reading it from the left, the common copy-paste, would make the limit trivially
    bypassable.) A deployment behind a different number of proxy hops must re-derive this; with
    no header at all — local dev, tests, a direct connection — it falls back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if hops:
        return hops[-1]
    client = request.client
    return client.host if client is not None else "unknown"


# Bucket registry: bucket name -> (limit, window_seconds) as configured. Limits are read from
# `app.config` at *call* time rather than captured at import, so a test (or a deployment that
# tunes the env var and restarts nothing) gets a limiter built from the current numbers.
def _bucket_limits() -> dict[str, tuple[int, float]]:
    return {
        "commander_chat": (
            app_config.RATE_LIMIT_COMMANDER_CHAT_MAX,
            app_config.RATE_LIMIT_COMMANDER_CHAT_WINDOW_SECONDS,
        ),
        "citizen_report": (
            app_config.RATE_LIMIT_CITIZEN_REPORT_MAX,
            app_config.RATE_LIMIT_CITIZEN_REPORT_WINDOW_SECONDS,
        ),
    }


_limiters: dict[str, SlidingWindowLimiter] = {}
_limiters_lock = threading.Lock()


def get_limiter(bucket: str) -> SlidingWindowLimiter:
    """The process-wide limiter for `bucket`, created on first use."""
    limits = _bucket_limits()
    try:
        limit, window_seconds = limits[bucket]
    except KeyError as exc:
        raise KeyError(
            f"unknown rate-limit bucket {bucket!r}; known buckets: {sorted(limits)}"
        ) from exc

    with _limiters_lock:
        limiter = _limiters.get(bucket)
        if limiter is None:
            limiter = _limiters[bucket] = SlidingWindowLimiter(
                limit=limit,
                window_seconds=window_seconds,
                max_tracked_clients=app_config.RATE_LIMIT_MAX_TRACKED_CLIENTS,
            )
        return limiter


def reset_limiters() -> None:
    """Drop every cached limiter (tests, or after changing limits at runtime)."""
    with _limiters_lock:
        _limiters.clear()


def rate_limit(bucket: str) -> Callable[[Request], None]:
    """Build a FastAPI dependency enforcing `bucket`'s limit. Use with `Depends(...)`.

    Rejection is a 429 with `Retry-After`, the standard signal — an honest, actionable answer
    ("come back in N seconds") rather than a 403 that reads like a permanent ban.
    """

    def dependency(request: Request) -> None:
        if not app_config.RATE_LIMIT_ENABLED:
            return
        limiter = get_limiter(bucket)
        allowed, retry_after = limiter.check(client_identifier(request), LiveClock().now())
        if allowed:
            return
        # Round up: advertising 0 seconds for a sub-second wait invites an immediate retry that
        # is still refused, which reads as a broken limiter rather than a working one.
        retry_after_seconds = max(1, int(retry_after + 0.999))
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for {bucket} "
                f"({limiter.limit} requests per {limiter.window_seconds:g}s). "
                f"Retry in {retry_after_seconds}s."
            ),
            headers={"Retry-After": str(retry_after_seconds)},
        )

    return dependency
