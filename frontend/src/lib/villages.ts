import type { Feature, FeatureCollection, Point } from 'geojson'
import type { SettlementPriority, VillageExposure, VillageIsolation } from '../types/schemas'

/**
 * BUILD_PLAN.md task 2.7 ("villages rendered as ranked pins from TickResult.priorities").
 *
 * Real village geometry now flows through GET /api/aoi/{id}/exposure (backend/app/impact/
 * exposure.py, backend/app/schemas/exposure.py) — `lib/exposure.ts` fetches it once per AOI and
 * MapView passes it in as `exposureByVillageId` below, which is preferred whenever a village_id
 * has a real match. The deterministic hash-ring position is now ONLY a graceful fallback for the
 * brief window before that fetch resolves (or for a village_id the exposure endpoint genuinely
 * has no record for) — never presented as a real location, and never used once real data has
 * loaded for that village.
 */

export const TIER_COLOR: Record<SettlementPriority['tier'], string> = {
  P1: '#dc2626', // matches RightRail's bg-red-600 tier badge
  P2: '#f97316', // matches RightRail's bg-orange-500 tier badge
  P3: '#64748b', // matches RightRail's bg-slate-600 tier badge
}

const RING_RADIUS_DEG = 0.012 // just outside grid.ts's ~0.021deg-wide 3x3 cell block

/** Deterministic 32-bit FNV-1a hash — same village_id always lands at the same pixel, so pins
 * don't jitter between ticks or reloads. */
function hashString(value: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193)
  }
  return hash >>> 0
}

/** Places a village_id on a ring around the AOI centre, angle and radius both derived from a
 * hash of the id — deterministic, spread out, and outside the cell grid's footprint. Exported so
 * tests (and, if needed later, other synthetic-geometry consumers) can address the same point a
 * feature collection would place. */
export function stubVillagePosition(
  villageId: string,
  aoiCenter: { lat: number; lon: number },
): { lat: number; lon: number } {
  const hash = hashString(villageId)
  const angle = (hash % 360) * (Math.PI / 180)
  const radiusJitter = ((hash >>> 8) % 100) / 100 // 0..1, from a different slice of the hash
  const radius = RING_RADIUS_DEG * (1 + radiusJitter * 0.6)
  return {
    lat: aoiCenter.lat + radius * Math.sin(angle),
    lon: aoiCenter.lon + radius * Math.cos(angle),
  }
}

export interface VillageFeatureProperties {
  village_id: string
  name: string | null
  tier: SettlementPriority['tier']
  eps: number
  population: number | null
  isolated_now: boolean | null
  color: string
  position_is_real: boolean
}

/** Builds one point feature per ranked settlement (`TickResult.priorities`), enriched with
 * `VillageIsolation` fields (population, isolation status) when a matching village_id is present
 * in `TickResult.isolations` — the two lists are joined on `village_id`, not assumed to be in the
 * same order or the same length.
 *
 * Position, in preference order: `VillageIsolation.geometry` (if the backend ever populates it),
 * then the real point from `exposureByVillageId` (GET /api/aoi/{id}/exposure), then the
 * documented synthetic hash-ring fallback — see module docstring. `position_is_real` on each
 * feature tells the caller which one it got, so the map can style a synthetic pin honestly
 * (e.g. a dashed ring) rather than presenting it identically to a real one. */
export function villagesToFeatureCollection(
  priorities: SettlementPriority[],
  isolations: VillageIsolation[],
  aoiCenter: { lat: number; lon: number },
  exposureByVillageId?: Map<string, VillageExposure>,
): FeatureCollection<Point, VillageFeatureProperties> {
  const isolationById = new Map(isolations.map((v) => [v.village_id, v]))
  const features: Feature<Point, VillageFeatureProperties>[] = priorities.map((priority) => {
    const isolation = isolationById.get(priority.village_id)
    const exposure = exposureByVillageId?.get(priority.village_id)
    let position: { lat: number; lon: number }
    let positionIsReal: boolean
    if (isolation?.geometry?.type === 'Point') {
      position = { lat: isolation.geometry.coordinates[1], lon: isolation.geometry.coordinates[0] }
      positionIsReal = true
    } else if (exposure) {
      position = { lat: exposure.lat, lon: exposure.lon }
      positionIsReal = true
    } else {
      position = stubVillagePosition(priority.village_id, aoiCenter)
      positionIsReal = false
    }
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [position.lon, position.lat] },
      properties: {
        village_id: priority.village_id,
        name: isolation?.name ?? exposure?.name ?? null,
        tier: priority.tier,
        eps: priority.eps,
        population: isolation?.population ?? (exposure?.population_worldpop_est != null ? Math.round(exposure.population_worldpop_est) : null),
        isolated_now: isolation?.isolated_now ?? null,
        color: TIER_COLOR[priority.tier],
        position_is_real: positionIsReal,
      },
    }
  })

  return { type: 'FeatureCollection', features }
}
