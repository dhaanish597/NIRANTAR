/**
 * BUILD_PLAN.md task 5.3 — "Queue acknowledgements and sync on reconnect": `VillageView.tsx`'s
 * real "I have evacuated" button (`api.acknowledgeVillage`, task 3.10) currently just shows an
 * error when the request fails. This module makes it durable across a real offline gap: a failed
 * acknowledgement is persisted to IndexedDB, then actually retried — not just re-shown as a
 * button to press again — the moment the browser's real `online` event fires.
 *
 * Uses the browser's own connectivity signal (`navigator.onLine` / `window`'s `online`/`offline`
 * events), not a polling timer — this is exactly what those events are for, and CLAUDE.md rule 10
 * ("network cable unplugged") makes a citizen's device going fully offline a real, expected case
 * here, not an edge case to poll around.
 *
 * Shares one IndexedDB database with `offlineData.ts` via `offlineDb.ts` — see that file's
 * docstring for a real bug (two independently-`openDB`'d stores racing for the same DB version)
 * this consolidation fixes.
 */
import { api } from './api'
import { getOfflineDb, PENDING_ACKS_STORE } from './offlineDb'

export interface QueuedAck {
  id?: number // IndexedDB auto-increment key — absent until first written.
  alert_id: string
  village_id: string
  queuedAt: string // ISO 8601, informational — see offlineTiles.ts's note on why this is not a
  // CLAUDE.md rule-14 concern (never fed into risk/decision logic, purely a UI "queued since" label).
}

/** Persist an acknowledgement that could not be sent right now. Never throws — a citizen's tap on
 * "I have evacuated" must be saved even if IndexedDB itself is somehow unavailable; the caller's
 * UI state is the fallback record in that (rare) case. */
export async function queueAcknowledgement(payload: {
  alert_id: string
  village_id: string
}): Promise<void> {
  try {
    const db = await getOfflineDb()
    const record: QueuedAck = { ...payload, queuedAt: new Date().toISOString() }
    await db.add(PENDING_ACKS_STORE, record)
  } catch {
    // See module docstring — fails open, same pattern as offlineData.ts/offlineTiles.ts.
  }
}

export async function getQueuedAcknowledgements(): Promise<QueuedAck[]> {
  try {
    const db = await getOfflineDb()
    return (await db.getAll(PENDING_ACKS_STORE)) as QueuedAck[]
  } catch {
    return []
  }
}

/** Attempts to send every queued acknowledgement for real (the same `POST /api/village/
 * acknowledge` the button itself calls). Each entry is removed ONLY on a real success — a queue
 * entry that fails again (still offline, or a genuine server error) stays queued for the next
 * sync attempt rather than being silently dropped. Returns the count actually synced, for callers
 * that want to surface it. */
export async function syncQueuedAcknowledgements(): Promise<number> {
  const queued = await getQueuedAcknowledgements()
  let synced = 0
  for (const entry of queued) {
    try {
      await api.acknowledgeVillage({ alert_id: entry.alert_id, village_id: entry.village_id })
      if (entry.id !== undefined) {
        const db = await getOfflineDb()
        await db.delete(PENDING_ACKS_STORE, entry.id)
      }
      synced += 1
    } catch {
      // Still offline, or the server rejected it — leave it queued, try again on the next
      // 'online' event or explicit sync call rather than losing the citizen's acknowledgement.
    }
  }
  return synced
}

let autoSyncListenerAttached = false

/** Wires `syncQueuedAcknowledgements()` to the browser's real `online` event, once. Safe to call
 * repeatedly (e.g. from multiple component mounts) — only attaches one listener. No-op outside a
 * browser environment (e.g. under vitest without jsdom's `window`, or SSR, neither of which apply
 * to this SPA today but kept consistent with `lib/installPrompt.ts`'s own environment guard). */
export function attachAckQueueAutoSync(): void {
  if (autoSyncListenerAttached || typeof window === 'undefined') return
  window.addEventListener('online', () => void syncQueuedAcknowledgements())
  autoSyncListenerAttached = true
}

/** Test-only reset — mirrors `_resetOfflineTilesForTests`'s existing pattern. Also clears any
 * real queued records left in IndexedDB by a previous test: unlike `offlineData.ts`'s
 * single-fixed-key snapshot store, `pending_acks` is keyed by auto-increment id, so records from
 * a prior test would otherwise silently accumulate across tests in the same file instead of
 * being overwritten. Deliberately does NOT reset `offlineDb.ts`'s shared connection (that would
 * also blow away `offlineData.ts`'s half of the shared database mid-test-file for no reason) —
 * only clears THIS module's own store's content. */
export async function _resetAckQueueForTests(): Promise<void> {
  try {
    const db = await getOfflineDb()
    await db.clear(PENDING_ACKS_STORE)
  } catch {
    // No real IndexedDB in this environment yet (nothing to clear) — fine.
  }
  autoSyncListenerAttached = false
}
