import { describe, expect, it } from 'vitest'
import {
  CHANNEL_PROFILES,
  formatSimulatedDuration,
  MESH_PROFILE,
  simulateMeshPropagation,
} from './meshSimulation'

describe('CHANNEL_PROFILES', () => {
  it('has exactly the four real channels backend/app/dissemination/channels.py defines', () => {
    expect(CHANNEL_PROFILES.map((c) => c.id).sort()).toEqual(
      ['cell_broadcast', 'mesh', 'push', 'sms'].sort(),
    )
  })

  it('every profile has a valid latency range and rates in [0,1] (matches _SimulatedChannelBase\'s own constructor validation)', () => {
    for (const profile of CHANNEL_PROFILES) {
      expect(profile.minLatencySeconds).toBeGreaterThanOrEqual(0)
      expect(profile.maxLatencySeconds).toBeGreaterThan(profile.minLatencySeconds)
      expect(profile.deliveryRate).toBeGreaterThanOrEqual(0)
      expect(profile.deliveryRate).toBeLessThanOrEqual(1)
      expect(profile.ackRateGivenDelivered).toBeGreaterThanOrEqual(0)
      expect(profile.ackRateGivenDelivered).toBeLessThanOrEqual(1)
    }
  })

  it('mesh is the slowest and least reliable channel (the whole reason this task exists)', () => {
    const mesh = MESH_PROFILE
    const others = CHANNEL_PROFILES.filter((c) => c.id !== 'mesh')
    for (const other of others) {
      expect(mesh.maxLatencySeconds).toBeGreaterThan(other.maxLatencySeconds)
      expect(mesh.deliveryRate).toBeLessThan(other.deliveryRate)
    }
  })

  it('mesh matches the exact real constants in channels.py (min 60s, max 1800s, 60% delivery, 30% ack)', () => {
    expect(MESH_PROFILE).toMatchObject({
      minLatencySeconds: 60.0,
      maxLatencySeconds: 1800.0,
      deliveryRate: 0.6,
      ackRateGivenDelivered: 0.3,
    })
  })
})

describe('simulateMeshPropagation', () => {
  it('the origin node (0) is never included in the hop list', () => {
    const result = simulateMeshPropagation(8, 1)
    expect(result.hops.every((h) => h.nodeIndex !== 0)).toBe(true)
  })

  it('produces exactly nodeCount - 1 hops (one per non-origin phone)', () => {
    const result = simulateMeshPropagation(10, 42)
    expect(result.hops).toHaveLength(9)
  })

  it('is deterministic for a given seed (same seed -> same outcome, a UI nicety, not a backend-parity claim)', () => {
    const a = simulateMeshPropagation(10, 7)
    const b = simulateMeshPropagation(10, 7)
    expect(a).toEqual(b)
  })

  it('a different seed can produce a different outcome', () => {
    const a = simulateMeshPropagation(20, 1)
    const b = simulateMeshPropagation(20, 2)
    expect(a).not.toEqual(b)
  })

  it('every hop latency is within the real mesh channel bounds', () => {
    const result = simulateMeshPropagation(30, 99)
    for (const hop of result.hops) {
      expect(hop.latencySeconds).toBeGreaterThanOrEqual(MESH_PROFILE.minLatencySeconds)
      expect(hop.latencySeconds).toBeLessThanOrEqual(MESH_PROFILE.maxLatencySeconds)
    }
  })

  it('an acknowledged hop is always also a delivered hop (never acked without delivery)', () => {
    const result = simulateMeshPropagation(50, 3)
    for (const hop of result.hops) {
      if (hop.acknowledged) expect(hop.delivered).toBe(true)
    }
  })

  it('deliveredCount/acknowledgedCount match the actual hop flags', () => {
    const result = simulateMeshPropagation(50, 5)
    expect(result.deliveredCount).toBe(result.hops.filter((h) => h.delivered).length)
    expect(result.acknowledgedCount).toBe(result.hops.filter((h) => h.acknowledged).length)
  })

  it('over a large sample, the delivered fraction is close to the real 60% delivery rate', () => {
    const result = simulateMeshPropagation(2000, 123)
    const fraction = result.deliveredCount / result.hops.length
    expect(fraction).toBeGreaterThan(0.5)
    expect(fraction).toBeLessThan(0.7)
  })

  it('a delivered hop always relays from an already-reached node (origin or an earlier delivered hop)', () => {
    const result = simulateMeshPropagation(20, 11)
    const reached = new Set([0])
    for (const hop of result.hops) {
      if (hop.delivered) {
        expect(reached.has(hop.relayFromNodeIndex)).toBe(true)
        reached.add(hop.nodeIndex)
      }
    }
  })

  it('hops are sorted chronologically by simulated latency', () => {
    const result = simulateMeshPropagation(30, 17)
    for (let i = 1; i < result.hops.length; i++) {
      expect(result.hops[i].latencySeconds).toBeGreaterThanOrEqual(result.hops[i - 1].latencySeconds)
    }
  })

  it('totalElapsedSeconds is the latest (max) hop latency', () => {
    const result = simulateMeshPropagation(15, 8)
    expect(result.totalElapsedSeconds).toBe(Math.max(...result.hops.map((h) => h.latencySeconds)))
  })

  it('a single-node run (just the origin) produces no hops and zero elapsed time', () => {
    const result = simulateMeshPropagation(1, 1)
    expect(result.hops).toEqual([])
    expect(result.totalElapsedSeconds).toBe(0)
  })
})

describe('formatSimulatedDuration', () => {
  it('formats under an hour as minutes', () => {
    expect(formatSimulatedDuration(23 * 60)).toBe('23 min')
  })

  it('formats an exact hour with no leftover minutes', () => {
    expect(formatSimulatedDuration(60 * 60)).toBe('1h')
  })

  it('formats hours and minutes together', () => {
    expect(formatSimulatedDuration(65 * 60)).toBe('1h 5m')
  })

  it('rounds to the nearest minute', () => {
    expect(formatSimulatedDuration(89)).toBe('1 min') // 89s rounds up to 1m, not "0 min"
  })
})
