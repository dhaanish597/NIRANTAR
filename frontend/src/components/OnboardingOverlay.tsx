import { useEffect, useState } from 'react'
import { hasSeenOnboarding, markOnboardingSeen } from '../lib/onboarding'

const AUTO_DISMISS_MS = 20_000

/**
 * BUILD_PLAN.md task 5.10 — a 20-second first-run overlay so a judge who touches the demo laptop
 * for the first time is never lost. Shown once per browser via `lib/onboarding.ts`'s
 * `localStorage`-backed dismissal (a pattern introduced for this task — see that module's
 * docstring for why nothing existing was reused).
 *
 * "20-second" is read literally: the overlay auto-dismisses itself after 20s (with a visible
 * countdown) in addition to being explicitly skippable at any time via the "Got it" button — a
 * judge who ignores it isn't left with a stuck overlay blocking the map, and a judge in a hurry
 * doesn't have to wait it out.
 */
export function OnboardingOverlay() {
  // Lazy initial state (read once, on mount) rather than an effect that calls setVisible(true)
  // synchronously — localStorage is read directly during the initializer, no cascading render.
  const [visible, setVisible] = useState(() => !hasSeenOnboarding())
  const [secondsLeft, setSecondsLeft] = useState(AUTO_DISMISS_MS / 1000)

  useEffect(() => {
    if (!visible) return
    const start = Date.now()
    const interval = window.setInterval(() => {
      const remainingMs = AUTO_DISMISS_MS - (Date.now() - start)
      if (remainingMs <= 0) {
        setVisible(false)
        markOnboardingSeen()
        return
      }
      setSecondsLeft(Math.ceil(remainingMs / 1000))
    }, 250)
    return () => window.clearInterval(interval)
  }, [visible])

  if (!visible) return null

  const dismiss = () => {
    setVisible(false)
    markOnboardingSeen()
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md rounded-lg border border-white/10 bg-slate-900 p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold">NIRANTAR — NER Landslide Early Warning</h2>
        <ul className="mb-4 list-disc space-y-2 pl-5 text-sm text-slate-300">
          <li>
            This map runs <span className="font-medium text-emerald-400">LIVE</span> by default.
            Click <span className="font-medium">Run Case Study</span> to replay a real historical
            disaster (e.g. Aizawl, 28 May 2024) on an accelerated clock.
          </li>
          <li>
            During a replay, watch cells escalate Green → Red, roads get flagged, and the
            Priority List rank villages P1/P2/P3 in real time.
          </li>
          <li>
            Click any village for its evacuation detail, or open the Explainability panel for the
            plain-language reasoning behind a risk score.
          </li>
          <li>Everything shown works with the network cable unplugged — nothing here needs live internet.</li>
        </ul>
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500">Dismissing automatically in {secondsLeft}s…</span>
          <button
            type="button"
            onClick={dismiss}
            className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold hover:bg-emerald-500"
          >
            Got it — let&apos;s go
          </button>
        </div>
      </div>
    </div>
  )
}
