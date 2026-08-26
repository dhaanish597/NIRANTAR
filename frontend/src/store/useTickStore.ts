import { create } from 'zustand'
import { api } from '../lib/api'
import { getCitizenReports, queueCitizenReport as persistCitizenReport, type CitizenReport } from '../lib/citizenReports'
import { cacheActionCards, getCachedActionCards } from '../lib/offlineData'
import { connectTickSocket, type WsStatus } from '../lib/ws'
import type {
  ActionCard,
  Announcement,
  AoiInfo,
  AuditEvent,
  CellRisk,
  ModeState,
  RoadSegmentRisk,
  ScenarioSummary,
  SettlementPriority,
  TickResult,
  VerificationRecord,
  VillageIsolation,
} from '../types/schemas'

const MAX_ACTION_CARDS = 20
const MAX_AUDIT_EVENTS = 50
const MAX_ANNOUNCEMENTS = 50
// Generous headroom over any real scenario's frame count (aizawl-2024 is 67 frames) — this is
// the full per-tick history of the CURRENT replay run, kept so the counterfactual scorecard
// (BUILD_PLAN.md task 4.10) can derive "first Yellow/Orange/Red", road-severance timestamps, etc.
// from real tick-by-tick data rather than only the latest snapshot.
const MAX_REPLAY_TICKS = 2000

interface TickStoreState {
  wsStatus: WsStatus
  aoi: AoiInfo | null
  scenarios: ScenarioSummary[]
  modeState: ModeState | null
  latestTick: TickResult | null
  /** Every tick received since the most recent `startReplay()` call, in chronological order,
   * capped at MAX_REPLAY_TICKS (BUILD_PLAN.md task 4.10's counterfactual scorecard — see
   * `lib/scorecard.ts`). Deliberately NOT cleared on `stopReplay()` so the scorecard for a replay
   * that just finished stays viewable after returning to LIVE. */
  replayTicks: TickResult[]
  cellRisks: CellRisk[]
  roadRisks: RoadSegmentRisk[]
  isolations: VillageIsolation[]
  priorities: SettlementPriority[]
  actionCards: ActionCard[]
  auditEvents: AuditEvent[]
  error: string | null
  /** BUILD_PLAN.md task 2.8: which village's detail drawer is open, set by clicking a map pin
   * (MapView) or a Priority List row (RightRail). Lives here (not component-local state) so
   * either entry point can open/close the same drawer. */
  selectedVillageId: string | null
  /** BUILD_PLAN.md task 4.10: whether the Counterfactual Lead-Time Scorecard modal is open.
   * Lives here (store-owned), same pattern as `selectedVillageId`, so both the trigger
   * (ReplayControlBar) and the modal itself (CounterfactualScorecard, rendered from App.tsx) can
   * read/set it without prop drilling. */
  scorecardOpen: boolean
  /** BUILD_PLAN.md task 3.8: which `alert_id` the Audit Trail view modal should fetch and
   * display, or `null` when closed. Store-owned (not component-local) for the same reason
   * `selectedVillageId`/`scorecardOpen` are: several independent entry points (a DDMA Console
   * recommendation row, the Village View action card) all need to be able to open the SAME
   * modal (rendered once from App.tsx) at a specific alert_id. */
  auditTrailAlertId: string | null

  announcements: Announcement[]
  verificationByAlertId: Record<string, VerificationRecord>
  citizenReports: CitizenReport[]

  hydrateCitizenReports: () => void
  queueCitizenReport: (input: Pick<CitizenReport, 'category' | 'note'>) => void
  applyAnnouncement: (announcement: Announcement) => void
  setVerification: (alertId: string, record: VerificationRecord) => void

  connect: () => void
  disconnect: () => void
  loadInitial: (aoiId: string) => Promise<void>
  startReplay: (scenarioId: string) => Promise<void>
  stopReplay: () => Promise<void>
  /** BUILD_PLAN.md task 5.3: loads the last IndexedDB-cached action cards (frontend/src/lib/
   * offlineData.ts) into the store, called once at app boot (App.tsx) BEFORE any real WebSocket
   * tick can arrive — so a citizen opening the app fully offline still sees the last known action
   * card/route/shelter/contact instead of an empty screen. Never overwrites real tick data: a
   * no-op once any tick has actually populated `actionCards` (checked at call time, not by
   * ordering alone, so a slow cache read racing a fast first tick can't clobber it). */
  hydrateFromOfflineCache: () => Promise<void>
  /** Exposed (not just used internally by connect()) so it's directly unit-testable without a
   * real WebSocket — see src/store/useTickStore.test.ts. */
  applyTick: (tick: TickResult) => void
  selectVillage: (villageId: string | null) => void
  openScorecard: () => void
  closeScorecard: () => void
  openAuditTrail: (alertId: string) => void
  closeAuditTrail: () => void
}

