import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useTickStore } from '../store/useTickStore'
import { AuditWorkspace } from './AuditWorkspace'

beforeEach(() => {
  useTickStore.setState({ auditEvents: [], auditTrailAlertId: null })
})

describe('AuditWorkspace', () => {
  it('shows a NotBuilt fallback when no audit events exist', () => {
    render(<AuditWorkspace />)
    expect(screen.getByText(/No audit events have been received/)).toBeInTheDocument()
  })

  it('lists distinct alert_ids and opens the trail modal on click', () => {
    useTickStore.setState({
      auditEvents: [
        {
          event_id: 'e1',
          alert_id: 'alert-1',
          kind: 'AI_FLAGGED',
          actor: 'system',
          t: '2026-01-01T00:00:00+05:30',
          payload: {},
          input_hash: 'x',
          prev_hash: 'x',
          hash: 'x',
        },
      ],
    })
    render(<AuditWorkspace />)
    expect(screen.getByText('alert-1')).toBeInTheDocument()
    fireEvent.click(screen.getByText('View trail'))
    expect(useTickStore.getState().auditTrailAlertId).toBe('alert-1')
  })
})
