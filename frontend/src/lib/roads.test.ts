import { describe, expect, it } from 'vitest'
import type { RoadSegmentRisk } from '../types/schemas'
import { STAGE_COLOR } from './escalation'
import { colorForPBlocked, roadRisksToFeatureCollection } from './roads'

function makeRoad(overrides: Partial<RoadSegmentRisk> = {}): RoadSegmentRisk {
  return {
    edge_id: 'e1',
    name: 'NH-6',
    highway_class: 'trunk',
    is_bridge: false,
    p_blocked: 0.5,
    severed: false,
    contributing_cells: [],
    ...overrides,
  }
}

const aoiCenter = { lat: 23.7307, lon: 92.7173 }

describe('colorForPBlocked', () => {
  it('reuses the same colour buckets as the cell risk layer', () => {
    expect(colorForPBlocked(0.1)).toBe(STAGE_COLOR.GREEN)
    expect(colorForPBlocked(0.9)).toBe(STAGE_COLOR.RED)
  })
})

describe('roadRisksToFeatureCollection', () => {
  it('skips roads with fewer than 2 cells that parse under the stub grid convention', () => {
    const fc = roadRisksToFeatureCollection(
      [makeRoad({ contributing_cells: [] }), makeRoad({ edge_id: 'e2', contributing_cells: ['aizawl_401'] })],
      aoiCenter,
    )
    expect(fc.features).toHaveLength(0)
  })

  it('draws a line through the resolvable contributing cells, coloured by p_blocked', () => {
    const fc = roadRisksToFeatureCollection(
      [makeRoad({ contributing_cells: ['aizawl_401', 'aizawl_402', 'unparseable'], p_blocked: 0.9 })],
      aoiCenter,
    )
    expect(fc.features).toHaveLength(1)
    const feature = fc.features[0]
    expect(feature.geometry.type).toBe('LineString')
    expect(feature.geometry.coordinates).toHaveLength(2) // the unparseable id is dropped
    expect(feature.properties.color).toBe(STAGE_COLOR.RED)
    expect(feature.properties.edge_id).toBe('e1')
    expect(feature.properties.name).toBe('NH-6')
  })

  it('renders an empty collection for an empty road_risks list', () => {
    const fc = roadRisksToFeatureCollection([], aoiCenter)
    expect(fc.type).toBe('FeatureCollection')
    expect(fc.features).toHaveLength(0)
  })
})
