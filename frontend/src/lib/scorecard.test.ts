import { describe, expect, it } from 'vitest'
import type { AuditEvent, RoadSegmentRisk, SettlementPriority, TickResult, VillageIsolation } from '../types/schemas'
import {
  firstEscalationTimestamps,
  hasAnyEscalationHistory,
  latestPriorityTierVillages,
  leadTimeHours,
  namedRoadSeveranceTimestamp,
  roadsFlaggedSummary,
  villagesFlaggedCount,
  whatWeWouldHaveMissedLine,
} from './scorecard'

function makeTick(overrides: Partial<TickResult> = {}): TickResult {
  return {
    t: '2024-05-28T00:00:00+05:30',
    mode: 'replay',
    scenario_id: 'aizawl-2024',
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

function makeAuditEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    event_id: 'e1',
    alert_id: 'a1',
    kind: 'AI_FLAGGED',
    actor: 'system',
    t: '2024-05-28T00:00:00+05:30',
    payload: {},
    input_hash: 'x',
    prev_hash: 'x',
    hash: 'x',
    ...overrides,
  }
}

describe('firstEscalationTimestamps / hasAnyEscalationHistory', () => {
  it('returns all-null and false when no ESCALATED events exist (the honest current-reality case)', () => {
    const ticks = [makeTick({ new_audit_events: [makeAuditEvent({ kind: 'AI_FLAGGED' })] })]
    expect(firstEscalationTimestamps(ticks)).toEqual({ YELLOW: null, ORANGE: null, RED: null })
    expect(hasAnyEscalationHistory(ticks)).toBe(false)
  })

  it('picks up the first ESCALATED event per stage, in chronological tick order', () => {
    const ticks = [
      makeTick({
        t: '2024-05-28T01:00:00+05:30',
        new_audit_events: [
          makeAuditEvent({ kind: 'ESCALATED', t: '2024-05-28T01:00:00+05:30', payload: { to_stage: 'YELLOW' } }),
        ],
      }),
      makeTick({
        t: '2024-05-28T02:00:00+05:30',
        new_audit_events: [
          makeAuditEvent({ kind: 'ESCALATED', t: '2024-05-28T02:00:00+05:30', payload: { to_stage: 'ORANGE' } }),
          makeAuditEvent({ kind: 'ESCALATED', t: '2024-05-28T02:00:00+05:30', payload: { to_stage: 'YELLOW' } }), // a second entity, later — must not overwrite the first YELLOW
        ],
      }),
      makeTick({
        t: '2024-05-28T03:00:00+05:30',
        new_audit_events: [
          makeAuditEvent({ kind: 'ESCALATED', t: '2024-05-28T03:00:00+05:30', payload: { to_stage: 'RED' } }),
        ],
      }),
    ]
    expect(firstEscalationTimestamps(ticks)).toEqual({
      YELLOW: '2024-05-28T01:00:00+05:30',
      ORANGE: '2024-05-28T02:00:00+05:30',
      RED: '2024-05-28T03:00:00+05:30',
    })
    expect(hasAnyEscalationHistory(ticks)).toBe(true)
  })

  it('ignores GREEN (the floor stage, never a meaningful "escalation")', () => {
    const ticks = [
      makeTick({ new_audit_events: [makeAuditEvent({ kind: 'ESCALATED', payload: { to_stage: 'GREEN' } })] }),
    ]
    expect(firstEscalationTimestamps(ticks)).toEqual({ YELLOW: null, ORANGE: null, RED: null })
  })
})

describe('latestPriorityTierVillages / villagesFlaggedCount', () => {
  const priority = (id: string, tier: SettlementPriority['tier']): SettlementPriority => ({
    village_id: id,
    eps: 0.8,
    tier,
    components: {},
  })
  const isolation = (id: string, name: string): VillageIsolation => ({
    village_id: id,
    name,
    population: 500,
    p_isolated: 0.5,
    isolated_now: false,
    alternate_route_exists: true,
    est_duration_hours: null,
    severed_links: [],
  })

  it('returns an empty list and 0 for no ticks', () => {
    expect(latestPriorityTierVillages([], 'P1')).toEqual([])
    expect(villagesFlaggedCount([])).toBe(0)
  })

  it('uses only the LATEST tick (a live snapshot, not accumulated across the run)', () => {
    const ticks = [
      makeTick({ priorities: [priority('v1', 'P1')], isolations: [isolation('v1', 'Durtlang')] }),
      makeTick({ priorities: [priority('v1', 'P3')], isolations: [isolation('v1', 'Durtlang')] }),
    ]
    expect(latestPriorityTierVillages(ticks, 'P1')).toEqual([])
    expect(latestPriorityTierVillages(ticks, 'P3').map((v) => v.villageId)).toEqual(['v1'])
    expect(villagesFlaggedCount(ticks)).toBe(1)
  })
})

