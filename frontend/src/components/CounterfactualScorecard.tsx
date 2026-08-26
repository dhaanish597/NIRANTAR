import { deathTollInfo, getScenarioDetail } from '../lib/scenarioDetails'
import {
  firstEscalationTimestamps,
  hasAnyEscalationHistory,
  latestPriorityTierVillages,
  leadTimeHours,
  namedRoadSeveranceTimestamp,
  roadsFlaggedSummary,
  villagesFlaggedCount,
  whatWeWouldHaveMissedLine,
} from '../lib/scorecard'
import { useTickStore } from '../store/useTickStore'

/**
 * BUILD_PLAN.md task 4.10 — the Counterfactual Lead-Time Scorecard, "the closing artifact of
 * every replay": what actually happened (a scenario's real `ground_truth`) next to what our
 * system produced (derived from real `TickResult`s received during the run — see
 * `lib/scorecard.ts`), plus one honest "what we would have missed" line.
 *
 * Opened via a button (ReplayControlBar, "Scorecard") rather than auto-popping at some inferred
 * "replay finished" moment — `scorecardOpen` lives on the store (same pattern as
 * `selectedVillageId`) so it stays open/reachable even after "Return to Live" is pressed, letting
 * a presenter pull it up right when the demo script (docs/DEMO_SCRIPT.md beat 9) wants it.
 *
 * HONESTY NOTE (see `lib/scorecard.ts` for the full reasoning): the "what our system produced"
 * escalation-stage row is genuinely empty right now — `decision/escalation.py`'s real
 * stage-transition events are not wired into the live pipeline yet. This panel says so plainly
 * instead of fabricating placeholder timestamps, per this agent's explicit brief.
 */
