import { useState } from 'react'
import { useTickStore } from '../store/useTickStore'
import { MapView } from './MapView'
import { ReplayControlBar } from './ReplayControlBar'
import { RightRail } from './RightRail'
import { ScenarioPickerModal } from './ScenarioPickerModal'

/** The Government "Dashboard" workspace (sub-project 1: restores the map/right-rail/replay-bar
 * that pre-existed the in-flight ConsoleShell rewrite, which had dropped them from App.tsx
 * entirely). Sub-project 2 adds the heatmap, working layer toggles, and the Risk Intelligence
 * Panel on top of this — this is the minimal, real, functional slice. */
export function DashboardWorkspace() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const wsStatus = useTickStore((s) => s.wsStatus)
  const error = useTickStore((s) => s.error)

  return (
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
        </div>
        <RightRail />
      </div>
      <ReplayControlBar />
      <ScenarioPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </>
  )
}
