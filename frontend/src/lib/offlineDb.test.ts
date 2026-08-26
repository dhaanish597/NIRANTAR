import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  _resetOfflineDbForTests,
  ACTION_CARDS_STORE,
  getOfflineDb,
  PENDING_ACKS_STORE,
} from './offlineDb'

beforeEach(() => {
  _resetOfflineDbForTests()
})

afterEach(() => {
  _resetOfflineDbForTests()
})

describe('getOfflineDb', () => {
  it('a single open creates BOTH stores offlineData.ts and ackQueue.ts need', async () => {
    // Regression test for the real bug this module's own docstring documents: two independent
    // openDB() calls sharing one database name/version, each with a different upgrade callback,
    // silently only create ONE of the two stores (whichever module's openDB() call ran first)
    // because IndexedDB's `upgrade` only fires on a version INCREASE, not on every open.
    const db = await getOfflineDb()
    expect(db.objectStoreNames.contains(ACTION_CARDS_STORE)).toBe(true)
    expect(db.objectStoreNames.contains(PENDING_ACKS_STORE)).toBe(true)
  })

  it('repeated calls return the same connection (one shared open, not one per caller)', async () => {
    const a = await getOfflineDb()
    const b = await getOfflineDb()
    expect(a).toBe(b)
  })
})
