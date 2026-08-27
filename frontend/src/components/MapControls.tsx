import { useState } from 'react'

export type MapLayerKey = 'risk' | 'rainfall' | 'villages' | 'shelters' | 'roads' | 'route'
export type MapLayerState = Record<MapLayerKey, boolean>

const layers: Array<[MapLayerKey, string, boolean]> = [
  ['risk', 'Risk overlay', true],
  ['rainfall', 'Rainfall', false],
  ['villages', 'Villages', true],
  ['shelters', 'Shelters', false],
  ['roads', 'Road hazards', true],
  ['route', 'Evacuation route', false],
]

function Icon({ name }: { name: 'plus' | 'minus' | 'target' | 'expand' | 'layers' | 'reset' }) {
  const paths = {
    plus: <><path d="M12 5v14M5 12h14" /></>,
    minus: <path d="M5 12h14" />,
    target: <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>,
    expand: <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M21 16v5h-5" /><path d="M3 8l5-5M16 3l5 5M3 16l5 5M16 21l5-5" /></>,
    layers: <><path d="m12 3 8 4-8 4-8-4 8-4Z" /><path d="m4 12 8 4 8-4M4 17l8 4 8-4" /></>,
    reset: <><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6" /><path d="M4 4v4.6h4.6" /></>,
  }
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

export function MapControls({ onZoomIn, onZoomOut, onReset, onLocate, onFullscreen, onLayerChange, routeEnabled = false }: {
  onZoomIn: () => void; onZoomOut: () => void; onReset: () => void; onLocate: () => void; onFullscreen: () => void; onLayerChange?: (key: MapLayerKey, enabled: boolean) => void; routeEnabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState<MapLayerState>({ risk: true, rainfall: false, villages: true, shelters: false, roads: true, route: routeEnabled })
  const toggle = (key: MapLayerKey) => setState((current) => { const enabled = !current[key]; onLayerChange?.(key, enabled); return { ...current, [key]: enabled } })
  return <div className="map-controls" aria-label="Map navigation controls">
    <div className="map-control-group">
      <button type="button" aria-label="Zoom in" onClick={onZoomIn}><Icon name="plus" /></button>
      <button type="button" aria-label="Zoom out" onClick={onZoomOut}><Icon name="minus" /></button>
    </div>
    <div className="map-control-group map-control-group-secondary">
      <button type="button" aria-label="Reset map view" onClick={onReset}><Icon name="reset" /></button>
      <button type="button" aria-label="Center on operational area" onClick={onLocate}><Icon name="target" /></button>
      <button type="button" aria-label="Fullscreen map" onClick={onFullscreen}><Icon name="expand" /></button>
      <button type="button" aria-label="Map layers" aria-expanded={open} className={open ? 'active' : ''} onClick={() => setOpen(!open)}><Icon name="layers" /></button>
    </div>
    {open && <div className="layer-menu"><div className="layer-menu-heading"><span>Operational layers</span><small>Visible on map</small></div>{layers.map(([key, label, available]) => <label key={key} className={!available ? 'disabled' : ''}><input type="checkbox" aria-label={label} checked={state[key]} disabled={!available} onChange={() => toggle(key)} /><span>{label}</span>{!available && <em>not in feed</em>}</label>)}</div>}
  </div>
}
