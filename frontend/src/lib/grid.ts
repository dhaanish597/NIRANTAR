import type { Feature, FeatureCollection, Polygon } from 'geojson'
import type { CellRisk } from '../types/schemas'
import { colorForPFail } from './escalation'

/**
 * Phase 0 has no real cell geometry: CellObservation/CellRisk (backend/app/schemas/) carry only
 * a `cell_id`, not a polygon — that's Phase 1's scripts/build_grid.py (BUILD_PLAN.md task 1.2),
 * which produces a real 500 m analysis grid from a DEM. Until then, this file derives a synthetic
 * 3x3 square layout purely from the cell_id naming convention used by
 * backend/app/ingest/live/stub_source.py and data/scenarios/_smoke.json
 * ("aizawl_{row}{col}", row in {40,41,42}, col in {1,2,3}), centered on the AOI's stub center.
 *
 * This is fabricated positioning for visualization only — it is not a claim about where any real
 * slope is. When Phase 1 lands real cell geometry, this file is deleted and MapView reads
 * `geometry` off the real schema instead.
 */

const ROW_CODES: Record<string, number> = { '40': 0, '41': 1, '42': 2 }
const CELL_SIZE_DEG = 0.006 // ~650m at this latitude — arbitrary, for visual spacing only
const GRID_GAP_DEG = 0.001

export interface CellGridPosition {
  cellId: string
  row: number
  col: number
}

/** Parses "aizawl_401" -> {row: 0, col: 0}, "aizawl_423" -> {row: 2, col: 2}. Returns null for
 * any cell_id that doesn't match the Phase 0 stub naming convention (e.g. real Phase 1 ids). */
export function parseStubCellId(cellId: string): CellGridPosition | null {
  const match = /^aizawl_(\d{2})(\d)$/.exec(cellId)
  if (!match) return null
  const [, rowCode, colDigit] = match
  const row = ROW_CODES[rowCode]
  if (row === undefined) return null
  const col = Number(colDigit) - 1
  if (col < 0 || col > 2) return null
  return { cellId, row, col }
}

function squarePolygon(centerLat: number, centerLon: number, sizeDeg: number): Polygon {
  const half = sizeDeg / 2
  return {
    type: 'Polygon',
    coordinates: [
      [
        [centerLon - half, centerLat - half],
        [centerLon + half, centerLat - half],
        [centerLon + half, centerLat + half],
        [centerLon - half, centerLat + half],
        [centerLon - half, centerLat - half],
      ],
    ],
  }
}

export interface CellFeatureProperties {
  cell_id: string
  p_fail: number
  color: string
}

/** Builds a GeoJSON FeatureCollection of coloured squares for MapView, one per cell risk whose
 * cell_id parses under the Phase 0 stub convention. Unparseable ids are silently skipped (not
 * every cell_id a future real adapter emits will fit this synthetic grid). */
export function cellRisksToFeatureCollection(
  cellRisks: CellRisk[],
  aoiCenter: { lat: number; lon: number },
): FeatureCollection<Polygon, CellFeatureProperties> {
  const step = CELL_SIZE_DEG + GRID_GAP_DEG
  const features: Feature<Polygon, CellFeatureProperties>[] = []

  for (const risk of cellRisks) {
    const pos = parseStubCellId(risk.cell_id)
    if (!pos) continue
    const centerLat = aoiCenter.lat + (1 - pos.row) * step
    const centerLon = aoiCenter.lon + (pos.col - 1) * step
    features.push({
      type: 'Feature',
      geometry: squarePolygon(centerLat, centerLon, CELL_SIZE_DEG),
      properties: {
        cell_id: risk.cell_id,
        p_fail: risk.p_fail,
        color: colorForPFail(risk.p_fail),
      },
    })
  }

  return { type: 'FeatureCollection', features }
}
