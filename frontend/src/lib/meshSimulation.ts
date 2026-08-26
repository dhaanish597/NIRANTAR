/**
 * BUILD_PLAN.md task 5.5 — `MeshChannel` simulation visual: "a small visual of phone-to-phone
 * store-and-forward propagation through a village with no tower coverage. Cite the real number —
 * ~1,841 NER villages without mobile coverage. Label it clearly as a simulation."
 *
 * **Data-source ruling, checked before writing anything (this task's own instruction):**
 * `dissemination/channels.py`'s `ChannelSendResult` (task 3.5) is real and tested, but
 * `pipeline.py`'s own module docstring (ruling 6) states plainly it is NOT auto-fired — sending
 * every alert-worthy card out over every simulated channel the instant the AI flags it would
 * bypass CLAUDE.md's human-in-the-loop rule. Confirmed by reading `pipeline.py` and
 * `DdmaConsole.tsx` directly: no `ChannelSendResult` (or anything derived from it) has ever
 * reached `TickResult`/the frontend. There is no real per-alert dissemination data to visualize.
 *
 * So: this module builds the visual against the REAL, committed per-channel PARAMETERS
 * `_SimulatedChannelBase` subclasses in `backend/app/dissemination/channels.py` are constructed
 * with (`CHANNEL_PROFILES` below — copied by hand from that file, not invented; keep in sync by
 * hand the same way `frontend/src/types/schemas.ts` already keeps the Pydantic schemas in sync),
 * rather than either (a) faking a live per-alert animation from nothing, or (b) leaving this task
 * undone. The propagation this module simulates is illustrative — seeded pseudo-randomly in the
 * BROWSER (`mulberry32`, a small deterministic PRNG, not Python's `random.Random` the backend
 * uses) — clearly labelled a SIMULATION PREVIEW everywhere it renders, never presented as a real
 * alert's actual delivery outcome. Backend `ChannelSendResult`'s own determinism (CLAUDE.md rule
 * 13, seeded from `(alert_id, channel_name)` via SHA-256) is a BACKEND correctness property for a
 * real dissemination run; this frontend preview has no `alert_id` to seed from at all (nothing
 * was actually sent), so it seeds from whatever the caller passes (a UI "Run simulation" click
 * counter) purely so the same click produces the same preview twice in a row, not to claim
 * cross-system reproducibility with a real backend run.
 */

// Copied by hand from backend/app/dissemination/channels.py's four `_SimulatedChannelBase`
// subclasses (task 3.5) — the same real, committed constants CLAUDE.md's own dissemination rule
// describes ("simulated with realistic latency and a delivery/ack rate"). Keep in sync by hand if
// channels.py's numbers ever change.
export interface ChannelProfile {
  id: 'cell_broadcast' | 'sms' | 'push' | 'mesh'
  label: string
  minLatencySeconds: number
  maxLatencySeconds: number
  deliveryRate: number
  ackRateGivenDelivered: number
}

export const CHANNEL_PROFILES: ChannelProfile[] = [
  {
    id: 'cell_broadcast',
    label: 'Cell broadcast',
    minLatencySeconds: 2.0,
    maxLatencySeconds: 15.0,
    deliveryRate: 0.97,
    ackRateGivenDelivered: 0.55,
  },
  {
    id: 'sms',
    label: 'SMS',
    minLatencySeconds: 5.0,
    maxLatencySeconds: 120.0,
    deliveryRate: 0.9,
    ackRateGivenDelivered: 0.4,
  },
  {
    id: 'push',
    label: 'Push notification',
    minLatencySeconds: 1.0,
    maxLatencySeconds: 20.0,
    deliveryRate: 0.75,
    ackRateGivenDelivered: 0.6,
  },
  {
    id: 'mesh',
    label: 'Mesh (phone-to-phone)',
    minLatencySeconds: 60.0,
    maxLatencySeconds: 1800.0,
    deliveryRate: 0.6,
    ackRateGivenDelivered: 0.3,
  },
]

export const MESH_PROFILE: ChannelProfile = CHANNEL_PROFILES.find((c) => c.id === 'mesh')!

