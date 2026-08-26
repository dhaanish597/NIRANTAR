import { mergeVillageDisplay, type VillageDisplayRecord } from './priorityDetail'
import type { EscalationStage, TickResult } from '../types/schemas'

/**
 * Pure functions backing `CounterfactualScorecard` (BUILD_PLAN.md task 4.10 — "the closing
 * artifact of every replay"). Derives every "what our system produced" fact from real
 * `TickResult`s the frontend actually received during the current replay run
 * (`useTickStore.replayTicks`) — nothing here invents a number. See the module's own functions
 * for what is and isn't available today (most notably `firstEscalationTimestamps`, which is
 * honestly empty until a separate backend integration lands — see its docstring).
 */

export type EscalationStageTimestamps = Record<'YELLOW' | 'ORANGE' | 'RED', string | null>

function stageFromPayload(payload: Record<string, unknown>): EscalationStage | null {
  const value = payload['to_stage']
  return value === 'GREEN' || value === 'YELLOW' || value === 'ORANGE' || value === 'RED'
    ? value
    : null
}

/**
 * First tick timestamp at which ANY entity reached Yellow/Orange/Red, read from real
 * `AuditEvent`s of kind `ESCALATED` (`payload.to_stage`, the exact shape
 * `backend/app/decision/escalation.py` writes — see that module for the payload contract).
 *
 * HONESTY NOTE (this is the gap this agent's task brief explicitly flagged): `decision/
 * escalation.py` (BUILD_PLAN.md task 3.2) is real and tested, but `pipeline.py` still calls
 * `decision/stub.py`, not it — no `ESCALATED` audit event is emitted by the live pipeline today,
 * confirmed by reading `backend/app/pipeline.py` directly (it imports `decision.stub`, never
 * `decision.escalation`). So this function will genuinely return `{YELLOW: null, ORANGE: null,
 * RED: null}` for every real replay right now. It is written against the REAL payload shape
 * `escalation.py` already produces (`entity_id`/`p_fail`/`from_stage`/`to_stage`/`from_label`/
 * `to_label`), so the moment a future session wires `decision/escalation.py` into `pipeline.py`,
 * this starts returning real timestamps with no UI or lib change required — exactly the "no UI
 * changes needed then" outcome this agent's brief asked for.
 */
export function firstEscalationTimestamps(ticks: TickResult[]): EscalationStageTimestamps {
  const found: Partial<EscalationStageTimestamps> = {}
  for (const tick of ticks) {
    for (const event of tick.new_audit_events) {
      if (event.kind !== 'ESCALATED') continue
      const stage = stageFromPayload(event.payload)
      if (!stage || stage === 'GREEN') continue
      if (!found[stage]) found[stage] = event.t
    }
  }
  return { YELLOW: found.YELLOW ?? null, ORANGE: found.ORANGE ?? null, RED: found.RED ?? null }
}

export function hasAnyEscalationHistory(ticks: TickResult[]): boolean {
  return ticks.some((tick) => tick.new_audit_events.some((event) => event.kind === 'ESCALATED'))
}

/** Villages in the requested EPS tier as of the LATEST tick of the run — a live "P1 evacuation
 * list" snapshot, not accumulated across the whole run (a village that was briefly P1 and later
 * downgraded should not still appear as if it still is). Reuses
 * `lib/priorityDetail.ts::mergeVillageDisplay` rather than re-deriving the priorities/isolations
 * join. */
export function latestPriorityTierVillages(
  ticks: TickResult[],
  tier: 'P1' | 'P2' | 'P3',
): VillageDisplayRecord[] {
  const last = ticks[ticks.length - 1]
  if (!last) return []
  return mergeVillageDisplay(last.priorities, last.isolations).filter((v) => v.tier === tier)
}

/** Count of settlements in the ranked priority list as of the latest tick — every tier, not just
 * P1 ("N villages flagged"). */
export function villagesFlaggedCount(ticks: TickResult[]): number {
  const last = ticks[ticks.length - 1]
  return last ? last.priorities.length : 0
}

export interface RoadsFlaggedSummary {
  flaggedCount: number
  severedCount: number
  severedNames: string[]
}

/**
 * Road segments with any predicted blockage risk, as of the latest tick. `RoadSegmentRisk`
 * (backend/app/schemas/impact.py) has no length/geometry field, so "M km of road flagged"
 * (BUILD_PLAN.md task 4.10's literal wording) cannot be computed from real data — reporting a
 * segment count instead of guessing a length is the honest option; `CounterfactualScorecard`
 * says so explicitly rather than silently omitting the unit.
 */
