/**
 * BUILD_PLAN.md task 5.8 — pure derivation of the what-if simulator's on-screen summary
 * ("the resulting failure distribution, road severance and isolation cascade") from a real
 * `WhatIfResult` (`POST /api/whatif/simulate`, `backend/app/api/whatif.py`). No fabricated
 * numbers — every field here is counted directly off the real `TickResult` a throwaway backend
 * `Pipeline` produced for the simulated rainfall.
 */
import { escalationStage } from './escalation'
import type { EscalationStage, WhatIfResult } from '../types/schemas'

export interface FailureDistributionBucket {
  stage: EscalationStage
  count: number
}

/** Buckets every simulated cell's `p_fail` into the SAME real escalation stages (and thresholds)
 * the rest of the app already uses (`lib/escalation.ts::escalationStage`, which mirrors
 * `config.EscalationConfig`'s real 0.25/0.5/0.75 cutoffs) — not a separately invented banding. */
export function failureDistribution(result: WhatIfResult): FailureDistributionBucket[] {
  const counts: Record<EscalationStage, number> = { GREEN: 0, YELLOW: 0, ORANGE: 0, RED: 0 }
  for (const risk of result.tick.cell_risks) {
    counts[escalationStage(risk.p_fail)] += 1
  }
  return (['GREEN', 'YELLOW', 'ORANGE', 'RED'] as const).map((stage) => ({
    stage,
    count: counts[stage],
  }))
}

export interface WhatIfSummary {
  totalCells: number
  distribution: FailureDistributionBucket[]
  severedRoadCount: number
  totalRoadCount: number
  isolatedVillageCount: number
  totalVillageCount: number
  isolatedVillageNames: string[]
  actionCardCount: number
}

export function summarizeWhatIf(result: WhatIfResult): WhatIfSummary {
  const severedRoadCount = result.tick.road_risks.filter((r) => r.severed).length
  const isolatedVillages = result.tick.isolations.filter((v) => v.isolated_now)
  return {
    totalCells: result.tick.cell_risks.length,
    distribution: failureDistribution(result),
    severedRoadCount,
    totalRoadCount: result.tick.road_risks.length,
    isolatedVillageCount: isolatedVillages.length,
    totalVillageCount: result.tick.isolations.length,
    isolatedVillageNames: isolatedVillages.map((v) => v.name),
    actionCardCount: result.tick.new_action_cards.length,
  }
}
