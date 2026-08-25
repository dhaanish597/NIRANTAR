import type { ScenarioSummary } from '../types/schemas'

/**
 * Pure helpers backing ReplayControlBar (BUILD_PLAN.md task 4.9). Kept separate from the
 * component so the timeline-fraction math is directly unit-testable without mounting anything.
 */

/** The four preset multipliers task 4.9 asks for. */
export const SPEED_PRESETS = [1, 10, 60, 360] as const
export type SpeedPreset = (typeof SPEED_PRESETS)[number]

/**
 * Fraction (0..1) of the way through the active scenario's declared [start, end] window, given
 * the current scenario time. Returns null when any input is missing/unparseable — callers must
 * render "no progress data" rather than a fabricated 0%.
 */
export function computeReplayProgress(
  scenario: ScenarioSummary | undefined,
  scenarioTimeIso: string | null,
): number | null {
  if (!scenario || !scenarioTimeIso) return null
  const start = Date.parse(scenario.start)
  const end = Date.parse(scenario.end)
  const now = Date.parse(scenarioTimeIso)
  if (Number.isNaN(start) || Number.isNaN(end) || Number.isNaN(now) || end <= start) return null
  return Math.min(1, Math.max(0, (now - start) / (end - start)))
}
