import type { AuditEvent } from '../types/schemas'

/**
 * BUILD_PLAN.md task 3.8 — the Audit Trail view: "a vertical timeline per alert — AI Flagged ->
 * DDMA Approved -> Disseminated -> Village Acknowledged, with real timestamps."
 *
 * `GET /api/audit/{alert_id}` (backend/app/api/routes.py) returns exactly the real events an
 * `AuditLog` has recorded for one `alert_id`, in append (chronological) order — this module never
 * invents an event kind or a timestamp; it only labels/orders what the API actually returned and
 * says which of the four canonical stages have not been reached yet.
 *
 * KNOWN, PRE-EXISTING NAMESPACE GAP (documented, not fixed here — out of this task's scope):
 * `pipeline.py`'s own `AI_FLAGGED` event uses a TICK-scoped `alert_id`
 * (`tick-{aoi_id}-{t.isoformat()}`), while `decision/stub.py`'s `ActionCard.alert_id` (what
 * `DDMA_APPROVED`/`DISSEMINATED`/`VILLAGE_ACKNOWLEDGED` all key off) is VILLAGE-scoped
 * (`alert-{village_id}-{t.isoformat()}`). The two ids do not match for the same real-world
 * event, so looking up an `ActionCard`'s `alert_id` will show its own DDMA/dissemination/
 * acknowledgement chain but will not surface the originating `AI_FLAGGED` tick event under that
 * same id — `api/routes.py::get_audit_trail`'s own docstring already flags this. This module
 * renders whatever the API actually returns and marks AI Flagged as "not yet reached" in that
 * case, rather than fabricating a matching event.
 */

export interface CanonicalStage {
  label: string
  kinds: AuditEvent['kind'][]
}

export const CANONICAL_STAGES: CanonicalStage[] = [
  { label: 'AI Flagged', kinds: ['AI_FLAGGED'] },
  { label: 'DDMA Decision', kinds: ['DDMA_APPROVED', 'STOOD_DOWN'] },
  { label: 'Disseminated', kinds: ['DISSEMINATED'] },
  { label: 'Village Acknowledged', kinds: ['VILLAGE_ACKNOWLEDGED'] },
]

/** Canonical stages with no matching event kind present anywhere in `events` — rendered as
 * grayed-out "not yet reached" rows rather than silently omitted, so the timeline always shows
 * the full glossary sequence even when the chain hasn't reached the end. */
export function missingStages(events: AuditEvent[]): CanonicalStage[] {
  const present = new Set(events.map((e) => e.kind))
  return CANONICAL_STAGES.filter((stage) => !stage.kinds.some((k) => present.has(k)))
}

export function eventLabel(kind: AuditEvent['kind']): string {
  switch (kind) {
    case 'AI_FLAGGED':
      return 'AI Flagged'
    case 'DDMA_APPROVED':
      return 'DDMA Approved'
    case 'STOOD_DOWN':
      return 'Stood Down (rejected)'
    case 'DISSEMINATED':
      return 'Disseminated'
    case 'DELIVERED':
      return 'Delivered'
    case 'VILLAGE_ACKNOWLEDGED':
      return 'Village Acknowledged'
    case 'ESCALATED':
      return 'Escalated'
    default:
      return kind
  }
}

/** A short, human-readable summary of one event's real payload — e.g. CLAUDE.md's own example
 * ("847/1,020 handsets acknowledged") for DISSEMINATED — never a raw JSON dump. Falls back to a
 * generic key:value rendering for payload shapes this function doesn't special-case, so nothing
 * is silently hidden even for an event kind added later. */
export function eventSummary(event: AuditEvent): string {
  const p = event.payload as Record<string, unknown>
  switch (event.kind) {
    case 'AI_FLAGGED':
      return `${p.aoi_id ?? 'AOI'} · ${p.cell_count ?? '?'} cells · max p_fail ${
        typeof p.max_p_fail === 'number' ? (p.max_p_fail * 100).toFixed(0) + '%' : '?'
      } · ${p.action_cards_issued ?? 0} action card(s) issued`
    case 'DDMA_APPROVED':
    case 'STOOD_DOWN':
      return `${p.decision ?? '?'} by ${event.actor}${p.notes ? ` — "${p.notes}"` : ''}`
    case 'DISSEMINATED':
      return `${p.total_acknowledged ?? 0}/${p.total_recipients ?? 0} recipients acknowledged over ${
        Array.isArray(p.channels) ? p.channels.join(', ') : 'simulated channels'
      } (${p.total_delivered ?? 0} delivered)`
    case 'VILLAGE_ACKNOWLEDGED':
      return `Acknowledged by ${event.actor}`
    case 'ESCALATED':
      return `-> ${p.to_stage ?? '?'}`
    default:
      return Object.entries(p)
        .map(([k, v]) => `${k}: ${String(v)}`)
        .join(', ')
  }
}
