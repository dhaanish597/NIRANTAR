/**
 * BUILD_PLAN.md task 5.2 — offline map: PMTiles for the Aizawl AOI, served locally, cached in
 * IndexedDB, must render with the network disabled.
 *
 * The archive itself is built by `scripts/build_tiles.py` from real, already-committed static
 * data (`data/static/<aoi>/cells.gpkg`'s terrain-grid boundaries, task 1.2; `data/osm/<aoi>_
 * graph.geojson`'s real OSM road edges, task 2.1) — see that script's own module docstring for
 * the full tooling ruling and what is/isn't tiled. It is served same-origin at `/tiles/<aoi>.
 * pmtiles` (a small dev/build Vite plugin in vite.config.ts serves/copies it there — never a
 * remote tile host, CLAUDE.md rule 10 unchanged).
 *
 * This module is the "cached in IndexedDB" half: fetch the archive's bytes ONCE, persist them in
 * IndexedDB, and wrap them as a pmtiles `Source` that serves every subsequent byte-range read out
 * of that in-memory buffer — never a second network request for the same AOI in the same page
 * session, and (once IndexedDB has a copy from a previous visit) not even a first one. This is
 * what lets the offline reference layer keep rendering after the network is disabled, not just
 * the first time it loads.
 */
import { openDB, type IDBPDatabase } from 'idb'
import type { RangeResponse, Source } from 'pmtiles'

const DB_NAME = 'nirantar-offline-tiles'
const DB_VERSION = 1
const STORE_NAME = 'archives'

interface StoredArchive {
  aoiId: string
  buffer: ArrayBuffer
  byteLength: number
  cachedAt: string // ISO 8601 — informational only (when this AOI's archive was last fetched),
  // never fed into any risk/decision logic, so no Clock/determinism concern (CLAUDE.md rule 14)
  // applies here the way it does inside the pipeline.
}

let dbPromise: Promise<IDBPDatabase> | null = null

function openTilesDb(): Promise<IDBPDatabase> {
  dbPromise ??= openDB(DB_NAME, DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'aoiId' })
      }
    },
  })
  return dbPromise
}

/** A pmtiles `Source` backed by an in-memory `ArrayBuffer` — every `getBytes` range read is a
 * plain `slice()`, never a network call. */
export class BufferSource implements Source {
  private readonly key: string
  private readonly buffer: ArrayBuffer

  constructor(key: string, buffer: ArrayBuffer) {
    this.key = key
    this.buffer = buffer
  }

  getKey(): string {
    return this.key
  }

  getBytes(offset: number, length: number): Promise<RangeResponse> {
    return Promise.resolve({ data: this.buffer.slice(offset, offset + length) })
  }
}

const TILES_URL_BASE = '/tiles'

// In-flight/completed loads, keyed by aoiId — de-duplicates concurrent/repeated calls within the
// same page session (e.g. multiple <MapView> instances mounting, Ops screen + Village View) so
// only one fetch-or-IndexedDB-read happens per AOI per session, not one per mount.
const loadCache = new Map<string, Promise<BufferSource>>()

async function fetchAndCache(aoiId: string, db: IDBPDatabase): Promise<BufferSource> {
  const response = await fetch(`${TILES_URL_BASE}/${aoiId}.pmtiles`)
  if (!response.ok) {
    throw new Error(`could not fetch offline tiles for ${aoiId}: HTTP ${response.status}`)
  }
  const buffer = await response.arrayBuffer()
  const record: StoredArchive = {
    aoiId,
    buffer,
    byteLength: buffer.byteLength,
    cachedAt: new Date().toISOString(),
  }
  try {
    await db.put(STORE_NAME, record)
  } catch {
    // IndexedDB write failing (private browsing, quota exceeded, disabled site data, ...) must
    // not break the map for THIS session — the BufferSource below already holds the bytes in
    // memory even if they can't be persisted for next time. Fails open, same pattern
    // lib/onboarding.ts's localStorage wrapper already established for this codebase.
  }
  return new BufferSource(aoiId, buffer)
}

/** Cache-first: an archive already in IndexedDB from a previous session is used with ZERO network
 * requests — this is what makes the offline reference layer keep rendering after a page
 * reload/app restart with the network cable unplugged, not only within the tab that first fetched
 * it. Throws if no cached copy exists AND the network fetch fails — callers render without the
 * offline reference layer rather than crash the map (see MapView.tsx). */
export async function loadOfflineTileSource(aoiId: string): Promise<BufferSource> {
  const cachedPromise = loadCache.get(aoiId)
  if (cachedPromise) return cachedPromise

  const promise = (async () => {
    const db = await openTilesDb()
    const cached = await db.get(STORE_NAME, aoiId)
    if (cached) {
      return new BufferSource(aoiId, (cached as StoredArchive).buffer)
    }
    return fetchAndCache(aoiId, db)
  })()

  loadCache.set(aoiId, promise)
  // A failed load must not poison the cache for a later retry (e.g. the network comes back) —
  // only successful loads stay cached.
  promise.catch(() => loadCache.delete(aoiId))
  return promise
}

/** Test-only reset — mirrors `_resetInstallPromptForTests`/`_resetEvalReportCacheForTests`'s
 * existing pattern in this codebase for module-level state that would otherwise leak between
 * tests. */
export function _resetOfflineTilesForTests(): void {
  loadCache.clear()
  dbPromise = null
}
