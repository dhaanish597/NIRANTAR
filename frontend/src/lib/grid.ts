import type { Feature, FeatureCollection, Polygon } from 'geojson'
import type { CellRisk } from '../types/schemas'
import { colorForPFail } from './escalation'

/**
 * Phase 0 has no real cell geometry: CellObservation/CellRisk (backend/app/schemas/) carry only
 * a `cell_id`, not a polygon — that's Phase 1's scripts/build_grid.py (BUILD_PLAN.md task 1.2),
 * which produces a real 500 m analysis grid from a DEM. Until then, this file derives a synthetic
 * 3x3 square layout purely from the cell_id, centered on the AOI's stub center.
 *
 * Two id shapes are recognised, both mapping onto the SAME synthetic 3x3 layout:
 *   1. The Phase 0 stub convention ("aizawl_{row}{col}", row in {40,41,42}, col in {1,2,3}) —
 *      still used by `backend/app/ingest/live/stub_source.py` (LIVE mode) and by any scenario
 *      file not yet migrated (`wayanad-2024.json`, `tupul-2022.json` — a documented, separate
 *      gap, see BUILD_PLAN.md task 4.4/4.5's own AOI-config notes).
 *   2. A small, explicit, closed set of REAL `cells.gpkg` cell_ids (see
 *      `REMAPPED_REAL_CELL_POSITIONS` below) that a later session's cell-id migration remapped
 *      `data/scenarios/_smoke.json` and `aizawl-2024.json` onto — each real id occupies the exact
 *      slot its stub predecessor used, so this file's rendering logic didn't need to change, only
 *      which id maps to which slot.
 *
 * This is fabricated positioning for visualization only in BOTH cases — it is not a claim about
 * where any real slope is, even for the real cell_ids in case 2 (their true polygon, from
 * `cells.gpkg`, is not what's drawn here). When a real geometry API endpoint + full id migration
 * lands, this file is deleted and MapView reads `geometry` off the real schema instead.
 */

const ROW_CODES: Record<string, number> = { '40': 0, '41': 1, '42': 2 }
const CELL_SIZE_DEG = 0.006 // ~650m at this latitude — arbitrary, for visual spacing only
const GRID_GAP_DEG = 0.001
const STEP_DEG = CELL_SIZE_DEG + GRID_GAP_DEG

export interface CellGridPosition {
  cellId: string
  row: number
  col: number
}

/** See module docstring, id shape 2. Deliberately NOT parsed algorithmically — a real cells.gpkg
 * id (`aizawl_{row:03d}_{col:03d}`) does not encode a demo-grid position, so this is a small,
 * explicitly-listed table, not a general parser. Values chosen to include several real named
 * Aizawl villages' actual nearest analysis cell (see the cell-id migration commit for how each
 * was resolved), so escalation for `_smoke`/`aizawl-2024` now reaches real villages, not just
 * fabricated ones. */
const REMAPPED_REAL_CELL_POSITIONS: Record<string, { row: number; col: number }> = {
  aizawl_012_001: { row: 0, col: 0 }, // was aizawl_401
  aizawl_039_050: { row: 0, col: 1 }, // was aizawl_402
  aizawl_044_048: { row: 0, col: 2 }, // was aizawl_403
  aizawl_040_026: { row: 1, col: 0 }, // was aizawl_411 — Durtlang's real nearest cell
  aizawl_022_001: { row: 1, col: 1 }, // was aizawl_412 — Reiek's real nearest cell
  aizawl_003_024: { row: 1, col: 2 }, // was aizawl_413 — Muallungthu's real nearest cell
  aizawl_026_040: { row: 2, col: 0 }, // was aizawl_421 — Tuirial's real nearest cell
  aizawl_029_040: { row: 2, col: 1 }, // was aizawl_422 — Tuirial's real nearest cell (2nd village)
  aizawl_054_046: { row: 2, col: 2 }, // was aizawl_423 — Tuirini's real nearest cell
}

/** Parses "aizawl_401" -> {row: 0, col: 0}, "aizawl_423" -> {row: 2, col: 2}, OR a remapped real
 * id (see `REMAPPED_REAL_CELL_POSITIONS`) -> its assigned slot. Returns null for any other
 * cell_id (e.g. a real cells.gpkg id NOT in the small remapped set — the general case Phase 1C/2
 * still needs a real geometry endpoint for). */
export function parseStubCellId(cellId: string): CellGridPosition | null {
  const remapped = REMAPPED_REAL_CELL_POSITIONS[cellId]
  if (remapped) return { cellId, ...remapped }

  const match = /^aizawl_(\d{2})(\d)$/.exec(cellId)
  if (!match) return null
  const [, rowCode, colDigit] = match
  const row = ROW_CODES[rowCode]
  if (row === undefined) return null
  const col = Number(colDigit) - 1
  if (col < 0 || col > 2) return null
  return { cellId, row, col }
}

/** The same synthetic centre point `cellRisksToFeatureCollection` places a cell's square at,
 * exposed standalone so other synthetic-geometry consumers (e.g. lib/roads.ts's road sketch,
 * which threads a line through a road's `contributing_cells`) can share one fabricated layout
 * instead of each inventing its own. Returns null for any cell_id outside the Phase 0 stub
 * convention (see parseStubCellId). */
export function stubCellCenter(
  cellId: string,
  aoiCenter: { lat: number; lon: number },
): { lat: number; lon: number } | null {
  const pos = parseStubCellId(cellId)
  if (!pos) return null
  return {
    lat: aoiCenter.lat + (1 - pos.row) * STEP_DEG,
    lon: aoiCenter.lon + (pos.col - 1) * STEP_DEG,
  }
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
  const features: Feature<Polygon, CellFeatureProperties>[] = []

  for (const risk of cellRisks) {
    const center = stubCellCenter(risk.cell_id, aoiCenter)
    if (!center) continue
    features.push({
      type: 'Feature',
      geometry: squarePolygon(center.lat, center.lon, CELL_SIZE_DEG),
      properties: {
        cell_id: risk.cell_id,
        p_fail: risk.p_fail,
        color: colorForPFail(risk.p_fail),
      },
    })
  }

  return { type: 'FeatureCollection', features }
}
