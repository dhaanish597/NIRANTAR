import { findDrivingCellRisk, findVillageIsolation, mergeVillageDisplay } from '../lib/priorityDetail'
import { useTickStore } from '../store/useTickStore'

/**
 * BUILD_PLAN.md task 2.8: clicking a village (a map pin in MapView, or a Priority List row in
 * RightRail — both call `selectVillage`) opens this drawer showing the EPS component breakdown
 * (`SettlementPriority.components`), RII detail (`VillageIsolation` fields), and the SHAP
 * explanation of "the driving cell" (see lib/priorityDetail.ts's `findDrivingCellRisk` for how
 * that cell is chosen). Every section renders a graceful placeholder instead of nothing when its
 * backing data is empty/stub — Phase 2's impact/decision modules are still stubs in places, and a
 * judge should never see a blank drawer.
 */
export function VillageDetailDrawer() {
  const selectedVillageId = useTickStore((s) => s.selectedVillageId)
  const priorities = useTickStore((s) => s.priorities)
  const isolations = useTickStore((s) => s.isolations)
  const roadRisks = useTickStore((s) => s.roadRisks)
  const cellRisks = useTickStore((s) => s.cellRisks)
  const selectVillage = useTickStore((s) => s.selectVillage)

  if (!selectedVillageId) return null

  const priority = priorities.find((p) => p.village_id === selectedVillageId)
  const isolation = findVillageIsolation(selectedVillageId, isolations)
  const [display] = priority ? mergeVillageDisplay([priority], isolations) : []
  const drivingCell = findDrivingCellRisk(isolation, roadRisks, cellRisks)

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={() => selectVillage(null)}>
      <aside
        className="flex h-full w-96 flex-col gap-4 overflow-y-auto bg-slate-900 p-4 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{isolation?.name ?? selectedVillageId}</h2>
            <p className="text-xs text-slate-400">{selectedVillageId}</p>
          </div>
          <button
            type="button"
            onClick={() => selectVillage(null)}
            aria-label="Close village detail"
            className="rounded px-2 py-1 text-sm text-slate-400 hover:bg-white/10 hover:text-slate-200"
          >
            ✕
          </button>
        </div>

        {!priority && (
          <p className="text-sm text-slate-500">
            This village is not in the current priority ranking (no `SettlementPriority` entry for{' '}
            {selectedVillageId} in this tick).
          </p>
        )}

        {priority && display && (
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Evacuation Priority Score
            </h3>
            <div className="mb-2 flex items-center gap-2">
              <span className={`rounded px-2 py-0.5 text-xs font-bold ${tierBadgeClass(priority.tier)}`}>
                {priority.tier}
              </span>
              <span className="text-sm text-slate-300">EPS {priority.eps.toFixed(2)}</span>
              {display.population !== null && (
                <span className="text-sm text-slate-400">· pop. {display.population.toLocaleString()}</span>
              )}
            </div>
            {Object.keys(priority.components).length === 0 ? (
              <p className="text-sm text-slate-500">No component breakdown reported for this tick.</p>
            ) : (
              <ul className="space-y-1">
                {Object.entries(priority.components).map(([key, value]) => (
                  <ComponentBar key={key} label={key} value={value} />
                ))}
              </ul>
            )}
          </section>
        )}

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Road Isolation Index detail
          </h3>
          {!isolation && (
            <p className="text-sm text-slate-500">
              No isolation data for this village in the current tick (impact/isolation.py — task
              2.4 — has not produced one yet).
            </p>
          )}
          {isolation && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-400">Isolated now</dt>
              <dd>{isolation.isolated_now ? 'Yes' : 'No'}</dd>
              <dt className="text-slate-400">P(isolated)</dt>
              <dd>{(isolation.p_isolated * 100).toFixed(0)}%</dd>
              <dt className="text-slate-400">Alternate route</dt>
              <dd>{isolation.alternate_route_exists ? 'Exists' : 'None found'}</dd>
              <dt className="text-slate-400">Est. duration</dt>
              {/* ARCHITECTURE.md §4.4: est_duration_hours "ALWAYS labelled 'estimate' in UI" —
                  never presented as a precise figure, and never phrased as "time to landslide"
                  (CLAUDE.md's "safe evacuation window" glossary entry). */}
              <dd>
                {isolation.est_duration_hours === null
                  ? 'not estimated'
                  : `~${isolation.est_duration_hours.toFixed(1)}h (estimate)`}
              </dd>
              {isolation.severed_links.length > 0 && (
                <>
                  <dt className="text-slate-400">Severed links</dt>
                  <dd>{isolation.severed_links.join(', ')}</dd>
                </>
              )}
            </dl>
          )}
        </section>

        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Why: driving cell explanation
          </h3>
          {!drivingCell && (
            <p className="text-sm text-slate-500">
              No cell-level explanation is available yet for this village — either it has no
              severed road links this tick, or the SHAP attribution model (task 1.18) has not
              populated `CellRisk.attributions` yet.
            </p>
          )}
          {drivingCell && (
            <div className="text-sm">
              <p className="mb-1 text-slate-400">
                Cell {drivingCell.cell_id} · p_fail {(drivingCell.p_fail * 100).toFixed(0)}%
              </p>
              {drivingCell.attributions.length === 0 ? (
                <p className="text-slate-500">No attribution breakdown reported for this cell.</p>
              ) : (
                <ul className="space-y-1">
                  {drivingCell.attributions.map((attribution) => (
                    <li key={attribution.feature} className="flex items-center justify-between">
                      <span className="text-slate-300">{attribution.plain_language}</span>
                      <span className={attribution.contribution >= 0 ? 'text-red-400' : 'text-emerald-400'}>
                        {attribution.contribution >= 0 ? '+' : ''}
                        {attribution.display_pct.toFixed(0)}%
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      </aside>
    </div>
  )
}

function ComponentBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <li>
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{label}</span>
        <span>{value.toFixed(2)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded bg-white/10">
        <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
      </div>
    </li>
  )
}

function tierBadgeClass(tier: 'P1' | 'P2' | 'P3'): string {
  switch (tier) {
    case 'P1':
      return 'bg-red-600'
    case 'P2':
      return 'bg-orange-500'
    default:
      return 'bg-slate-600'
  }
}
