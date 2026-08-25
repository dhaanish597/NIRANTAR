import { useEffect, useState } from 'react'
import { MapView } from './components/MapView'
import { ModeBanner } from './components/ModeBanner'
import { RightRail } from './components/RightRail'
import { ScenarioPickerModal } from './components/ScenarioPickerModal'
import { VillageDetailDrawer } from './components/VillageDetailDrawer'
import { useTickStore } from './store/useTickStore'

// Phase 0 scope: a single hardcoded AOI. Real AOI selection is out of scope until more than one
// AOI has pre-baked data (BUILD_PLAN.md Phase 1+).
const AOI_ID = 'aizawl'

function App() {
  const [pickerOpen, setPickerOpen] = useState(false)
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
      <div className="relative flex flex-1 overflow-hidden">
        <div className="relative flex-1">
          <MapView />
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="absolute top-4 left-4 rounded bg-emerald-600 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-emerald-500"
          >
            Run Case Study
          </button>
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
        </div>
        <RightRail />
      </div>
      <ScenarioPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />
      <VillageDetailDrawer />
    </div>
  )
}

export default App
