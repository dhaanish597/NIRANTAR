import type { CellRisk, RoadSegmentRisk, SettlementPriority, VillageIsolation } from '../types/schemas'

/**
 * Pure join/lookup helpers shared by RightRail's Priority List panel and VillageDetailDrawer
 * (BUILD_PLAN.md tasks 2.7/2.8). Kept schema-shaped and side-effect free so they're directly
 * testable without a store or a rendered component.
 */

export interface VillageDisplayRecord {
  villageId: string
  tier: SettlementPriority['tier']
  eps: number
  components: Record<string, number>
  name: string | null
  population: number | null
  isolatedNow: boolean | null
  pIsolated: number | null
  alternateRouteExists: boolean | null
  estDurationHours: number | null
  severedLinks: string[]
}

/** Joins `TickResult.priorities` (the ranked settlement list) with `TickResult.isolations` (RII
 * detail) on `village_id`. The two lists are not guaranteed to contain the same villages or be in
 * the same order — a priority with no matching isolation record renders with `null` RII fields
 * rather than being dropped, since Phase 0/2 stub data may not populate both lists together. */
export function mergeVillageDisplay(
  priorities: SettlementPriority[],
  isolations: VillageIsolation[],
): VillageDisplayRecord[] {
  const isolationById = new Map(isolations.map((v) => [v.village_id, v]))
  return priorities.map((priority) => {
    const isolation = isolationById.get(priority.village_id)
    return {
      villageId: priority.village_id,
      tier: priority.tier,
      eps: priority.eps,
      components: priority.components,
      name: isolation?.name ?? null,
      population: isolation?.population ?? null,
      isolatedNow: isolation?.isolated_now ?? null,
      pIsolated: isolation?.p_isolated ?? null,
      alternateRouteExists: isolation?.alternate_route_exists ?? null,
      estDurationHours: isolation?.est_duration_hours ?? null,
      severedLinks: isolation?.severed_links ?? [],
    }
  })
}

export function findVillageIsolation(
  villageId: string,
  isolations: VillageIsolation[],
): VillageIsolation | undefined {
  return isolations.find((v) => v.village_id === villageId)
}

/**
 * Resolves "the driving cell's risk" for a village's SHAP explanation (task 2.8). Neither
 * `VillageIsolation` nor `SettlementPriority` names a specific cell directly, but a village's
 * `severed_links` (edge_ids) can be looked up in `road_risks` to find each severed road's
 * `contributing_cells`, and the highest-`p_fail` cell among those is the most defensible
 * candidate for "the slope driving this village's isolation risk" — every hop uses a real
 * relationship the schema actually encodes, rather than guessing or fabricating a link.
 * Returns null (render a "not available" state, never a fabricated attribution) when the village
 * has no severed links, or none of them resolve to a road with contributing cells, or none of
 * those cells appear in the current tick's cell_risks.
 */
export function findDrivingCellRisk(
  village: VillageIsolation | undefined,
  roadRisks: RoadSegmentRisk[],
  cellRisks: CellRisk[],
): CellRisk | null {
  if (!village) return null

  const candidateCellIds = new Set<string>()
  for (const edgeId of village.severed_links) {
    const road = roadRisks.find((r) => r.edge_id === edgeId)
    road?.contributing_cells.forEach((cellId) => candidateCellIds.add(cellId))
  }

  let best: CellRisk | null = null
  for (const cellId of candidateCellIds) {
    const cell = cellRisks.find((c) => c.cell_id === cellId)
    if (cell && (!best || cell.p_fail > best.p_fail)) best = cell
  }
  return best
}
