import 'fake-indexeddb/auto'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'
import { _resetOfflineDataForTests, cacheActionCards } from '../lib/offlineData'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, AuditEvent, VillageIsolation } from '../types/schemas'

// VillageView renders MapView (task 3.10 explicitly requires reusing it, not a second map
// implementation) — MapLibre GL needs a real WebGL canvas, which jsdom doesn't provide. Mocking
// the library (not MapView itself) keeps this a real test of MapView's own prop wiring
// (routeGeometry) while avoiding a WebGL dependency, the same tradeoff `browser-automation`/
// Playwright-based checks exist for at a different layer.
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

// Dynamic import AFTER the mock is registered (vi.mock is hoisted, but importing VillageView at
// module top-level after vi.mock is the standard, documented pattern).
const { VillageView } = await import('./VillageView')

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
    what_to_carry: ['ID', 'torch'],
    contact: 'DDMA control room (placeholder)',
    issued_at: '2026-05-28T03:14:00+00:00',
    valid_until: '2026-05-28T09:14:00+00:00',
    safe_window_hours: [0.5, 2.0],
    translations: {},
    audio_urls: {},
    ...overrides,
  }
}

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

function makeAckEvent(): AuditEvent {
  return {
    event_id: 'evt-ack',
    alert_id: 'alert-v1-1',
    kind: 'VILLAGE_ACKNOWLEDGED',
    actor: 'village:v1',
    t: '2026-05-28T04:00:00+00:00',
    payload: { village_id: 'v1' },
    input_hash: 'x',
    prev_hash: 'y',
    hash: 'z',
  }
}

beforeEach(() => {
  useTickStore.setState({ actionCards: [], isolations: [], auditTrailAlertId: null })
  _resetOfflineDataForTests()
})

describe('VillageView', () => {
  it('shows an honest empty state when no village currently has an active alert', () => {
    render(<VillageView onBack={() => {}} />)
    expect(screen.getByText(/No active alert for any village right now/)).toBeInTheDocument()
  })

  it('BUILD_PLAN.md task 5.3: the empty state falls back to the real IndexedDB-cached shelter/contact from the last known action card', async () => {
    await cacheActionCards([makeCard({ shelter_name: 'Cached Community Hall' })])
    render(<VillageView onBack={() => {}} />)
    await waitFor(() => expect(screen.getByText('Cached Community Hall')).toBeInTheDocument())
    expect(screen.getByText('DDMA control room (placeholder)')).toBeInTheDocument()
  })

  it('renders the big stage, headline, and reason for the village\'s action card', () => {
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)
    expect(screen.getByText('RED')).toBeInTheDocument()
    expect(screen.getByText('Evacuate Now')).toBeInTheDocument()
    expect(screen.getByText(/Rising 72-hour rainfall/)).toBeInTheDocument()
    expect(screen.getByText('Hunthar')).toBeInTheDocument()
  })

  it('renders roads to avoid, what to carry, and contact from the real ActionCard', () => {
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)
    expect(screen.getByText('NH-6')).toBeInTheDocument()
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('torch')).toBeInTheDocument()
    expect(screen.getByText(/DDMA control room \(placeholder\)/)).toBeInTheDocument()
  })

  it('the voice-alert play control is honestly disabled when no audio_urls exist (task 3.9 not built)', () => {
    useTickStore.setState({ actionCards: [makeCard({ audio_urls: {} })], isolations })
    render(<VillageView onBack={() => {}} />)
    const button = screen.getByRole('button', { name: /not yet available/ }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    expect(button.title).toMatch(/not yet available/i)
  })

  it('renders a real, enabled audio control when audio_urls IS populated (forward-compat)', () => {
    useTickStore.setState({
      actionCards: [makeCard({ audio_urls: { mizo: 'https://example.invalid/audio/mizo.mp3' } })],
      isolations,
    })
    render(<VillageView onBack={() => {}} />)
    expect(screen.queryByRole('button', { name: /not yet available/ })).not.toBeInTheDocument()
    expect(screen.getByText('mizo')).toBeInTheDocument()
  })

  it('never renders the phrase "time to landslide"', () => {
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)
    expect(screen.queryByText(/time to landslide/i)).not.toBeInTheDocument()
  })

  it('"I have evacuated" calls the real backend and shows the recorded VILLAGE_ACKNOWLEDGED event', async () => {
    const spy = vi.spyOn(api, 'acknowledgeVillage').mockResolvedValue(makeAckEvent())
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'I have evacuated' }))

    await waitFor(() => expect(screen.getByText(/Evacuation acknowledged/)).toBeInTheDocument())
    expect(spy).toHaveBeenCalledWith({ alert_id: 'alert-v1-1', village_id: 'v1' })
    spy.mockRestore()
  })

  it('BUILD_PLAN.md task 5.3: queues the acknowledgement (not an error) when the request fails, without crashing', async () => {
    const spy = vi.spyOn(api, 'acknowledgeVillage').mockRejectedValue(new Error('network error'))
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'I have evacuated' }))

    await waitFor(() => expect(screen.getByText(/Saved — offline/)).toBeInTheDocument())
    expect(spy).toHaveBeenCalledWith({ alert_id: 'alert-v1-1', village_id: 'v1' })
    spy.mockRestore()
  })

  it('BUILD_PLAN.md task 5.3: queues immediately without even attempting the request when navigator.onLine is false', async () => {
    const spy = vi.spyOn(api, 'acknowledgeVillage')
    const onLineSpy = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={() => {}} />)

    fireEvent.click(screen.getByRole('button', { name: 'I have evacuated' }))

    await waitFor(() => expect(screen.getByText(/Saved — offline/)).toBeInTheDocument())
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
    onLineSpy.mockRestore()
  })

  it('calls onBack when Back is clicked', () => {
    const onBack = vi.fn()
    useTickStore.setState({ actionCards: [makeCard()], isolations })
    render(<VillageView onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: '← Back' }))
    expect(onBack).toHaveBeenCalled()
  })

  it('calls onBack from the empty state too', () => {
    const onBack = vi.fn()
    render(<VillageView onBack={onBack} />)
    fireEvent.click(screen.getByRole('button', { name: '← Back to map' }))
    expect(onBack).toHaveBeenCalled()
  })
})
