import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import { CommanderWorkspace } from './CommanderWorkspace'

beforeEach(() => {
  useTickStore.setState({ priorities: [], roadRisks: [] })
})

describe('CommanderWorkspace', () => {
  it('shows a NotBuilt fallback when there is no priority feed yet', () => {
    render(<CommanderWorkspace onAnnounce={vi.fn()} onWhatIf={vi.fn()} />)
    expect(screen.getByText(/No recommendation is shown/)).toBeInTheDocument()
  })

  it('recommends the top-ranked village and links to Announce', () => {
    useTickStore.setState({
      priorities: [{ village_id: 'v1', eps: 0.91, tier: 'P1', components: { rainfall: 0.4 } }],
      roadRisks: [],
    })
    const onAnnounce = vi.fn()
    render(<CommanderWorkspace onAnnounce={onAnnounce} onWhatIf={vi.fn()} />)
    expect(screen.getByText(/v1/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Open Announce'))
    expect(onAnnounce).toHaveBeenCalledTimes(1)
  })
})
