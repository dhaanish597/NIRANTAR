import { useMemo, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api } from '../lib/api'
import { demoResponse, structuredFromLive } from '../lib/commander'
import { useTickStore } from '../store/useTickStore'
import type {
  CommanderChatMessage,
  CommanderRoute,
  CommanderStructuredResponse,
} from '../types/schemas'
import { CommanderResponse } from './CommanderResponse'
import './commander-workspace.css'

const SUGGESTIONS = [
  'Highest-risk villages',
  'Show safe evacuation routes',
  'Which roads may be cut off?',
  'Find nearby shelters',
  'Why is this area high risk?',
  'What should I announce?',
]

export function CommanderWorkspace({ onAnnounce, onWhatIf }: { onAnnounce: () => void; onWhatIf: () => void }) {
  const { priorities, roadRisks, isolations, actionCards, aoi, latestTick, modeState } = useTickStore()
  const mode = latestTick?.mode ?? modeState?.mode ?? 'live'
  const top = priorities[0]
  const [messages, setMessages] = useState<CommanderChatMessage[]>([])
  const [responses, setResponses] = useState<CommanderStructuredResponse[]>([])
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const routes = useMemo(
    () => actionCards.flatMap((card) => card.route ? [{
      route_rank: 1,
      route: card.route,
      safety_reason: 'Uses the current risk-filtered route and avoids affected roads.',
      risk_snapshot: [`Avoid: ${(card.roads_to_avoid || card.route.avoided_roads).join(', ') || 'none listed'}`],
    }] : []).slice(0, 3),
    [actionCards],
  )
  const shelters = useMemo(
    () => actionCards.map((card) => card.route).filter((route): route is NonNullable<typeof route> => Boolean(route)),
    [actionCards],
  )
  const kpis = [
    { label: 'Villages at risk', value: priorities.length || '-', note: priorities.length ? `${priorities.filter((item) => item.tier === 'P1').length} critical` : 'Awaiting verified feed' },
    { label: 'Affected roads', value: roadRisks.filter((road) => road.severed || road.p_blocked >= 0.45).length || '-', note: roadRisks.length ? 'Impact feed' : 'No verified road feed' },
    { label: 'Critical zones', value: latestTick?.cell_risks.filter((cell) => cell.p_fail >= 0.8).length || '-', note: 'Risk cells' },
    { label: 'Shelter routes', value: shelters.length || '-', note: 'Risk-aware destinations' },
    { label: 'Highest priority', value: top ? `${Math.round(top.eps * 100)}%` : '-', note: top?.village_id ?? 'No priority yet' },
  ]
  const responseSource = responses.at(-1)?.source

  async function submit(value = question) {
    const message = value.trim()
    if (!message || loading) return
    const next = [...messages, { role: 'user' as const, content: message }]
    setMessages(next)
    setQuestion('')
    setLoading(true)
    setStatus(null)
    try {
      const response = await api.commanderChat({
        message,
        history: next,
        village_id: top?.village_id,
        aoi_id: aoi?.id,
      })
      setResponses((current) => [
        ...current,
        structuredFromLive(response, message, priorities, roadRisks, isolations, shelters),
      ])
      setMessages([...next, { role: 'assistant', content: response.answer }])
      if (response.source === 'fallback') {
        setStatus('Deterministic local advisory active. Human approval remains required.')
      }
    } catch {
      const fallback = demoResponse(message, priorities, roadRisks, isolations, routes, shelters)
      setResponses((current) => [...current, fallback])
      setMessages([...next, { role: 'assistant', content: fallback.summary }])
      setStatus('Commander service unavailable. Deterministic local advisory active.')
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  async function saveRoute(item: CommanderRoute) {
    try {
      await api.saveRoutePlan({
        name: `${item.route.shelter_name} safety plan`,
        aoi_id: aoi?.id ?? 'aizawl',
        village_id: item.route.village_id,
        routes: [item],
      })
      setSaved('Route plan saved for officer review.')
    } catch {
      setSaved('Plan could not be saved. The route remains available in this response.')
    }
  }

  return <div className="commander-workspace"><div className="commander-page">
    <header className="commander-header">
      <div><div className="commander-kicker"><span className="commander-orb" /> AI ADVISORY COMMANDER</div><h1>Emergency operations copilot</h1><p>Ask about current risk, safe movement, roads, shelters, and next steps.</p></div>
      <div className="commander-live"><span /> {mode === 'replay' ? 'REPLAY' : 'LIVE STUB'}<br /><small>{aoi?.name ?? 'Aizawl'} · Human approval required</small></div>
    </header>
    <section className="commander-situation">
      <div className="commander-section-label"><div><span className="eyebrow">{mode === 'replay' ? 'RECONSTRUCTED SITUATION' : 'LIVE STUB SITUATION'}</span><h2>Current operational picture</h2></div><span className="updated">Data time: {latestTick?.t ? new Date(latestTick.t).toLocaleTimeString() : 'Awaiting feed'} · Source: {latestTick?.is_reconstructed ? 'reconstructed' : 'local stub'}</span></div>
      <div className="commander-kpis">{kpis.map((kpi) => <article key={kpi.label}><span className="kpi-icon">+</span><strong>{kpi.value}</strong><span>{kpi.label}</span><small>{kpi.note}</small></article>)}</div>
    </section>
    <main className="commander-chat">
      <div className="commander-chat-heading"><div><span className="eyebrow teal">COMMANDER CONVERSATION</span><h2>What do you need to know?</h2></div><span className="source-badge">{responseSource === 'nvidia' ? 'OPTIONAL NVIDIA RESPONSE' : responseSource === 'fallback' ? 'DETERMINISTIC LOCAL' : 'LOCAL DATA CONTEXT'}</span></div>
      {messages.length === 0 && <div className="commander-welcome"><div className="commander-avatar">N</div><div><strong>Commander is ready.</strong><p>I will translate your question into an operational view using current project data. The system proposes; an authorised officer decides.</p></div></div>}
      <div className="commander-thread">
        {messages.map((message, index) => <div className={`commander-message ${message.role}`} key={`${message.role}-${index}`}><div className="message-label">{message.role === 'user' ? 'YOU' : 'COMMANDER'}</div><p>{message.content}</p>{message.role === 'assistant' && responses[Math.floor((index - 1) / 2)] ? <CommanderResponse blocks={responses[Math.floor((index - 1) / 2)].blocks} onSave={saveRoute} onAnnounce={onAnnounce} onWhatIf={onWhatIf} /> : null}</div>)}
        {loading && <div className="commander-message assistant"><div className="message-label">COMMANDER</div><div className="commander-loading"><span>Analyzing the current situation</span><i /><i /><i /></div><div className="loading-lines"><b /><b /><b /></div></div>}
      </div>
      {status && <div className="commander-inline-status">{status}</div>}
      {saved && <div className="commander-inline-status">{saved}</div>}
      <form className="commander-composer" onSubmit={(event: FormEvent) => { event.preventDefault(); void submit() }}>
        <textarea aria-label="Ask the commander" value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={onKeyDown} placeholder="Ask Commander about risk, routes, roads, or shelters..." rows={2} disabled={loading} />
        <div className="composer-footer"><span>Enter to send · Shift + Enter for a new line</span><button type="submit" disabled={loading || !question.trim()}>{loading ? 'Analyzing...' : 'Ask Commander'}</button></div>
      </form>
      <div className="suggested-prompts"><span>Suggested questions</span>{SUGGESTIONS.map((suggestion) => <button type="button" key={suggestion} onClick={() => void submit(suggestion)} disabled={loading}>{suggestion}</button>)}</div>
    </main>
    <aside className="commander-human"><span className="eyebrow amber">HUMAN-IN-THE-LOOP</span><strong>The system proposes. An authorised officer decides.</strong><p>Recommendations never publish automatically.</p><button type="button" onClick={onAnnounce}>Open Announce</button><button type="button" onClick={onWhatIf}>Run What-if</button></aside>
  </div></div>
}
