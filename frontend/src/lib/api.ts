import type {
  ActionCard,
  Announcement,
  AoiExposure,
  AoiInfo,
  AuditEvent,
  ModeState,
  ScenarioSummary,
  WhatIfRequest,
  WhatIfResult,
  CommanderChatMessage,
  CommanderChatResponse,
  SavedRoutePlan,
  RiskForecast,
  CitizenReportRecord,
  CitizenReportStatus,
} from '../types/schemas'
import type { DdmaDecisionKind } from './ddma'
import type { CascadeAssetItem } from '../components/MultiplexGraphOverlay'
import type { ChokePointItem } from '../components/ChokePointTriageCard'
import type { AgentTraceStep } from '../components/AgentTraceInspector'

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

export interface MultiplexCascadeResponse {
  trigger_node_id: string
  max_hops: number
  impacted_assets: CascadeAssetItem[]
  total_critical_human_exposure: number
  traversal_latency_ms: number
}

export interface MultiplexChokepointsResponse {
  aoi_id: string
  chokepoints: ChokePointItem[]
}

export interface MultiplexCopilotResponse {
  status: string
  executive_sitrep: string
  recommendations: Array<{
    priority_rank: number
    action_type: string
    target_node_id: string
    recommendation_text: string
    survival_window_hrs: number
    citations: Array<{ node_id: string; node_label: string; edge_path: string; confidence_score: number }>
  }>
  verified_subgraph_node_count: number
  unverified_citations_blocked: number
  agent_traces: Array<{
    turn: number
    agent_role: string
    model_tier: string
    tool_called: string
    tool_args: Record<string, unknown>
    latency_ms: number
  }>
}

export interface RoboticsMissionResponse {
  mission_id: string
  action_type: string
  platform_type: 'UAV_DRONE' | 'USV_SONAR'
  aoi_id: string
  target_node_id: string
  target_label: string
  knowledge_partner_tag: string
  altitude_or_draft_m: number
  estimated_sortie_minutes: number
  waypoints_geojson: { type: string; features: unknown[] }
}

export interface RoboticsSdgResponse {
  aoi_id: string
  trigger_node_id: string
  sdg6_potable_water_person_hours_saved: number
  sdg11_isolated_residents_reconnected: number
  sdg13_cascade_lead_time_gain_minutes: number
  summary_narrative: string
}

export const api = {
  getState: () => request<ModeState>('/api/state'),
  getScenarios: () => request<ScenarioSummary[]>('/api/scenarios'),
  getAoi: (aoiId: string) => request<AoiInfo>(`/api/aoi/${aoiId}`),
  getAoiExposure: (aoiId: string) => request<AoiExposure>(`/api/aoi/${aoiId}/exposure`),
  getAoiGrid: (aoiId: string) => request<{ aoi_id: string; cell_count: number; cells: Array<{ cell_id: string; lat: number; lon: number }> }>(`/api/aoi/${encodeURIComponent(aoiId)}/grid`),
  getRiskForecast: (locationId: string) => request<RiskForecast>(`/api/risk/forecast?location_id=${encodeURIComponent(locationId)}`),
  startReplay: (scenarioId: string) =>
    request<ModeState>('/api/replay/start', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
  stopReplay: () => request<ModeState>('/api/replay/stop', { method: 'POST' }),
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
  acknowledgeVillage: (payload: { alert_id: string; village_id: string }) =>
    request<AuditEvent>('/api/village/acknowledge', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getAuditTrail: (alertId: string) =>
    request<AuditEvent[]>(`/api/audit/${encodeURIComponent(alertId)}`),
  runWhatIf: (payload: WhatIfRequest) =>
    request<WhatIfResult>('/api/whatif/simulate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendAnnouncement: (payload: {
    action_card: ActionCard
    officer_id: string
    recipient_count: number
    message?: string
    language?: string
  }) =>
    request<Announcement>('/api/announcements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listAnnouncements: () => request<Announcement[]>('/api/announcements'),
  commanderChat: (payload: { message: string; history: CommanderChatMessage[]; village_id?: string; aoi_id?: string }) =>
    request<CommanderChatResponse>('/api/commander/chat', { method: 'POST', body: JSON.stringify(payload) }),
  saveRoutePlan: (payload: { name: string; aoi_id: string; village_id: string; routes: CommanderChatResponse['routes'] }) =>
    request<SavedRoutePlan>('/api/commander/saved-routes', { method: 'POST', body: JSON.stringify(payload) }),
  listSavedRoutePlans: () => request<SavedRoutePlan[]>('/api/commander/saved-routes'),
  submitCitizenReport: (payload: {
    aoi_id: string
    category: string
    description: string
    lat: number
    lon: number
    accuracy_m?: number | null
    image_data_url: string
  }) => request<CitizenReportRecord>('/api/citizen-reports', { method: 'POST', body: JSON.stringify(payload) }),
  listCitizenReports: (aoiId = 'aizawl') => request<CitizenReportRecord[]>(`/api/citizen-reports?aoi_id=${encodeURIComponent(aoiId)}`),
  updateCitizenReportStatus: (reportId: string, payload: { status: CitizenReportStatus; officer_id: string; notes?: string }) =>
    request<CitizenReportRecord>(`/api/citizen-reports/${encodeURIComponent(reportId)}/status`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getMultiplexCascade: (triggerNodeId: string, maxHops = 3) =>
    request<MultiplexCascadeResponse>('/api/multiplex/cascade', {
      method: 'POST',
      body: JSON.stringify({ trigger_node_id: triggerNodeId, max_hops: maxHops }),
    }),
  getMultiplexChokepoints: (aoiId: string, topK = 3) =>
    request<MultiplexChokepointsResponse>(`/api/multiplex/chokepoints/${encodeURIComponent(aoiId)}?top_k=${topK}`),
  runMultiplexCopilot: (payload: { aoi_id: string; query: string; trigger_node_id?: string }) =>
    request<MultiplexCopilotResponse>('/api/multiplex/copilot', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deployRoboticsMission: (payload: { aoi_id: string; target_node_id: string; platform_type: 'UAV_DRONE' | 'USV_SONAR' }) =>
    request<RoboticsMissionResponse>('/api/multiplex/robotics/mission', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getRoboticsSdg: (payload: { aoi_id: string; trigger_node_id: string; mitigated_node_ids?: string[] }) =>
    request<RoboticsSdgResponse>('/api/multiplex/robotics/sdg', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
}

export type { AgentTraceStep }
