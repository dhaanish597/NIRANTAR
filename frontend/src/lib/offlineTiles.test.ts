import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { _resetOfflineTilesForTests, BufferSource, loadOfflineTileSource } from './offlineTiles'

function bufferOf(bytes: number[]): ArrayBuffer {
  return new Uint8Array(bytes).buffer
}

// Every test uses its own distinct AOI id (a real IndexedDB record is keyed by aoiId) rather than
// deleting/recreating the shared IndexedDB database between tests — `idb`'s connections are never
// explicitly closed between calls (there is no reason to close them in real app usage, the page
// just stays open), and IndexedDB's own `deleteDatabase` blocks on any still-open connection,
// which made an earlier version of this test file hang. Distinct keys sidestep that entirely
// without weakening what's actually under test.
let aoiCounter = 0
function freshAoiId(): string {
  aoiCounter += 1
  return `test-aoi-${aoiCounter}`
}

beforeEach(() => {
  _resetOfflineTilesForTests()
})

afterEach(() => {
  vi.unstubAllGlobals()
  _resetOfflineTilesForTests()
})

describe('BufferSource', () => {
  it('getKey returns the key it was constructed with', () => {
    const source = new BufferSource('aizawl', bufferOf([1, 2, 3]))
    expect(source.getKey()).toBe('aizawl')
  })

  it('getBytes slices the in-memory buffer — no network call involved', async () => {
    const source = new BufferSource('aizawl', bufferOf([1, 2, 3, 4, 5, 6, 7, 8]))
    const { data } = await source.getBytes(2, 3)
    expect(new Uint8Array(data)).toEqual(new Uint8Array([3, 4, 5]))
  })
})

describe('loadOfflineTileSource', () => {
  it('fetches the archive from the same-origin /tiles/ path on first load', async () => {
    const aoiId = freshAoiId()
    const bytes = bufferOf([9, 8, 7, 6])
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: () => Promise.resolve(bytes) })
    vi.stubGlobal('fetch', fetchMock)

    const source = await loadOfflineTileSource(aoiId)
    expect(fetchMock).toHaveBeenCalledWith(`/tiles/${aoiId}.pmtiles`)
    expect(source.getKey()).toBe(aoiId)
    const { data } = await source.getBytes(0, 2)
    expect(new Uint8Array(data)).toEqual(new Uint8Array([9, 8]))
  })

  it('de-duplicates concurrent loads for the same AOI into a single fetch', async () => {
    const aoiId = freshAoiId()
    const bytes = bufferOf([1, 2, 3])
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: () => Promise.resolve(bytes) })
    vi.stubGlobal('fetch', fetchMock)

    const [a, b] = await Promise.all([loadOfflineTileSource(aoiId), loadOfflineTileSource(aoiId)])
    expect(a).toBe(b)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('a later session (in-memory cache cleared, IndexedDB kept) makes zero network requests — the offline case', async () => {
    const aoiId = freshAoiId()
    const bytes = bufferOf([4, 5, 6])
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, arrayBuffer: () => Promise.resolve(bytes) })
    vi.stubGlobal('fetch', fetchMock)

    await loadOfflineTileSource(aoiId)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Simulate a fresh page load / new MapView mount: the module's in-memory promise cache is
    // gone, but IndexedDB (a real, separate persistence layer this test does NOT touch) is not.
    _resetOfflineTilesForTests()
    fetchMock.mockClear()

    const source = await loadOfflineTileSource(aoiId)
    expect(fetchMock).not.toHaveBeenCalled()
    const { data } = await source.getBytes(0, 3)
    expect(new Uint8Array(data)).toEqual(new Uint8Array([4, 5, 6]))
  })

  it('throws a clear, actionable error when the fetch fails and there is no cached copy', async () => {
    const aoiId = freshAoiId()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))
    await expect(loadOfflineTileSource(aoiId)).rejects.toThrow(/404/)
  })

  it('a failed load does not poison the cache — a later retry (e.g. network comes back) can still succeed', async () => {
    const aoiId = freshAoiId()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    await expect(loadOfflineTileSource(aoiId)).rejects.toThrow()

    const bytes = bufferOf([42])
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, arrayBuffer: () => Promise.resolve(bytes) }),
    )
    const source = await loadOfflineTileSource(aoiId)
    expect(source.getKey()).toBe(aoiId)
  })
})
