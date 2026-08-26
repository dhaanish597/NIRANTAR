import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { markOnboardingSeen } from '../lib/onboarding'
import { OnboardingOverlay } from './OnboardingOverlay'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('OnboardingOverlay', () => {
  it('shows on first run (localStorage empty)', () => {
    render(<OnboardingOverlay />)
    expect(screen.getByText(/NIRANTAR/)).toBeInTheDocument()
  })

  it('does not show once the user has already dismissed it (persisted)', () => {
    markOnboardingSeen()
    render(<OnboardingOverlay />)
    expect(screen.queryByText(/NIRANTAR/)).not.toBeInTheDocument()
  })

  it('dismisses and persists when "Got it" is clicked, and does not reappear on remount', () => {
    const { unmount } = render(<OnboardingOverlay />)
    expect(screen.getByText(/NIRANTAR/)).toBeInTheDocument()

    act(() => {
      fireEvent.click(screen.getByText(/Got it/))
    })
    expect(screen.queryByText(/NIRANTAR/)).not.toBeInTheDocument()
    unmount()

    render(<OnboardingOverlay />)
    expect(screen.queryByText(/NIRANTAR/)).not.toBeInTheDocument()
  })

  it('auto-dismisses after 20 seconds and persists the dismissal', () => {
    vi.useFakeTimers()
    render(<OnboardingOverlay />)
    expect(screen.getByText(/NIRANTAR/)).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(20_000)
    })
    expect(screen.queryByText(/NIRANTAR/)).not.toBeInTheDocument()

    vi.useRealTimers()
    render(<OnboardingOverlay />)
    expect(screen.queryByText(/NIRANTAR/)).not.toBeInTheDocument()
  })
})
