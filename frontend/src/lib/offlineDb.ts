/**
 * The single shared IndexedDB database backing BUILD_PLAN.md task 5.3's offline data
 * (`offlineData.ts`'s `action_cards` store) and acknowledgement queue (`ackQueue.ts`'s
 * `pending_acks` store).
 *
 * **Real bug found and fixed while verifying this in an actual browser (not caught by the vitest
 * suite — see the two modules' own test files for why):** `offlineData.ts` and `ackQueue.ts`
 * originally each called `idb`'s `openDB()` independently, with the SAME database name/version
 * but a DIFFERENT `upgrade` callback (one creating `action_cards`, the other `pending_acks`).
 * IndexedDB only fires `upgrade` when the requested version is greater than the database's
 * current version — so whichever module's `openDB()` call happened to run FIRST "won" and created
 * its own store; the OTHER module's `openDB()` call then saw the database already at the target
 * version, its `upgrade` callback never fired, and its store was silently never created. Every
 * write to the missing store then failed inside that module's own fail-open try/catch — no
 * visible error, just data quietly never persisted. A real headless-Chromium Playwright check
 * against the built app (not vitest/fake-indexeddb, where each test file's isolated module
 * registry happened to mask this) is what surfaced it: `getCachedActionCards()` kept returning
 * `[]` even seconds after a real tick should have cached something.
 *
 * Fixed the only correct way for two independent modules sharing one database: ONE shared
 * `openDB()` call, in this file, whose `upgrade` callback creates every store either module needs
 * — both modules import `getOfflineDb()` instead of calling `openDB` themselves.
 */
import { openDB, type IDBPDatabase } from 'idb'

export const OFFLINE_DB_NAME = 'nirantar-offline-data'
export const OFFLINE_DB_VERSION = 1
export const ACTION_CARDS_STORE = 'action_cards'
export const PENDING_ACKS_STORE = 'pending_acks'

let dbPromise: Promise<IDBPDatabase> | null = null

export function getOfflineDb(): Promise<IDBPDatabase> {
  dbPromise ??= openDB(OFFLINE_DB_NAME, OFFLINE_DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains(ACTION_CARDS_STORE)) {
        db.createObjectStore(ACTION_CARDS_STORE, { keyPath: 'key' })
      }
      if (!db.objectStoreNames.contains(PENDING_ACKS_STORE)) {
        db.createObjectStore(PENDING_ACKS_STORE, { keyPath: 'id', autoIncrement: true })
      }
    },
  })
  return dbPromise
}

/** Test-only reset — mirrors every other `_reset*ForTests` helper in this codebase (offlineTiles.ts). */
export function _resetOfflineDbForTests(): void {
  dbPromise = null
}
