import { useState } from 'react'
import { useTickStore } from '../store/useTickStore'
import { MapView } from './MapView'
import { ReplayControlBar } from './ReplayControlBar'
import { RightRail } from './RightRail'
import { ScenarioPickerModal } from './ScenarioPickerModal'
import type { MapLayerKey } from './MapControls'
import './dashboard-workspace.css'

/** The Government "Dashboard" workspace (sub-project 1: restores the map/right-rail/replay-bar
 * that pre-existed the in-flight ConsoleShell rewrite, which had dropped them from App.tsx
 * entirely). Sub-project 2 adds the heatmap, working layer toggles, and the Risk Intelligence
 * Panel on top of this — this is the minimal, real, functional slice. */
export function DashboardWorkspace() {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [layers, setLayers] = useState<Record<MapLayerKey, boolean>>({ risk: true, rainfall: false, villages: true, shelters: false, roads: true, route: false })
  const wsStatus = useTickStore((s) => s.wsStatus)
  const error = useTickStore((s) => s.error)
  const aoi = useTickStore((s) => s.aoi)
  const latestTick = useTickStore((s) => s.latestTick)

  return (
    <>
      <div className="dashboard-workspace relative flex flex-1 overflow-hidden">
        <div className="map-stage">
          <MapView layers={layers} onLayerChange={(key, enabled) => setLayers((current) => ({ ...current, [key]: enabled }))} />
          <div className="dashboard-map-header">
            <div><p className="eyebrow">Operational view</p><h1>{aoi?.name ?? 'Aizawl'} area of interest</h1><span>Live terrain context · decision overlays on top</span></div>
            <button type="button" onClick={() => setPickerOpen(true)} className="case-study-button">Run Case Study <span>↗</span></button>
          </div>
          <div className="map-status-badge"><span className="status-dot" /> Map ready <span>·</span> {latestTick?.is_reconstructed ? 'Reconstructed feed' : 'Awaiting live feed'}</div>
          <div className="dashboard-map-footer">BASEMAP · OpenStreetMap-compatible local vector context <span>·</span> AOI: {aoi?.name ?? 'Aizawl'}</div>
          {wsStatus !== 'open' && (
            <div className="map-feed-status">
              WebSocket: {wsStatus}
            </div>
          )}
          {error && (
            <div className="map-error-status">
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
