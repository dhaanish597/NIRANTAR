import { describe, expect, it } from 'vitest'
import type { SettlementPriority, VillageIsolation } from '../types/schemas'
import { stubVillagePosition, TIER_COLOR, villagesToFeatureCollection } from './villages'

const aoiCenter = { lat: 23.7307, lon: 92.7173 }

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

describe('stubVillagePosition', () => {
  it('is deterministic for the same village_id', () => {
    const a = stubVillagePosition('v1', aoiCenter)
    const b = stubVillagePosition('v1', aoiCenter)
    expect(a).toEqual(b)
  })

  it('places different village_ids at different positions', () => {
    const a = stubVillagePosition('v1', aoiCenter)
    const b = stubVillagePosition('v2', aoiCenter)
    expect(a).not.toEqual(b)
  })
})

describe('villagesToFeatureCollection', () => {
  it('produces one point feature per priority entry', () => {
    const fc = villagesToFeatureCollection([makePriority()], [makeIsolation()], aoiCenter)
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].geometry.type).toBe('Point')
  })

  it('enriches a priority with the matching isolation record by village_id', () => {
    const fc = villagesToFeatureCollection([makePriority()], [makeIsolation()], aoiCenter)
    expect(fc.features[0].properties).toMatchObject({
      village_id: 'v1',
      name: 'Durtlang',
      population: 4200,
      isolated_now: true,
      tier: 'P1',
    })
  })

  it('still renders a pin, with null RII fields, when no isolation record matches', () => {
    const fc = villagesToFeatureCollection([makePriority({ village_id: 'unmatched' })], [], aoiCenter)
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].properties).toMatchObject({
      village_id: 'unmatched',
      name: null,
      population: null,
      isolated_now: null,
    })
  })

  it('colours pins by tier using TIER_COLOR', () => {
    const fc = villagesToFeatureCollection(
      [makePriority({ village_id: 'a', tier: 'P1' }), makePriority({ village_id: 'b', tier: 'P3' })],
      [],
      aoiCenter,
    )
    expect(fc.features[0].properties.color).toBe(TIER_COLOR.P1)
    expect(fc.features[1].properties.color).toBe(TIER_COLOR.P3)
  })

  it('renders an empty collection for an empty priorities list', () => {
    const fc = villagesToFeatureCollection([], [], aoiCenter)
    expect(fc.features).toHaveLength(0)
  })
})
