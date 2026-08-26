import type { Attribution, CellRisk, RoadSegmentRisk, VillageIsolation } from '../types/schemas'
import { findDrivingCellRisk } from './priorityDetail'

/**
 * Pure helpers backing `ExplainabilityPanel` (BUILD_PLAN.md task 5.7). Kept schema-shaped and
 * side-effect free, same pattern as `lib/priorityDetail.ts`.
 */

/** The cell this panel explains: the selected village's "driving cell" when one is selected
 * (reuses `lib/priorityDetail.ts::findDrivingCellRisk` rather than re-deriving the same
 * severed-link -> contributing-cell chain), otherwise the highest-`p_fail` cell in the current
 * tick as a sensible AOI-wide default ("why is risk highest right now"). Returns null when there
 * is nothing to explain yet (no cells in the current tick). */
export function selectExplainedCell(
  selectedVillageId: string | null,
  isolations: VillageIsolation[],
  roadRisks: RoadSegmentRisk[],
  cellRisks: CellRisk[],
): CellRisk | null {
  if (selectedVillageId) {
    const village = isolations.find((v) => v.village_id === selectedVillageId)
    const driving = findDrivingCellRisk(village, roadRisks, cellRisks)
    if (driving) return driving
  }
  return highestRiskCell(cellRisks)
}

export function highestRiskCell(cellRisks: CellRisk[]): CellRisk | null {
  let best: CellRisk | null = null
  for (const cell of cellRisks) {
    if (!best || cell.p_fail > best.p_fail) best = cell
  }
  return best
}

/** CLAUDE.md rule 5: satellite soil moisture is a topsoil proxy, not pore-water pressure, and
 * every UI surface showing it must say so. `CellRisk.attributions` (task 1.18's SHAP output) is
 * the only place a soil-moisture *contribution* could reach the frontend today, so this is where
 * that labelling rule is enforced on the frontend side. Matches on the feature key (the stable,
 * machine-facing name) rather than `plain_language` (free text that could phrase it differently),
 * with a `plain_language`-text fallback for robustness. */
export function isSoilMoistureAttribution(attribution: Attribution): boolean {
  const key = attribution.feature.toLowerCase()
  const text = attribution.plain_language.toLowerCase()
  return key.includes('soil_moisture') || key.includes('soil moisture') || text.includes('soil moisture')
}

const SURFACE_PROXY_SUFFIX = ' (surface proxy, top ~5cm — not pore-water pressure)'

/** The label to render for one attribution — `plain_language` as-is, with the CLAUDE.md rule 5
 * surface-proxy caveat appended for soil moisture, and only once (idempotent if the text already
 * mentions "surface proxy", e.g. a future backend change that bakes the caveat in itself). */
export function attributionDisplayLabel(attribution: Attribution): string {
  if (!isSoilMoistureAttribution(attribution)) return attribution.plain_language
  if (attribution.plain_language.toLowerCase().includes('surface proxy')) {
    return attribution.plain_language
  }
  return `${attribution.plain_language}${SURFACE_PROXY_SUFFIX}`
}

/** CLAUDE.md rule 6 ("show confidence... rather than hiding them") plus BUILD_PLAN.md task 1.17's
 * own documented ruling on what `CellRisk.confidence` actually measures: 1 minus the normalized
 * binary entropy of `p_fail` — how decisive vs. undecided the model is at this value, NOT a
 * statistical confidence interval. Stated here once so every caller shows the same honest caveat
 * instead of implying a precision the number doesn't have. */
export const CONFIDENCE_CAVEAT =
  'A decisiveness heuristic (how far p_fail sits from a 50/50 coin flip) — not a statistical confidence interval.'
