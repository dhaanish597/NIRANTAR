import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { ActionCard } from '../types/schemas'
import {
  _resetOfflineDataForTests,
  cacheActionCards,
  deriveCachedEmergencyContacts,
  deriveCachedShelters,
  getCachedActionCards,
} from './offlineData'

function makeCard(overrides: Partial<ActionCard> = {}): ActionCard {
  return {
    alert_id: 'alert-1',
    village_id: 'v1',
    stage: 'RED',
    headline: 'Evacuate Now',
    reason_plain: 'r',
    shelter_name: 'Test Shelter',
    route: null,
    roads_to_avoid: [],
    what_to_carry: [],
    contact: 'DDMA control room (placeholder)',
    issued_at: 't',
    valid_until: 't',
    safe_window_hours: null,
    translations: {},
    audio_urls: {},
    ...overrides,
  }
}

beforeEach(() => {
  _resetOfflineDataForTests()
})

afterEach(() => {
  _resetOfflineDataForTests()
})

describe('cacheActionCards / getCachedActionCards', () => {
  it('returns an empty array before anything has ever been cached', async () => {
    expect(await getCachedActionCards()).toEqual([])
  })

  it('round-trips a real set of action cards through IndexedDB', async () => {
    const cards = [makeCard({ alert_id: 'a' }), makeCard({ alert_id: 'b', village_id: 'v2' })]
    await cacheActionCards(cards)
    expect(await getCachedActionCards()).toEqual(cards)
  })

  it('a later cache call overwrites the previous snapshot (single "last" record, not a history)', async () => {
    await cacheActionCards([makeCard({ alert_id: 'old' })])
    await cacheActionCards([makeCard({ alert_id: 'new' })])
    const cards = await getCachedActionCards()
    expect(cards.map((c) => c.alert_id)).toEqual(['new'])
  })

  it('caching an empty list is real and overwrites a previous non-empty snapshot', async () => {
    await cacheActionCards([makeCard()])
    await cacheActionCards([])
    expect(await getCachedActionCards()).toEqual([])
  })
})

describe('deriveCachedShelters', () => {
  it('returns no shelters for an empty card list', () => {
    expect(deriveCachedShelters([])).toEqual([])
  })

  it('derives a shelter from a card with a real routed EvacuationRoute', () => {
    const card = makeCard({
      route: {
        village_id: 'v1',
        shelter_id: 's1',
        shelter_name: 'Community Hall',
        geometry: { type: 'LineString', coordinates: [] },
        distance_m: 500,
        est_walk_minutes: 8,
        avoided_roads: [],
        shelter_capacity_ok: true,
      },
    })
    expect(deriveCachedShelters([card])).toEqual([
      { shelterId: 's1', shelterName: 'Community Hall', shelterCapacityOk: true },
    ])
  })

  it('falls back to the plain shelter_name (null capacity) when no route was found', () => {
    const card = makeCard({ route: null, shelter_name: 'Named Shelter Only' })
    expect(deriveCachedShelters([card])).toEqual([
      { shelterId: 'Named Shelter Only', shelterName: 'Named Shelter Only', shelterCapacityOk: null },
    ])
  })

  it('de-duplicates the same shelter referenced by multiple cards', () => {
    const cardA = makeCard({ alert_id: 'a', shelter_name: 'Shared Shelter' })
    const cardB = makeCard({ alert_id: 'b', shelter_name: 'Shared Shelter' })
    expect(deriveCachedShelters([cardA, cardB])).toHaveLength(1)
  })
})

describe('deriveCachedEmergencyContacts', () => {
  it('returns no contacts for an empty card list', () => {
    expect(deriveCachedEmergencyContacts([])).toEqual([])
  })

  it('de-duplicates a shared contact string across cards', () => {
    const cardA = makeCard({ alert_id: 'a', contact: 'DDMA control room (placeholder)' })
    const cardB = makeCard({ alert_id: 'b', contact: 'DDMA control room (placeholder)' })
    expect(deriveCachedEmergencyContacts([cardA, cardB])).toEqual(['DDMA control room (placeholder)'])
  })

  it('keeps genuinely distinct contact strings as separate entries', () => {
    const cardA = makeCard({ alert_id: 'a', contact: 'Contact A' })
    const cardB = makeCard({ alert_id: 'b', contact: 'Contact B' })
    expect(deriveCachedEmergencyContacts([cardA, cardB]).sort()).toEqual(['Contact A', 'Contact B'])
  })

  it('drops an empty contact string rather than surfacing a blank entry', () => {
    expect(deriveCachedEmergencyContacts([makeCard({ contact: '' })])).toEqual([])
  })
})
