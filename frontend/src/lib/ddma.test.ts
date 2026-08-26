import { describe, expect, it } from 'vitest'
import type { ActionCard, SettlementPriority, VillageIsolation } from '../types/schemas'
import { DDMA_OFFICER_ID_PLACEHOLDER, recommendationContext } from './ddma'

function makeCard(overrides: Partial<ActionCard> = {}): ActionCard {
  return {
    alert_id: 'alert-v1-1',
    village_id: 'v1',
    stage: 'RED',
    headline: 'Evacuate Now',
    reason_plain: 'reason',
    shelter_name: 'shelter',
    route: null,
    roads_to_avoid: [],
    what_to_carry: [],
    contact: 'placeholder',
    issued_at: '2026-05-28T00:00:00+00:00',
    valid_until: '2026-05-28T06:00:00+00:00',
    safe_window_hours: null,
    translations: {},
    audio_urls: {},
    ...overrides,
  }
}

describe('DDMA_OFFICER_ID_PLACEHOLDER', () => {
  it('is a clearly-labelled placeholder, not a real officer identity', () => {
    expect(DDMA_OFFICER_ID_PLACEHOLDER.toLowerCase()).toContain('placeholder')
    expect(DDMA_OFFICER_ID_PLACEHOLDER.toLowerCase()).toContain('no real ddma login')
  })
})

describe('recommendationContext', () => {
  const priorities: SettlementPriority[] = [
    { village_id: 'v1', eps: 0.82, tier: 'P1', components: { p_fail: 0.5, rii: 0.3 } },
  ]
  const isolations: VillageIsolation[] = [
    {
      village_id: 'v1',
      name: 'Hunthar',
      population: 1200,
      p_isolated: 0.9,
      isolated_now: true,
      alternate_route_exists: false,
      est_duration_hours: 6,
      severed_links: ['e1'],
    },
  ]

  it('joins EPS/tier/components from priorities and population/isolation from isolations', () => {
    const ctx = recommendationContext(makeCard(), priorities, isolations)
    expect(ctx.eps).toBe(0.82)
    expect(ctx.tier).toBe('P1')
    expect(ctx.components).toEqual({ p_fail: 0.5, rii: 0.3 })
    expect(ctx.population).toBe(1200)
    expect(ctx.isolatedNow).toBe(true)
  })

  it('returns nulls (not fabricated defaults) when no matching priority/isolation exists', () => {
    const ctx = recommendationContext(makeCard({ village_id: 'unknown' }), priorities, isolations)
    expect(ctx.eps).toBeNull()
    expect(ctx.tier).toBeNull()
    expect(ctx.components).toEqual({})
    expect(ctx.population).toBeNull()
    expect(ctx.isolatedNow).toBeNull()
  })
})
