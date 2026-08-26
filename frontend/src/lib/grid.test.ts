import { describe, expect, it } from 'vitest'
import type { CellRisk } from '../types/schemas'
import { cellRisksToFeatureCollection, parseStubCellId } from './grid'

function makeRisk(cellId: string, pFail: number): CellRisk {
  return {
    cell_id: cellId,
    p_fail: pFail,
    threshold_exceedance: pFail,
    confidence: 0.5,
    attributions: [],
    model_version: 'test',
  }
}

describe('parseStubCellId', () => {
  it('parses the 3x3 stub grid used by stub_source.py and _smoke.json', () => {
    expect(parseStubCellId('aizawl_401')).toEqual({ cellId: 'aizawl_401', row: 0, col: 0 })
    expect(parseStubCellId('aizawl_412')).toEqual({ cellId: 'aizawl_412', row: 1, col: 1 })
    expect(parseStubCellId('aizawl_423')).toEqual({ cellId: 'aizawl_423', row: 2, col: 2 })
  })

  it('returns null for ids that do not match the Phase 0 stub convention', () => {
    expect(parseStubCellId('not-a-cell')).toBeNull()
    expect(parseStubCellId('aizawl_999')).toBeNull() // row code 99 unknown
    expect(parseStubCellId('aizawl_404')).toBeNull() // col digit 4 out of [1,2,3]
  })

  it('resolves the remapped real Wayanad/Tupul cell ids (tasks 4.4/4.5) via the lookup table', () => {
    // wayanad-2024.json's real cell_ids, remapped this session onto real
    // scripts/build_grid.py ids — same nine visual slots their stub predecessors held.
    expect(parseStubCellId('wayanad_008_041')).toEqual({ cellId: 'wayanad_008_041', row: 0, col: 0 })
    expect(parseStubCellId('wayanad_060_003')).toEqual({ cellId: 'wayanad_060_003', row: 2, col: 1 })
    // tupul-2022.json's, including the real cell nearest the real village literally named 'Tupul'.
    expect(parseStubCellId('tupul_036_012')).toEqual({ cellId: 'tupul_036_012', row: 0, col: 0 })
    expect(parseStubCellId('tupul_001_010')).toEqual({ cellId: 'tupul_001_010', row: 2, col: 2 })
  })

  it('still returns null for a real id that has not been remapped/registered', () => {
    expect(parseStubCellId('aizawl_007_014')).toBeNull()
  })
})

describe('cellRisksToFeatureCollection', () => {
  const aoiCenter = { lat: 23.7307, lon: 92.7173 }

  it('produces one polygon feature per parseable cell, carrying p_fail and a colour', () => {
    const fc = cellRisksToFeatureCollection(
      [makeRisk('aizawl_401', 0.1), makeRisk('aizawl_423', 0.9)],
      aoiCenter,
    )
    expect(fc.features).toHaveLength(2)
    expect(fc.features[0].properties.p_fail).toBe(0.1)
    expect(fc.features[0].properties.color).not.toBe(fc.features[1].properties.color)
  })

  it('skips cell ids that do not parse under the stub convention', () => {
    const fc = cellRisksToFeatureCollection([makeRisk('unparseable', 0.5)], aoiCenter)
    expect(fc.features).toHaveLength(0)
  })

  it('every feature is a valid 5-point closed polygon ring', () => {
    const fc = cellRisksToFeatureCollection([makeRisk('aizawl_402', 0.3)], aoiCenter)
    const ring = fc.features[0].geometry.coordinates[0]
    expect(ring).toHaveLength(5)
    expect(ring[0]).toEqual(ring[4]) // closed ring
  })
})
