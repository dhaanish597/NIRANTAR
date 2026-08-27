import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, AuditEvent } from '../types/schemas'
import { CitizenApp } from './CitizenApp'

// The alert/route tabs render MapView (ported from VillageView.tsx) — same MapLibre GL /
// jsdom-WebGL tradeoff VillageView.test.tsx already documents and mocks.
vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor(_opts: unknown) {}
    on(event: string, arg2: unknown, arg3?: unknown) {
      if (event === 'load' && typeof arg2 === 'function' && arg3 === undefined) arg2()
      return this
    }
    once(event: string, cb: () => void) {
      if (event === 'load') cb()
      return this
    }
    addSource() {
      return this
    }
    addLayer() {
      return this
    }
    getSource() {
      return { setData: vi.fn() }
    }
    getCanvas() {
      return { style: {} }
    }
    isStyleLoaded() {
      return true
    }
    setCenter() {
      return this
    }
    remove() {}
  }
  return { MapLibreMap: FakeMap }
})

vi.mock('../lib/api', () => ({
  api: { acknowledgeVillage: vi.fn() },
}))

const CARD: ActionCard = {
  alert_id: 'alert-1',
  village_id: 'v1',
  stage: 'RED',
  headline: 'Evacuate now',
  reason_plain: 'Heavy rainfall and slope movement',
  shelter_name: 'Community Hall',
  route: {
    village_id: 'v1',
    shelter_id: 's1',
    shelter_name: 'Community Hall',
    geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
    distance_m: 2400,
    est_walk_minutes: 18,
    avoided_roads: [],
    shelter_capacity_ok: true,
  },
  roads_to_avoid: ['NH-6'],
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
  useTickStore.setState({ actionCards: [], isolations: [], announcements: [] })
})

describe('CitizenApp — alert tab (ported from VillageView)', () => {
  it('shows a fallback when there is no active alert for any village', () => {
    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText(/No active alert for any village right now/)).toBeInTheDocument()
  })

  it('renders the real stage card and acknowledges evacuation', async () => {
    useTickStore.setState({ actionCards: [CARD] })
    const event: AuditEvent = {
      event_id: 'evt-1',
      alert_id: 'alert-1',
      kind: 'VILLAGE_ACKNOWLEDGED',
      actor: 'village:v1',
      t: '2026-01-01T01:00:00+05:30',
      payload: {},
      input_hash: 'x',
      prev_hash: 'x',
      hash: 'x',
    }
    vi.mocked(api.acknowledgeVillage).mockResolvedValue(event)

    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText('RED')).toBeInTheDocument()
    expect(screen.getByText('Evacuate now')).toBeInTheDocument()

    fireEvent.click(screen.getByText('I have evacuated'))
    await waitFor(() =>
      expect(api.acknowledgeVillage).toHaveBeenCalledWith({ alert_id: 'alert-1', village_id: 'v1' }),
    )
    expect(await screen.findByText('✓ Evacuation acknowledged')).toBeInTheDocument()
  })
})

describe('CitizenApp — route tab (ported from VillageView)', () => {
  it('renders the real shelter/distance detail when a route exists', () => {
    useTickStore.setState({ actionCards: [CARD] })
    render(<CitizenApp route="route" onNavigate={vi.fn()} />)
    expect(screen.getByText('Community Hall')).toBeInTheDocument()
    expect(screen.getByText(/2\.4 km/)).toBeInTheDocument()
  })
})

describe('CitizenApp — announcement tab', () => {
  it('shows a NotBuilt fallback when no announcement has been sent', () => {
    render(<CitizenApp route="announcement" onNavigate={vi.fn()} />)
    expect(screen.getByText(/No announcement has been sent yet/)).toBeInTheDocument()
  })

  it('renders a real announcement from the shared store', () => {
    useTickStore.setState({
      announcements: [
        {
          id: 'ann-1',
          alert_id: 'a1',
          village_id: 'v1',
          stage: 'RED',
          message: 'Evacuate to the community hall',
          language: 'en',
          issued_by: 'officer-1',
          issued_at: '2026-01-01T00:00:00+05:30',
          channel_results: [],
          cap_xml: '<alert></alert>',
        },
      ],
    })
    render(<CitizenApp route="announcement" onNavigate={vi.fn()} />)
    expect(screen.getByText('Evacuate to the community hall')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
  })

  it('nav includes an Announcements tab', () => {
    render(<CitizenApp route="alert" onNavigate={vi.fn()} />)
    expect(screen.getByText(/Announcements/)).toBeInTheDocument()
  })
})
