/**
 * Hand-written TypeScript mirror of backend/app/schemas/ (docs/ARCHITECTURE.md §4). No codegen
 * in Phase 0 — keep this in sync by hand when a Pydantic schema changes. Field names and shapes
 * match the backend exactly (Pydantic's default JSON encoding), including which fields are
 * optional, so `JSON.parse` of a WebSocket message can be cast straight to these types.
 */
import type { Geometry } from 'geojson'

export type RunMode = 'live' | 'replay'

export interface ModeState {
  mode: RunMode
  scenario_id: string | null
  scenario_time: string | null // ISO 8601
  speed_factor: number
  paused: boolean
}

export interface Attribution {
  feature: string
  plain_language: string
  contribution: number
  display_pct: number
}

export interface CellRisk {
  cell_id: string
  p_fail: number
  threshold_exceedance: number
  confidence: number
  attributions: Attribution[]
  model_version: string
}

export interface RoadSegmentRisk {
  edge_id: string
  name: string | null
  highway_class: string
  is_bridge: boolean
  p_blocked: number
  severed: boolean
  contributing_cells: string[]
}

export interface Demographics {
  children: number
  seniors: number
  adults: number
  high_risk_households: number
  source: 'simulated'
}

export interface VillageIsolation {
  village_id: string
  name: string
  population: number
  demographics?: Demographics
  p_isolated: number
  isolated_now: boolean
  alternate_route_exists: boolean
  est_duration_hours: number | null
  severed_links: string[]
}

export interface SettlementPriority {
  village_id: string
  eps: number
  tier: 'P1' | 'P2' | 'P3'
  components: Record<string, number>
}

export interface EvacuationRoute {
  village_id: string
  shelter_id: string
  shelter_name: string
  geometry: Geometry
  distance_m: number
  est_walk_minutes: number
  avoided_roads: string[]
  shelter_capacity_ok: boolean
}

export type EscalationStage = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'

export interface ActionCard {
  alert_id: string
  village_id: string
  stage: EscalationStage
  headline: string
  reason_plain: string
  shelter_name: string
  route: EvacuationRoute | null
  roads_to_avoid: string[]
  what_to_carry: string[]
  contact: string
  issued_at: string // ISO 8601
  valid_until: string // ISO 8601
  safe_window_hours: [number, number] | null
  translations: Record<string, string>
  audio_urls: Record<string, string>
}

export interface AuditEvent {
  event_id: string
  alert_id: string
  kind:
    | 'AI_FLAGGED'
    | 'DDMA_APPROVED'
    | 'DISSEMINATED'
    | 'DELIVERED'
    | 'VILLAGE_ACKNOWLEDGED'
    | 'ESCALATED'
    | 'STOOD_DOWN'
  actor: string
  t: string // ISO 8601
  payload: Record<string, unknown>
  input_hash: string
  prev_hash: string
  hash: string
}

/** The one object the frontend ever receives over /ws/ticks. */
export interface TickResult {
  t: string // ISO 8601
  mode: RunMode
  scenario_id: string | null
  aoi_id: string
  cell_risks: CellRisk[]
  road_risks: RoadSegmentRisk[]
  isolations: VillageIsolation[]
  priorities: SettlementPriority[]
  new_action_cards: ActionCard[]
  new_audit_events: AuditEvent[]
  is_reconstructed: boolean
}

export interface ScenarioSummary {
  id: string
  aoi_id: string
  held_out_of_training: boolean
  frame_count: number
  start: string
  end: string
  provenance: Record<string, unknown>
}

export interface AoiInfo {
  id: string
  name: string
  center: { lat: number; lon: number }
  note?: string
}

/** BUILD_PLAN.md task 5.8 — POST /api/whatif/simulate's request body
 * (backend/app/api/whatif.py::WhatIfRequest). */
export interface WhatIfRequest {
  aoi_id: string
  rainfall_mm: number
  duration_hours: number
}

/** POST /api/whatif/simulate's response (backend/app/api/whatif.py::WhatIfResult) — a REAL
 * TickResult from a throwaway Pipeline run, never written to the live audit log or /ws/ticks. */
export interface WhatIfResult {
  request: WhatIfRequest
  assumptions: string[]
  cell_count: number
  tick: TickResult
}

export interface ChannelResultSummary {
  channel: string
  recipient_count: number
  delivered_count: number
  acknowledged_count: number
}

/** POST/GET /api/announcements' wire shape (backend/app/schemas/announcement.py::Announcement).
 * The real dissemination trigger: this is what a DDMA officer's Approve/Modify action in the
 * Announce workspace actually produces, and what the Citizen Announcement tab reads. */
export interface Announcement {
  id: string
  alert_id: string
  village_id: string
  stage: EscalationStage
  message: string
  language: string
  issued_by: string
  issued_at: string // ISO 8601
  channel_results: ChannelResultSummary[]
  cap_xml: string
}

/** Frontend-only for now (no backend schema until sub-project 3's verification workflow) — the
 * shape Dashboard (sub-project 2) needs to exist so it can badge a route "Verified Safe" without
 * a later schema change. */
export interface VerificationRecord {
  status: 'pending' | 'verified' | 'rejected'
  verifiedBy?: string
  verifiedAt?: string // ISO 8601
}

export interface CommanderRoute {
  route_rank: number
  route: EvacuationRoute
  safety_reason: string
  risk_snapshot: string[]
}

export interface CommanderChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface CommanderChatResponse {
  answer: string
  source: 'nvidia' | 'fallback'
  routes: CommanderRoute[]
  context: Record<string, unknown>
}

export type CommanderIntent = 'SAFE_ROUTE' | 'HIGH_RISK_VILLAGES' | 'ROAD_ISOLATION' | 'EXPLAIN_RISK' | 'SHELTERS' | 'ANNOUNCEMENT' | 'GENERAL'

export interface CommanderResponseBlock {
  type: 'text' | 'risk' | 'road' | 'route' | 'shelter' | 'map' | 'evidence' | 'action'
  data: Record<string, unknown>
}

export interface CommanderStructuredResponse {
  type: 'commander_response'
  intent: CommanderIntent
  summary: string
  blocks: CommanderResponseBlock[]
  source: 'nvidia' | 'fallback'
}

export interface SavedRoutePlan {
  id: string
  name: string
  aoi_id: string
  village_id: string
  routes: CommanderRoute[]
  created_at: string
}
