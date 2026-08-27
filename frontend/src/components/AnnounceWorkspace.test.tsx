import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, Announcement } from '../types/schemas'
import { AnnounceWorkspace } from './AnnounceWorkspace'

vi.mock('../lib/api', () => ({
  api: {
    sendAnnouncement: vi.fn(),
    submitDdmaDecision: vi.fn(),
  },
}))

const CARD: ActionCard = {
  alert_id: 'alert-1',
  village_id: 'v1',
  stage: 'RED',
  headline: 'Evacuate now',
  reason_plain: 'Heavy rainfall and slope movement',
  shelter_name: 'Community Hall',
  route: null,
  roads_to_avoid: [],
  what_to_carry: [],
  contact: '108',
  issued_at: '2026-01-01T00:00:00+05:30',
  valid_until: '2026-01-02T00:00:00+05:30',
  safe_window_hours: null,
  translations: {},
  audio_urls: {},
}

beforeEach(() => {
  vi.clearAllMocks()
  useTickStore.setState({
    actionCards: [CARD],
    priorities: [{ village_id: 'v1', eps: 0.8, tier: 'P1', components: {} }],
    isolations: [
      {
        village_id: 'v1',
        name: 'Test Village',
        population: 2840,
        p_isolated: 0.5,
        isolated_now: true,
        alternate_route_exists: false,
        est_duration_hours: null,
        severed_links: [],
      },
    ],
  })
})

describe('AnnounceWorkspace', () => {
  it('Approve & Dispatch calls sendAnnouncement with the village population as recipient_count', async () => {
    const announcement: Announcement = {
      id: 'ann-1',
      alert_id: 'alert-1',
      village_id: 'v1',
      stage: 'RED',
      message: 'Heavy rainfall and slope movement',
      language: 'en',
      issued_by: 'ddma-officer-placeholder (no real DDMA login system — type any identifier)',
      issued_at: '2026-01-01T00:00:00+05:30',
      channel_results: [
        { channel: 'sms', recipient_count: 2840, delivered_count: 2500, acknowledged_count: 900 },
      ],
      cap_xml: '<alert></alert>',
    }
    vi.mocked(api.sendAnnouncement).mockResolvedValue(announcement)

    render(<AnnounceWorkspace />)
    fireEvent.click(screen.getByText('Approve & Dispatch'))

    await waitFor(() => expect(api.sendAnnouncement).toHaveBeenCalledTimes(1))
    expect(api.sendAnnouncement).toHaveBeenCalledWith(
      expect.objectContaining({ action_card: CARD, recipient_count: 2840 }),
    )
    expect(await screen.findByText(/Dispatched for real/)).toBeInTheDocument()
    expect(screen.getByText(/2500\/2840 delivered/)).toBeInTheDocument()
  })

  it('Reject calls submitDdmaDecision, not sendAnnouncement', async () => {
    vi.mocked(api.submitDdmaDecision).mockResolvedValue({
      event_id: 'evt-1',
      alert_id: 'alert-1',
      kind: 'STOOD_DOWN',
      actor: 'ddma:officer',
      t: '2026-01-01T00:00:00+05:30',
      payload: {},
      input_hash: 'x',
      prev_hash: 'x',
      hash: 'x',
    })

    render(<AnnounceWorkspace />)
    fireEvent.click(screen.getByText('Reject'))

    await waitFor(() => expect(api.submitDdmaDecision).toHaveBeenCalledTimes(1))
    expect(api.sendAnnouncement).not.toHaveBeenCalled()
  })
})
