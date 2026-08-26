import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  _resetInstallPromptForTests,
  getDeferredInstallPrompt,
  promptInstall,
  subscribeToInstallPrompt,
} from './installPrompt'

function dispatchFakeBeforeInstallPrompt(overrides: { outcome?: 'accepted' | 'dismissed' } = {}) {
  const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: string; platform: string }>
  }
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome: overrides.outcome ?? 'accepted', platform: 'web' })
  window.dispatchEvent(event)
  return event
}

beforeEach(() => {
  _resetInstallPromptForTests()
})

afterEach(() => {
  _resetInstallPromptForTests()
})

describe('installPrompt', () => {
  it('has no deferred prompt before beforeinstallprompt has fired', () => {
    expect(getDeferredInstallPrompt()).toBeNull()
  })

  it('captures the event when beforeinstallprompt fires', () => {
    dispatchFakeBeforeInstallPrompt()
    expect(getDeferredInstallPrompt()).not.toBeNull()
  })

  it('subscribeToInstallPrompt fires immediately with the current value, and again on change', () => {
    const calls: Array<boolean> = []
    const unsubscribe = subscribeToInstallPrompt((event) => calls.push(event !== null))
    expect(calls).toEqual([false]) // nothing deferred yet

    dispatchFakeBeforeInstallPrompt()
    expect(calls).toEqual([false, true])
    unsubscribe()
  })

  it('promptInstall returns "unavailable" when there is nothing to prompt', async () => {
    expect(await promptInstall()).toBe('unavailable')
  })

  it('promptInstall calls the real captured event.prompt(), returns the real user choice, and clears the prompt', async () => {
    const event = dispatchFakeBeforeInstallPrompt({ outcome: 'accepted' })
    const outcome = await promptInstall()
    expect(event.prompt).toHaveBeenCalled()
    expect(outcome).toBe('accepted')
    expect(getDeferredInstallPrompt()).toBeNull() // consumed, can't be reused
  })

  it('clears the deferred prompt on appinstalled', () => {
    dispatchFakeBeforeInstallPrompt()
    expect(getDeferredInstallPrompt()).not.toBeNull()
    window.dispatchEvent(new Event('appinstalled'))
    expect(getDeferredInstallPrompt()).toBeNull()
  })
})
