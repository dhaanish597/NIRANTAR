import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AoiExposure } from '../types/schemas'

const getAoiExposure = vi.fn()
vi.mock('./api', () => ({ api: { getAoiExposure: (...args: unknown[]) => getAoiExposure(...args) } }))

import { _resetAoiExposureForTests, loadAoiExposure } from './exposure'

const SAMPLE: AoiExposure = {
  aoi_id: 'aizawl',
  villages: [{ village_id: 'v_1', name: 'Durtlang', lat: 23.75, lon: 92.7, population_worldpop_est: 100, osm_population: null }],
  shelters: [],
}

afterEach(() => {
  _resetAoiExposureForTests()
  getAoiExposure.mockReset()
})

describe('loadAoiExposure', () => {
  it('fetches once per AOI and caches the result', async () => {
    getAoiExposure.mockResolvedValue(SAMPLE)
    const a = await loadAoiExposure('aizawl')
    const b = await loadAoiExposure('aizawl')
    expect(a).toBe(SAMPLE)
    expect(b).toBe(SAMPLE)
    expect(getAoiExposure).toHaveBeenCalledTimes(1)
  })

  it('fetches separately per AOI', async () => {
    getAoiExposure.mockResolvedValue(SAMPLE)
    await loadAoiExposure('aizawl')
    await loadAoiExposure('wayanad')
    expect(getAoiExposure).toHaveBeenCalledTimes(2)
    expect(getAoiExposure).toHaveBeenNthCalledWith(1, 'aizawl')
    expect(getAoiExposure).toHaveBeenNthCalledWith(2, 'wayanad')
  })

  it('does not poison the cache on a failed fetch — a later call retries', async () => {
    getAoiExposure.mockRejectedValueOnce(new Error('network down'))
    await expect(loadAoiExposure('aizawl')).rejects.toThrow('network down')

    getAoiExposure.mockResolvedValueOnce(SAMPLE)
    const result = await loadAoiExposure('aizawl')
    expect(result).toBe(SAMPLE)
    expect(getAoiExposure).toHaveBeenCalledTimes(2)
  })
})
