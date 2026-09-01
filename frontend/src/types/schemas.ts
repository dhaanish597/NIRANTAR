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
  geometry?: Geometry | null
  terrain?: Record<string, number | string | null>
}

export interface RoadSegmentRisk {
  edge_id: string
  name: string | null
  highway_class: string
  is_bridge: boolean
  p_blocked: number
  severed: boolean
  contributing_cells: string[]
  geometry?: Geometry | null
  affected_settlements?: string[]
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
  geometry?: Geometry | null
  connected_road_ids?: string[]
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
  bbox?: [number, number, number, number]
  note?: string
}

/** backend/app/schemas/exposure.py — real village/shelter points from `exposure.gpkg`, fetched
 * once per AOI (GET /api/aoi/{id}/exposure) and joined client-side against per-tick
 * SettlementPriority/VillageIsolation by `village_id`. Never fabricated positions. */
export interface VillageExposure {
  village_id: string
  name: string
  lat: number
  lon: number
  population_worldpop_est: number | null
  osm_population: number | null
}

export interface ShelterExposure {
  shelter_id: string
  name: string
  amenity: string | null
  lat: number
  lon: number
}

export interface AoiExposure {
  aoi_id: string
  villages: VillageExposure[]
  shelters: ShelterExposure[]
}

/** BUILD_PLAN.md task 5.8 — POST /api/whatif/simulate's request body
 * (backend/app/api/whatif.py::WhatIfRequest). */
export interface WhatIfRequest {
  aoi_id: string
  rainfall_mm: number
  duration_hours: number
  antecedent_rainfall_mm?: number
  soil_moisture_pct?: number
}

export type ForecastSource = 'LIVE' | 'MODEL' | 'FALLBACK'

export interface ForecastArea {
  id: string
  name: string
  risk_probability: number
  risk_level: string
}

export interface RiskForecastDay {
  date: string
  day_label: string
  risk_level: string
  risk_probability: number
  rainfall_mm: number
  confidence: number
  primary_driver: string
  explanation: string
  affected_villages: number
  affected_road_segments: number
  cell_risks: CellRisk[]
  road_risks: RoadSegmentRisk[]
  isolations: VillageIsolation[]
  priorities: SettlementPriority[]
  areas: ForecastArea[]
}

export interface RiskForecast {
  location: string
  location_id: string
  generated_at: string
  source: ForecastSource
  forecast: RiskForecastDay[]
}

export type CitizenReportCategory = 'Slope crack' | 'Blocked road' | 'Rockfall or debris' | 'Water seepage' | 'Retaining wall damage' | 'Other'
export type CitizenReportStatus = 'submitted' | 'acknowledged' | 'in_review' | 'actioned' | 'dismissed'
export interface CitizenReportTrace {
  step_name: 'Ingestion' | 'Classification' | 'Dedup' | 'Hotspot' | 'Forecast' | 'Urgency' | 'Recommendation'
  step_order: number
  detail: string
  source: 'deterministic' | 'nvidia'
  created_at: string
}
export interface CitizenReportRecord {
  id: string
  aoi_id: string
  category: CitizenReportCategory
  citizen_selected_category: CitizenReportCategory
  description: string
  lat: number
  lon: number
  accuracy_m: number | null
  image_url: string
  image_mime_type: string
  image_width: number | null
  image_height: number | null
  image_size_bytes: number
  quality_score: number
  relevance_score: number
  severity: number
  classification_source: 'nvidia' | 'fallback'
  classification_reasoning: string
  duplicate_of: string | null
  hotspot_count: number
  forecast_next_7_days: number
  current_aoi_max_p_fail: number | null
  urgency_score: number
  recommendation: string
  status: CitizenReportStatus
  officer_id: string | null
  officer_notes: string
  created_at: string
  updated_at: string
  agent_traces: CitizenReportTrace[]
}

/** POST /api/whatif/simulate's response (backend/app/api/whatif.py::WhatIfResult) — a REAL
 * TickResult from a throwaway Pipeline run, never written to the live audit log or /ws/ticks. */
export interface WhatIfResult {
  request: WhatIfRequest
  assumptions: string[]
  cell_count: number
  tick: TickResult
  summary?: WhatIfSummary
  metadata?: WhatIfMetadata
}

export interface WhatIfSummary {
  total_cells: number
  critical_cells: number
  high_cells: number
  total_roads: number
  roads_at_risk: number
  severed_roads: number
  total_settlements: number
  isolated_settlements: number
  population_at_risk: number
}

export interface WhatIfMetadata {
  source: 'model'
  mode: 'simulation'
  spatial_resolution: string
  assumptions: string[]
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
