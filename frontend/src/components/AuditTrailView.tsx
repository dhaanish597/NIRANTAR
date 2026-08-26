import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { CANONICAL_STAGES, eventLabel, eventSummary, missingStages } from '../lib/auditTrail'
import { useTickStore } from '../store/useTickStore'
import type { AuditEvent } from '../types/schemas'

/**
 * BUILD_PLAN.md task 3.8 — the Audit Trail view: "a vertical timeline per alert ... This slide
 * sells the whole product." Fetches the real chain via `GET /api/audit/{alert_id}`
 * (`api.getAuditTrail`) and renders exactly what it returns — no fabricated event kind or
 * timestamp, ever (see `lib/auditTrail.ts`'s own docstring for the one pre-existing, documented
 * alert_id-namespace caveat this inherits from the backend).
 *
 * Opened via `useTickStore.openAuditTrail(alertId)` from wherever a real `alert_id` is at hand
 * (a DDMA Console recommendation row, a Village View action card) — same store-owned-modal
 * pattern `scorecardOpen`/`selectedVillageId` already establish. A manual alert-id lookup box is
 * included so the trail for any alert can be inspected directly (useful for the demo/rehearsal,
 * and for verifying the chain without relying on another screen's click-through).
 */
export function AuditTrailView() {
  const storeAlertId = useTickStore((s) => s.auditTrailAlertId)
  const close = useTickStore((s) => s.closeAuditTrail)

  // A manual lookup overrides the store's alert_id locally; it resets whenever the STORE opens a
  // *different* alert_id (a fresh "open" from a DDMA Console row / Village View click should win
  // over a stale manual lookup from last time the modal was open). Derived during render — React's
  // own documented pattern for "reset state when a prop/store value changes" — rather than a
  // `useEffect` that calls `setState` synchronously, which is an unnecessary extra render and the
  // pattern this file's own lint pass (`npm run lint`) flags as `react(set-state-in-effect)`.
  const [manualAlertId, setManualAlertId] = useState<string | null>(null)
  const [syncedStoreAlertId, setSyncedStoreAlertId] = useState(storeAlertId)
  const [lookupDraft, setLookupDraft] = useState(storeAlertId ?? '')
  if (storeAlertId !== syncedStoreAlertId) {
    setSyncedStoreAlertId(storeAlertId)
    setManualAlertId(null)
    setLookupDraft(storeAlertId ?? '')
  }
  const activeId = manualAlertId ?? storeAlertId

  const [events, setEvents] = useState<AuditEvent[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A genuine external-system fetch — GET /api/audit/{alert_id} — belongs in an effect, unlike
  // the pure local-state sync above.
  useEffect(() => {
    if (activeId === null) return
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .getAuditTrail(activeId)
      .then((data) => {
        if (!cancelled) setEvents(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeId])

  if (storeAlertId === null) return null

  const handleLookup = () => {
    if (lookupDraft.trim().length === 0) return
    setManualAlertId(lookupDraft.trim())
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={close}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-white/10 bg-slate-900 p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Audit Trail</h2>
            <p className="text-xs text-slate-400">
              AI Flagged → DDMA Approved → Disseminated → Village Acknowledged
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close audit trail"
            className="rounded px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        <div className="mb-4 flex items-center gap-2">
          <input
            type="text"
            value={lookupDraft}
            onChange={(event) => setLookupDraft(event.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && handleLookup()}
            placeholder="alert_id"
            aria-label="Alert ID"
            className="flex-1 rounded border border-white/10 bg-white/5 px-2 py-1.5 text-sm text-slate-200"
          />
          <button
            type="button"
            onClick={handleLookup}
            className="rounded bg-white/10 px-3 py-1.5 text-sm font-semibold hover:bg-white/20"
          >
            Look up
          </button>
        </div>

        {loading && <p className="text-sm text-slate-500">Loading…</p>}
        {error && (
          <p className="text-sm text-red-300">Could not load GET /api/audit/{activeId}: {error}</p>
        )}

        {events && events.length === 0 && !loading && (
          <p className="text-sm text-slate-500">
            No audit events recorded yet for <code className="text-slate-400">{activeId}</code> —
            not a fabricated timeline, this is a genuinely empty real chain (200, empty list, per
            <code className="ml-1 text-slate-400">GET /api/audit/&#123;alert_id&#125;</code>&apos;s
            own documented behaviour).
          </p>
        )}

        {events && events.length > 0 && (
          <ol className="relative ml-3 space-y-4 border-l border-white/15 pl-5">
            {events.map((event) => (
              <TimelineEvent key={event.event_id} event={event} />
            ))}
            {missingStages(events).map((stage) => (
              <TimelineGap key={stage.label} label={stage.label} />
            ))}
          </ol>
        )}

        {!events && !loading && !error && (
          <ol className="relative ml-3 space-y-2 border-l border-white/10 pl-5 opacity-50">
            {CANONICAL_STAGES.map((stage) => (
              <li key={stage.label} className="text-sm text-slate-500">
                {stage.label}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

function TimelineEvent({ event }: { event: AuditEvent }) {
  return (
    <li className="relative">
      <span
        className={`absolute top-1 -left-[27px] h-3 w-3 rounded-full border-2 border-slate-900 ${dotColor(event.kind)}`}
        aria-hidden="true"
      />
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-100">{eventLabel(event.kind)}</span>
        <span className="text-xs text-slate-400">{new Date(event.t).toLocaleString()}</span>
      </div>
      <p className="mt-0.5 text-xs text-slate-400">{eventSummary(event)}</p>
      <p className="mt-0.5 font-mono text-[10px] text-slate-600">actor: {event.actor}</p>
    </li>
  )
}

function TimelineGap({ label }: { label: string }) {
  return (
    <li className="relative">
      <span
        className="absolute top-1 -left-[27px] h-3 w-3 rounded-full border-2 border-slate-900 bg-slate-700"
        aria-hidden="true"
      />
      <span className="text-sm text-slate-500">{label} — not yet reached</span>
    </li>
  )
}

function dotColor(kind: AuditEvent['kind']): string {
  switch (kind) {
    case 'AI_FLAGGED':
      return 'bg-amber-500'
    case 'ESCALATED':
      return 'bg-orange-500'
    case 'DDMA_APPROVED':
      return 'bg-emerald-500'
    case 'STOOD_DOWN':
      return 'bg-slate-500'
    case 'DISSEMINATED':
      return 'bg-sky-500'
    case 'DELIVERED':
      return 'bg-sky-400'
    case 'VILLAGE_ACKNOWLEDGED':
      return 'bg-emerald-400'
    default:
      return 'bg-slate-500'
  }
}
