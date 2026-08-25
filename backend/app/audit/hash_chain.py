"""Pure hashing logic for the audit log's hash chain (BUILD_PLAN.md task 3.6, pulled forward
just enough for Phase 0's one AI_FLAGGED event per tick — see docs/ARCHITECTURE.md §3/§6).

Kept as plain functions, not methods on the stateful log, so the chain math is trivially
unit-testable and deterministic (CLAUDE.md rule 13): same inputs always produce the same hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS_HASH = "0" * 64


def hash_payload(payload: dict[str, Any]) -> str:
    """Deterministic hash of a JSON-serializable payload — sorted keys, no whitespace."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def chain_hash(prev_hash: str, input_hash: str, *, event_id: str, kind: str) -> str:
    """An event's own hash: depends on what came before it plus what makes this event unique."""
    canonical = f"{prev_hash}:{input_hash}:{event_id}:{kind}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
