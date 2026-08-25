import { deathTollInfo, formatAoiIdFallback, getScenarioDetail, whatWentWrongLine } from '../lib/scenarioDetails'
import { useTickStore } from '../store/useTickStore'
import type { ScenarioSummary } from '../types/schemas'

interface Props {
  open: boolean
  onClose: () => void
}

export function ScenarioPickerModal({ open, onClose }: Props) {
  const scenarios = useTickStore((s) => s.scenarios)
  const aoi = useTickStore((s) => s.aoi)
  const startReplay = useTickStore((s) => s.startReplay)

  if (!open) return null

  const handleRun = async (scenarioId: string) => {
    await startReplay(scenarioId)
    onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-slate-900 p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Run Case Study</h2>
        {scenarios.length === 0 && (
          <p className="text-sm text-slate-400">No scenarios available.</p>
        )}
        <ul className="space-y-3">
          {scenarios.map((scenario) => (
            <ScenarioCard
              key={scenario.id}
              scenario={scenario}
              locationFallback={
                aoi && aoi.id === scenario.aoi_id ? aoi.name : formatAoiIdFallback(scenario.aoi_id)
              }
              onRun={() => void handleRun(scenario.id)}
            />
          ))}
        </ul>
        <button
          type="button"
          onClick={onClose}
          className="mt-4 text-sm text-slate-400 hover:text-slate-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

/**
 * BUILD_PLAN.md task 4.8: event name, date, location, death toll with a source note, a one-line
 * "what went wrong," and a "Held out of training" badge. Every fact beyond frame_count/aoi_id
 * (already on `ScenarioSummary`) is read from the committed scenario JSON itself via
 * lib/scenarioDetails.ts, never hardcoded here — see that module's docstring for why, and for how
 * `_smoke` (which has none of these fields) degrades gracefully.
 */
function ScenarioCard({
  scenario,
  locationFallback,
  onRun,
}: {
  scenario: ScenarioSummary
  locationFallback: string
  onRun: () => void
}) {
  const detail = getScenarioDetail(scenario.id)
  const deathToll = deathTollInfo(detail)
  const whatWentWrong = whatWentWrongLine(detail)

  return (
    <li className="rounded border border-white/10 p-3">
      <div className="mb-1 flex items-start justify-between gap-2">
        <div>
          <div className="font-medium">{detail?.name ?? scenario.id}</div>
          <div className="text-xs text-slate-400">
            {detail?.event_date ? `${detail.event_date} · ` : ''}
            {locationFallback}
          </div>
        </div>
        {scenario.held_out_of_training && (
          <span
            title="This event was excluded from model training data and any spatial buffer around it (BUILD_PLAN.md task 1.13) — the number the map is about to show was never seen by the model."
            className="shrink-0 rounded bg-amber-500 px-2 py-0.5 text-[10px] font-bold whitespace-nowrap text-black"
          >
            Held out of training
          </span>
        )}
      </div>

      {whatWentWrong && <p className="mb-1 text-xs text-slate-300">{whatWentWrong}</p>}

      {deathToll && (
        <p className="mb-1 text-xs text-slate-400">
          Deaths: {deathToll.deaths}
          {deathToll.sourceNote && <span className="text-slate-500"> — {deathToll.sourceNote}</span>}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-slate-500">{scenario.frame_count} frames</span>
        <button
          type="button"
          onClick={onRun}
          className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
        >
          Run
        </button>
      </div>
    </li>
  )
}
