import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, AuditEvent, SettlementPriority, VillageIsolation } from '../types/schemas'
import { DdmaConsole } from './DdmaConsole'

function makeCard(overrides: Partial<ActionCard> = {}): ActionCard {
  return {
    alert_id: 'alert-v1-1',
    village_id: 'v1',
    stage: 'RED',
    headline: 'Evacuate Now',
    reason_plain: 'Rising 72-hour rainfall over this slope.',
    shelter_name: 'Test Shelter',
    route: null,
    roads_to_avoid: ['NH-6'],
    what_to_carry: ['ID'],
    contact: 'placeholder',
    issued_at: '2026-05-28T03:14:00+00:00',
    valid_until: '2026-05-28T09:14:00+00:00',
    safe_window_hours: [0.0, 1.0],
    translations: {},
    audio_urls: {},
    ...overrides,
  }
}

const priorities: SettlementPriority[] = [
  { village_id: 'v1', eps: 0.82, tier: 'P1', components: { p_fail: 0.5, rii: 0.3 } },
]
const isolations: VillageIsolation[] = [
  {
    village_id: 'v1',
    name: 'Hunthar',
    population: 1200,
    p_isolated: 0.9,
    isolated_now: true,
    alternate_route_exists: false,
    est_duration_hours: 6,
    severed_links: ['e1'],
  },
]

function makeAuditEvent(kind: AuditEvent['kind']): AuditEvent {
  return {
    event_id: 'evt-1',
    alert_id: 'alert-v1-1',
    kind,
    actor: 'ddma:officer_1',
    t: '2026-05-28T03:19:00+00:00',
    payload: { decision: 'approved' },
    input_hash: 'x',
    prev_hash: 'y',
    hash: 'z',
  }
}

beforeEach(() => {
  useTickStore.setState({ actionCards: [], priorities: [], isolations: [], auditTrailAlertId: null })
})

describe('DdmaConsole', () => {
  it('shows an honest empty state when no recommendations are pending', () => {
    render(<DdmaConsole onBack={() => {}} />)
    expect(screen.getByText(/No AI recommendations issued yet/)).toBeInTheDocument()
  })

  it('makes human-in-the-loop visually obvious: no machine issues an evacuation order', () => {
    render(<DdmaConsole onBack={() => {}} />)
    expect(screen.getByText(/No machine issues an evacuation order\./)).toBeInTheDocument()
  })

  it('renders the AI rationale, EPS breakdown, and affected population for a pending card', () => {
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)
    expect(screen.getByText(/Rising 72-hour rainfall/)).toBeInTheDocument()
    expect(screen.getByText(/EPS 0.82 breakdown/)).toBeInTheDocument()
    expect(screen.getByText('p_fail')).toBeInTheDocument()
    expect(screen.getByText(/pop\. 1,200/)).toBeInTheDocument()
  })

  it('shows Approve / Modify / Reject buttons for a pending recommendation', () => {
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Modify' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
  })

  it('Modify is disabled until a note is entered', () => {
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)
    const modifyButton = screen.getByRole('button', { name: 'Modify' }) as HTMLButtonElement
    expect(modifyButton.disabled).toBe(true)
    fireEvent.change(screen.getByPlaceholderText(/Notes/), { target: { value: 'move shelter' } })
    expect(modifyButton.disabled).toBe(false)
  })

  it('Approve calls the real backend via api.submitDdmaDecision and shows the recorded event', async () => {
    const spy = vi.spyOn(api, 'submitDdmaDecision').mockResolvedValue(makeAuditEvent('DDMA_APPROVED'))
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.getByText(/Approved — recorded as/)).toBeInTheDocument())
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ decision: 'approved', action_card: expect.objectContaining({ alert_id: 'alert-v1-1' }) }),
    )
    spy.mockRestore()
  })

  it('Reject calls the backend with decision "rejected"', async () => {
    const spy = vi.spyOn(api, 'submitDdmaDecision').mockResolvedValue(makeAuditEvent('STOOD_DOWN'))
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(spy).toHaveBeenCalled())
    expect(spy.mock.calls[0][0]).toEqual(expect.objectContaining({ decision: 'rejected' }))
    spy.mockRestore()
  })

  it('shows an error message when the decision submission fails, without crashing', async () => {
    const spy = vi.spyOn(api, 'submitDdmaDecision').mockRejectedValue(new Error('POST /api/ddma/decide -> 500'))
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.getByText(/Could not submit decision/)).toBeInTheDocument())
    spy.mockRestore()
  })

  it('"View audit trail" opens the audit trail modal for this card\'s alert_id', async () => {
    const spy = vi.spyOn(api, 'submitDdmaDecision').mockResolvedValue(makeAuditEvent('DDMA_APPROVED'))
    useTickStore.setState({ actionCards: [makeCard()], priorities, isolations })
    render(<DdmaConsole onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => screen.getByRole('button', { name: 'View audit trail' }))
    fireEvent.click(screen.getByRole('button', { name: 'View audit trail' }))

    expect(useTickStore.getState().auditTrailAlertId).toBe('alert-v1-1')
    spy.mockRestore()
  })

  it('calls onBack when "Back to map" is clicked', () => {
    const onBack = vi.fn()
    render(<DdmaConsole onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: /Back to map/ }))
    expect(onBack).toHaveBeenCalled()
  })
})
