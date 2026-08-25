import type { EscalationStage } from '../types/schemas'

/**
 * Mirrors backend/app/decision/stub.py::escalation_stage() exactly — same thresholds, same
 * stage names (CLAUDE.md §4 glossary: Green Watch / Yellow Pre-Alert / Orange Evacuation Ready /
 * Red Evacuate Now). Duplicated rather than fetched from the API because Phase 0 has no
 * "get current thresholds" endpoint; if the backend thresholds ever move to config.py and become
 * UI-tunable (BUILD_PLAN.md task 5.6, the false-alarm-cost slider), this needs to start reading
 * them from the API instead of hardcoding — flagging that now so it isn't forgotten.
 */
export function escalationStage(pFail: number): EscalationStage {
  if (pFail >= 0.75) return 'RED'
  if (pFail >= 0.5) return 'ORANGE'
  if (pFail >= 0.25) return 'YELLOW'
  return 'GREEN'
}

/** Colours chosen for legibility against the dark background (index.css), not a design pass. */
export const STAGE_COLOR: Record<EscalationStage, string> = {
  GREEN: '#22c55e',
  YELLOW: '#eab308',
  ORANGE: '#f97316',
  RED: '#ef4444',
}

export function colorForPFail(pFail: number): string {
  return STAGE_COLOR[escalationStage(pFail)]
}
