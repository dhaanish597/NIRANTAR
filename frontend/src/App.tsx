import { useEffect, useState } from 'react'
import { AuditTrailView } from './components/AuditTrailView'
import { CounterfactualScorecard } from './components/CounterfactualScorecard'
import { DdmaConsole } from './components/DdmaConsole'
import { InstallPrompt } from './components/InstallPrompt'
import { MapView } from './components/MapView'
import { ModeBanner } from './components/ModeBanner'
import { OnboardingOverlay } from './components/OnboardingOverlay'
import { ReplayControlBar } from './components/ReplayControlBar'
import { RightRail } from './components/RightRail'
import { ScenarioPickerModal } from './components/ScenarioPickerModal'
import { VillageDetailDrawer } from './components/VillageDetailDrawer'
import { VillageView } from './components/VillageView'
import { useTickStore } from './store/useTickStore'

// Phase 0 scope: a single hardcoded AOI. Real AOI selection is out of scope until more than one
// AOI has pre-baked data (BUILD_PLAN.md Phase 1+).
const AOI_ID = 'aizawl'

// BUILD_PLAN.md tasks 3.7/3.10: no router library is used anywhere in this codebase (see
// package.json) — a simple local screen switch is the smallest addition consistent with the
// existing single-page-app structure, rather than introducing react-router for two extra screens.
type Screen = 'ops' | 'ddma' | 'village'

function App() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [screen, setScreen] = useState<Screen>('ops')
  const loadInitial = useTickStore((s) => s.loadInitial)
  const connect = useTickStore((s) => s.connect)
  const disconnect = useTickStore((s) => s.disconnect)
  const wsStatus = useTickStore((s) => s.wsStatus)
  const error = useTickStore((s) => s.error)

  useEffect(() => {
    void loadInitial(AOI_ID)
    connect()
    return () => disconnect()
  }, [loadInitial, connect, disconnect])

  return (
    <div className="flex h-screen flex-col">
      <ModeBanner />

      {screen === 'ops' && (
        <>
          <div className="relative flex flex-1 overflow-hidden">
            <div className="relative flex-1">
              <MapView />
              <div className="absolute top-4 left-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="rounded bg-emerald-600 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-emerald-500"
                >
                  Run Case Study
                </button>
                <button
                  type="button"
                  onClick={() => setScreen('ddma')}
                  className="rounded bg-slate-800 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-slate-700"
                >
                  DDMA Console
                </button>
                <button
                  type="button"
                  onClick={() => setScreen('village')}
                  className="rounded bg-slate-800 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-slate-700"
                >
                  Village View
                </button>
              </div>
              {wsStatus !== 'open' && (
                <div className="absolute bottom-4 left-4 rounded bg-black/60 px-3 py-1.5 text-xs text-slate-300">
                  WebSocket: {wsStatus}
                </div>
              )}
              {error && (
                <div className="absolute right-4 bottom-4 rounded bg-red-900/80 px-3 py-1.5 text-xs text-red-100">
                  {error}
                </div>
              )}
              <InstallPrompt />
            </div>
            <RightRail />
          </div>
          <ReplayControlBar />
        </>
      )}

      {screen === 'ddma' && <DdmaConsole onBack={() => setScreen('ops')} />}
      {screen === 'village' && <VillageView onBack={() => setScreen('ops')} />}

      <ScenarioPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />
      <VillageDetailDrawer />
      <CounterfactualScorecard />
      <AuditTrailView />
      <OnboardingOverlay />
    </div>
  )
}

export default App
