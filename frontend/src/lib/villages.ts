import type { Feature, FeatureCollection, Point } from 'geojson'
import type { SettlementPriority, VillageIsolation } from '../types/schemas'

/**
 * BUILD_PLAN.md task 2.7 ("villages rendered as ranked pins from TickResult.priorities"). Neither
 * `SettlementPriority` nor `VillageIsolation` (backend/app/schemas/impact.py) carries a lat/lon —
 * real village geometry exists on disk (`data/static/aizawl/exposure.gpkg`, task 1.3) but nothing
 * has wired it through the API to the frontend yet (a backend/schema task, out of scope here).
 * Rather than render no pins at all, this derives a deterministic pseudo-position per
 * `village_id` — same spirit as lib/grid.ts's synthetic cell squares and lib/roads.ts's road
 * sketch: fabricated for visualization only, not a claim about where any real village sits.
 * Delete this in favour of real village geometry once the API carries it.
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
}

/** Builds one point feature per ranked settlement (`TickResult.priorities`), enriched with
 * `VillageIsolation` fields (population, isolation status) when a matching village_id is present
 * in `TickResult.isolations` — the two lists are joined on `village_id`, not assumed to be in the
 * same order or the same length. */
export function villagesToFeatureCollection(
  priorities: SettlementPriority[],
  isolations: VillageIsolation[],
  aoiCenter: { lat: number; lon: number },
): FeatureCollection<Point, VillageFeatureProperties> {
  const isolationById = new Map(isolations.map((v) => [v.village_id, v]))
  const features: Feature<Point, VillageFeatureProperties>[] = priorities.map((priority) => {
    const isolation = isolationById.get(priority.village_id)
    const position = stubVillagePosition(priority.village_id, aoiCenter)
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [position.lon, position.lat] },
      properties: {
        village_id: priority.village_id,
        name: isolation?.name ?? null,
        tier: priority.tier,
        eps: priority.eps,
        population: isolation?.population ?? null,
        isolated_now: isolation?.isolated_now ?? null,
        color: TIER_COLOR[priority.tier],
      },
    }
  })

  return { type: 'FeatureCollection', features }
}