/** Small deterministic PRNG (mulberry32) — seeded so a given `seed` always produces the same
 * simulated hop sequence in the same browser session (a UI nicety: replaying a click looks the
 * same), not a claim of matching the backend's own Python-side seeded RNG (see module docstring). */
function mulberry32(seed: number): () => number {
  let a = seed
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export interface SimulatedHop {
  /** 1-based index of the villager's phone reached at this hop (0 is the origin phone, not
   * included in this list). */
  nodeIndex: number
  delivered: boolean
  acknowledged: boolean
  latencySeconds: number
  /** Which already-reached node (0 = origin) this hop's device relayed from — purely illustrative
   * connecting-line data for the visual, not a claim about real device proximity/routing. */
  relayFromNodeIndex: number
}

export interface MeshSimulationResult {
  nodeCount: number
  hops: SimulatedHop[]
  deliveredCount: number
  acknowledgedCount: number
  totalElapsedSeconds: number // the latest hop's latency — "how long until every reachable phone
  // in this simulated run had a chance to relay it", not a real measured field duration.
}

/** Simulates one phone-to-phone store-and-forward run through `nodeCount` villagers' phones (the
 * origin phone, node 0, is the one that briefly had signal and received the alert — e.g. near a
 * hilltop/road per BUILD_PLAN.md's own framing — and is not counted as a "hop"). Each subsequent
 * node's delivery/ack outcome is drawn using the REAL `MESH_PROFILE` rates (see module docstring)
 * against the seeded PRNG. */
export function simulateMeshPropagation(nodeCount: number, seed: number): MeshSimulationResult {
  const rng = mulberry32(seed)

  // Pass 1: draw each non-origin node's own outcome (order doesn't matter here — each node's
  // delivered/acknowledged/latency is independent of every other node's).
  const draws: Array<{ nodeIndex: number; delivered: boolean; acknowledged: boolean; latencySeconds: number }> = []
  for (let i = 1; i < nodeCount; i++) {
    const delivered = rng() < MESH_PROFILE.deliveryRate
    const acknowledged = delivered && rng() < MESH_PROFILE.ackRateGivenDelivered
    const latencySeconds =
      MESH_PROFILE.minLatencySeconds +
      rng() * (MESH_PROFILE.maxLatencySeconds - MESH_PROFILE.minLatencySeconds)
    draws.push({ nodeIndex: i, delivered, acknowledged, latencySeconds })
  }
  // Chronological order — a hop with a shorter simulated latency happens sooner. Sorted BEFORE
  // assigning relay sources (pass 2) so a hop can only ever relay from a node that had already
  // (chronologically) received the alert — never from a node whose own delivery happens later.
  draws.sort((a, b) => a.latencySeconds - b.latencySeconds)

  // Pass 2: walk the chronological order, assigning each delivered hop a relay source drawn from
  // whichever nodes have already been reached AT THAT POINT in simulated time.
  const hops: SimulatedHop[] = []
  const reachedNodes = [0] // origin only, so far
  for (const draw of draws) {
    // A relay source is only meaningful for a delivered hop (it had to come from SOMEWHERE that
    // already had the alert) — an undelivered hop has no real relay path, so it's attributed to
    // the origin purely as a harmless default, never rendered as a connecting line in the UI.
    const relayFromNodeIndex = draw.delivered
      ? reachedNodes[Math.floor(rng() * reachedNodes.length)]
      : 0
    hops.push({ ...draw, relayFromNodeIndex })
    if (draw.delivered) reachedNodes.push(draw.nodeIndex)
  }

  return {
    nodeCount,
    hops,
    deliveredCount: hops.filter((h) => h.delivered).length,
    acknowledgedCount: hops.filter((h) => h.acknowledged).length,
    totalElapsedSeconds: hops.length > 0 ? Math.max(...hops.map((h) => h.latencySeconds)) : 0,
  }
}

/** "23 min" / "1h 05m" — a plain, honest formatter for a simulated elapsed-time label (never
 * rendered as if it were a measured real-world duration — see the component's own labelling). */
export function formatSimulatedDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  if (totalMinutes < 60) return `${totalMinutes} min`
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`
}
