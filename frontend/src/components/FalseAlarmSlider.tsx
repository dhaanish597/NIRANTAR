import { useMemo, useState } from 'react'
import { getEvalReport, operatingPoints } from '../lib/evalReport'

/**
 * BUILD_PLAN.md task 5.6 — the false-alarm-cost slider.
 *
 * Built (before task 3.7's real DDMA Console existed) as a self-contained panel placed in the
 * right rail (RightRail.tsx), so it stayed visible on the main operational screen rather than
 * being buried inside the console. `DdmaConsole.tsx` (task 3.7) is now real and reachable via the
 * "DDMA Console" button, but this panel is left here rather than moved — it is a general
 * risk-threshold explainer relevant to the whole operational view, not specific to the
 * Approve/Modify/Reject workflow the console adds.
 *
 * RULING (documented, not silently decided): the panel snaps to the three REAL operating
 * thresholds measured in `data/models/eval_report.md` §5/§6 (0.30 / 0.50 / 0.70) — it does not
 * interpolate a number between them. `ml/evaluate.py` only ever computed a confusion matrix and a
 * false-alarm-cost row at those three points; anything in between would be a number nobody
 * measured, which is exactly what CLAUDE.md's honesty rules forbid ("never state a prediction
 * accuracy number that we have not measured"). Snapping (rather than allowing free movement
 * gated as "illustrative-only") was chosen because it is the simpler, more defensible option: it
 * makes it structurally impossible to display an unmeasured number, instead of relying on a label
 * to keep a continuous-looking control honest.
 */
export function FalseAlarmSlider() {
  // `getEvalReport()`/`operatingPoints()` are pure and internally memoized (module-level cache in
  // lib/evalReport.ts) — computed directly during render (no setState-in-effect/useMemo
  // anti-pattern) since re-deriving a 3-row merge on every render is trivially cheap.
  const [points, error] = useMemo<[ReturnType<typeof operatingPoints>, string | null]>(() => {
    try {
      return [operatingPoints(getEvalReport()), null]
    } catch (err) {
      return [[], err instanceof Error ? err.message : String(err)]
    }
  }, [])
  const [index, setIndex] = useState(1) // default: the middle measured threshold (0.50)

  if (error || points.length === 0) {
    return (
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          False-alarm-cost slider
        </h2>
        <p className="text-sm text-red-300">
          Could not load data/models/eval_report.md: {error ?? 'no operating points parsed'}
        </p>
      </section>
    )
  }

  const point = points[Math.min(index, points.length - 1)]
  const report = getEvalReport()

  return (
    <section>
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        False-alarm-cost slider
      </h2>
      <p className="mb-2 text-[11px] text-slate-500">
        Operational-view risk threshold explainer — see the DDMA Console (task 3.7) for the real
        per-recommendation Approve/Modify/Reject workflow.
      </p>

      <input
        type="range"
        min={0}
        max={points.length - 1}
        step={1}
        value={index}
        onChange={(event) => setIndex(Number(event.target.value))}
        aria-label="Operating threshold"
        className="w-full accent-emerald-500"
      />
      <div className="mb-2 flex justify-between text-[10px] text-slate-500">
        {points.map((p) => (
          <span key={p.threshold}>{p.threshold.toFixed(2)}</span>
        ))}
      </div>

      <div className="rounded border border-white/10 bg-white/5 p-3 text-sm">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-semibold">Threshold {point.threshold.toFixed(2)}</span>
          <span className="text-xs text-slate-400">model {report.modelVersion}</span>
        </div>
        <p className="text-slate-300">
          <span className="font-medium text-slate-100">{point.cellsFlagged}</span> of{' '}
          {report.nLabeledCells} labeled cells flagged ({point.pctCellsFlagged.toFixed(1)}%) —{' '}
          <span className="font-medium text-slate-100">
            {point.eventsCaught}/{point.eventsTotal}
          </span>{' '}
          known historical events caught,{' '}
          <span className="font-medium text-slate-100">{point.eventsMissed}</span> missed.
        </p>
        <dl className="mt-2 grid grid-cols-4 gap-x-2 gap-y-0.5 text-xs text-slate-400">
          <dt>TP</dt>
          <dt>FP</dt>
          <dt>FN</dt>
          <dt>TN</dt>
          <dd className="text-slate-200">{point.tp}</dd>
          <dd className="text-slate-200">{point.fp}</dd>
          <dd className="text-slate-200">{point.fn}</dd>
          <dd className="text-slate-200">{point.tn}</dd>
        </dl>
      </div>

      <p className="mt-2 text-[11px] text-slate-500">
        Source: data/models/eval_report.md (n={report.nLabeledCells} labeled cells, one AOI —
        treat as illustrative, not a stable rate; see the report&apos;s own §2). Only the three
        thresholds actually measured are selectable — no interpolation.
      </p>
    </section>
  )
}
