import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as scenarioDetails from '../lib/scenarioDetails'
import { useTickStore } from '../store/useTickStore'
import type { TickResult } from '../types/schemas'
import { CounterfactualScorecard } from './CounterfactualScorecard'

function makeTick(overrides: Partial<TickResult> = {}): TickResult {
  return {
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
    ...overrides,
  }
}

beforeEach(() => {
  useTickStore.setState({
    scorecardOpen: false,
    replayTicks: [],
    modeState: null,
    latestTick: null,
  })
})

describe('CounterfactualScorecard', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<CounterfactualScorecard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows an honest empty state when no replay ticks have been captured yet', () => {
    useTickStore.setState({ scorecardOpen: true, replayTicks: [] })
    render(<CounterfactualScorecard />)
    expect(screen.getByText(/no replay tick data captured yet/i)).toBeInTheDocument()
  })

  it('renders the real ground-truth column from the scenario JSON (not hardcoded)', () => {
    const spy = vi.spyOn(scenarioDetails, 'getScenarioDetail').mockReturnValue({
      id: 'aizawl-2024',
      name: 'Aizawl multi-slope failures, Mizoram',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: { confidence: 'reconstructed' },
      ground_truth: {
        official_warnings: [{ t: '2024-05-27T08:00:00+05:30', issuer: 'IMD', level: 'red', spatial_scale: 'district', note: 'No slope-specific warning issued' }],
        road_events: [{ t: '2024-05-28T07:00:00+05:30', road: 'NH-6', location: 'Hunthar', effect: 'severed', consequence: 'Aizawl isolated from the rest of the country' }],
        outcome: { deaths: '27–34', source_note: 'Report as a range with source.' },
      },
    })
    useTickStore.setState({
      scorecardOpen: true,
      replayTicks: [makeTick({ scenario_id: 'aizawl-2024' })],
      modeState: { mode: 'replay', scenario_id: 'aizawl-2024', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<CounterfactualScorecard />)
    expect(screen.getByText(/No slope-specific warning issued/)).toBeInTheDocument()
    expect(screen.getByText(/Aizawl isolated from the rest of the country/)).toBeInTheDocument()
    expect(screen.getByText(/27–34/)).toBeInTheDocument()
    spy.mockRestore()
  })

  it('shows the honest "escalation history not yet available" note when no ESCALATED events exist (current reality)', () => {
    useTickStore.setState({
      scorecardOpen: true,
      replayTicks: [makeTick()],
      modeState: { mode: 'replay', scenario_id: 'aizawl-2024', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<CounterfactualScorecard />)
    expect(screen.getAllByText('not yet available').length).toBeGreaterThan(0)
    expect(screen.getByText(/Escalation history not yet available for this replay/)).toBeInTheDocument()
  })

  it('reports first Yellow/Orange/Red once real ESCALATED audit events flow through (forward-compat)', () => {
    useTickStore.setState({
      scorecardOpen: true,
      replayTicks: [
        makeTick({
          t: '2024-05-28T03:00:00+05:30',
          new_audit_events: [
            {
              event_id: 'e1', alert_id: 'esc-c1', kind: 'ESCALATED', actor: 'system',
              t: '2024-05-28T03:00:00+05:30', payload: { to_stage: 'RED' },
              input_hash: 'x', prev_hash: 'x', hash: 'x',
            },
          ],
        }),
      ],
      modeState: { mode: 'replay', scenario_id: 'aizawl-2024', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<CounterfactualScorecard />)
    expect(screen.queryByText(/Escalation history not yet available/)).not.toBeInTheDocument()
  })

  it('reports the real P1 list and village/road counts from the latest tick', () => {
    useTickStore.setState({
      scorecardOpen: true,
      replayTicks: [
        makeTick({
          priorities: [{ village_id: 'v1', eps: 0.9, tier: 'P1', components: {} }],
          isolations: [
            { village_id: 'v1', name: 'Hunthar', population: 1200, p_isolated: 0.9, isolated_now: true, alternate_route_exists: false, est_duration_hours: 6, severed_links: ['e1'] },
          ],
          road_risks: [
            { edge_id: 'e1', name: 'NH-6', highway_class: 'trunk', is_bridge: false, p_blocked: 0.95, severed: true, contributing_cells: [] },
          ],
        }),
      ],
      modeState: { mode: 'replay', scenario_id: 'aizawl-2024', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<CounterfactualScorecard />)
    expect(screen.getByText(/Hunthar/)).toBeInTheDocument()
    expect(screen.getByText(/1 villages flagged/)).toBeInTheDocument()
    expect(screen.getByText(/1 road segments flagged, 1 severed/)).toBeInTheDocument()
  })

  it('always renders a "what we would have missed" line', () => {
    useTickStore.setState({
      scorecardOpen: true,
      replayTicks: [makeTick()],
      modeState: { mode: 'replay', scenario_id: 'aizawl-2024', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<CounterfactualScorecard />)
    expect(screen.getByText('What we would have missed')).toBeInTheDocument()
  })

  it('calls closeScorecard when the close button is clicked', () => {
    useTickStore.setState({ scorecardOpen: true, replayTicks: [] })
    render(<CounterfactualScorecard />)
    screen.getByLabelText('Close scorecard').click()
    expect(useTickStore.getState().scorecardOpen).toBe(false)
  })
})
