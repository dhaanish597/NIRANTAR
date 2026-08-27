import type { Feature, FeatureCollection, LineString } from 'geojson'
import type { RoadSegmentRisk } from '../types/schemas'
import { STAGE_COLOR, escalationStage } from './escalation'
import { stubCellCenter } from './grid'

/**
 * BUILD_PLAN.md task 2.7 ("road layer coloured by p_blocked on the map") — but
 * `RoadSegmentRisk` (backend/app/schemas/impact.py) carries no geometry field, only
 * `contributing_cells: list[str]`. Real edge geometry is `scripts/build_road_graph.py`'s job
 * (task 2.1, not yet done) plus a schema addition to carry it to the frontend, neither of which
 * is in this agent's scope (frontend-only, no backend changes). Rather than render nothing, this
 * sketches a line through the same synthetic cell centres `lib/grid.ts` already uses for cell
 * squares, threading through whichever of a road's `contributing_cells` fall on the Phase 0 stub
 * 3x3 grid. This is fabricated positioning for visualization only, exactly like grid.ts's squares
 * — not a claim about a road's real alignment. Delete this in favour of real edge geometry once
 * task 2.1/2.3 lands it.
 *
 * A road with fewer than 2 cells that parse under the stub convention has nothing to draw a line
 * between and is skipped, same as grid.ts silently skips unparseable cell ids.
 */

export function colorForPBlocked(pBlocked: number): string {
  // Reuses the exact same p_fail escalation buckets/colours as the cell layer (lib/escalation.ts)
  // so the map reads as one consistent colour language rather than two competing scales.
  return STAGE_COLOR[escalationStage(pBlocked)]
}

export interface RoadFeatureProperties {
  edge_id: string
  name: string | null
  p_blocked: number
  severed: boolean
  is_bridge: boolean
  color: string
}

export function roadRisksToFeatureCollection(
  roadRisks: RoadSegmentRisk[],
  aoiCenter: { lat: number; lon: number },
): FeatureCollection<LineString, RoadFeatureProperties> {
  const features: Feature<LineString, RoadFeatureProperties>[] = []

  for (const road of roadRisks) {
    if (road.geometry?.type === 'LineString') {
      features.push({ type: 'Feature', geometry: road.geometry as LineString, properties: { edge_id: road.edge_id, name: road.name, p_blocked: road.p_blocked, severed: road.severed, is_bridge: road.is_bridge, color: colorForPBlocked(road.p_blocked) } })
      continue
    }
    const points = road.contributing_cells
      .map((cellId) => stubCellCenter(cellId, aoiCenter))
      .filter((p): p is { lat: number; lon: number } => p !== null)
    if (points.length < 2) continue

    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: points.map((p) => [p.lon, p.lat]),
      },
      properties: {
        edge_id: road.edge_id,
        name: road.name,
        p_blocked: road.p_blocked,
        severed: road.severed,
        is_bridge: road.is_bridge,
        color: colorForPBlocked(road.p_blocked),
      },
    })
  }

  return { type: 'FeatureCollection', features }
}
