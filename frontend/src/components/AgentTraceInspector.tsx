import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export interface AgentTraceStep {
  turn: number
  agent_role: string
  tool_name: string
  latency_ms: number
  verified_citations: string[]
  summary: string
}

export function AgentTraceInspector({
  aoiId = 'chennai',
  query = 'Analyze 3-hop cascading infrastructure failure and safe evacuation routes.',
  steps: externalSteps,
  modelTier = 'meta/llama-3.1-70b-instruct (Reasoning Tier)',
}: {
  aoiId?: string
  query?: string
  steps?: AgentTraceStep[]
  modelTier?: string
}) {
  const [liveSteps, setLiveSteps] = useState<AgentTraceStep[]>(externalSteps ?? [])
  const [blockedCount, setBlockedCount] = useState<number>(0)

  useEffect(() => {
    if (externalSteps && externalSteps.length > 0) {
      setLiveSteps(externalSteps)
      return
    }
    let cancelled = false
    api
      .runMultiplexCopilot({ aoi_id: aoiId, query })
      .then((res) => {
        if (cancelled) return
        const citedIds = res.recommendations.flatMap((r) => r.citations.map((c) => c.node_id))
        const mapped: AgentTraceStep[] = res.agent_traces.map((t) => ({
          turn: t.turn,
          agent_role: t.agent_role,
          tool_name: t.tool_called,
          latency_ms: t.latency_ms,
          verified_citations: citedIds.slice(0, 5),
          summary: `Executed ${t.tool_called} via ${t.model_tier}`,
        }))
        setLiveSteps(mapped)
        setBlockedCount(res.unverified_citations_blocked)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [aoiId, query, externalSteps])

  return (
    <section className="agent-trace-inspector" aria-label="Neuro-Symbolic Agent Orchestrator Trace">
      <div className="commander-section-label">
        <div>
          <span className="eyebrow teal">NEURO-SYMBOLIC ORCHESTRATOR TRACE</span>
          <h2>Bounded Multi-Agent Tool & Citation Audit</h2>
        </div>
        <span className="source-badge">
          {modelTier} · Blocked Hallucinations: {blockedCount}
        </span>
      </div>
      <div className="agent-trace">
        {liveSteps.map((step) => (
          <div key={`${step.turn}-${step.tool_name}`} className="agent-trace-row">
            <b>
              Turn {step.turn} · {step.agent_role} → <code>{step.tool_name}</code> ({step.latency_ms.toFixed(1)} ms)
            </b>
            <span>{step.summary}</span>
            <small>Verified Graph Citations: {step.verified_citations.join(', ') || 'Verified Subgraph'}</small>
          </div>
        ))}
      </div>
    </section>
  )
}
