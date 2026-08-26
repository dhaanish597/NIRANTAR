import { describe, expect, it } from 'vitest'
import type { Attribution, CellRisk, RoadSegmentRisk, VillageIsolation } from '../types/schemas'
import {
  attributionDisplayLabel,
  highestRiskCell,
  isSoilMoistureAttribution,
  selectExplainedCell,
} from './explainability'

function makeCell(overrides: Partial<CellRisk> = {}): CellRisk {
  return {
    cell_id: 'c1',
    p_fail: 0.5,
    threshold_exceedance: 0.5,
    confidence: 0.5,
    attributions: [],
    model_version: 'test',
    ...overrides,
  }
}

describe('highestRiskCell', () => {
  it('returns null for an empty list', () => {
    expect(highestRiskCell([])).toBeNull()
  })

  it('returns the cell with the highest p_fail', () => {
    const cells = [makeCell({ cell_id: 'a', p_fail: 0.3 }), makeCell({ cell_id: 'b', p_fail: 0.9 })]
    expect(highestRiskCell(cells)?.cell_id).toBe('b')
  })
})

describe('selectExplainedCell', () => {
  it('falls back to the highest-risk cell when no village is selected', () => {
    const cells = [makeCell({ cell_id: 'a', p_fail: 0.2 }), makeCell({ cell_id: 'b', p_fail: 0.8 })]
    expect(selectExplainedCell(null, [], [], cells)?.cell_id).toBe('b')
  })

  it('prefers the selected village\'s driving cell (via severed_links -> contributing_cells)', () => {
    const isolations: VillageIsolation[] = [
      {
        village_id: 'v1', name: 'Durtlang', population: 100, p_isolated: 0.9, isolated_now: true,
        alternate_route_exists: false, est_duration_hours: 4, severed_links: ['e1'],
      },
    ]
    const roadRisks: RoadSegmentRisk[] = [
      { edge_id: 'e1', name: 'NH-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.9, severed: true, contributing_cells: ['a'] },
    ]
    const cells = [makeCell({ cell_id: 'a', p_fail: 0.2 }), makeCell({ cell_id: 'b', p_fail: 0.9 })]
    expect(selectExplainedCell('v1', isolations, roadRisks, cells)?.cell_id).toBe('a')
  })

  it('falls back to highest-risk cell when the selected village has no resolvable driving cell', () => {
    const cells = [makeCell({ cell_id: 'a', p_fail: 0.2 }), makeCell({ cell_id: 'b', p_fail: 0.9 })]
    expect(selectExplainedCell('unknown-village', [], [], cells)?.cell_id).toBe('b')
  })

  it('returns null when there are no cells at all', () => {
    expect(selectExplainedCell(null, [], [], [])).toBeNull()
  })
})

describe('isSoilMoistureAttribution / attributionDisplayLabel', () => {
  const soilAttribution: Attribution = {
    feature: 'soil_moisture',
    plain_language: 'topsoil moisture: +12%',
    contribution: 0.12,
    display_pct: 12,
  }
  const otherAttribution: Attribution = {
    feature: 'slope_mean_deg',
    plain_language: 'average slope (26°)',
    contribution: 0.2,
    display_pct: 20,
  }

  it('detects the soil_moisture feature key', () => {
    expect(isSoilMoistureAttribution(soilAttribution)).toBe(true)
    expect(isSoilMoistureAttribution(otherAttribution)).toBe(false)
  })

  it('appends the CLAUDE.md rule-5 surface-proxy caveat for soil moisture, unmodified for others', () => {
    expect(attributionDisplayLabel(soilAttribution)).toBe(
      'topsoil moisture: +12% (surface proxy, top ~5cm — not pore-water pressure)',
    )
    expect(attributionDisplayLabel(otherAttribution)).toBe('average slope (26°)')
  })

  it('does not double-append the caveat if plain_language already says "surface proxy"', () => {
    const alreadyLabeled: Attribution = {
      feature: 'soil_moisture',
      plain_language: 'soil moisture (surface proxy): +12%',
      contribution: 0.12,
      display_pct: 12,
    }
    expect(attributionDisplayLabel(alreadyLabeled)).toBe('soil moisture (surface proxy): +12%')
  })
})
