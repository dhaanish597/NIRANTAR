import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import { ReplayControlBar } from './ReplayControlBar'

beforeEach(() => {
  useTickStore.setState({
    modeState: null,
    latestTick: null,
    scenarios: [],
  })
})

describe('ReplayControlBar', () => {
  it('renders nothing in LIVE mode', () => {
    useTickStore.setState({ modeState: { mode: 'live', scenario_id: null, scenario_time: null, speed_factor: 1, paused: false } })
    const { container } = render(<ReplayControlBar />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the control bar in REPLAY mode, showing scenario id and a persistent progress bar', () => {
    useTickStore.setState({
      modeState: {
        mode: 'replay',
        scenario_id: '_smoke',
        scenario_time: '2025-01-01T04:30:00+05:30',
        speed_factor: 3600,
        paused: false,
      },
      scenarios: [
        {
          id: '_smoke',
          aoi_id: 'aizawl',
          held_out_of_training: false,
          frame_count: 10,
          start: '2025-01-01T00:00:00+05:30',
          end: '2025-01-01T09:00:00+05:30',
          provenance: {},
        },
      ],
    })
    render(<ReplayControlBar />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    expect(screen.getByText('_smoke')).toBeInTheDocument()
    // speed_factor 3600 isn't one of the four presets — shown as extra text, not a false match.
    expect(screen.getByText(/current: 3600×/)).toBeInTheDocument()
  })

  it('shows Resume instead of Pause when modeState.paused is true', () => {
    useTickStore.setState({
      modeState: { mode: 'replay', scenario_id: '_smoke', scenario_time: null, speed_factor: 1, paused: true },
    })
    render(<ReplayControlBar />)
    expect(screen.getByText(/▶ Resume/)).toBeInTheDocument()
  })

  it('highlights the preset button matching the real current speed_factor', () => {
    useTickStore.setState({
      modeState: { mode: 'replay', scenario_id: '_smoke', scenario_time: null, speed_factor: 60, paused: false },
    })
    render(<ReplayControlBar />)
    const button = screen.getByText('60×')
    expect(button.className).toContain('bg-emerald-700')
  })

  it('Pause and speed preset buttons are disabled (not yet wired to the backend — task 4.7)', () => {
    useTickStore.setState({
      modeState: { mode: 'replay', scenario_id: '_smoke', scenario_time: null, speed_factor: 1, paused: false },
    })
    render(<ReplayControlBar />)
    expect(screen.getByText(/⏸ Pause/)).toBeDisabled()
    expect(screen.getByText('1×')).toBeDisabled()
  })

  it('"Return to Live" calls the real, already-wired stop-replay endpoint', async () => {
    useTickStore.setState({
      modeState: { mode: 'replay', scenario_id: '_smoke', scenario_time: null, speed_factor: 1, paused: false },
    })
    const spy = vi.spyOn(api, 'stopReplay').mockResolvedValue({
      mode: 'live', scenario_id: null, scenario_time: null, speed_factor: 1, paused: false,
    })
    render(<ReplayControlBar />)
    screen.getByText('Return to Live').click()
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })

  it('"Scorecard" opens the counterfactual scorecard (BUILD_PLAN.md task 4.10)', () => {
    useTickStore.setState({
      modeState: { mode: 'replay', scenario_id: '_smoke', scenario_time: null, speed_factor: 1, paused: false },
      scorecardOpen: false,
    })
    render(<ReplayControlBar />)
    screen.getByText('Scorecard').click()
    expect(useTickStore.getState().scorecardOpen).toBe(true)
  })
})
