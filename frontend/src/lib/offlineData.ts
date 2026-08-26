/**
 * BUILD_PLAN.md task 5.3 — offline data: "last action card, route geometry, shelter list,
 * emergency contacts in IndexedDB."
 *
 * **Scope ruling, checked against the real schemas before writing this (same honesty framing
 * task 5.5's own ruling below uses):** neither `backend/app/schemas/` nor `types/schemas.ts` has
 * a standalone "list of shelters" or "list of emergency contacts" object anywhere — `ActionCard`
 * only ever carries ONE shelter (`shelter_name`, `route.shelter_id`/`shelter_name`) and ONE
 * contact string (`contact`, itself already an honestly-labelled placeholder per
 * `config.ACTION_CARD_CONTACT_PLACEHOLDER` — "not yet configured for this AOI"). Rather than
 * invent a richer backend endpoint out of scope for this task, this module caches the REAL data
 * that exists — every recent `ActionCard` the store has actually received (same cap as
 * `useTickStore`'s own in-memory `actionCards`, `MAX_ACTION_CARDS`) — and derives "shelter list"
 * / "emergency contacts" as the real, de-duplicated set of shelters/contacts those cached cards
 * actually reference. A single source of truth (the cached cards) that can't drift from what was
 * genuinely issued, rather than four independently-written stores that could disagree.
 *
 * Populated by `useTickStore.applyTick` on every tick (frontend/src/store/useTickStore.ts) and
 * read back by `hydrateFromOfflineCache()` on app boot — BEFORE any WebSocket tick has arrived —
 * so a citizen opening the (installed, task 5.1) PWA with no connectivity at all still sees the
 * last known action card, route, shelter, and contact info, not an empty screen.
 *
 * Shares one IndexedDB database with `ackQueue.ts` via `offlineDb.ts` — see that file's docstring
 * for a real bug (two independently-`openDB`'d stores racing for the same DB version) this
 * consolidation fixes.
 */
import { ACTION_CARDS_STORE, getOfflineDb } from './offlineDb'
import type { ActionCard } from '../types/schemas'

// Single-row cache — task 5.3 asks for "the last [snapshot]", not a full history (that's what
// the real, hash-chained audit trail is for). One fixed key keeps `get`/`put` trivial.
const SNAPSHOT_KEY = 'latest'

interface CachedSnapshot {
  key: typeof SNAPSHOT_KEY
  actionCards: ActionCard[]
  cachedAt: string // ISO 8601, informational only — see offlineTiles.ts's identical note on why
  // this is not a CLAUDE.md rule-14 concern (never fed into risk/decision logic).
}

/** Persist the current set of known action cards (called from `useTickStore.applyTick`). Fails
 * open — a storage error must never break tick handling. */
export async function cacheActionCards(actionCards: ActionCard[]): Promise<void> {
  try {
    const db = await getOfflineDb()
    const record: CachedSnapshot = {
      key: SNAPSHOT_KEY,
      actionCards,
      cachedAt: new Date().toISOString(),
    }
    await db.put(ACTION_CARDS_STORE, record)
  } catch {
    // IndexedDB unavailable/full/private-browsing — this session simply isn't building an
    // offline cache this time; the live in-memory store (useTickStore) is unaffected either way.
  }
}

/** The last cached snapshot, or null if nothing has ever been cached in this browser. Fails open
 * (returns null) rather than throwing, for the same reason as `cacheActionCards`. */
export async function getCachedActionCards(): Promise<ActionCard[]> {
  try {
    const db = await getOfflineDb()
    const record = (await db.get(ACTION_CARDS_STORE, SNAPSHOT_KEY)) as CachedSnapshot | undefined
    return record?.actionCards ?? []
  } catch {
    return []
  }
}

export interface CachedShelter {
  shelterId: string
  shelterName: string
  shelterCapacityOk: boolean | null // null when a card referenced this shelter by name only,
  // with no routed EvacuationRoute (e.g. no reachable route was found) — never fabricated.
}

/** The real, de-duplicated set of shelters referenced by the cached action cards' routes —
 * "shelter list", derived from real data (see module docstring for why this isn't a separate,
 * independently-populated store). */
export function deriveCachedShelters(actionCards: ActionCard[]): CachedShelter[] {
  const byId = new Map<string, CachedShelter>()
  for (const card of actionCards) {
    if (card.route) {
      byId.set(card.route.shelter_id, {
        shelterId: card.route.shelter_id,
        shelterName: card.route.shelter_name,
        shelterCapacityOk: card.route.shelter_capacity_ok,
      })
    } else if (card.shelter_name && !byId.has(card.shelter_name)) {
      // No routed EvacuationRoute exists for this card (decision/routing.py found none) — the
      // card still names an intended shelter, so it's still real, citable information, just
      // without a shelter_id or capacity flag to go with it.
      byId.set(card.shelter_name, {
        shelterId: card.shelter_name,
        shelterName: card.shelter_name,
        shelterCapacityOk: null,
      })
    }
  }
  return [...byId.values()]
}

/** The real, de-duplicated set of contact strings the cached action cards carry — "emergency
 * contacts". Today this is expected to be a single entry (every `ActionCard.contact` currently
 * comes from the one AOI-wide `config.ACTION_CARD_CONTACT_PLACEHOLDER`, itself an honestly
 * labelled placeholder, not a real number) — kept as a de-duplicated LIST rather than one string
 * because CLAUDE.md's own contact field is documented as AOI-configurable, so more than one
 * distinct value is a real, expected future case, not a bug if it ever happens. */
export function deriveCachedEmergencyContacts(actionCards: ActionCard[]): string[] {
  return [...new Set(actionCards.map((c) => c.contact).filter((c) => c.length > 0))]
}

/** Test-only reset — mirrors `_resetOfflineTilesForTests`'s existing pattern. Delegates to the
 * shared `offlineDb.ts` reset since this module no longer owns its own db connection. */
export { _resetOfflineDbForTests as _resetOfflineDataForTests } from './offlineDb'
