import { useTickStore } from '../store/useTickStore'
import { NotBuilt } from './NotBuilt'

/** The Government "AI Emergency Commander" top-level workspace (new 5-item IA). Ports the real,
 * data-driven recommendation logic the in-flight ConsoleWorkspaces.tsx rewrite already built
 * (Task 14 retires that file) — unchanged behavior, just remounted at its own route instead of
 * nested under a "Commander" sub-nav that no longer exists. Sub-project 6 replaces this with the
 * full conversational chat interface; this is the real, functional slice Foundation ships. */
export function CommanderWorkspace({
  onAnnounce,
  onWhatIf,
}: {
  onAnnounce: () => void
  onWhatIf: () => void
}) {
  const priorities = useTickStore((s) => s.priorities)
  const roads = useTickStore((s) => s.roadRisks)
  const top = priorities[0]

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6">
      <p className="text-xs uppercase tracking-wide text-slate-500">AI Emergency Commander</p>
      <h1 className="mb-4 text-xl font-bold">Decision support, not autonomous response.</h1>
      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <article className="rounded border border-white/10 bg-white/5 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-200">Situation summary</h2>
          <p className="text-sm text-slate-400">
            {priorities.length
              ? `${priorities.filter((x) => x.tier === 'P1').length} P1 villages are currently in the received priority feed.`
              : 'Awaiting a verified priority feed.'}
          </p>
          <p className="text-sm text-slate-400">
            {roads.length
              ? `${roads.filter((x) => x.severed).length} road segments are marked severed in the current impact feed.`
              : 'Awaiting road impact feed.'}
          </p>
        </article>
        <article className="rounded border border-white/10 bg-white/5 p-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-200">Recommendation</h2>
          {top ? (
            <>
              <p className="text-sm text-slate-300">
                Consider preparing an announcement for <strong>{top.village_id}</strong>; it is
                ranked {top.tier} with EPS {top.eps.toFixed(2)}.
              </p>
              <h3 className="mt-2 text-xs font-semibold uppercase text-slate-500">Why</h3>
              <ul className="text-xs text-slate-400">
                {Object.keys(top.components)
                  .slice(0, 3)
                  .map((x) => (
                    <li key={x}>{x} contributes to the current EPS</li>
                  ))}
              </ul>
            </>
          ) : (
            <NotBuilt
              task="TASK-AI-COMMANDER"
              what="No recommendation is shown without a current decision-pipeline context."
              blocks="AI recommendation backend and risk/priority tick"
            />
          )}
        </article>
      </div>
      <div className="rounded border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
        <strong>HUMAN-IN-THE-LOOP</strong> — this system proposes. An authorised officer decides.
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={onAnnounce}
            className="rounded bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20"
          >
            Open Announce
          </button>
          <button
            type="button"
            onClick={onWhatIf}
            className="rounded bg-white/10 px-3 py-1.5 text-xs font-semibold hover:bg-white/20"
          >
            Run What-if
          </button>
        </div>
      </div>
    </div>
  )
}
