import { describe, expect, it } from 'vitest'
import type { ScenarioSummary } from '../types/schemas'
import { computeReplayProgress } from './replayTimeline'

function makeScenario(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: '_smoke',
    aoi_id: 'aizawl',
    held_out_of_training: false,
    frame_count: 10,
    start: '2025-01-01T00:00:00+05:30',
    end: '2025-01-01T09:00:00+05:30',
    provenance: {},
    ...overrides,
  }
}

describe('computeReplayProgress', () => {
  it('returns 0 at the scenario start', () => {
    expect(computeReplayProgress(makeScenario(), '2025-01-01T00:00:00+05:30')).toBe(0)
  })

  it('returns 1 at the scenario end', () => {
    expect(computeReplayProgress(makeScenario(), '2025-01-01T09:00:00+05:30')).toBe(1)
  })

  it('returns the fractional position in between', () => {
    // 4.5h into a 9h window
    expect(computeReplayProgress(makeScenario(), '2025-01-01T04:30:00+05:30')).toBeCloseTo(0.5, 5)
  })

  it('clamps to [0, 1] for a time outside the window', () => {
    expect(computeReplayProgress(makeScenario(), '2024-12-31T00:00:00+05:30')).toBe(0)
    expect(computeReplayProgress(makeScenario(), '2025-01-02T00:00:00+05:30')).toBe(1)
  })

  it('returns null when there is no active scenario', () => {
    expect(computeReplayProgress(undefined, '2025-01-01T00:00:00+05:30')).toBeNull()
  })

  it('returns null when scenario_time is null', () => {
    expect(computeReplayProgress(makeScenario(), null)).toBeNull()
  })

  it('returns null for an unparseable timestamp rather than a fabricated fraction', () => {
    expect(computeReplayProgress(makeScenario(), 'not-a-date')).toBeNull()
  })
})
