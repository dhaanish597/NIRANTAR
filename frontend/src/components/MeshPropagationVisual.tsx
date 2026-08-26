import { useEffect, useRef, useState } from 'react'
import {
  CHANNEL_PROFILES,
  formatSimulatedDuration,
  MESH_PROFILE,
  simulateMeshPropagation,
  type MeshSimulationResult,
} from '../lib/meshSimulation'

// A demo-watchable village: enough phones to see a real spread-out relay pattern without the
// panel becoming unwieldy. Not a claim about a real village's household count.
const NODE_COUNT = 16
// The whole simulated run (however many real minutes/hours the slowest hop's latency represents)
// is compressed into this many milliseconds of on-screen animation — clearly labelled as
// compressed everywhere it's shown, never presented as real elapsed time.
const DEMO_DURATION_MS = 4000

/**
 * BUILD_PLAN.md task 5.5 — `MeshChannel` simulation visual.
 *
 * **Data-source ruling (see `lib/meshSimulation.ts`'s own docstring for the full reasoning,
 * checked against the real code before writing anything):** `dissemination/channels.py`'s
 * `ChannelSendResult` is real, but no real per-alert dissemination has ever reached the frontend —
 * `pipeline.py` deliberately does not auto-fire dissemination (human-in-the-loop, ruling 6), and
 * neither `DdmaConsole.tsx` nor `TickResult` carries anything derived from `ChannelSendResult`.
 * This panel is therefore built against the REAL, committed per-channel parameters in
 * `channels.py` (`lib/meshSimulation.ts::CHANNEL_PROFILES`), driving an illustrative,
 * browser-seeded simulation — labelled a SIMULATION PREVIEW throughout, never presented as a real
 * alert's actual delivery outcome.
 *
 * Placed in the DDMA Console (`DdmaConsole.tsx`) — the operational screen where a DDMA officer
 * would actually want to understand "if the tower network is down, how does this reach the last
 * village", not the citizen-facing Village View.
 */
