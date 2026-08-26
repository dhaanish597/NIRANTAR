import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { _resetInstallPromptForTests } from '../lib/installPrompt'
import { InstallPrompt } from './InstallPrompt'

function dispatchFakeBeforeInstallPrompt(outcome: 'accepted' | 'dismissed' = 'accepted') {
  const event = new Event('beforeinstallprompt', { cancelable: true }) as Event & {
    prompt: () => Promise<void>
    userChoice: Promise<{ outcome: string; platform: string }>
  }
  event.prompt = vi.fn().mockResolvedValue(undefined)
  event.userChoice = Promise.resolve({ outcome, platform: 'web' })
  act(() => {
    window.dispatchEvent(event)
  })
  return event
}

beforeEach(() => {
  _resetInstallPromptForTests()
})

afterEach(() => {
  _resetInstallPromptForTests()
})

describe('InstallPrompt', () => {
  it('renders nothing when the browser has not offered a real install prompt', () => {
    const { container } = render(<InstallPrompt />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the banner once a real beforeinstallprompt event fires', () => {
    render(<InstallPrompt />)
    dispatchFakeBeforeInstallPrompt()
    expect(screen.getByText('Install')).toBeInTheDocument()
  })

  it('clicking Install calls the real captured event.prompt() and hides the banner', async () => {
    render(<InstallPrompt />)
    const event = dispatchFakeBeforeInstallPrompt('accepted')

    await act(async () => {
      fireEvent.click(screen.getByText('Install'))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(event.prompt).toHaveBeenCalled()
    expect(screen.queryByText('Install')).not.toBeInTheDocument()
  })

  it('the dismiss button hides the banner without calling prompt()', () => {
    render(<InstallPrompt />)
    const event = dispatchFakeBeforeInstallPrompt()
    act(() => {
      fireEvent.click(screen.getByLabelText('Dismiss install prompt'))
    })
    expect(event.prompt).not.toHaveBeenCalled()
    expect(screen.queryByText('Install')).not.toBeInTheDocument()
  })
})