export function CounterfactualScorecard() {
  const open = useTickStore((s) => s.scorecardOpen)
  const close = useTickStore((s) => s.closeScorecard)
  const replayTicks = useTickStore((s) => s.replayTicks)
  const modeState = useTickStore((s) => s.modeState)
  const latestTick = useTickStore((s) => s.latestTick)

  if (!open) return null

  const scenarioId = latestTick?.scenario_id ?? modeState?.scenario_id ?? null
  const detail = scenarioId ? getScenarioDetail(scenarioId) : undefined
  const deathToll = deathTollInfo(detail)
  const warning = detail?.ground_truth?.official_warnings?.[0]
  const groundTruthRoadEvent = detail?.ground_truth?.road_events?.[0]

  const escalation = firstEscalationTimestamps(replayTicks)
  const hasEscalation = hasAnyEscalationHistory(replayTicks)
  const p1 = latestPriorityTierVillages(replayTicks, 'P1')
  const nVillages = villagesFlaggedCount(replayTicks)
  const roads = roadsFlaggedSummary(replayTicks)
  const roadNameToTrack = groundTruthRoadEvent?.road ?? 'NH-6'
  const severance = namedRoadSeveranceTimestamp(replayTicks, roadNameToTrack)
  const severanceLead = severance ? leadTimeHours(severance.t, groundTruthRoadEvent?.t ?? null) : null

  const missedLine = whatWeWouldHaveMissedLine({
    hasEscalationHistory: hasEscalation,
    roadSeverance: severance,
    groundTruthRoadEvent: groundTruthRoadEvent
      ? { t: groundTruthRoadEvent.t, road: groundTruthRoadEvent.road }
      : null,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={close}>
      <div
        className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg border border-white/10 bg-slate-900 p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">Counterfactual Lead-Time Scorecard</h2>
            <p className="text-xs text-slate-400">{detail?.name ?? scenarioId ?? 'No scenario'}</p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close scorecard"
            className="rounded px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        {replayTicks.length === 0 && (
          <p className="mb-4 text-sm text-slate-500">
            No replay tick data captured yet for this run — run a case study first (Run Case
            Study → pick a scenario). This panel populates from real ticks received during a
            replay, not from any fabricated placeholder.
          </p>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section className="rounded border border-white/10 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              What actually happened
            </h3>
            {!detail?.ground_truth && (
              <p className="text-sm text-slate-500">
                No <code>ground_truth</code> block on this scenario (e.g. <code>_smoke</code> is
                fabricated and carries none).
              </p>
            )}
            {warning && (
              <p className="mb-2 text-sm text-slate-300">
                Official warning: <span className="font-medium">{warning.level}</span> by{' '}
                {warning.issuer} at {new Date(warning.t).toLocaleString()}
                {warning.spatial_scale ? ` (${warning.spatial_scale} scale)` : ''}
                {warning.note ? ` — "${warning.note}"` : ''}
              </p>
            )}
            {groundTruthRoadEvent && (
              <p className="mb-2 text-sm text-slate-300">
                Road event: {groundTruthRoadEvent.road} {groundTruthRoadEvent.effect} at{' '}
                {new Date(groundTruthRoadEvent.t).toLocaleString()}
                {groundTruthRoadEvent.consequence ? ` — ${groundTruthRoadEvent.consequence}` : ''}
              </p>
            )}
            {deathToll && (
              <p className="text-sm text-slate-300">
                Outcome: {deathToll.deaths}
                {deathToll.sourceNote && (
                  <span className="text-slate-500"> — {deathToll.sourceNote}</span>
                )}
              </p>
            )}
          </section>

          <section className="rounded border border-white/10 p-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              What our system produced
            </h3>

            <dl className="mb-2 grid grid-cols-2 gap-x-2 gap-y-1 text-sm">
              <dt className="text-slate-400">First Yellow</dt>
              <dd className="text-slate-200">
                {escalation.YELLOW ? new Date(escalation.YELLOW).toLocaleString() : 'not yet available'}
              </dd>
              <dt className="text-slate-400">First Orange</dt>
              <dd className="text-slate-200">
                {escalation.ORANGE ? new Date(escalation.ORANGE).toLocaleString() : 'not yet available'}
              </dd>
              <dt className="text-slate-400">First Red</dt>
              <dd className="text-slate-200">
                {escalation.RED ? new Date(escalation.RED).toLocaleString() : 'not yet available'}
              </dd>
            </dl>
            {!hasEscalation && (
              <p className="mb-2 text-[11px] text-slate-500">
                Escalation history not yet available for this replay — decision/escalation.py
                (task 3.2) is not wired into the live pipeline yet. This is a backend integration
                gap, not a data problem with this scenario.
              </p>
            )}

            <p className="mb-1 text-sm text-slate-300">
              P1 evacuation list:{' '}
              {p1.length === 0
                ? 'none (as of the latest tick)'
                : p1.map((v) => v.name ?? v.villageId).join(', ')}
            </p>
            <p className="mb-1 text-sm text-slate-300">{nVillages} villages flagged (any tier)</p>
            <p className="mb-1 text-sm text-slate-300">
              {roads.flaggedCount} road segments flagged, {roads.severedCount} severed
              {roads.severedNames.length > 0 ? ` (${roads.severedNames.join(', ')})` : ''} —
              segment length isn&apos;t in the current road schema, so this is a segment count,
              not km.
            </p>
            <p className="text-sm text-slate-300">
              {roadNameToTrack} severance predicted at:{' '}
              {severance ? (
                <>
                  {new Date(severance.t).toLocaleString()}
                  {severanceLead !== null &&
                    ` (${severanceLead >= 0 ? severanceLead.toFixed(1) + 'h ahead of' : Math.abs(severanceLead).toFixed(1) + 'h behind'} the official time)`}
                </>
              ) : (
                'not predicted in this run'
              )}
            </p>
          </section>
        </div>

        <section className="mt-4 rounded border border-amber-500/30 bg-amber-500/5 p-3">
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-400">
            What we would have missed
          </h3>
          <p className="text-sm text-slate-200">{missedLine}</p>
        </section>
      </div>
    </div>
  )
}
