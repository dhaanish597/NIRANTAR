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
 *   1. The Phase 0 stub convention ("<aoi>_{row}{col}", row in {40,41,42}, col in {1,2,3}) —
 *      still used by `backend/app/ingest/live/stub_source.py` (LIVE mode, Aizawl only).
 *   2. A small, explicit, closed set of REAL `cells.gpkg` cell_ids (see
 *      `REMAPPED_REAL_CELL_POSITIONS` below) that this session's cell-id migration remapped
 *      `data/scenarios/_smoke.json`, `aizawl-2024.json`, `wayanad-2024.json`, and
 *      `tupul-2022.json` onto (BUILD_PLAN.md tasks 4.3-4.5) — each real id occupies the exact
 *      slot its stub predecessor used, so this file's rendering logic didn't need to change, only
 *      which id maps to which slot. A real id's row/col in its own AOI's `cells.gpkg` has no
 *      relationship to this 3x3 visual layout (it's a position in that AOI's actual ~4,000+ cell
 *      terrain grid) — there is no regex to derive a slot from, hence an explicit table rather
 *      than a second parsed convention. Ids from different AOIs can't collide (each is prefixed
 *      with its own AOI id), so this is one flat table, not one keyed by AOI.
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

/** Deliberately NOT parsed algorithmically — see module docstring, id shape 2. One entry per real
 * cell_id that appears in a committed scenario file, each mapped onto one of the same nine visual
 * grid slots (row/col in 0..2) its stub predecessor used. */
export const REMAPPED_REAL_CELL_POSITIONS: Record<string, CellGridPosition> = {
  // _smoke.json / aizawl-2024.json (9 real cells, each a real named Aizawl village's actual
  // nearest analysis cell — see the cell-id migration commit for how each was resolved).
  aizawl_012_001: { cellId: 'aizawl_012_001', row: 0, col: 0 }, // was aizawl_401
  aizawl_039_050: { cellId: 'aizawl_039_050', row: 0, col: 1 }, // was aizawl_402
  aizawl_044_048: { cellId: 'aizawl_044_048', row: 0, col: 2 }, // was aizawl_403
  aizawl_040_026: { cellId: 'aizawl_040_026', row: 1, col: 0 }, // was aizawl_411 — Durtlang
  aizawl_022_001: { cellId: 'aizawl_022_001', row: 1, col: 1 }, // was aizawl_412 — Reiek
  aizawl_003_024: { cellId: 'aizawl_003_024', row: 1, col: 2 }, // was aizawl_413 — Muallungthu
  aizawl_026_040: { cellId: 'aizawl_026_040', row: 2, col: 0 }, // was aizawl_421 — Tuirial
  aizawl_029_040: { cellId: 'aizawl_029_040', row: 2, col: 1 }, // was aizawl_422 — Tuirial (2nd)
  aizawl_054_046: { cellId: 'aizawl_054_046', row: 2, col: 2 }, // was aizawl_423 — Tuirini
  // wayanad-2024.json (9 real cells, nearest to 9 real Wayanad villages incl. Chooralmala,
  // Mundakai, Puthumala, Meppadi, Vythiri — all confirmed present in the real OSM data this
  // session's scripts/fetch_exposure.py --aoi wayanad run found).
  wayanad_008_041: { cellId: 'wayanad_008_041', row: 0, col: 0 }, // nearest to Chooralmala
  wayanad_006_040: { cellId: 'wayanad_006_040', row: 0, col: 1 }, // nearest to Mundakai
  wayanad_009_037: { cellId: 'wayanad_009_037', row: 0, col: 2 }, // nearest to Puthumala
  wayanad_020_035: { cellId: 'wayanad_020_035', row: 1, col: 0 }, // nearest to Meppadi
  wayanad_021_015: { cellId: 'wayanad_021_015', row: 1, col: 1 }, // nearest to Vythiri
  wayanad_065_008: { cellId: 'wayanad_065_008', row: 1, col: 2 }, // nearest to Naalam Mile
  wayanad_064_008: { cellId: 'wayanad_064_008', row: 2, col: 0 }, // nearest to Kellur
  wayanad_060_003: { cellId: 'wayanad_060_003', row: 2, col: 1 }, // nearest to Mazhuvannur
  wayanad_064_010: { cellId: 'wayanad_064_010', row: 2, col: 2 }, // nearest to Ancham Mile
  // tupul-2022.json (9 real cells, nearest to 9 real Tupul/Noney villages incl. the real village
  // literally named "Tupul" — the disaster site itself).
  tupul_036_012: { cellId: 'tupul_036_012', row: 0, col: 0 }, // nearest to the real village 'Tupul'
  tupul_006_033: { cellId: 'tupul_006_033', row: 0, col: 1 }, // nearest to Joypur Khunou
  tupul_041_032: { cellId: 'tupul_041_032', row: 0, col: 2 }, // nearest to S. Laijang
  tupul_038_026: { cellId: 'tupul_038_026', row: 1, col: 0 }, // nearest to Boungjang
  tupul_043_022: { cellId: 'tupul_043_022', row: 1, col: 1 }, // nearest to Kharam Pallen
  tupul_038_013: { cellId: 'tupul_038_013', row: 1, col: 2 }, // nearest to Charoipandongba Kabui
  tupul_007_021: { cellId: 'tupul_007_021', row: 2, col: 0 }, // nearest to Joupi
  tupul_025_023: { cellId: 'tupul_025_023', row: 2, col: 1 }, // nearest to Loibol Khullen
  tupul_001_010: { cellId: 'tupul_001_010', row: 2, col: 2 }, // nearest to L. Gamnonphai
}

/** Parses "aizawl_401" -> {row: 0, col: 0}, "aizawl_423" -> {row: 2, col: 2}, OR resolves a real
 * remapped id (see `REMAPPED_REAL_CELL_POSITIONS`) -> its assigned slot. Returns null for any
 * other cell_id (e.g. a real cells.gpkg id not in the small remapped set, or a stub id from an
 * AOI with no `<aoi>_{row}{col}` LIVE-mode convention). */
export function parseStubCellId(cellId: string): CellGridPosition | null {
  const remapped = REMAPPED_REAL_CELL_POSITIONS[cellId]
  if (remapped) return remapped

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
