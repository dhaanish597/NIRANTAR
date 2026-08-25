import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import { VillageDetailDrawer } from './VillageDetailDrawer'

beforeEach(() => {
  useTickStore.setState({
    selectedVillageId: null,
    priorities: [],
    isolations: [],
    roadRisks: [],
    cellRisks: [],
  })
})

describe('VillageDetailDrawer', () => {
  it('renders nothing when no village is selected', () => {
    const { container } = render(<VillageDetailDrawer />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a graceful placeholder when the village has no priority/isolation data yet', () => {
    useTickStore.setState({ selectedVillageId: 'v1', priorities: [], isolations: [] })
    render(<VillageDetailDrawer />)
    expect(screen.getByText(/not in the current priority ranking/i)).toBeInTheDocument()
    expect(screen.getByText(/no isolation data for this village/i)).toBeInTheDocument()
    expect(screen.getByText(/no cell-level explanation is available/i)).toBeInTheDocument()
  })

  it('renders the EPS breakdown, RII detail, and driving-cell SHAP explanation when data exists', () => {
    useTickStore.setState({
      selectedVillageId: 'v1',
      priorities: [
        {
          village_id: 'v1',
          eps: 0.82,
          tier: 'P1',
          components: { p_fail: 0.5, pop: 0.2, rii: 0.9, shelter: 0.1 },
        },
      ],
      isolations: [
        {
          village_id: 'v1',
          name: 'Durtlang',
          population: 4200,
          p_isolated: 0.75,
          isolated_now: true,
          alternate_route_exists: false,
          est_duration_hours: 6.5,
          severed_links: ['e1'],
        },
      ],
      roadRisks: [
        {
          edge_id: 'e1',
          name: 'NH-6',
          highway_class: 'trunk',
          is_bridge: false,
          p_blocked: 0.9,
          severed: true,
          contributing_cells: ['c1', 'c2'],
        },
      ],
      cellRisks: [
        {
          cell_id: 'c1',
          p_fail: 0.4,
          threshold_exceedance: 0.4,
          confidence: 0.6,
          attributions: [],
          model_version: 'test',
        },
        {
          cell_id: 'c2',
          p_fail: 0.85,
          threshold_exceedance: 0.85,
          confidence: 0.7,
          attributions: [
            { feature: 'rain_72h', plain_language: '72-hour rainfall', contribution: 0.38, display_pct: 38 },
          ],
          model_version: 'test',
        },
      ],
    })
    render(<VillageDetailDrawer />)

    expect(screen.getByText('Durtlang')).toBeInTheDocument()
    expect(screen.getByText('P1')).toBeInTheDocument()
    expect(screen.getByText(/EPS 0.82/)).toBeInTheDocument()
    expect(screen.getByText(/pop\. 4,200/)).toBeInTheDocument()

    // RII detail — the estimate must read as an estimate, never a bare figure.
    expect(screen.getByText(/~6.5h \(estimate\)/)).toBeInTheDocument()

    // Driving cell is c2 (higher p_fail among e1's contributing cells), not c1.
    expect(screen.getByText(/Cell c2/)).toBeInTheDocument()
    expect(screen.getByText('72-hour rainfall')).toBeInTheDocument()
    expect(screen.getByText('+38%')).toBeInTheDocument()
  })

  it('closes when the close button is clicked', () => {
    useTickStore.setState({ selectedVillageId: 'v1' })
    render(<VillageDetailDrawer />)
    screen.getByLabelText(/close village detail/i).click()
    expect(useTickStore.getState().selectedVillageId).toBeNull()
  })
})
