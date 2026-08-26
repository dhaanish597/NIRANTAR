import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import type { CellRisk } from '../types/schemas'
import { ExplainabilityPanel } from './ExplainabilityPanel'

function makeCell(overrides: Partial<CellRisk> = {}): CellRisk {
  return {
    cell_id: 'aizawl_11',
    p_fail: 0.62,
    threshold_exceedance: 0.4,
    confidence: 0.71,
    attributions: [],
    model_version: 'xgb-terrain-v1',
    ...overrides,
  }
}

beforeEach(() => {
  useTickStore.setState({
    selectedVillageId: null,
    isolations: [],
    roadRisks: [],
    cellRisks: [],
    latestTick: null,
  })
})

describe('ExplainabilityPanel', () => {
  it('renders a graceful empty state when there are no cell risks yet', () => {
    render(<ExplainabilityPanel />)
    expect(screen.getByText(/no cell-level risk/i)).toBeInTheDocument()
  })

  it('explains the highest-p_fail cell when no village is selected', () => {
    useTickStore.setState({
      cellRisks: [makeCell({ cell_id: 'low', p_fail: 0.1 }), makeCell({ cell_id: 'high', p_fail: 0.9 })],
    })
    render(<ExplainabilityPanel />)
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText(/p_fail\s*90%/)).toBeInTheDocument()
  })

  it('renders SHAP bars in plain language from CellRisk.attributions', () => {
    useTickStore.setState({
      cellRisks: [
        makeCell({
          attributions: [
            { feature: 'rain_72h', plain_language: '72-hour rainfall', contribution: 0.38, display_pct: 38 },
            { feature: 'slope_mean_deg', plain_language: 'slope 41°', contribution: -0.1, display_pct: -10 },
          ],
        }),
      ],
    })
    render(<ExplainabilityPanel />)
    expect(screen.getByText('72-hour rainfall')).toBeInTheDocument()
    expect(screen.getByText('+38%')).toBeInTheDocument()
    expect(screen.getByText('slope 41°')).toBeInTheDocument()
    expect(screen.getByText('-10%')).toBeInTheDocument()
  })

  it('renders gracefully (no crash, honest empty text) when attributions are empty', () => {
    useTickStore.setState({ cellRisks: [makeCell({ attributions: [] })] })
    render(<ExplainabilityPanel />)
    expect(screen.getByText(/no attribution breakdown reported/i)).toBeInTheDocument()
  })

  it('labels a soil_moisture attribution as a surface proxy per CLAUDE.md rule 5', () => {
    useTickStore.setState({
      cellRisks: [
        makeCell({
          attributions: [
            { feature: 'soil_moisture', plain_language: 'topsoil moisture: +12%', contribution: 0.12, display_pct: 12 },
          ],
        }),
      ],
    })
    render(<ExplainabilityPanel />)
    expect(screen.getByText(/topsoil moisture: \+12% \(surface proxy/)).toBeInTheDocument()
  })

  it('shows confidence with its decisiveness-heuristic caveat, not implying a statistical CI', () => {
    useTickStore.setState({ cellRisks: [makeCell({ confidence: 0.71 })] })
    render(<ExplainabilityPanel />)
    expect(screen.getByText('confidence 71%')).toBeInTheDocument()
    expect(screen.getByText(/not a statistical confidence interval/i)).toBeInTheDocument()
  })

  it('shows the real tick-level provenance fields that ARE on the wire (mode, is_reconstructed, t)', () => {
    useTickStore.setState({
      cellRisks: [makeCell()],
      latestTick: {
        t: '2024-05-28T05:00:00+05:30',
        mode: 'replay',
        scenario_id: 'aizawl-2024',
        aoi_id: 'aizawl',
        cell_risks: [],
        road_risks: [],
        isolations: [],
        priorities: [],
        new_action_cards: [],
        new_audit_events: [],
        is_reconstructed: true,
      },
    })
    render(<ExplainabilityPanel />)
    expect(screen.getByText('replay')).toBeInTheDocument()
    expect(screen.getByText(/yes — reconstructed/)).toBeInTheDocument()
  })

  it('honestly states that per-input provenance is not yet broadcast to the frontend', () => {
    useTickStore.setState({ cellRisks: [makeCell()] })
    render(<ExplainabilityPanel />)
    expect(screen.getByText(/not yet broadcast to the frontend/i)).toBeInTheDocument()
  })
})
