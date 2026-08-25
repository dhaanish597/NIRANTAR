import { useTickStore } from '../store/useTickStore'

/** The one place besides core/mode.py, core/clock.py, and ingest/ allowed to know which mode is
 * active (CLAUDE.md §2) — reads it from state rather than deciding anything itself. */
export function ModeBanner() {
  const latestTick = useTickStore((s) => s.latestTick)
  const modeState = useTickStore((s) => s.modeState)
  const scenarios = useTickStore((s) => s.scenarios)

  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'
  const scenarioId = latestTick?.scenario_id ?? modeState?.scenario_id ?? null
  const t = latestTick?.t ?? modeState?.scenario_time ?? null
  const scenario = scenarios.find((s) => s.id === scenarioId)
  const isReplay = mode === 'replay'

  return (
    <div
      className={`flex items-center justify-between px-4 py-2 text-sm font-medium ${
        isReplay ? 'bg-amber-600 text-black' : 'bg-emerald-700 text-white'
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="font-bold uppercase tracking-wide">
          {isReplay ? 'REPLAY MODE — reconstructed data' : 'LIVE'}
        </span>
        {isReplay && scenarioId && <span>{scenarioId}</span>}
        {isReplay && scenario?.held_out_of_training && (
          <span className="rounded bg-black/20 px-2 py-0.5 text-xs">Held out of training</span>
        )}
      </div>
      <div className="text-xs opacity-80">{t ? new Date(t).toLocaleString() : ''}</div>
    </div>
  )
}
