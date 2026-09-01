import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

// MapView needs MapLibre GL, which needs a real WebGL canvas jsdom doesn't provide — same
// tradeoff VillageView.test.tsx already documents and mocks.
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

import { DashboardWorkspace } from './DashboardWorkspace'

describe('DashboardWorkspace', () => {
  it('renders a Run Case Study trigger', () => {
    render(<DashboardWorkspace />)
    expect(document.querySelector('.dashboard-workspace')).toBeInTheDocument()
    expect(screen.getByText('Run Case Study')).toBeInTheDocument()
  })
})
