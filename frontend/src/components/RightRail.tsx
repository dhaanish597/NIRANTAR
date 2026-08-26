import { mergeVillageDisplay, type VillageDisplayRecord } from '../lib/priorityDetail'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, EscalationStage } from '../types/schemas'
import { ExplainabilityPanel } from './ExplainabilityPanel'
import { FalseAlarmSlider } from './FalseAlarmSlider'

export function RightRail() {
  const priorities = useTickStore((s) => s.priorities)
  const isolations = useTickStore((s) => s.isolations)
  const actionCards = useTickStore((s) => s.actionCards)
  const selectVillage = useTickStore((s) => s.selectVillage)
  const latestCard = actionCards[0]

  // BUILD_PLAN.md task 2.7: population + isolation status per village, joined from
  // TickResult.priorities and TickResult.isolations by village_id (see lib/priorityDetail.ts).
  const villageRows = mergeVillageDisplay(priorities, isolations)

  return (
    <aside className="flex h-full w-80 flex-col gap-4 overflow-y-auto border-l border-white/10 bg-slate-900/80 p-4">
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Priority list
        </h2>
        {villageRows.length === 0 && (
          <p className="text-sm text-slate-500">No settlements ranked yet.</p>
        )}
        <ul className="space-y-2">
          {villageRows.map((row) => (
            <PriorityRow key={row.villageId} row={row} onSelect={() => selectVillage(row.villageId)} />
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Latest action card
        </h2>
        {!latestCard && <p className="text-sm text-slate-500">No action card issued yet.</p>}
        {latestCard && <ActionCardView card={latestCard} />}
      </section>

      {/* BUILD_PLAN.md task 5.7: SHAP bars in plain language, per-input provenance, confidence. */}
      <ExplainabilityPanel />

      {/* BUILD_PLAN.md task 5.6: false-alarm-cost slider, DDMA-console-shaped panel (task 3.7's
          real console doesn't exist yet). */}
      <FalseAlarmSlider />
    </aside>
  )
}

function PriorityRow({ row, onSelect }: { row: VillageDisplayRecord; onSelect: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className="flex w-full items-center justify-between rounded bg-white/5 px-3 py-2 text-left text-sm hover:bg-white/10"
      >
        <span className="flex flex-col">
          <span>{row.name ?? row.villageId}</span>
          <span className="text-xs text-slate-400">
            {row.population !== null ? `pop. ${row.population.toLocaleString()}` : 'population unknown'}
            {row.isolatedNow !== null && (row.isolatedNow ? ' · isolated' : ' · not isolated')}
          </span>
        </span>
        <span className={tierBadgeClass(row.tier)}>{row.tier}</span>
      </button>
    </li>
  )
}

function ActionCardView({ card }: { card: ActionCard }) {
  return (
    <div className="rounded border border-white/10 bg-white/5 p-3 text-sm">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold">{card.headline}</span>
        <span className={`rounded px-2 py-0.5 text-xs font-bold ${stageBadgeClass(card.stage)}`}>
          {card.stage}
        </span>
      </div>
      <p className="text-slate-300">{card.reason_plain}</p>
      <p className="mt-2 text-slate-400">Shelter: {card.shelter_name}</p>
      {card.roads_to_avoid.length > 0 && (
        <p className="text-slate-400">Avoid: {card.roads_to_avoid.join(', ')}</p>
      )}
    </div>
  )
}

function tierBadgeClass(tier: VillageDisplayRecord['tier']): string {
  switch (tier) {
    case 'P1':
      return 'rounded bg-red-600 px-2 py-0.5 text-xs font-bold'
    case 'P2':
      return 'rounded bg-orange-500 px-2 py-0.5 text-xs font-bold'
    default:
      return 'rounded bg-slate-600 px-2 py-0.5 text-xs font-bold'
  }
}

function stageBadgeClass(stage: EscalationStage): string {
  switch (stage) {
    case 'RED':
      return 'bg-red-600'
    case 'ORANGE':
      return 'bg-orange-500'
    case 'YELLOW':
      return 'bg-yellow-500 text-black'
    default:
      return 'bg-emerald-600'
  }
}
