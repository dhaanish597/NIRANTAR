import { api } from './api'
import type { AoiExposure } from '../types/schemas'

/**
 * Real village/shelter points (GET /api/aoi/{id}/exposure — backend/app/impact/exposure.py),
 * cached per AOI for the page session. Static geometry, fetched once, never re-requested on
 * every tick — the live risk/priority data that gets JOINED onto these points by `village_id`
 * still comes from the websocket tick stream as normal.
 */
const cache = new Map<string, Promise<AoiExposure>>()

export function loadAoiExposure(aoiId: string): Promise<AoiExposure> {
  const cached = cache.get(aoiId)
  if (cached) return cached
  const promise = api.getAoiExposure(aoiId)
  cache.set(aoiId, promise)
  // A failed fetch must not poison the cache for a later retry — same pattern
  // lib/offlineTiles.ts already established for this codebase.
  promise.catch(() => cache.delete(aoiId))
  return promise
}

export function _resetAoiExposureForTests(): void {
  cache.clear()
}
