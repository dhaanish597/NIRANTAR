import { CONFIDENCE_CAVEAT, attributionDisplayLabel, selectExplainedCell } from '../lib/explainability'
import { useTickStore } from '../store/useTickStore'
import type { Attribution } from '../types/schemas'

/**
 * BUILD_PLAN.md task 5.7 — the explainability panel: SHAP bars in plain language
 * (`CellRisk.attributions`), data provenance per input, and confidence (`CellRisk.confidence`).
 *
 * Explains either the currently-selected village's "driving cell" (see
 * `lib/explainability.ts::selectExplainedCell`, which reuses `lib/priorityDetail.ts`'s existing
 * severed-link -> contributing-cell resolution — VillageDetailDrawer already has an "explanation"
 * section for a selected village, this generalizes the same idea into a standalone always-visible
 * panel) or, with nothing selected, the AOI's single highest-`p_fail` cell as a sensible default
 * ("why is risk highest right now").
 *
 * HONESTY NOTE on data provenance (documented, not silently degraded): BUILD_PLAN.md's task
 * brief names `ObservationFrame.provenance` and `CellObservation.source`/`is_reconstructed`
 * (backend/app/schemas/ingest.py) as "your real fields" for per-input provenance. They are real
 * — but as of this session, `TickResult` (backend/app/schemas/tick.py, the one object that
 * reaches the frontend over `/ws/ticks`) does not carry them: it only carries a tick-level
 * `is_reconstructed` boolean, not the richer per-frame `provenance: dict[str,str]` or any
 * per-cell `source`/`is_reconstructed`. That data lives in the ingest layer and is consumed
 * internally by `pipeline.py`, but nothing re-exports it onto the wire today. Rather than
 * fabricate a source/timestamp/resolution string that was never actually sent to this client,
 * this panel shows exactly what IS real and on the wire (mode, tick-level `is_reconstructed`,
 * timestamp, AOI, and the cell's `model_version`) and says plainly that per-input provenance
 * detail is a backend wiring gap, not a frontend limitation — the same honesty framing this
 * agent's brief asked for on the counterfactual scorecard (task 4.10). No UI change will be
 * needed here once `TickResult`/`CellRisk` are extended to carry it.
 */
export function ExplainabilityPanel() {
  const selectedVillageId = useTickStore((s) => s.selectedVillageId)
  const isolations = useTickStore((s) => s.isolations)
  const roadRisks = useTickStore((s) => s.roadRisks)
  const cellRisks = useTickStore((s) => s.cellRisks)
  const latestTick = useTickStore((s) => s.latestTick)

  const cell = selectExplainedCell(selectedVillageId, isolations, roadRisks, cellRisks)

  return (
    <section>
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Explainability
      </h2>

      {!cell && (
        <p className="text-sm text-slate-500">
          No cell-level risk in the current tick to explain yet.
        </p>
      )}

      {cell && (
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between">
            <span className="text-slate-300">
              Cell <span className="font-mono text-xs">{cell.cell_id}</span> · p_fail{' '}
              {(cell.p_fail * 100).toFixed(0)}%
            </span>
            <span
              title={CONFIDENCE_CAVEAT}
              className="rounded bg-white/10 px-2 py-0.5 text-xs text-slate-300"
            >
              confidence {(cell.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-[11px] text-slate-500">{CONFIDENCE_CAVEAT}</p>

          <div>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Why (SHAP, plain language)
            </h3>
            {cell.attributions.length === 0 ? (
              <p className="text-slate-500">
                No attribution breakdown reported for this cell this tick.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {cell.attributions.map((attribution) => (
                  <AttributionBar key={attribution.feature} attribution={attribution} />
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Data provenance
            </h3>
            <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
              <dt className="text-slate-500">Mode</dt>
              <dd className="text-slate-300">{latestTick?.mode ?? 'unknown'}</dd>
              <dt className="text-slate-500">Reconstructed?</dt>
              <dd className="text-slate-300">
                {latestTick?.is_reconstructed === undefined
                  ? 'unknown'
                  : latestTick.is_reconstructed
                    ? 'yes — reconstructed scenario data'
                    : 'no'}
              </dd>
              <dt className="text-slate-500">Tick time</dt>
              <dd className="text-slate-300">
                {latestTick?.t ? new Date(latestTick.t).toLocaleString() : 'unknown'}
              </dd>
              <dt className="text-slate-500">Model version</dt>
              <dd className="text-slate-300">{cell.model_version}</dd>
            </dl>
            <p className="mt-1.5 text-[11px] text-slate-500">
              Per-input source/timestamp/resolution (e.g. IMERG rainfall vs. scenario-reconstructed
              rainfall) is not yet broadcast to the frontend — <code>TickResult</code> does not
              currently carry <code>ObservationFrame.provenance</code> or per-cell{' '}
              <code>source</code>/<code>is_reconstructed</code>. This is a backend wiring gap, not
              fabricated data standing in for it.
            </p>
          </div>
        </div>
      )}
    </section>
  )
}

function AttributionBar({ attribution }: { attribution: Attribution }) {
  const pct = Math.min(100, Math.abs(attribution.display_pct))
  const positive = attribution.contribution >= 0
  return (
    <li>
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300">{attributionDisplayLabel(attribution)}</span>
        <span className={positive ? 'text-red-400' : 'text-emerald-400'}>
          {positive ? '+' : ''}
          {attribution.display_pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded bg-white/10">
        <div
          className={`h-full ${positive ? 'bg-red-500' : 'bg-emerald-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  )
}
