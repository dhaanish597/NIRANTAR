import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { queueCitizenReport } from '../lib/citizenReports'
import type { Announcement, AuditEvent, RiskForecast, TickResult } from '../types/schemas'
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
    replayTicks: [],
    cellRisks: [],
    roadRisks: [],
    isolations: [],
    priorities: [],
    actionCards: [],
    auditEvents: [],
    selectedVillageId: null,
    scorecardOpen: false,
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

  it('replaces roadRisks and isolations with the latest tick snapshot (task 2.7)', () => {
    const roadRisk = {
      edge_id: 'e1', name: 'NH-6', highway_class: 'trunk', is_bridge: false,
      p_blocked: 0.9, severed: true, contributing_cells: ['aizawl_401'],
    }
    const isolation = {
      village_id: 'v1', name: 'Durtlang', population: 4200, p_isolated: 0.8,
      isolated_now: true, alternate_route_exists: false, est_duration_hours: 6,
      severed_links: ['e1'],
    }
    useTickStore.getState().applyTick(makeTick({ road_risks: [roadRisk], isolations: [isolation] }))
    expect(useTickStore.getState().roadRisks).toEqual([roadRisk])
    expect(useTickStore.getState().isolations).toEqual([isolation])

    useTickStore.getState().applyTick(makeTick({ road_risks: [], isolations: [] }))
    expect(useTickStore.getState().roadRisks).toHaveLength(0)
    expect(useTickStore.getState().isolations).toHaveLength(0)
  })
})

describe('forecast isolation', () => {
  it('never replaces authoritative map arrays with fallback forecast data', () => {
    const operationalCell = {
      cell_id: 'operational', p_fail: 0.7, threshold_exceedance: 0.7,
      confidence: 0.8, attributions: [], model_version: 'test',
    }
    const forecastCell = { ...operationalCell, cell_id: 'forecast' }
    useTickStore.getState().applyTick(makeTick({ cell_risks: [operationalCell] }))
    const forecast: RiskForecast = {
      location: 'Aizawl', location_id: 'aizawl', generated_at: '2026-01-01T00:00:00Z',
      source: 'FALLBACK',
      forecast: [{
        date: '2026-01-01', day_label: 'TODAY', risk_level: 'HIGH', risk_probability: 0.7,
        rainfall_mm: 20, confidence: 0.5, primary_driver: 'Fallback', explanation: 'Fallback',
        affected_villages: 0, affected_road_segments: 0, cell_risks: [forecastCell],
        road_risks: [], isolations: [], priorities: [], areas: [],
      }],
    }

    useTickStore.getState().setForecast(forecast)
    useTickStore.getState().selectForecastDay(forecast.forecast[0])

    expect(useTickStore.getState().cellRisks.map((cell) => cell.cell_id)).toEqual(['operational'])
  })
})

describe('selectVillage', () => {
  it('sets and clears selectedVillageId', () => {
    useTickStore.getState().selectVillage('v1')
    expect(useTickStore.getState().selectedVillageId).toBe('v1')
    useTickStore.getState().selectVillage(null)
    expect(useTickStore.getState().selectedVillageId).toBeNull()
  })
})

describe('openScorecard / closeScorecard', () => {
  it('sets and clears scorecardOpen', () => {
    useTickStore.getState().openScorecard()
    expect(useTickStore.getState().scorecardOpen).toBe(true)
    useTickStore.getState().closeScorecard()
    expect(useTickStore.getState().scorecardOpen).toBe(false)
  })
})

describe('replayTicks (BUILD_PLAN.md task 4.10)', () => {
  it('accumulates replay ticks in order, but ignores live ticks', () => {
    const replayTick1 = makeTick({ t: '2025-01-01T00:00:00+05:30', mode: 'replay' })
    const liveTick = makeTick({ t: '2025-01-01T00:30:00+05:30', mode: 'live' })
    const replayTick2 = makeTick({ t: '2025-01-01T01:00:00+05:30', mode: 'replay' })

    useTickStore.getState().applyTick(replayTick1)
    useTickStore.getState().applyTick(liveTick)
    useTickStore.getState().applyTick(replayTick2)

    const ticks = useTickStore.getState().replayTicks
    expect(ticks.map((t) => t.t)).toEqual(['2025-01-01T00:00:00+05:30', '2025-01-01T01:00:00+05:30'])
  })

  it('startReplay resets replayTicks so a new run starts with no residue from the last one', async () => {
    useTickStore.getState().applyTick(makeTick({ mode: 'replay' }))
    expect(useTickStore.getState().replayTicks).toHaveLength(1)

    const spy = vi.spyOn(api, 'startReplay').mockResolvedValue({
      mode: 'replay',
      scenario_id: '_smoke',
      scenario_time: null,
      speed_factor: 1,
      paused: false,
    })
    await useTickStore.getState().startReplay('_smoke')
    expect(useTickStore.getState().replayTicks).toHaveLength(0)
    spy.mockRestore()
  })

  it('does not clear replayTicks on a live tick after a replay run (scorecard stays viewable)', () => {
    useTickStore.getState().applyTick(makeTick({ mode: 'replay' }))
    useTickStore.getState().applyTick(makeTick({ mode: 'live' }))
    expect(useTickStore.getState().replayTicks).toHaveLength(1)
  })
})

function makeAnnouncement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 'ann-1',
    alert_id: 'a1',
    village_id: 'v1',
    stage: 'RED',
    message: 'Evacuate now',
    language: 'en',
    issued_by: 'officer-1',
    issued_at: '2026-01-01T00:00:00+05:30',
    channel_results: [],
    cap_xml: '<alert></alert>',
    ...overrides,
  }
}

describe('announcements / verification / citizen reports', () => {
  beforeEach(() => {
    localStorage.clear()
    useTickStore.setState({ announcements: [], verificationByAlertId: {}, citizenReports: [] })
  })

  it('applyAnnouncement prepends newest-first', () => {
    useTickStore.getState().applyAnnouncement(makeAnnouncement({ id: 'ann-1' }))
    useTickStore.getState().applyAnnouncement(makeAnnouncement({ id: 'ann-2' }))
    expect(useTickStore.getState().announcements.map((a) => a.id)).toEqual(['ann-2', 'ann-1'])
  })

  it('setVerification stores a record keyed by alert_id', () => {
    useTickStore.getState().setVerification('a1', { status: 'verified', verifiedBy: 'officer-1' })
    expect(useTickStore.getState().verificationByAlertId['a1']).toEqual({
      status: 'verified',
      verifiedBy: 'officer-1',
    })
  })

  it('queueCitizenReport updates the store and localStorage together', () => {
    useTickStore.getState().queueCitizenReport({ category: 'Crack', note: 'test' })
    expect(useTickStore.getState().citizenReports).toHaveLength(1)
    expect(useTickStore.getState().citizenReports[0].source).toBe('simulated')
  })

  it('hydrateCitizenReports reads whatever is already in localStorage', () => {
    queueCitizenReport({ category: 'Blocked road', note: 'pre-existing' })
    useTickStore.getState().hydrateCitizenReports()
    expect(useTickStore.getState().citizenReports).toHaveLength(1)
    expect(useTickStore.getState().citizenReports[0].note).toBe('pre-existing')
  })
})
