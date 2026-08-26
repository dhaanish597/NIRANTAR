import { describe, expect, it } from 'vitest'
import type { ActionCard } from '../types/schemas'
import { actionCardForVillage, villagesWithActionCards } from './villageView'

function makeCard(alertId: string, villageId: string): ActionCard {
  return {
    alert_id: alertId,
    village_id: villageId,
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
  }
}

describe('actionCardForVillage', () => {
  it('returns null for a null village id', () => {
    expect(actionCardForVillage([makeCard('a', 'v1')], null)).toBeNull()
  })

  it('returns the first matching card (newest-first ordering assumption)', () => {
    const cards = [makeCard('a', 'v1'), makeCard('b', 'v2'), makeCard('c', 'v1')]
    expect(actionCardForVillage(cards, 'v1')?.alert_id).toBe('a')
  })

  it('returns null when no card matches the village', () => {
    expect(actionCardForVillage([makeCard('a', 'v1')], 'v99')).toBeNull()
  })
})

describe('villagesWithActionCards', () => {
  it('returns distinct village ids preserving first-seen order', () => {
    const cards = [makeCard('a', 'v1'), makeCard('b', 'v2'), makeCard('c', 'v1')]
    expect(villagesWithActionCards(cards)).toEqual(['v1', 'v2'])
  })

  it('returns an empty list for no cards', () => {
    expect(villagesWithActionCards([])).toEqual([])
  })
})
