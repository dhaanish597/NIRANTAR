import type { ActionCard, EscalationStage, SettlementPriority } from '../types/schemas'
import { useTickStore } from '../store/useTickStore'

export function RightRail() {
  const priorities = useTickStore((s) => s.priorities)
  const actionCards = useTickStore((s) => s.actionCards)
  const latestCard = actionCards[0]

  return (
    <aside className="flex h-full w-80 flex-col gap-4 overflow-y-auto border-l border-white/10 bg-slate-900/80 p-4">
      <section>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Priority list
        </h2>
        {priorities.length === 0 && (
          <p className="text-sm text-slate-500">No settlements ranked yet.</p>
        )}
        <ul className="space-y-2">
          {priorities.map((p) => (
            <PriorityRow key={p.village_id} priority={p} />
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
    </aside>
  )
}

function PriorityRow({ priority }: { priority: SettlementPriority }) {
  return (
    <li className="flex items-center justify-between rounded bg-white/5 px-3 py-2 text-sm">
      <span>{priority.village_id}</span>
      <span className={tierBadgeClass(priority.tier)}>{priority.tier}</span>
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

function tierBadgeClass(tier: SettlementPriority['tier']): string {
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
