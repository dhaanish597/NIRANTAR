import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { buildClientFallbackForecast } from '../lib/forecast'
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
export function DashboardWorkspace({ onOpenReports = () => undefined }: { onOpenReports?: (reportId?: string) => void }) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [layers, setLayers] = useState<Record<MapLayerKey, boolean>>({ risk: true, rainfall: false, villages: true, shelters: false, roads: true, route: false })
  const wsStatus = useTickStore((s) => s.wsStatus)
  const error = useTickStore((s) => s.error)
  const aoi = useTickStore((s) => s.aoi)
  const latestTick = useTickStore((s) => s.latestTick)
  const modeState = useTickStore((s) => s.modeState)
  const latestTickRef = useRef(latestTick)
  const forecast = useTickStore((s) => s.forecast)
  const selectedForecastDate = useTickStore((s) => s.selectedForecastDate)
  const setForecast = useTickStore((s) => s.setForecast)
  const selectForecastDay = useTickStore((s) => s.selectForecastDay)
  const [forecastLoading, setForecastLoading] = useState(true)
  const [forecastError, setForecastError] = useState<string | null>(null)
  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'

  useEffect(() => { latestTickRef.current = latestTick }, [latestTick])

  useEffect(() => {
    let active = true
    if (mode === 'replay') {
      setForecast(null)
      setForecastLoading(false)
      setForecastError('Forecast disabled in replay; reconstructed scenario frames are authoritative.')
      return () => { active = false }
    }
    setForecastLoading(true)
    if (typeof api.getRiskForecast !== 'function') {
      setForecast(buildClientFallbackForecast(aoi?.id ?? 'aizawl', aoi?.name ?? 'Aizawl', latestTickRef.current))
      setForecastLoading(false)
      return () => { active = false }
    }
    const timeout = new Promise<never>((_, reject) => {
      window.setTimeout(() => reject(new Error('forecast request timed out')), 8000)
    })
    void Promise.race([api.getRiskForecast(aoi?.id ?? 'aizawl'), timeout]).then((next) => {
      if (!active) return
      setForecast(next)
      setForecastError(null)
    }).catch(() => { if (active) { setForecast(buildClientFallbackForecast(aoi?.id ?? 'aizawl', aoi?.name ?? 'Aizawl', latestTickRef.current)); setForecastError('Forecast service unavailable; deterministic fallback is active.') } }).finally(() => { if (active) setForecastLoading(false) })
    return () => { active = false }
  }, [aoi?.id, aoi?.name, mode, setForecast])

  return (
    <>
      <ForecastStrip forecast={forecast} selectedDate={selectedForecastDate} loading={forecastLoading} error={forecastError} onSelect={selectForecastDay} />
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
        <RightRail onOpenReports={onOpenReports} />
      </div>
      <ReplayControlBar />
      <ScenarioPickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} />
    </>
  )
}

function ForecastStrip({ forecast, selectedDate, loading, error, onSelect }: { forecast: import('../types/schemas').RiskForecast | null; selectedDate: string | null; loading: boolean; error: string | null; onSelect: (day: import('../types/schemas').RiskForecastDay) => void }) {
  return <section className="forecast-strip" aria-label="Five-day landslide risk forecast">
    <div className="forecast-heading"><div><p className="eyebrow">Date-wise outlook</p><h2>Landslide risk forecast</h2></div><span className={`forecast-source ${forecast?.source?.toLowerCase() ?? 'pending'}`}>{forecast?.source ?? (loading ? 'LOADING' : 'UNAVAILABLE')}</span></div>
    {error && <p className="forecast-error">Forecast unavailable: {error}</p>}
    {loading && !forecast && <div className="forecast-loading">Loading five-day outlook…</div>}
    {forecast && <div className="forecast-cards">{forecast.forecast.map((day) => <button key={day.date} type="button" className={`forecast-card ${selectedDate === day.date ? 'selected' : ''}`} aria-pressed={selectedDate === day.date} onClick={() => onSelect(day)}><span className="forecast-day">{day.day_label}</span><time dateTime={day.date}>{new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time><strong className={`forecast-risk ${day.risk_level.toLowerCase().replace(' ', '-')}`}>{day.risk_level}</strong><b>{Math.round(day.risk_probability * 100)}%</b><span>{day.rainfall_mm.toFixed(1)} mm rain</span></button>)}</div>}
  </section>
}
