import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { AuditEvent } from '../types/schemas'
import { AuditTrailView } from './AuditTrailView'

function makeEvent(kind: AuditEvent['kind'], overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    event_id: `evt-${kind}`,
    alert_id: 'alert-v1-1',
    kind,
    actor: 'system',
    t: '2026-05-28T03:14:00+00:00',
    payload: {},
    input_hash: 'x',
    prev_hash: 'y',
    hash: 'z',
    ...overrides,
  }
}

beforeEach(() => {
  useTickStore.setState({ auditTrailAlertId: null })
})

describe('AuditTrailView', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<AuditTrailView />)
    expect(container).toBeEmptyDOMElement()
  })

  it('fetches and renders the real chain via GET /api/audit/{alert_id} when opened', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockResolvedValue([
      makeEvent('AI_FLAGGED', { t: '2026-05-28T03:14:00+00:00' }),
      makeEvent('DDMA_APPROVED', { t: '2026-05-28T03:19:00+00:00', actor: 'ddma:officer_1' }),
    ])
    useTickStore.setState({ auditTrailAlertId: 'alert-v1-1' })
    render(<AuditTrailView />)

    await waitFor(() => expect(screen.getByText('AI Flagged')).toBeInTheDocument())
    expect(screen.getByText('DDMA Approved')).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith('alert-v1-1')
    spy.mockRestore()
  })

  it('gracefully shows "not yet reached" for stages the chain has not gotten to yet', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockResolvedValue([makeEvent('AI_FLAGGED')])
    useTickStore.setState({ auditTrailAlertId: 'alert-v1-1' })
    render(<AuditTrailView />)

    await waitFor(() => expect(screen.getByText('AI Flagged')).toBeInTheDocument())
    expect(screen.getByText(/DDMA Decision — not yet reached/)).toBeInTheDocument()
    expect(screen.getByText(/Disseminated — not yet reached/)).toBeInTheDocument()
    expect(screen.getByText(/Village Acknowledged — not yet reached/)).toBeInTheDocument()
    spy.mockRestore()
  })

  it('shows a real (not fabricated) empty state for an alert with no events yet', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockResolvedValue([])
    useTickStore.setState({ auditTrailAlertId: 'no-such-alert' })
    render(<AuditTrailView />)

    await waitFor(() =>
      expect(screen.getByText(/No audit events recorded yet/)).toBeInTheDocument(),
    )
    spy.mockRestore()
  })

  it('shows an error message if the fetch fails, without crashing', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockRejectedValue(new Error('network error'))
    useTickStore.setState({ auditTrailAlertId: 'alert-v1-1' })
    render(<AuditTrailView />)

    await waitFor(() => expect(screen.getByText(/Could not load/)).toBeInTheDocument())
    spy.mockRestore()
  })

  it('manual lookup re-fetches a different alert_id', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockResolvedValue([makeEvent('AI_FLAGGED')])
    useTickStore.setState({ auditTrailAlertId: 'alert-v1-1' })
    render(<AuditTrailView />)
    await waitFor(() => expect(spy).toHaveBeenCalledWith('alert-v1-1'))

    fireEvent.change(screen.getByLabelText('Alert ID'), { target: { value: 'alert-v2-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Look up' }))

    await waitFor(() => expect(spy).toHaveBeenCalledWith('alert-v2-2'))
    spy.mockRestore()
  })

  it('calls closeAuditTrail when the close button is clicked', async () => {
    const spy = vi.spyOn(api, 'getAuditTrail').mockResolvedValue([])
    useTickStore.setState({ auditTrailAlertId: 'alert-v1-1' })
    render(<AuditTrailView />)
    await waitFor(() => expect(spy).toHaveBeenCalled())

    fireEvent.click(screen.getByLabelText('Close audit trail'))
    expect(useTickStore.getState().auditTrailAlertId).toBeNull()
    spy.mockRestore()
  })
})
