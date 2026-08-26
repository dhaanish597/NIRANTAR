/**
 * Persistence helper backing `OnboardingOverlay` (BUILD_PLAN.md task 5.10 — "a 20-second
 * first-run overlay so a judge who touches the laptop for the first time is never lost", shown
 * once per browser).
 *
 * No other module in this codebase used browser storage before this (checked: no `localStorage`
 * reference existed anywhere under `frontend/src` prior to this task), so there was no existing
 * pattern to extend — this establishes one: a single namespaced key, read/write wrapped in
 * try/catch. `localStorage` can throw (not just return null) in a private-browsing context in
 * some browsers, or when a test environment doesn't provide it at all — a demo laptop should
 * never crash on this, it should just fall back to showing the overlay every time (fail open,
 * never fail closed and trap a judge behind a broken overlay).
 */

const ONBOARDING_STORAGE_KEY = 'nirantar:onboarding-dismissed-v1'

export function hasSeenOnboarding(): boolean {
  try {
    return window.localStorage.getItem(ONBOARDING_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function markOnboardingSeen(): void {
  try {
    window.localStorage.setItem(ONBOARDING_STORAGE_KEY, '1')
  } catch {
    // Storage unavailable (private browsing, disabled cookies/storage, non-browser test
    // environment) — degrade to "the overlay will just show again next time", never throw.
  }
}
