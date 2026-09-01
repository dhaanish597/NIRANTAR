"""Static exposure contract — real village/shelter points for the map's spatial layers.

`VillageIsolation`/`SettlementPriority` (schemas/impact.py) carry a village's RISK, not its
location — `village_id`/name/population live there per-tick, but no lat/lon. The real point comes
from `data/static/<aoi>/exposure.gpkg` (scripts/fetch_exposure.py, task 1.3), which nothing has
served to the frontend before now. This is deliberately a SEPARATE, static, cacheable endpoint
rather than added fields on the per-tick schemas: exposure geometry does not change tick to tick,
so it does not belong in the websocket payload every frame re-sends (see api/routes.py's
`get_aoi_exposure` route docstring for the full rationale).

`village_id` here uses the exact same `f"v_{osm_id}"` convention `impact/priority.py` and
`impact/isolation.py` already use, so the frontend can join this against `TickResult.priorities`/
`TickResult.isolations` by `village_id` with no translation.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class VillageExposure(BaseModel):
    village_id: str
    name: str
    lat: float
    lon: float
    population_worldpop_est: float | None = None
    osm_population: int | None = None


class ShelterExposure(BaseModel):
    shelter_id: str
    name: str
    amenity: str | None = None
    lat: float
    lon: float


class AoiExposure(BaseModel):
    aoi_id: str
    villages: list[VillageExposure] = Field(default_factory=list)
    shelters: list[ShelterExposure] = Field(default_factory=list)
