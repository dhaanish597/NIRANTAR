import type {
  ActionCard,
  AoiInfo,
  AuditEvent,
  ModeState,
  ScenarioSummary,
  WhatIfRequest,
  WhatIfResult,
} from '../types/schemas'
import type { DdmaDecisionKind } from './ddma'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`${init?.method ?? 'GET'} ${path} -> ${response.status}: ${body}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  getState: () => request<ModeState>('/api/state'),
  getScenarios: () => request<ScenarioSummary[]>('/api/scenarios'),
  getAoi: (aoiId: string) => request<AoiInfo>(`/api/aoi/${aoiId}`),
  startReplay: (scenarioId: string) =>
    request<ModeState>('/api/replay/start', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
  stopReplay: () => request<ModeState>('/api/replay/stop', { method: 'POST' }),
  // BUILD_PLAN.md task 3.7: DDMA Console Approve/Modify/Reject -> POST /api/ddma/decide
  // (backend/app/api/routes.py), calling the real, tested `audit/producers.py::record_ddma_decision`.
  submitDdmaDecision: (payload: {
    action_card: ActionCard
    officer_id: string
    decision: DdmaDecisionKind
    notes?: string
  }) =>
    request<AuditEvent>('/api/ddma/decide', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  // BUILD_PLAN.md task 3.10: Village View "I have evacuated" -> POST /api/village/acknowledge,
  // calling the real, tested `audit/producers.py::record_village_acknowledged`.
  acknowledgeVillage: (payload: { alert_id: string; village_id: string }) =>
    request<AuditEvent>('/api/village/acknowledge', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  // BUILD_PLAN.md task 3.8: the Audit Trail view's real data source.
  getAuditTrail: (alertId: string) =>
    request<AuditEvent[]>(`/api/audit/${encodeURIComponent(alertId)}`),
  // BUILD_PLAN.md task 5.8: the what-if rainfall simulator — a real TickResult from a throwaway
  // backend Pipeline run (never the live one), DDMA pre-positioning support, not a real alert.
  runWhatIf: (payload: WhatIfRequest) =>
    request<WhatIfResult>('/api/whatif/simulate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}
