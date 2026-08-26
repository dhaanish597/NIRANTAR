import { describe, expect, it } from 'vitest'
import type { CellRisk, RoadSegmentRisk, TickResult, VillageIsolation, WhatIfResult } from '../types/schemas'
import { failureDistribution, summarizeWhatIf } from './whatIf'

function makeCellRisk(pFail: number, id = 'c1'): CellRisk {
  return {
    cell_id: id,
    p_fail: pFail,
    threshold_exceedance: pFail,
    confidence: 0.9,
    attributions: [],
    model_version: 'test',
  }
}

function makeRoad(severed: boolean, id = 'e1'): RoadSegmentRisk {
  return {
    edge_id: id,
    name: 'Test Road',
    highway_class: 'trunk',
    is_bridge: false,
    p_blocked: severed ? 0.9 : 0.1,
    severed,
    contributing_cells: [],
  }
}

function makeIsolation(isolatedNow: boolean, name: string, id: string): VillageIsolation {
  return {
    village_id: id,
    name,
    population: 100,
    p_isolated: isolatedNow ? 0.9 : 0.1,
    isolated_now: isolatedNow,
    alternate_route_exists: false,
    est_duration_hours: isolatedNow ? 6 : null,
    severed_links: [],
  }
}

function makeTick(overrides: Partial<TickResult> = {}): TickResult {
  return {
    t: '2026-01-01T00:00:00+05:30',
    mode: 'live',
    scenario_id: null,
    aoi_id: 'aizawl',
    cell_risks: [],
    road_risks: [],
    isolations: [],
    priorities: [],
    new_action_cards: [],
    new_audit_events: [],
    is_reconstructed: true,
    ...overrides,
  }
}

function makeResult(tick: TickResult): WhatIfResult {
  return {
    request: { aoi_id: 'aizawl', rainfall_mm: 250, duration_hours: 12 },
    assumptions: ['Rainfall is applied uniformly across every cell in the AOI.'],
    cell_count: tick.cell_risks.length,
    tick,
  }
}

describe('failureDistribution', () => {
  it('buckets every cell into the real escalation stages using the same thresholds as the rest of the app', () => {
    const tick = makeTick({
      cell_risks: [
        makeCellRisk(0.1, 'green'),
        makeCellRisk(0.3, 'yellow'),
        makeCellRisk(0.6, 'orange'),
        makeCellRisk(0.9, 'red'),
      ],
    })
    const dist = failureDistribution(makeResult(tick))
    expect(dist).toEqual([
      { stage: 'GREEN', count: 1 },
      { stage: 'YELLOW', count: 1 },
      { stage: 'ORANGE', count: 1 },
      { stage: 'RED', count: 1 },
    ])
  })

  it('returns all-zero buckets for an empty cell_risks list, not an error', () => {
    const dist = failureDistribution(makeResult(makeTick()))
    expect(dist.every((b) => b.count === 0)).toBe(true)
    expect(dist).toHaveLength(4)
  })

  it('an extreme rainfall input that pushes every cell to p_fail=1.0 buckets everything as RED', () => {
    const tick = makeTick({ cell_risks: Array.from({ length: 50 }, (_, i) => makeCellRisk(1.0, `c${i}`)) })
    const dist = failureDistribution(makeResult(tick))
    expect(dist.find((b) => b.stage === 'RED')?.count).toBe(50)
    expect(dist.filter((b) => b.stage !== 'RED').every((b) => b.count === 0)).toBe(true)
  })
})

describe('summarizeWhatIf', () => {
  it('counts severed roads correctly, out of the total', () => {
    const tick = makeTick({
      road_risks: [makeRoad(true, 'a'), makeRoad(false, 'b'), makeRoad(true, 'c')],
    })
    const summary = summarizeWhatIf(makeResult(tick))
    expect(summary.severedRoadCount).toBe(2)
    expect(summary.totalRoadCount).toBe(3)
  })

  it('counts isolated villages and lists their real names, out of the total', () => {
    const tick = makeTick({
      isolations: [
        makeIsolation(true, 'Durtlang', 'v1'),
        makeIsolation(false, 'Reiek', 'v2'),
        makeIsolation(true, 'Tuirial', 'v3'),
      ],
    })
    const summary = summarizeWhatIf(makeResult(tick))
    expect(summary.isolatedVillageCount).toBe(2)
    expect(summary.totalVillageCount).toBe(3)
    expect(summary.isolatedVillageNames.sort()).toEqual(['Durtlang', 'Tuirial'])
  })

  it('reflects zero severance/isolation honestly when nothing is affected (a mild rainfall input)', () => {
    const tick = makeTick({
      road_risks: [makeRoad(false, 'a')],
      isolations: [makeIsolation(false, 'Reiek', 'v1')],
    })
    const summary = summarizeWhatIf(makeResult(tick))
    expect(summary.severedRoadCount).toBe(0)
    expect(summary.isolatedVillageCount).toBe(0)
    expect(summary.isolatedVillageNames).toEqual([])
  })

  it('totalCells matches the real cell_risks length, not the (possibly stale) cell_count field', () => {
    const tick = makeTick({ cell_risks: [makeCellRisk(0.1), makeCellRisk(0.2)] })
    const summary = summarizeWhatIf(makeResult(tick))
    expect(summary.totalCells).toBe(2)
  })

  it('actionCardCount reflects the real number of action cards issued', () => {
    const card = {
      alert_id: 'a', village_id: 'v1', stage: 'RED' as const, headline: 'h', reason_plain: 'r',
      shelter_name: 's', route: null, roads_to_avoid: [], what_to_carry: [], contact: 'c',
      issued_at: 't', valid_until: 't', safe_window_hours: null, translations: {}, audio_urls: {},
    }
    const tick = makeTick({ new_action_cards: [card, { ...card, alert_id: 'b' }] })
    const summary = summarizeWhatIf(makeResult(tick))
    expect(summary.actionCardCount).toBe(2)
  })
})
