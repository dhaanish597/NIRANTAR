import { useEffect, useState } from 'react'
import { promptInstall, subscribeToInstallPrompt } from '../lib/installPrompt'

/**
 * BUILD_PLAN.md task 5.1 — "install prompt working". A small, dismissible banner that appears
 * only when the browser has actually offered a real `beforeinstallprompt` event (see
 * `lib/installPrompt.ts`) — never a fake "Install" button that does nothing on browsers that
 * don't support installability (Firefox, Safari) or haven't met the criteria yet.
 */
export function InstallPrompt() {
  const [installable, setInstallable] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => subscribeToInstallPrompt((event) => setInstallable(event !== null)), [])

  if (!installable || dismissed) return null

  const handleInstall = async () => {
    const outcome = await promptInstall()
    if (outcome !== 'unavailable') setDismissed(true)
  }

  return (
    <div className="absolute right-4 bottom-16 flex items-center gap-2 rounded bg-slate-800/95 px-3 py-2 text-xs text-slate-200 shadow-lg">
      <span>Install NIRANTAR for offline use</span>
      <button
        type="button"
        onClick={() => void handleInstall()}
        className="rounded bg-emerald-600 px-2 py-1 font-semibold hover:bg-emerald-500"
      >
        Install
      </button>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss install prompt"
        className="px-1 text-slate-400 hover:text-slate-200"
      >
        ✕
      </button>
    </div>
  )
}