export function roadsFlaggedSummary(ticks: TickResult[]): RoadsFlaggedSummary {
  const last = ticks[ticks.length - 1]
  if (!last) return { flaggedCount: 0, severedCount: 0, severedNames: [] }
  const flagged = last.road_risks.filter((r) => r.p_blocked > 0)
  const severed = last.road_risks.filter((r) => r.severed)
  const severedNames = [...new Set(severed.map((r) => r.name ?? r.edge_id))]
  return { flaggedCount: flagged.length, severedCount: severed.length, severedNames }
}

export interface RoadSeveranceEvent {
  t: string
  edgeId: string
  name: string | null
}

/** First tick (in chronological run order) at which a road whose `name` contains `nameSubstring`
 * (case-insensitive — e.g. "NH-6") was reported `severed`. This is real data the current
 * pipeline DOES produce (even `impact/stub.py`'s Phase 0 stub emits a road literally named
 * "NH-6" and flips `severed` once average p_fail crosses its severance threshold), unlike the
 * escalation-stage history above. */
export function namedRoadSeveranceTimestamp(
  ticks: TickResult[],
  nameSubstring: string,
): RoadSeveranceEvent | null {
  const needle = nameSubstring.toLowerCase()
  for (const tick of ticks) {
    for (const road of tick.road_risks) {
      if (road.severed && road.name && road.name.toLowerCase().includes(needle)) {
        return { t: tick.t, edgeId: road.edge_id, name: road.name }
      }
    }
  }
  return null
}

/** Hours between a predicted timestamp and an actual (ground-truth) timestamp. Positive means we
 * predicted BEFORE the actual event (real lead time); negative means we were late. Returns null
 * if either timestamp is missing or unparseable — callers must not fabricate a number. */
export function leadTimeHours(predictedIso: string | null, actualIso: string | null): number | null {
  if (!predictedIso || !actualIso) return null
  const predicted = Date.parse(predictedIso)
  const actual = Date.parse(actualIso)
  if (Number.isNaN(predicted) || Number.isNaN(actual)) return null
  return (actual - predicted) / 3_600_000
}

/**
 * BUILD_PLAN.md task 4.10's required "one honest line: what we would have missed."
 *
 * Composed dynamically from what this run's real data shows, in preference order:
 *   1. If no escalation-stage history exists at all (true for every replay today — see
 *      `firstEscalationTimestamps`'s docstring), say so plainly rather than comparing against a
 *      timestamp that was never produced.
 *   2. If a named road severance WAS detected and the scenario's ground truth has a matching
 *      road event, report the real lead/lag time between them.
 *   3. Otherwise, an honest "no match found in this run" fallback that does not imply nothing
 *      would have been caught — only that this particular run/scenario didn't produce a
 *      comparable data point.
 */
export function whatWeWouldHaveMissedLine(params: {
  hasEscalationHistory: boolean
  roadSeverance: RoadSeveranceEvent | null
  groundTruthRoadEvent: { t: string; road: string } | null
}): string {
  const { hasEscalationHistory, roadSeverance, groundTruthRoadEvent } = params

  if (!hasEscalationHistory) {
    return (
      "Escalation-stage lead time (first Yellow/Orange/Red) can't be honestly shown yet: " +
      'decision/escalation.py (BUILD_PLAN.md task 3.2) is real and tested, but the live pipeline ' +
      "(pipeline.py) still runs Phase 0's decision stub and has not been wired to it — a known " +
      'backend integration gap, not a hidden limitation. It will populate here automatically, ' +
      'with no UI changes, once that wiring lands.'
    )
  }

  if (roadSeverance && groundTruthRoadEvent) {
    const hours = leadTimeHours(roadSeverance.t, groundTruthRoadEvent.t)
    if (hours !== null) {
      const direction =
        hours >= 0
          ? `${hours.toFixed(1)}h ahead of`
          : `${Math.abs(hours).toFixed(1)}h behind`
      return (
        `Our system flagged ${roadSeverance.name ?? roadSeverance.edgeId} as severed ${direction} ` +
        `the official ${groundTruthRoadEvent.road} severance recorded at ` +
        `${new Date(groundTruthRoadEvent.t).toLocaleString()}.`
      )
    }
  }

  return (
    'No road-severance prediction in this run lines up with a ground-truth road event to compare ' +
    "against — treat this replay's system output as incomplete for this comparison, not as " +
    'evidence that nothing would have been caught.'
  )
}
