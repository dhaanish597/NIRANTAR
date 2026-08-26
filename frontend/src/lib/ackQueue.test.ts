import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import {
  _resetAckQueueForTests,
  attachAckQueueAutoSync,
  getQueuedAcknowledgements,
  queueAcknowledgement,
  syncQueuedAcknowledgements,
} from './ackQueue'

beforeEach(async () => {
  await _resetAckQueueForTests()
})

afterEach(async () => {
  vi.restoreAllMocks()
  await _resetAckQueueForTests()
})

describe('queueAcknowledgement / getQueuedAcknowledgements', () => {
  it('starts empty', async () => {
    expect(await getQueuedAcknowledgements()).toEqual([])
  })

  it('persists a real queued entry to IndexedDB', async () => {
    await queueAcknowledgement({ alert_id: 'a1', village_id: 'v1' })
    const queued = await getQueuedAcknowledgements()
    expect(queued).toHaveLength(1)
    expect(queued[0]).toMatchObject({ alert_id: 'a1', village_id: 'v1' })
    expect(typeof queued[0].queuedAt).toBe('string')
  })

  it('accumulates multiple distinct queued acknowledgements', async () => {
    await queueAcknowledgement({ alert_id: 'a1', village_id: 'v1' })
    await queueAcknowledgement({ alert_id: 'a2', village_id: 'v2' })
    expect(await getQueuedAcknowledgements()).toHaveLength(2)
  })
}, 20000)

describe('syncQueuedAcknowledgements', () => {
  it('sends every queued entry for real and removes it on success', async () => {
    await queueAcknowledgement({ alert_id: 'a1', village_id: 'v1' })
    const spy = vi
      .spyOn(api, 'acknowledgeVillage')
      .mockResolvedValue({
        event_id: 'e1', alert_id: 'a1', kind: 'VILLAGE_ACKNOWLEDGED', actor: 'village:v1',
        t: 't', payload: {}, input_hash: 'x', prev_hash: 'y', hash: 'z',
      })

    const synced = await syncQueuedAcknowledgements()

    expect(synced).toBe(1)
    expect(spy).toHaveBeenCalledWith({ alert_id: 'a1', village_id: 'v1' })
    expect(await getQueuedAcknowledgements()).toEqual([])
  })

  it('leaves an entry queued (does not drop it) when the sync attempt itself fails', async () => {
    await queueAcknowledgement({ alert_id: 'a1', village_id: 'v1' })
    vi.spyOn(api, 'acknowledgeVillage').mockRejectedValue(new Error('still offline'))

    const synced = await syncQueuedAcknowledgements()

    expect(synced).toBe(0)
    expect(await getQueuedAcknowledgements()).toHaveLength(1)
  })

  it('syncs each entry independently — one failure does not block a later success', async () => {
    await queueAcknowledgement({ alert_id: 'fails', village_id: 'v1' })
    await queueAcknowledgement({ alert_id: 'succeeds', village_id: 'v2' })
    vi.spyOn(api, 'acknowledgeVillage').mockImplementation((payload) => {
      if (payload.alert_id === 'fails') return Promise.reject(new Error('nope'))
      return Promise.resolve({
        event_id: 'e2', alert_id: payload.alert_id, kind: 'VILLAGE_ACKNOWLEDGED',
        actor: 'village:v2', t: 't', payload: {}, input_hash: 'x', prev_hash: 'y', hash: 'z',
      })
    })

    const synced = await syncQueuedAcknowledgements()

    expect(synced).toBe(1)
    const remaining = await getQueuedAcknowledgements()
    expect(remaining).toHaveLength(1)
    expect(remaining[0].alert_id).toBe('fails')
  })

  it('is a real no-op (returns 0) when nothing is queued', async () => {
    expect(await syncQueuedAcknowledgements()).toBe(0)
  })
})

describe('attachAckQueueAutoSync', () => {
  // A real `window.addEventListener('online', ...)` cannot be un-attached by
  // `_resetAckQueueForTests()` (it only resets this module's OWN "have I attached" bookkeeping,
  // not the browser's listener registry) — so, matching the function's real intended lifetime
  // ("attach once, for as long as the page lives"), this is deliberately ONE test exercising both
  // "it actually syncs" and "calling it again doesn't attach a second listener", rather than two
  // separate tests that would either double-attach or fight over reset ordering.
  it('attaches exactly one real listener (repeated calls are no-ops) that syncs the queue when the browser online event fires', async () => {
    await queueAcknowledgement({ alert_id: 'a1', village_id: 'v1' })
    const spy = vi
      .spyOn(api, 'acknowledgeVillage')
      .mockResolvedValue({
        event_id: 'e1', alert_id: 'a1', kind: 'VILLAGE_ACKNOWLEDGED', actor: 'village:v1',
        t: 't', payload: {}, input_hash: 'x', prev_hash: 'y', hash: 'z',
      })

    attachAckQueueAutoSync()
    attachAckQueueAutoSync()
    attachAckQueueAutoSync()
    window.dispatchEvent(new Event('online'))

    // syncQueuedAcknowledgements() runs async off the event listener — wait for it to settle.
    await vi.waitFor(() => expect(spy).toHaveBeenCalledTimes(1))
    await vi.waitFor(async () => expect(await getQueuedAcknowledgements()).toEqual([]))
  })
})
