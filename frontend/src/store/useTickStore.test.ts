import { beforeEach, describe, expect, it } from 'vitest'
import type { AuditEvent, TickResult } from '../types/schemas'
import { useTickStore } from './useTickStore'

// Only applyTick is exercised here — connect()/disconnect() open a real WebSocket, which is
// out of scope for a unit test (the WS wiring itself is proven by the backend's
// tests/test_api_http.py and by manually running the dev stack).

function makeTick(overrides: Partial<TickResult> = {}): TickResult {
  return {
    t: '2025-01-01T00:00:00+05:30',
    mode: 'replay',
    scenario_id: '_smoke',
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

function makeAuditEvent(eventId: string): AuditEvent {
  return {
    event_id: eventId,
    alert_id: 'a1',
    kind: 'AI_FLAGGED',
    actor: 'system',
    t: '2025-01-01T00:00:00+05:30',
    payload: {},
    input_hash: 'x',
    prev_hash: 'x',
    hash: 'x',
  }
}

beforeEach(() => {
  useTickStore.setState({
    latestTick: null,
    cellRisks: [],
    priorities: [],
    actionCards: [],
    auditEvents: [],
  })
})

describe('applyTick', () => {
  it('replaces cellRisks and priorities with the latest tick snapshot (not accumulated)', () => {
    useTickStore.getState().applyTick(
      makeTick({
        cell_risks: [
          {
            cell_id: 'c1',
            p_fail: 0.5,
            threshold_exceedance: 0.5,
            confidence: 0.5,
            attributions: [],
            model_version: 'test',
          },
        ],
      }),
    )
    expect(useTickStore.getState().cellRisks).toHaveLength(1)

    useTickStore.getState().applyTick(makeTick({ cell_risks: [] }))
    expect(useTickStore.getState().cellRisks).toHaveLength(0) // snapshot, not accumulated
  })

  it('accumulates action cards across ticks, newest first', () => {
    const cardA = {
      alert_id: 'a', village_id: 'v1', stage: 'ORANGE' as const, headline: 'h', reason_plain: 'r',
      shelter_name: 's', route: null, roads_to_avoid: [], what_to_carry: [], contact: 'c',
      issued_at: 't', valid_until: 't', safe_window_hours: null, translations: {}, audio_urls: {},
    }
    const cardB = { ...cardA, alert_id: 'b' }

    useTickStore.getState().applyTick(makeTick({ new_action_cards: [cardA] }))
    useTickStore.getState().applyTick(makeTick({ new_action_cards: [cardB] }))

    const cards = useTickStore.getState().actionCards
    expect(cards.map((c) => c.alert_id)).toEqual(['b', 'a'])
  })

  it('caps accumulated audit events at 50', () => {
    for (let i = 0; i < 60; i++) {
      useTickStore.getState().applyTick(makeTick({ new_audit_events: [makeAuditEvent(`e${i}`)] }))
    }
    const events = useTickStore.getState().auditEvents
    expect(events).toHaveLength(50)
    expect(events[0].event_id).toBe('e59') // newest first
  })

  it('stores the tick itself as latestTick', () => {
    const tick = makeTick({ t: '2025-01-01T05:00:00+05:30' })
    useTickStore.getState().applyTick(tick)
    expect(useTickStore.getState().latestTick).toEqual(tick)
  })
})
