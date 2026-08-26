import { beforeEach, describe, expect, it, vi } from 'vitest'
import { hasSeenOnboarding, markOnboardingSeen } from './onboarding'

beforeEach(() => {
  window.localStorage.clear()
})

describe('hasSeenOnboarding / markOnboardingSeen', () => {
  it('is false before markOnboardingSeen has ever been called', () => {
    expect(hasSeenOnboarding()).toBe(false)
  })

  it('is true after markOnboardingSeen is called (persists across "sessions", i.e. re-reads)', () => {
    markOnboardingSeen()
    expect(hasSeenOnboarding()).toBe(true)
  })

  it('fails open (returns false, never throws) when localStorage.getItem throws', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => hasSeenOnboarding()).not.toThrow()
    expect(hasSeenOnboarding()).toBe(false)
    spy.mockRestore()
  })

  it('markOnboardingSeen never throws even when localStorage.setItem throws', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('storage disabled')
    })
    expect(() => markOnboardingSeen()).not.toThrow()
    spy.mockRestore()
  })
})
