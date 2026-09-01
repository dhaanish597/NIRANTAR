import { useEffect, useState } from 'react'
import { mergeVillageDisplay, type VillageDisplayRecord } from '../lib/priorityDetail'
import { useTickStore } from '../store/useTickStore'
import type { ActionCard, EscalationStage } from '../types/schemas'
import type { CitizenReportRecord } from '../types/schemas'
import { api } from '../lib/api'
import { ExplainabilityPanel } from './ExplainabilityPanel'
import { FalseAlarmSlider } from './FalseAlarmSlider'

export function RightRail({ onOpenReports = () => undefined }: { onOpenReports?: (reportId?: string) => void }) {
  const priorities = useTickStore((s) => s.priorities)
  const isolations = useTickStore((s) => s.isolations)
  const actionCards = useTickStore((s) => s.actionCards)
  const selectVillage = useTickStore((s) => s.selectVillage)
  const latestCard = actionCards[0]
  const forecast = useTickStore((s) => s.forecast)
  const selectedForecastDate = useTickStore((s) => s.selectedForecastDate)
  const selectedForecast = forecast?.forecast.find((day) => day.date === selectedForecastDate)
  const [reports, setReports] = useState<CitizenReportRecord[]>([])

  useEffect(() => {
    const refreshReports = () => void api.listCitizenReports().then(setReports).catch(() => undefined)
    refreshReports()
    const timer = window.setInterval(refreshReports, 5000)
    return () => window.clearInterval(timer)
  }, [])

  // BUILD_PLAN.md task 2.7: population + isolation status per village, joined from
  // TickResult.priorities and TickResult.isolations by village_id (see lib/priorityDetail.ts).
  const villageRows = mergeVillageDisplay(priorities, isolations)

  return (
    <aside className="flex h-full w-80 flex-col gap-4 overflow-y-auto border-l border-white/10 bg-slate-900/80 p-4">
      <section className="selected-forecast-summary">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Selected forecast</h2>
        {selectedForecast ? <><div className="forecast-summary-risk"><strong>{Math.round(selectedForecast.risk_probability * 100)}%</strong><span>{selectedForecast.risk_level}</span></div><p className="text-sm text-slate-300">{selectedForecast.explanation}</p><p className="text-xs text-slate-400">{selectedForecast.affected_villages} villages · {selectedForecast.affected_road_segments} road segments affected</p></> : <p className="text-sm text-slate-500">Waiting for forecast data.</p>}
      </section>
      <section>
        <div className="flex items-center justify-between">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Citizen reports</h2>
          <button type="button" className="text-xs text-teal-300" onClick={() => onOpenReports()}>Open queue</button>
        </div>
        {reports.length === 0 && <p className="text-sm text-slate-500">No citizen evidence received yet.</p>}
        <ul className="space-y-2">
          {reports.slice(0, 3).map((report) => (
            <li key={report.id}>
              <button type="button" onClick={() => onOpenReports(report.id)} className="w-full rounded border border-white/10 bg-white/5 px-3 py-2 text-left text-sm hover:bg-white/10">
                <span className="flex items-center justify-between"><strong>{report.category}</strong><span className="text-amber-300">{report.urgency_score}/100</span></span>
                <span className="mt-1 block text-xs text-slate-400">{report.status.replace('_', ' ')} · 7 agents complete</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

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

      {/* BUILD_PLAN.md task 5.6: false-alarm-cost slider, a general risk-threshold explainer for
          the operational view. The real per-recommendation Approve/Modify/Reject workflow is the
          DDMA Console (task 3.7, DdmaConsole.tsx, reachable via App.tsx's "DDMA Console" button). */}
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
