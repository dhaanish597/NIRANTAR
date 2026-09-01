import { useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type {
  CellRisk,
  RoadSegmentRisk,
  VillageIsolation,
  WhatIfRequest,
  WhatIfResult,
} from '../types/schemas'
import { SimulatorMap } from './SimulatorMap'
import './what-if.css'
import './what-if-presets.css'

type Controls = Omit<WhatIfRequest, 'aoi_id'>
type Selection = { type: 'cell' | 'road' | 'village'; id: string }

const DEFAULTS: Controls = {
  rainfall_mm: 250,
  duration_hours: 12,
  antecedent_rainfall_mm: 0,
  soil_moisture_pct: 65,
}

const PRESETS: Array<{ name: string; description: string; values: Controls }> = [
  {
    name: 'Low rainfall',
    description: '100 mm over 24 hours',
    values: { rainfall_mm: 100, duration_hours: 24, antecedent_rainfall_mm: 0, soil_moisture_pct: 40 },
  },
  {
    name: 'Moderate rainfall',
    description: '250 mm over 12 hours',
    values: { rainfall_mm: 250, duration_hours: 12, antecedent_rainfall_mm: 50, soil_moisture_pct: 65 },
  },
  {
    name: 'Severe rainfall',
    description: '400 mm over 12 hours',
    values: { rainfall_mm: 400, duration_hours: 12, antecedent_rainfall_mm: 100, soil_moisture_pct: 80 },
  },
]

export function WhatIfSimulator() {
  const [controls, setControls] = useState<Controls>(DEFAULTS)
  const [result, setResult] = useState<WhatIfResult | null>(null)
  const [selected, setSelected] = useState<Selection | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = (key: keyof Controls, value: number) => {
    setControls((current) => ({ ...current, [key]: value }))
  }

  const run = async () => {
    setRunning(true)
    setError(null)
    setSelected(null)
    try {
      setResult(await api.runWhatIf({ aoi_id: 'aizawl', ...controls }))
    } catch (cause) {
      setResult(null)
      setError(
        cause instanceof Error
          ? `Simulation unavailable: ${cause.message}`
          : 'Simulation unavailable. Run the local demo preflight and try again.',
      )
    } finally {
      setRunning(false)
    }
  }

  const tick = result?.tick
  const intensity = controls.rainfall_mm / controls.duration_hours

  return (
    <div className="whatif-page">
      <header className="whatif-header">
        <div>
          <span className="eyebrow">DDMA PRE-POSITIONING SUPPORT</span>
          <h1>What-if Simulator</h1>
          <p className="whatif-subtitle">Counterfactual rainfall simulation</p>
          <p>Run explicit storm assumptions through the same risk and impact pipeline as replay.</p>
        </div>
        <div className="whatif-header-actions">
          <div className="aoi-chip"><small>AOI</small><strong>AIZAWL</strong></div>
          <div className="sim-state"><i /> {running ? 'RUNNING' : result ? 'COMPLETE' : 'READY'}</div>
          <button className="button secondary" type="button" onClick={() => { setControls(DEFAULTS); setResult(null); setError(null) }} disabled={running}>Reset</button>
          <button className="button" type="button" onClick={() => void run()} disabled={running}>{running ? 'Running...' : 'Run simulation'}</button>
        </div>
      </header>

      <div className="whatif-layout">
        <aside className="scenario-panel">
          <div className="panel-heading"><span className="step">01</span><div><span className="eyebrow">SCENARIO CONTROLS</span><h2>Storm assumptions</h2></div></div>
          <p className="panel-note">Counterfactual simulation only. It is not a forecast and never changes operational alerts.</p>

          <div className="preset-block">
            <div className="preset-heading"><span>TEST CASES</span><small>Deterministic comparison inputs</small></div>
            <div className="preset-grid">
              {PRESETS.map((preset) => (
                <button type="button" className="preset-card" key={preset.name} onClick={() => { setControls(preset.values); setResult(null) }}>
                  <b>{preset.name}</b><small>{preset.description}</small>
                </button>
              ))}
            </div>
          </div>

          <Section title="Rainfall">
            <Slider label="Total rainfall in millimetres" value={controls.rainfall_mm} min={10} max={600} step={10} unit=" mm" onChange={(value) => update('rainfall_mm', value)} />
            <Slider label="Storm duration" value={controls.duration_hours} min={1} max={48} step={1} unit=" h" onChange={(value) => update('duration_hours', value)} />
            <Slider label="Antecedent rainfall" value={controls.antecedent_rainfall_mm ?? 0} min={0} max={350} step={5} unit=" mm" onChange={(value) => update('antecedent_rainfall_mm', value)} />
            <div className="intensity-card"><span>CONSTANT INTENSITY ASSUMPTION</span><strong>{intensity.toFixed(1)} <small>mm/h</small></strong><em>{controls.rainfall_mm} mm / {controls.duration_hours} h</em></div>
          </Section>

          <Section title="Ground condition">
            <Slider label="Surface soil-moisture proxy (top 5 cm)" value={controls.soil_moisture_pct ?? 0} min={0} max={100} step={1} unit="%" onChange={(value) => update('soil_moisture_pct', value)} />
          </Section>

          <div className="scenario-summary">
            <div className="summary-title"><span>SCENARIO SUMMARY</span><b>COUNTERFACTUAL INPUT</b></div>
            <div className="summary-grid">
              <Summary label="Rainfall" value={`${controls.rainfall_mm} mm`} />
              <Summary label="Duration" value={`${controls.duration_hours} h`} />
              <Summary label="Intensity" value={`${intensity.toFixed(1)} mm/h`} />
              <Summary label="Antecedent" value={`${controls.antecedent_rainfall_mm ?? 0} mm`} />
            </div>
          </div>
          <button className="run-wide" type="button" onClick={() => void run()} disabled={running}>{running ? 'Running shared pipeline...' : 'Run full impact cascade'} <span>-&gt;</span></button>
        </aside>

        <main className="sim-main">
          {error && <div className="map-error-status" role="alert">{error}</div>}
          <div className="map-wrap">
            <SimulatorMap cells={tick?.cell_risks ?? []} roads={tick?.road_risks ?? []} villages={tick?.isolations ?? []} onSelect={setSelected} />
            {!result && !running && <div className="map-empty"><span>COUNTERFACTUAL SIMULATION</span><strong>Configure rainfall, then run the model</strong><small>No fabricated frontend result is shown when the backend is unavailable.</small></div>}
            {running && <div className="map-running"><div className="spinner" /><strong>Running model and impact pipeline...</strong><span>Risk -&gt; runout -&gt; roads -&gt; isolation -&gt; priority -&gt; routing</span></div>}
          </div>
          {result && <Impact result={result} selected={selected} onSelect={setSelected} />}
        </main>

        {selected && tick && <Inspector selection={selected} result={result} onClose={() => setSelected(null)} />}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="control-section"><h3>{title}</h3>{children}</section>
}

function Slider({ label, value, min, max, step, unit, onChange }: { label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (value: number) => void }) {
  return <div className="field"><label>{label}<span>{value}{unit}</span></label><input aria-label={label} type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} /></div>
}

function Summary({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><b>{value}</b></div>
}

function Kpi({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: string }) {
  return <div className={`kpi ${tone}`}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
}

function Impact({ result, selected, onSelect }: { result: WhatIfResult; selected: Selection | null; onSelect: (selection: Selection) => void }) {
  const { tick, summary } = result
  const maxRisk = Math.max(0, ...tick.cell_risks.map((cell) => cell.p_fail))
  const hazard = maxRisk >= 0.75 ? 'VERY HIGH' : maxRisk >= 0.55 ? 'HIGH' : maxRisk >= 0.3 ? 'MODERATE' : 'LOW'
  return <section className="impact-analysis">
    <div className="result-banner"><div><span className="eyebrow">02 · IMPACT ANALYSIS</span><h2>Model-derived cascade</h2></div><div className="demo-badge">MODEL + PHYSICS OUTPUT</div><span className="hazard-badge">{hazard}</span></div>
    <div className="kpis">
      <Kpi label="Critical cells" value={`${summary?.critical_cells ?? 0}`} detail={`of ${tick.cell_risks.length}`} tone="red" />
      <Kpi label="Roads at risk" value={`${summary?.roads_at_risk ?? 0} / ${tick.road_risks.length}`} detail={`${summary?.severed_roads ?? 0} severed`} tone="orange" />
      <Kpi label="Settlements isolated" value={`${summary?.isolated_settlements ?? 0} / ${tick.isolations.length}`} detail="Graph-derived" tone="red" />
      <Kpi label="Population at risk" value={(summary?.population_at_risk ?? 0).toLocaleString()} detail="Built exposure data" tone="teal" />
    </div>
    <div className="cascade-strip"><span>LANDSLIDE RISK</span><b>-&gt;</b><span>RUNOUT</span><b>-&gt;</b><span>ROAD SEVERANCE</span><b>-&gt;</b><span>ISOLATION</span><b>-&gt;</b><strong>PRIORITY + ROUTE</strong></div>
    <div className="impact-columns">
      <VillageList villages={tick.isolations} selected={selected} onSelect={onSelect} />
      <RoadList roads={tick.road_risks} selected={selected} onSelect={onSelect} />
      <div className="priority-box"><h3>Operational priorities</h3>{tick.priorities.slice(0, 6).map((priority) => { const village = tick.isolations.find((item) => item.village_id === priority.village_id); const card = tick.new_action_cards.find((item) => item.village_id === priority.village_id); return <div className="priority-row" key={priority.village_id}><b>{priority.tier}</b><span><strong>{village?.name ?? priority.village_id}</strong><small>{card?.route ? `${card.route.shelter_name} · ${(card.route.distance_m / 1000).toFixed(1)} km` : 'No safe route generated at this tick'}</small></span><em>{Math.round(priority.eps * 100)}%</em></div> })}</div>
    </div>
    <div className="panel-note"><strong>Assumptions:</strong> {result.assumptions.join(' ')}</div>
  </section>
}

function VillageList({ villages, selected, onSelect }: { villages: VillageIsolation[]; selected: Selection | null; onSelect: (selection: Selection) => void }) {
  return <div><h3>Settlement isolation <small>click to inspect</small></h3>{villages.slice().sort((a, b) => b.p_isolated - a.p_isolated).slice(0, 8).map((village) => <button type="button" className={`entity-row ${selected?.id === village.village_id ? 'active' : ''}`} key={village.village_id} onClick={() => onSelect({ type: 'village', id: village.village_id })}><span className="entity-main"><b>{village.name}</b><small>{village.population.toLocaleString()} residents · {village.severed_links.length} severed links</small></span><span className="entity-risk">{Math.round(village.p_isolated * 100)}%<small>isolation</small></span></button>)}</div>
}

function RoadList({ roads, selected, onSelect }: { roads: RoadSegmentRisk[]; selected: Selection | null; onSelect: (selection: Selection) => void }) {
  return <div><h3>Road-network impact <small>model-derived status</small></h3>{roads.filter((road) => road.p_blocked >= 0.3).sort((a, b) => b.p_blocked - a.p_blocked).slice(0, 8).map((road) => <button type="button" className={`entity-row ${selected?.id === road.edge_id ? 'active' : ''}`} key={road.edge_id} onClick={() => onSelect({ type: 'road', id: road.edge_id })}><span className={`road-mark ${road.severed ? 'cut' : ''}`} /><span className="entity-main"><b>{road.name || `Unnamed OSM segment ${road.edge_id}`}</b><small>{road.highway_class} · {road.contributing_cells.length} risk cells</small></span><span className={`road-status ${road.severed ? 'cut-text' : ''}`}>{road.severed ? 'SEVERED' : 'AT RISK'}<small>{Math.round(road.p_blocked * 100)}%</small></span></button>)}</div>
}

function Inspector({ selection, result, onClose }: { selection: Selection; result: WhatIfResult; onClose: () => void }) {
  const tick = result.tick
  const item = selection.type === 'cell' ? tick.cell_risks.find((value) => value.cell_id === selection.id) : selection.type === 'road' ? tick.road_risks.find((value) => value.edge_id === selection.id) : tick.isolations.find((value) => value.village_id === selection.id)
  if (!item) return null
  const cell = item as CellRisk
  const road = item as RoadSegmentRisk
  const village = item as VillageIsolation
  return <aside className="inspector"><button className="close-inspector" type="button" onClick={onClose} aria-label="Close inspector">x</button><span className="eyebrow">MAP INSPECTOR · {selection.type.toUpperCase()}</span><h2>{selection.type === 'cell' ? cell.cell_id : selection.type === 'road' ? road.name || `Unnamed OSM segment ${road.edge_id}` : village.name}</h2>{selection.type === 'cell' && <><div className="inspector-score"><strong>{Math.round(cell.p_fail * 100)}%</strong><span>FAILURE PROBABILITY</span></div><p className="why">Why?</p><p className="explanation">{cell.attributions.length ? cell.attributions.map((attribute) => attribute.plain_language).join(' · ') : 'Threshold-only output; SHAP attribution is not available for this cell.'}</p><dl className="inspector-grid"><Summary label="Confidence" value={`${Math.round(cell.confidence * 100)}%`} /><Summary label="Model" value={cell.model_version} /></dl></>}{selection.type === 'road' && <><div className="inspector-score"><strong>{Math.round(road.p_blocked * 100)}%</strong><span>{road.severed ? 'SEVERED' : 'AT RISK'}</span></div><dl className="inspector-grid"><Summary label="Class" value={road.highway_class} /><Summary label="Contributing cells" value={`${road.contributing_cells.length}`} /></dl></>}{selection.type === 'village' && <><div className="inspector-score"><strong>{Math.round(village.p_isolated * 100)}%</strong><span>{village.isolated_now ? 'ISOLATED' : 'AT RISK OF ISOLATION'}</span></div><dl className="inspector-grid"><Summary label="Population" value={village.population.toLocaleString()} /><Summary label="Severed links" value={`${village.severed_links.length}`} /><Summary label="Alternate route" value={village.alternate_route_exists ? 'Available' : 'Unavailable'} /></dl></>}</aside>
}
