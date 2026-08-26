import { describe, expect, it } from 'vitest'
import type { AuditEvent } from '../types/schemas'
import { CANONICAL_STAGES, eventLabel, eventSummary, missingStages } from './auditTrail'

function makeEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    event_id: 'e1',
    alert_id: 'a1',
    kind: 'AI_FLAGGED',
    actor: 'system',
    t: '2026-05-28T03:14:00+00:00',
    payload: {},
    input_hash: 'x',
    prev_hash: 'y',
    hash: 'z',
    ...overrides,
  }
}

describe('missingStages', () => {
  it('reports all four canonical stages missing for an empty chain', () => {
    expect(missingStages([]).map((s) => s.label)).toEqual(CANONICAL_STAGES.map((s) => s.label))
  })

  it('marks AI Flagged present once an AI_FLAGGED event exists, others still missing', () => {
    const missing = missingStages([makeEvent({ kind: 'AI_FLAGGED' })])
    expect(missing.map((s) => s.label)).toEqual([
      'DDMA Decision',
      'Disseminated',
      'Village Acknowledged',
    ])
  })

  it('treats STOOD_DOWN as satisfying the "DDMA Decision" stage (a real rejection, not a gap)', () => {
    const missing = missingStages([makeEvent({ kind: 'STOOD_DOWN' })])
    expect(missing.map((s) => s.label)).not.toContain('DDMA Decision')
  })

  it('reports no missing stages once all four are present', () => {
    const events = [
      makeEvent({ kind: 'AI_FLAGGED' }),
      makeEvent({ kind: 'DDMA_APPROVED' }),
      makeEvent({ kind: 'DISSEMINATED' }),
      makeEvent({ kind: 'VILLAGE_ACKNOWLEDGED' }),
    ]
    expect(missingStages(events)).toEqual([])
  })
})

describe('eventLabel', () => {
  it('gives a human label for every real audit event kind', () => {
    expect(eventLabel('AI_FLAGGED')).toBe('AI Flagged')
    expect(eventLabel('DDMA_APPROVED')).toBe('DDMA Approved')
    expect(eventLabel('STOOD_DOWN')).toBe('Stood Down (rejected)')
    expect(eventLabel('DISSEMINATED')).toBe('Disseminated')
    expect(eventLabel('VILLAGE_ACKNOWLEDGED')).toBe('Village Acknowledged')
  })
})

describe('eventSummary', () => {
  it('summarizes DISSEMINATED using the real recipient/delivered/acknowledged counts (CLAUDE.md-style)', () => {
    const summary = eventSummary(
      makeEvent({
        kind: 'DISSEMINATED',
        payload: {
          total_recipients: 1020,
          total_delivered: 950,
          total_acknowledged: 847,
          channels: ['cell_broadcast', 'sms'],
        },
      }),
    )
    expect(summary).toContain('847/1020')
    expect(summary).toContain('cell_broadcast')
  })

  it('summarizes DDMA_APPROVED with the decision and actor', () => {
    const summary = eventSummary(
      makeEvent({ kind: 'DDMA_APPROVED', actor: 'ddma:officer_1', payload: { decision: 'approved' } }),
    )
    expect(summary).toContain('approved')
    expect(summary).toContain('ddma:officer_1')
  })

  it('summarizes VILLAGE_ACKNOWLEDGED with the actor', () => {
    const summary = eventSummary(makeEvent({ kind: 'VILLAGE_ACKNOWLEDGED', actor: 'village:v1' }))
    expect(summary).toContain('village:v1')
  })

  it('never throws on an unrecognized payload shape (generic fallback)', () => {
    expect(() =>
      eventSummary(makeEvent({ kind: 'ESCALATED', payload: { to_stage: 'RED' } })),
    ).not.toThrow()
  })
})
