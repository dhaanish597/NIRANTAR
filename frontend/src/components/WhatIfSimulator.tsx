import { useState } from 'react'
import { api } from '../lib/api'
import { STAGE_COLOR } from '../lib/escalation'
import { summarizeWhatIf, type WhatIfSummary } from '../lib/whatIf'
import type { WhatIfResult } from '../types/schemas'

const DEFAULT_RAINFALL_MM = 250
const DEFAULT_DURATION_HOURS = 12

type RunState =
  | { status: 'idle' }
  | { status: 'running' }
  | { status: 'done'; result: WhatIfResult; summary: WhatIfSummary }
  | { status: 'error'; error: string }

/**
 * BUILD_PLAN.md task 5.8 — the what-if rainfall simulator: "a rainfall slider ('simulate 250 mm
 * over 12 h') that re-runs the pipeline on synthetic input and shows the resulting failure
 * distribution, road severance and isolation cascade. Position as DDMA pre-positioning support."
 *
 * Calls the real `POST /api/whatif/simulate` (`backend/app/api/whatif.py`) — a REAL `TickResult`
 * from a throwaway backend `Pipeline` run over the AOI's real cell grid, NEVER written to the
 * live audit trail or pushed onto `/ws/ticks`. This component deliberately does NOT touch
 * `useTickStore` — a what-if result must never be mistaken for (or silently override) real
 * live/replay map state; it renders entirely from its own local component state.
 *
 * The request is genuinely expensive (the real 2,912-cell Aizawl grid takes ~15-20s measured
 * against real ML inference + SHAP + the full impact/decision chain — see
 * `backend/tests/test_whatif.py`'s own timing note) — shown honestly as a loading state, not
 * hidden behind a fake instant response.
 */
export function WhatIfSimulator() {
  const [rainfallMm, setRainfallMm] = useState(DEFAULT_RAINFALL_MM)
  const [durationHours, setDurationHours] = useState(DEFAULT_DURATION_HOURS)
  const [runState, setRunState] = useState<RunState>({ status: 'idle' })

  const runSimulation = async () => {
    setRunState({ status: 'running' })
    try {
      const result = await api.runWhatIf({
        aoi_id: 'aizawl',
        rainfall_mm: rainfallMm,
        duration_hours: durationHours,
      })
      setRunState({ status: 'done', result, summary: summarizeWhatIf(result) })
    } catch (err) {
      setRunState({ status: 'error', error: err instanceof Error ? err.message : String(err) })
    }
  }

  return (
    <section>
      <div className="mb-1 flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          What-if rainfall simulator
        </h2>
        <span className="rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-bold text-sky-300">
          DDMA PRE-POSITIONING SUPPORT
        </span>
      </div>
      <p className="mb-2 text-[11px] text-slate-500">
        Re-runs the real risk/impact/decision pipeline on a hypothetical rainfall event across
        every real cell in the AOI. This is NOT a real alert — nothing here is written to the
        audit trail, and it never appears on the live map (BUILD_PLAN.md task 5.8).
      </p>

      <div className="mb-2 grid grid-cols-2 gap-3">
        <label className="text-xs text-slate-400">
          Total rainfall (mm)
          <input
            type="range"
            min={10}
            max={500}
            step={10}
            value={rainfallMm}
            onChange={(event) => setRainfallMm(Number(event.target.value))}
            disabled={runState.status === 'running'}
            aria-label="Total rainfall in millimetres"
            className="mt-1 w-full accent-sky-500"
          />
          <span className="text-slate-200">{rainfallMm} mm</span>
        </label>
        <label className="text-xs text-slate-400">
          Over duration (hours)
          <input
            type="range"
            min={1}
            max={48}
            step={1}
            value={durationHours}
            onChange={(event) => setDurationHours(Number(event.target.value))}
            disabled={runState.status === 'running'}
            aria-label="Duration in hours"
            className="mt-1 w-full accent-sky-500"
          />
          <span className="text-slate-200">{durationHours} h</span>
        </label>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => void runSimulation()}
          disabled={runState.status === 'running'}
          className="rounded bg-sky-700 px-3 py-1.5 text-xs font-semibold hover:bg-sky-600 disabled:opacity-50"
        >
          {runState.status === 'running'
            ? 'Simulating… (real pipeline run, up to ~20s)'
            : `Simulate ${rainfallMm} mm over ${durationHours} h`}
        </button>
        <button
          type="button"
          onClick={() => {
            setRainfallMm(DEFAULT_RAINFALL_MM)
            setDurationHours(DEFAULT_DURATION_HOURS)
          }}
          disabled={runState.status === 'running'}
          className="rounded bg-white/10 px-2 py-1.5 text-xs text-slate-400 hover:bg-white/20 disabled:opacity-50"
        >
          Reset to 250mm/12h
        </button>
      </div>

      {runState.status === 'error' && (
        <p className="mb-2 text-xs text-red-300">Could not run simulation: {runState.error}</p>
      )}

      {runState.status === 'done' && (
        <WhatIfResults result={runState.result} summary={runState.summary} />
      )}
    </section>
  )
}

function WhatIfResults({ result, summary }: { result: WhatIfResult; summary: WhatIfSummary }) {
  return (
    <div className="rounded border border-white/10 bg-white/5 p-3 text-xs">
      <p className="mb-2 text-slate-300">
        <span className="font-semibold text-slate-100">{summary.totalCells}</span> cells
        simulated, model{' '}
        <span className="text-slate-400">
          {result.tick.cell_risks[0]?.model_version ?? 'n/a'}
        </span>
      </p>

      <p className="mb-1 text-slate-500">Failure distribution (real escalation-stage thresholds)</p>
      <div className="mb-3 flex h-3 w-full overflow-hidden rounded">
        {summary.distribution.map((bucket) => (
          <div
            key={bucket.stage}
            title={`${bucket.stage}: ${bucket.count} cells`}
            style={{
              width: `${summary.totalCells > 0 ? (bucket.count / summary.totalCells) * 100 : 0}%`,
              backgroundColor: STAGE_COLOR[bucket.stage],
            }}
          />
        ))}
      </div>
      <div className="mb-3 flex justify-between text-[10px] text-slate-500">
        {summary.distribution.map((bucket) => (
          <span key={bucket.stage}>
            {bucket.stage} {bucket.count}
          </span>
        ))}
      </div>

      <dl className="mb-2 grid grid-cols-2 gap-x-3 gap-y-1">
        <dt className="text-slate-500">Road severance</dt>
        <dd className="text-slate-200">
          {summary.severedRoadCount} / {summary.totalRoadCount} edges
        </dd>
        <dt className="text-slate-500">Isolation cascade</dt>
        <dd className="text-slate-200">
          {summary.isolatedVillageCount} / {summary.totalVillageCount} villages
        </dd>
        <dt className="text-slate-500">Recommendations that would be issued</dt>
        <dd className="text-slate-200">{summary.actionCardCount}</dd>
      </dl>

      {summary.isolatedVillageNames.length > 0 && (
        <p className="mb-2 text-slate-400">
          Isolated: {summary.isolatedVillageNames.join(', ')}
        </p>
      )}

      <details className="text-slate-500">
        <summary className="cursor-pointer select-none">Assumptions</summary>
        <ul className="mt-1 list-inside list-disc space-y-0.5">
          {result.assumptions.map((assumption) => (
            <li key={assumption}>{assumption}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
