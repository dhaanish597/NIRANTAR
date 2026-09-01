import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
  return { MapLibreMap: FakeMap, addProtocol: vi.fn() }
})

vi.mock('./lib/ws', () => ({ connectTickSocket: () => () => {} }))
vi.mock('./lib/api', () => ({
  api: {
    getState: () => Promise.resolve({ mode: 'live', scenario_id: null, scenario_time: null, speed_factor: 1, paused: false }),
    getScenarios: () => Promise.resolve([]),
    getAoi: () => Promise.resolve({ id: 'aizawl', name: 'Aizawl', center: { lat: 0, lon: 0 } }),
    listCitizenReports: () => Promise.resolve([]),
    listAnnouncements: () => Promise.resolve([]),
  },
}))
// OnboardingOverlay is a real, required root mount (see App.tsx) — but its own copy literally
// contains the exact text "Run Case Study", which collides with DashboardWorkspace's button of
// the same text under a plain getByText query. This routing test isn't exercising onboarding, so
// mark it already-seen (its own real dismissal mechanism, lib/onboarding.ts) rather than asserting
// against ambiguous text.
vi.mock('./lib/onboarding', () => ({ hasSeenOnboarding: () => true, markOnboardingSeen: () => {} }))

import App from './App'

beforeEach(() => {
  history.pushState({}, '', '/')
})

describe('App routing', () => {
  it('redirects / to the Dashboard workspace', () => {
    render(<App />)
    expect(screen.getByText('Run Case Study')).toBeInTheDocument()
  })

  it('renders the 5 Government nav items', () => {
    render(<App />)
    for (const label of ['Dashboard', 'AI Emergency Commander', 'What-if Simulator', 'Audit', 'Announce']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('navigates to the Announce workspace', () => {
    render(<App />)
    // fireEvent (not a raw .click()) so React's batched state update actually flushes before the
    // assertion below runs — a plain element.click() leaves it pending in the microtask queue.
    fireEvent.click(screen.getByText('Announce'))
    expect(screen.getByText('Officer ID')).toBeInTheDocument()
  })

  it('renders the Citizen app on a /citizen path', () => {
    history.pushState({}, '', '/citizen/alert')
    render(<App />)
    expect(screen.getByText(/Announcements/)).toBeInTheDocument()
  })
})