let disconnectSocket: (() => void) | null = null

export const useTickStore = create<TickStoreState>((set, get) => ({
  wsStatus: 'closed',
  aoi: null,
  scenarios: [],
  modeState: null,
  latestTick: null,
  replayTicks: [],
  cellRisks: [],
  roadRisks: [],
  isolations: [],
  priorities: [],
  actionCards: [],
  auditEvents: [],
  error: null,
  selectedVillageId: null,
  scorecardOpen: false,
  auditTrailAlertId: null,

  announcements: [],
  verificationByAlertId: {},
  citizenReports: [],

  hydrateCitizenReports: () => set({ citizenReports: getCitizenReports() }),

  queueCitizenReport: (input) => {
    const report = persistCitizenReport(input)
    set((state) => ({ citizenReports: [...state.citizenReports, report] }))
  },

  applyAnnouncement: (announcement) =>
    set((state) => ({
      announcements: [announcement, ...state.announcements].slice(0, MAX_ANNOUNCEMENTS),
    })),

  setVerification: (alertId, record) =>
    set((state) => ({
      verificationByAlertId: { ...state.verificationByAlertId, [alertId]: record },
    })),

  connect: () => {
    if (disconnectSocket) return // already connected
    disconnectSocket = connectTickSocket({
      onTick: (tick) => get().applyTick(tick),
      onAnnouncement: (announcement) => get().applyAnnouncement(announcement),
      onStatusChange: (wsStatus) => set({ wsStatus }),
    })
  },

  disconnect: () => {
    disconnectSocket?.()
    disconnectSocket = null
  },

  loadInitial: async (aoiId: string) => {
    try {
      const [modeState, scenarios, aoi] = await Promise.all([
        api.getState(),
        api.getScenarios(),
        api.getAoi(aoiId),
      ])
      set({ modeState, scenarios, aoi, error: null })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  startReplay: async (scenarioId: string) => {
    try {
      const modeState = await api.startReplay(scenarioId)
      // A fresh replay run starts a fresh tick history — BUILD_PLAN.md task 4.7's backend note
      // ("restart must fully reset downstream state") applies just as much to the frontend's own
      // accumulated history the scorecard reads from.
      set({ modeState, error: null, replayTicks: [] })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  stopReplay: async () => {
    try {
      const modeState = await api.stopReplay()
      set({ modeState, error: null })
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  hydrateFromOfflineCache: async () => {
    const cached = await getCachedActionCards()
    if (cached.length === 0) return
    // Guard at write time, not just at call time: a real tick could have arrived (and already
    // set real actionCards) while this async cache read was in flight.
    if (get().actionCards.length > 0) return
    set({ actionCards: cached })
  },

  applyTick: (tick: TickResult) => {
    const nextActionCards = [...tick.new_action_cards, ...get().actionCards].slice(
      0,
      MAX_ACTION_CARDS,
    )
    // BUILD_PLAN.md task 5.3: cache the up-to-date action card list to IndexedDB on every tick —
    // fire-and-forget (offlineData.ts's own `cacheActionCards` fails open on any storage error),
    // never blocks tick handling.
    void cacheActionCards(nextActionCards)
    set((state) => ({
      latestTick: tick,
      cellRisks: tick.cell_risks,
      roadRisks: tick.road_risks,
      isolations: tick.isolations,
      priorities: tick.priorities,
      actionCards: nextActionCards,
      auditEvents: [...tick.new_audit_events, ...state.auditEvents].slice(0, MAX_AUDIT_EVENTS),
      // Only replay ticks feed the counterfactual scorecard (task 4.10) — a LIVE tick received
      // while a previous replay's history is still being reviewed must not contaminate it.
      replayTicks:
        tick.mode === 'replay'
          ? [...state.replayTicks, tick].slice(-MAX_REPLAY_TICKS)
          : state.replayTicks,
    }))
  },

  selectVillage: (villageId: string | null) => set({ selectedVillageId: villageId }),
  openScorecard: () => set({ scorecardOpen: true }),
  closeScorecard: () => set({ scorecardOpen: false }),
  openAuditTrail: (alertId: string) => set({ auditTrailAlertId: alertId }),
  closeAuditTrail: () => set({ auditTrailAlertId: null }),
}))
