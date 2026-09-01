from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from app.core.clock import Clock, LiveClock
from app.schemas.commander import SavedRoutePlan, SavedRoutePlanCreate


class CommanderStore:
    def __init__(
        self,
        path: str | Path = "data/commander.sqlite3",
        *,
        clock: Clock | None = None,
    ):
        self.path = Path(path)
        self.clock = clock or LiveClock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS saved_route_plans (id TEXT PRIMARY KEY, name TEXT NOT NULL, aoi_id TEXT NOT NULL, village_id TEXT NOT NULL, routes_json TEXT NOT NULL, created_at TEXT NOT NULL)")

    def save(self, plan: SavedRoutePlanCreate) -> SavedRoutePlan:
        created_at = self.clock.now()
        identity = json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        plan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{created_at.isoformat()}:{identity}"))
        result = SavedRoutePlan(id=plan_id, created_at=created_at, **plan.model_dump())
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO saved_route_plans VALUES (?, ?, ?, ?, ?, ?)", (result.id, result.name, result.aoi_id, result.village_id, json.dumps([x.model_dump(mode='json') for x in result.routes]), result.created_at.isoformat()))
        return result

    def list(self) -> list[SavedRoutePlan]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT id, name, aoi_id, village_id, routes_json, created_at FROM saved_route_plans ORDER BY created_at DESC").fetchall()
        return [SavedRoutePlan(id=row[0], name=row[1], aoi_id=row[2], village_id=row[3], routes=json.loads(row[4]), created_at=row[5]) for row in rows]
