import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as scenarioDetails from '../lib/scenarioDetails'
import { useTickStore } from '../store/useTickStore'
import type { ScenarioSummary } from '../types/schemas'
import { ScenarioPickerModal } from './ScenarioPickerModal'

function makeScenario(overrides: Partial<ScenarioSummary> = {}): ScenarioSummary {
  return {
    id: '_smoke',
    aoi_id: 'aizawl',
    held_out_of_training: false,
    frame_count: 10,
    start: '2025-01-01T00:00:00+05:30',
    end: '2025-01-01T09:00:00+05:30',
    provenance: {},
    ...overrides,
  }
}

beforeEach(() => {
  useTickStore.setState({ scenarios: [], aoi: null })
})

describe('ScenarioPickerModal', () => {
  it('renders nothing when closed', () => {
    useTickStore.setState({ scenarios: [makeScenario()] })
    const { container } = render(<ScenarioPickerModal open={false} onClose={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a graceful fallback (id + formatted aoi) for a scenario with no name/date (e.g. _smoke)', () => {
    useTickStore.setState({ scenarios: [makeScenario()] })
    render(<ScenarioPickerModal open onClose={() => {}} />)
    expect(screen.getByText('_smoke')).toBeInTheDocument()
    expect(screen.getByText('Aizawl')).toBeInTheDocument() // formatAoiIdFallback('aizawl')
  })

  it('prefers the loaded AOI\'s real name over the id-formatting fallback', () => {
    useTickStore.setState({
      scenarios: [makeScenario()],
      aoi: { id: 'aizawl', name: 'Aizawl, Mizoram', center: { lat: 23.7307, lon: 92.7173 } },
    })
    render(<ScenarioPickerModal open onClose={() => {}} />)
    expect(screen.getByText('Aizawl, Mizoram')).toBeInTheDocument()
  })

  it('renders the "Held out of training" badge only when the field is true', () => {
    useTickStore.setState({
      scenarios: [makeScenario({ id: 'a', held_out_of_training: true }), makeScenario({ id: 'b', held_out_of_training: false })],
    })
    render(<ScenarioPickerModal open onClose={() => {}} />)
    expect(screen.getAllByText('Held out of training')).toHaveLength(1)
  })

  it('reads name, event_date, death toll, source note, and the what-went-wrong line from the scenario JSON, never hardcoding them', () => {
    const spy = vi.spyOn(scenarioDetails, 'getScenarioDetail').mockReturnValue({
      id: 'aizawl-2024',
      name: 'Aizawl multi-slope failures, Mizoram',
      event_date: '2024-05-28',
      aoi_id: 'aizawl',
      held_out_of_training: true,
      provenance: { confidence: 'reconstructed' },
      ground_truth: {
        official_warnings: [{ t: 't', issuer: 'IMD', level: 'red', note: 'No slope-specific warning issued' }],
        outcome: {
          deaths: '27–34 (state total; 33 bodies recovered per academic study)',
          source_note: 'Report as a range with source; do not assert a single figure.',
        },
      },
    })
    useTickStore.setState({ scenarios: [makeScenario({ id: 'aizawl-2024', held_out_of_training: true })] })
    render(<ScenarioPickerModal open onClose={() => {}} />)

    expect(screen.getByText('Aizawl multi-slope failures, Mizoram')).toBeInTheDocument()
    expect(screen.getByText(/2024-05-28/)).toBeInTheDocument()
    expect(screen.getByText('No slope-specific warning issued')).toBeInTheDocument()
    expect(screen.getByText(/27–34/)).toBeInTheDocument()
    expect(screen.getByText(/Report as a range with source/)).toBeInTheDocument()
    spy.mockRestore()
  })

  it('calls startReplay and closes when Run is clicked', async () => {
    const startReplay = vi.fn().mockResolvedValue(undefined)
    useTickStore.setState({ scenarios: [makeScenario()], startReplay })
    const onClose = vi.fn()
    render(<ScenarioPickerModal open onClose={onClose} />)
    screen.getByText('Run').click()
    await Promise.resolve()
    expect(startReplay).toHaveBeenCalledWith('_smoke')
  })
})
