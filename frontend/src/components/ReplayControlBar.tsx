import { computeReplayProgress, SPEED_PRESETS } from '../lib/replayTimeline'
import { useTickStore } from '../store/useTickStore'

/**
 * BUILD_PLAN.md task 4.9: play/pause, a speed selector (1x/10x/60x/360x), a timeline scrubber,
 * and a persistent "REPLAY MODE — reconstructed data" banner.
 *
 * The banner already exists (`ModeBanner`, CLAUDE.md §2/§10's "only mode-aware components decide
 * mode UI" rule) — this component only adds the control surface, and reads `mode` itself (the
 * same pattern ModeBanner uses) purely to decide whether it renders at all, since a replay
 * control bar is meaningless outside REPLAY.
 *
 * Honesty ruling (documented, not silently done): `core/mode.py`'s `pause()`/`resume()`/
 * `set_speed()` exist on the backend state machine, but `api/routes.py` only exposes
 * `POST /api/replay/start` and `POST /api/replay/stop` over HTTP — there is no REST route (and
 * `/ws/ticks` is server -> client only) for pause/resume/speed-change yet. That wiring is
 * BUILD_PLAN.md task 4.7 (backend, out of this agent's scope — no backend files may be touched
 * here). Rather than call an endpoint that doesn't exist (a demo-time 404) or silently pretend a
 * click worked, Play/Pause and the speed presets are rendered as real controls that display true
 * backend state (`modeState.paused`, `modeState.speed_factor`) but are disabled with a visible
 * "not yet wired" note until task 4.7 lands the routes — at which point wiring them up is an
 * isolated follow-up (see `TODO(4.7)` below). The timeline scrubber and the "Return to Live"
 * button ARE fully real: the scrubber is a read-only progress bar computed from genuine
 * `modeState.scenario_time` against the scenario's real `start`/`end`, and "Return to Live" calls
 * the real, already-wired `POST /api/replay/stop`.
 */
export function ReplayControlBar() {
  const modeState = useTickStore((s) => s.modeState)
  const latestTick = useTickStore((s) => s.latestTick)
  const scenarios = useTickStore((s) => s.scenarios)
  const stopReplay = useTickStore((s) => s.stopReplay)

  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'
  if (mode !== 'replay') return null

  const scenarioId = latestTick?.scenario_id ?? modeState?.scenario_id ?? null
  const scenario = scenarios.find((s) => s.id === scenarioId)
  const scenarioTime = latestTick?.t ?? modeState?.scenario_time ?? null
  const progress = computeReplayProgress(scenario, scenarioTime)
  const paused = modeState?.paused ?? false
  const speedFactor = modeState?.speed_factor ?? null

  return (
    <div className="flex items-center gap-4 border-t border-white/10 bg-slate-900/90 px-4 py-2 text-xs text-slate-300">
      <button
        type="button"
        disabled
        title="Pause/resume is not yet wired to the backend — BUILD_PLAN.md task 4.7 exposes core/mode.py's pause()/resume() over REST first."
        className="rounded bg-white/10 px-3 py-1 font-semibold text-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {paused ? '▶ Resume' : '⏸ Pause'}
      </button>

      <div className="flex items-center gap-1">
        <span className="text-slate-500">Speed</span>
        {SPEED_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            disabled
            title="Changing speed mid-replay is not yet wired to the backend — BUILD_PLAN.md task 4.7."
            className={`rounded px-2 py-1 disabled:cursor-not-allowed ${
              speedFactor === preset ? 'bg-emerald-700 text-white' : 'bg-white/10 text-slate-400'
            } disabled:opacity-50`}
          >
            {preset}×
          </button>
        ))}
        {speedFactor !== null && !(SPEED_PRESETS as readonly number[]).includes(speedFactor) && (
          <span className="text-slate-500">current: {speedFactor}×</span>
        )}
      </div>

      <div className="flex flex-1 items-center gap-2">
        <span className="text-slate-500">
          {scenarioTime ? new Date(scenarioTime).toLocaleTimeString() : '—'}
        </span>
        <div className="h-1.5 flex-1 overflow-hidden rounded bg-white/10" role="progressbar" aria-label="Scenario time">
          <div
            className="h-full bg-amber-500"
            style={{ width: `${progress === null ? 0 : progress * 100}%` }}
          />
        </div>
        <span className="text-slate-500">{scenario ? scenario.id : scenarioId}</span>
      </div>

      <button
        type="button"
        onClick={() => void stopReplay()}
        className="rounded bg-red-700 px-3 py-1 font-semibold text-white hover:bg-red-600"
      >
        Return to Live
      </button>
    </div>
  )
}
