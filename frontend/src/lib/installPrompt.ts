/**
 * Wraps the browser's `beforeinstallprompt` event (BUILD_PLAN.md task 5.1 — "install prompt
 * working") behind a small subscribe API so the UI component stays a thin renderer. The browser
 * fires `beforeinstallprompt` once, early, and only if the page passes PWA installability
 * criteria (served over a secure context with a valid manifest + registered service worker,
 * roughly) — a listener registered after the event already fired would miss it, so this module
 * attaches its listener at import time (module scope), not inside a component effect that could
 * mount after the fact.
 */

// Minimal shape of the (non-standard, Chromium-only) BeforeInstallPromptEvent — not in
// lib.dom.d.ts, so declared locally rather than pulling in a whole extra type-only dependency for
// one interface.
export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

type Listener = (event: BeforeInstallPromptEvent | null) => void

let deferredPrompt: BeforeInstallPromptEvent | null = null
const listeners = new Set<Listener>()

function isBrowserEnvironment(): boolean {
  return typeof window !== 'undefined' && typeof window.addEventListener === 'function'
}

if (isBrowserEnvironment()) {
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault() // suppress the browser's own mini-infobar; we render our own control
    deferredPrompt = event as unknown as BeforeInstallPromptEvent
    for (const listener of listeners) listener(deferredPrompt)
  })
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null
    for (const listener of listeners) listener(null)
  })
}

/** Current deferred prompt, if the browser has offered one and it hasn't been consumed/cleared
 * yet. Null means "not installable right now" (already installed, criteria not met, or the
 * browser doesn't support the event at all — e.g. Firefox/Safari, which never fire it). */
export function getDeferredInstallPrompt(): BeforeInstallPromptEvent | null {
  return deferredPrompt
}

/** Subscribe to changes in install-prompt availability. Returns an unsubscribe function. Fires
 * immediately with the current value so a component mounting after the event already fired still
 * sees it (covers the common case where `beforeinstallprompt` arrives before React mounts). */
export function subscribeToInstallPrompt(listener: Listener): () => void {
  listeners.add(listener)
  listener(deferredPrompt)
  return () => listeners.delete(listener)
}

/** Shows the browser's real install UI using the captured event, then clears it — a
 * `BeforeInstallPromptEvent` can only be used once. */
export async function promptInstall(): Promise<'accepted' | 'dismissed' | 'unavailable'> {
  const event = deferredPrompt
  if (!event) return 'unavailable'
  await event.prompt()
  const choice = await event.userChoice
  deferredPrompt = null
  for (const listener of listeners) listener(null)
  return choice.outcome
}

/** Test-only reset — mirrors the `_resetEvalReportCacheForTests` pattern already used in
 * `lib/evalReport.ts` for module-level state that would otherwise leak between tests. */
export function _resetInstallPromptForTests(): void {
  deferredPrompt = null
  listeners.clear()
}
