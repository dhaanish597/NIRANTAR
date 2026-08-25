import { describe, expect, it } from 'vitest'
import type { CellRisk, RoadSegmentRisk, SettlementPriority, VillageIsolation } from '../types/schemas'
import { findDrivingCellRisk, findVillageIsolation, mergeVillageDisplay } from './priorityDetail'

function makePriority(overrides: Partial<SettlementPriority> = {}): SettlementPriority {
  return {
    village_id: 'v1',
    eps: 0.8,
    tier: 'P1',
    components: { p_fail: 0.5, pop: 0.2, rii: 0.6, shelter: 0.1 },
    ...overrides,
  }
}

function makeIsolation(overrides: Partial<VillageIsolation> = {}): VillageIsolation {
  return {
    village_id: 'v1',
    name: 'Durtlang',
    population: 4200,
    p_isolated: 0.7,
    isolated_now: true,
    alternate_route_exists: false,
    est_duration_hours: 6,
    severed_links: ['e1'],
    ...overrides,
  }
}

function makeRoad(overrides: Partial<RoadSegmentRisk> = {}): RoadSegmentRisk {
  return {
    edge_id: 'e1',
    name: 'NH-6',
    highway_class: 'trunk',
    is_bridge: false,
    p_blocked: 0.8,
    severed: true,
    contributing_cells: ['c1', 'c2'],
    ...overrides,
  }
}

function makeCellRisk(cellId: string, pFail: number): CellRisk {
  return {
    cell_id: cellId,
    p_fail: pFail,
    threshold_exceedance: pFail,
    confidence: 0.5,
    attributions: [{ feature: 'rain_72h', plain_language: '72-hour rainfall', contribution: 0.3, display_pct: 38 }],
    model_version: 'test',
  }
}

describe('mergeVillageDisplay', () => {
  it('joins a priority with its matching isolation record on village_id', () => {
    const [record] = mergeVillageDisplay([makePriority()], [makeIsolation()])
    expect(record).toMatchObject({
      villageId: 'v1',
      tier: 'P1',
      name: 'Durtlang',
      population: 4200,
      isolatedNow: true,
      pIsolated: 0.7,
      alternateRouteExists: false,
      estDurationHours: 6,
      severedLinks: ['e1'],
    })
  })

  it('fills nulls rather than dropping the row when no isolation record matches', () => {
    const [record] = mergeVillageDisplay([makePriority({ village_id: 'unmatched' })], [])
    expect(record.name).toBeNull()
    expect(record.population).toBeNull()
    expect(record.isolatedNow).toBeNull()
    expect(record.severedLinks).toEqual([])
  })

  it('preserves the EPS component breakdown untouched', () => {
    const [record] = mergeVillageDisplay([makePriority()], [makeIsolation()])
    expect(record.components).toEqual({ p_fail: 0.5, pop: 0.2, rii: 0.6, shelter: 0.1 })
  })
})

describe('findVillageIsolation', () => {
  it('finds by village_id', () => {
    expect(findVillageIsolation('v1', [makeIsolation()])?.name).toBe('Durtlang')
  })

  it('returns undefined when not found', () => {
    expect(findVillageIsolation('nope', [makeIsolation()])).toBeUndefined()
  })
})

describe('findDrivingCellRisk', () => {
  it('returns null when the village is undefined', () => {
    expect(findDrivingCellRisk(undefined, [], [])).toBeNull()
  })

  it('returns null when the village has no severed links', () => {
    const village = makeIsolation({ severed_links: [] })
    expect(findDrivingCellRisk(village, [makeRoad()], [makeCellRisk('c1', 0.5)])).toBeNull()
  })

  it('returns null when severed link ids do not match any road_risks entry', () => {
    const village = makeIsolation({ severed_links: ['does-not-exist'] })
    expect(findDrivingCellRisk(village, [makeRoad()], [makeCellRisk('c1', 0.5)])).toBeNull()
  })

  it('picks the highest-p_fail cell among the severed roads contributing cells', () => {
    const village = makeIsolation({ severed_links: ['e1'] })
    const cellRisks = [makeCellRisk('c1', 0.4), makeCellRisk('c2', 0.9)]
    const result = findDrivingCellRisk(village, [makeRoad()], cellRisks)
    expect(result?.cell_id).toBe('c2')
    expect(result?.attributions).toHaveLength(1)
  })

  it('returns null when contributing cells are not present in the current cell_risks', () => {
    const village = makeIsolation({ severed_links: ['e1'] })
    expect(findDrivingCellRisk(village, [makeRoad()], [makeCellRisk('unrelated', 0.9)])).toBeNull()
  })
})