describe('roadsFlaggedSummary', () => {
  const road = (overrides: Partial<RoadSegmentRisk> = {}): RoadSegmentRisk => ({
    edge_id: 'e1',
    name: 'NH-6',
    highway_class: 'trunk',
    is_bridge: false,
    p_blocked: 0.9,
    severed: true,
    contributing_cells: [],
    ...overrides,
  })

  it('returns zeros for no ticks', () => {
    expect(roadsFlaggedSummary([])).toEqual({ flaggedCount: 0, severedCount: 0, severedNames: [] })
  })

  it('counts flagged (p_blocked > 0) vs. severed roads from the latest tick, deduping severed names', () => {
    const ticks = [
      makeTick({
        road_risks: [
          road({ edge_id: 'e1', name: 'NH-6', p_blocked: 0.9, severed: true }),
          road({ edge_id: 'e2', name: 'NH-6', p_blocked: 0.9, severed: true }), // same road, two segments
          road({ edge_id: 'e3', name: 'SH-12', p_blocked: 0.1, severed: false }),
          road({ edge_id: 'e4', name: null, p_blocked: 0, severed: false }),
        ],
      }),
    ]
    const summary = roadsFlaggedSummary(ticks)
    expect(summary.flaggedCount).toBe(3)
    expect(summary.severedCount).toBe(2)
    expect(summary.severedNames).toEqual(['NH-6'])
  })
})

describe('namedRoadSeveranceTimestamp', () => {
  it('returns null when no matching road is ever severed', () => {
    const ticks = [makeTick({ road_risks: [{ edge_id: 'e1', name: 'NH-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.1, severed: false, contributing_cells: [] }] })]
    expect(namedRoadSeveranceTimestamp(ticks, 'NH-6')).toBeNull()
  })

  it('returns the first tick (chronologically) where a matching road is severed, case-insensitively', () => {
    const ticks = [
      makeTick({ t: 't1', road_risks: [{ edge_id: 'e1', name: 'nh-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.4, severed: false, contributing_cells: [] }] }),
      makeTick({ t: 't2', road_risks: [{ edge_id: 'e1', name: 'nh-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.95, severed: true, contributing_cells: [] }] }),
      makeTick({ t: 't3', road_risks: [{ edge_id: 'e1', name: 'nh-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.95, severed: true, contributing_cells: [] }] }),
    ]
    expect(namedRoadSeveranceTimestamp(ticks, 'NH-6')).toEqual({ t: 't2', edgeId: 'e1', name: 'nh-6' })
  })
})

describe('leadTimeHours', () => {
  it('returns null when either timestamp is missing', () => {
    expect(leadTimeHours(null, '2024-05-28T07:00:00+05:30')).toBeNull()
    expect(leadTimeHours('2024-05-28T05:00:00+05:30', null)).toBeNull()
  })

  it('is positive when the predicted time is BEFORE the actual time (real lead time)', () => {
    const hours = leadTimeHours('2024-05-28T05:00:00+05:30', '2024-05-28T07:00:00+05:30')
    expect(hours).toBeCloseTo(2)
  })

  it('is negative when the predicted time is AFTER the actual time (we were late)', () => {
    const hours = leadTimeHours('2024-05-28T08:00:00+05:30', '2024-05-28T07:00:00+05:30')
    expect(hours).toBeCloseTo(-1)
  })
})

describe('whatWeWouldHaveMissedLine', () => {
  it('states the escalation-integration gap plainly when there is no escalation history (current reality)', () => {
    const line = whatWeWouldHaveMissedLine({
      hasEscalationHistory: false,
      roadSeverance: null,
      groundTruthRoadEvent: null,
    })
    expect(line).toMatch(/decision\/escalation\.py/)
    expect(line).toMatch(/not been wired/)
  })

  it('reports a real lead-time comparison when both a prediction and ground truth exist', () => {
    const line = whatWeWouldHaveMissedLine({
      hasEscalationHistory: true,
      roadSeverance: { t: '2024-05-28T05:00:00+05:30', edgeId: 'e1', name: 'NH-6' },
      groundTruthRoadEvent: { t: '2024-05-28T07:00:00+05:30', road: 'NH-6' },
    })
    expect(line).toMatch(/NH-6/)
    expect(line).toMatch(/2\.0h ahead of/)
  })

  it('falls back to an honest "no match" line without implying nothing would have been caught', () => {
    const line = whatWeWouldHaveMissedLine({
      hasEscalationHistory: true,
      roadSeverance: null,
      groundTruthRoadEvent: null,
    })
    expect(line).toMatch(/incomplete/)
    expect(line).toMatch(/not as evidence/i)
  })
})