export function MeshPropagationVisual() {
  const [seed, setSeed] = useState(1)
  const [result, setResult] = useState<MeshSimulationResult>(() =>
    simulateMeshPropagation(NODE_COUNT, seed),
  )
  const [revealedCount, setRevealedCount] = useState(0)
  const [running, setRunning] = useState(false)
  const timeoutIdsRef = useRef<number[]>([])

  const clearPendingTimeouts = () => {
    for (const id of timeoutIdsRef.current) window.clearTimeout(id)
    timeoutIdsRef.current = []
  }

  useEffect(() => clearPendingTimeouts, []) // clear any in-flight timers on unmount

  const runSimulation = () => {
    clearPendingTimeouts()
    const nextSeed = seed + 1
    setSeed(nextSeed)
    const nextResult = simulateMeshPropagation(NODE_COUNT, nextSeed)
    setResult(nextResult)
    setRevealedCount(0)
    setRunning(true)

    const scale = nextResult.totalElapsedSeconds > 0 ? DEMO_DURATION_MS / nextResult.totalElapsedSeconds : 0
    nextResult.hops.forEach((hop, index) => {
      const id = window.setTimeout(() => {
        setRevealedCount(index + 1)
        if (index === nextResult.hops.length - 1) setRunning(false)
      }, hop.latencySeconds * scale)
      timeoutIdsRef.current.push(id)
    })
    if (nextResult.hops.length === 0) setRunning(false)
  }

  const revealedHops = result.hops.slice(0, revealedCount)
  const reachedNodeIndices = new Set([0, ...revealedHops.filter((h) => h.delivered).map((h) => h.nodeIndex)])
  const ackedNodeIndices = new Set(revealedHops.filter((h) => h.acknowledged).map((h) => h.nodeIndex))
  const simulatedElapsedSeconds =
    revealedHops.length > 0 ? revealedHops[revealedHops.length - 1].latencySeconds : 0
  const finished = !running && revealedCount === result.hops.length && result.hops.length > 0

  return (
    <section>
      <div className="mb-1 flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
          Mesh propagation
        </h2>
        <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold text-amber-300">
          SIMULATION PREVIEW
        </span>
      </div>
      <p className="mb-2 text-[11px] text-slate-500">
        ~1,841 NER villages have no mobile coverage (CLAUDE.md §1) — for those, an alert has to
        reach ONE phone with signal (e.g. near a hilltop or road) and then relay
        phone-to-phone via Bluetooth/Wi-Fi Direct store-and-forward. This is not live dissemination
        data (no real alert has been sent) — it is a preview driven by the REAL, committed
        `mesh` channel parameters in <code className="text-slate-400">dissemination/channels.py</code>.
      </p>

      <div className="mb-3 grid grid-cols-8 gap-1.5">
        {Array.from({ length: NODE_COUNT }, (_, i) => i).map((nodeIndex) => {
          const isOrigin = nodeIndex === 0
          const reached = reachedNodeIndices.has(nodeIndex)
          const acked = ackedNodeIndices.has(nodeIndex)
          return (
            <div
              key={nodeIndex}
              title={
                isOrigin
                  ? 'Origin phone (first had signal)'
                  : acked
                    ? 'Delivered + acknowledged'
                    : reached
                      ? 'Delivered'
                      : 'Not yet reached'
              }
              className={`flex h-7 w-7 items-center justify-center rounded text-[10px] font-bold transition-colors duration-300 ${
                isOrigin
                  ? 'bg-emerald-500 text-black'
                  : acked
                    ? 'bg-sky-500 text-black'
                    : reached
                      ? 'bg-emerald-700 text-white'
                      : 'bg-white/10 text-slate-500'
              }`}
            >
              {isOrigin ? '📡' : reached ? '📱' : ''}
            </div>
          )
        })}
      </div>

      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          onClick={runSimulation}
          disabled={running}
          className="rounded bg-slate-700 px-3 py-1.5 text-xs font-semibold hover:bg-slate-600 disabled:opacity-50"
        >
          {running ? 'Simulating…' : 'Run simulation'}
        </button>
        <span className="text-[11px] text-slate-500">
          Simulated time elapsed:{' '}
          <span className="text-slate-300">{formatSimulatedDuration(simulatedElapsedSeconds)}</span>
          <span className="ml-1 text-slate-600">(animation compressed for display)</span>
        </span>
      </div>

      {finished && (
        <p className="mb-2 rounded border border-white/10 bg-white/5 p-2 text-xs text-slate-300">
          <span className="font-semibold text-slate-100">{result.deliveredCount + 1}</span> of{' '}
          {result.nodeCount} phones reached,{' '}
          <span className="font-semibold text-slate-100">{result.acknowledgedCount}</span>{' '}
          acknowledged, over{' '}
          <span className="font-semibold text-slate-100">
            {formatSimulatedDuration(result.totalElapsedSeconds)}
          </span>{' '}
          (simulated) — real mesh parameters: {MESH_PROFILE.minLatencySeconds}
          {'–'}
          {MESH_PROFILE.maxLatencySeconds}s per-hop latency,{' '}
          {(MESH_PROFILE.deliveryRate * 100).toFixed(0)}% delivery rate,{' '}
          {(MESH_PROFILE.ackRateGivenDelivered * 100).toFixed(0)}% ack rate.
        </p>
      )}

      <details className="text-[11px] text-slate-500">
        <summary className="cursor-pointer select-none">Compare all four channels</summary>
        <div className="mt-1 overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="text-slate-400">
                <th className="pr-2 font-medium">Channel</th>
                <th className="pr-2 font-medium">Latency</th>
                <th className="pr-2 font-medium">Delivery</th>
                <th className="font-medium">Ack</th>
              </tr>
            </thead>
            <tbody>
              {CHANNEL_PROFILES.map((c) => (
                <tr key={c.id} className={c.id === 'mesh' ? 'text-sky-300' : 'text-slate-400'}>
                  <td className="pr-2">{c.label}</td>
                  <td className="pr-2">
                    {c.minLatencySeconds}
                    {'–'}
                    {c.maxLatencySeconds}s
                  </td>
                  <td className="pr-2">{(c.deliveryRate * 100).toFixed(0)}%</td>
                  <td>{(c.ackRateGivenDelivered * 100).toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
