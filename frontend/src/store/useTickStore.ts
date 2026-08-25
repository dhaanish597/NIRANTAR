import { create } from 'zustand'
import { api } from '../lib/api'
import { connectTickSocket, type WsStatus } from '../lib/ws'
import type {
  ActionCard,
  AoiInfo,
  AuditEvent,
  CellRisk,
  ModeState,
  ScenarioSummary,
  SettlementPriority,
  TickResult,
} from '../types/schemas'

const MAX_ACTION_CARDS = 20
const MAX_AUDIT_EVENTS = 50

interface TickStoreState {
  wsStatus: WsStatus
  aoi: AoiInfo | null
  scenarios: ScenarioSummary[]
  modeState: ModeState | null
  latestTick: TickResult | null
  cellRisks: CellRisk[]
  priorities: SettlementPriority[]
  actionCards: ActionCard[]
  auditEvents: AuditEvent[]
  error: string | null

  connect: () => void
  disconnect: () => void
  loadInitial: (aoiId: string) => Promise<void>
  startReplay: (scenarioId: string) => Promise<void>
  stopReplay: () => Promise<void>
  /** Exposed (not just used internally by connect()) so it's directly unit-testable without a
   * real WebSocket — see src/store/useTickStore.test.ts. */
  applyTick: (tick: TickResult) => void
}

let disconnectSocket: (() => void) | null = null

export const useTickStore = create<TickStoreState>((set, get) => ({
  wsStatus: 'closed',
  aoi: null,
  scenarios: [],
  modeState: null,
  latestTick: null,
  cellRisks: [],
  priorities: [],
  actionCards: [],
  auditEvents: [],
  error: null,

  connect: () => {
    if (disconnectSocket) return // already connected
    disconnectSocket = connectTickSocket({
      onTick: (tick) => get().applyTick(tick),
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
      set({ modeState, error: null })
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

  applyTick: (tick: TickResult) =>
    set((state) => ({
      latestTick: tick,
      cellRisks: tick.cell_risks,
      priorities: tick.priorities,
      actionCards: [...tick.new_action_cards, ...state.actionCards].slice(0, MAX_ACTION_CARDS),
      auditEvents: [...tick.new_audit_events, ...state.auditEvents].slice(0, MAX_AUDIT_EVENTS),
    })),
}))
