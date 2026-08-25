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

export interface VillageIsolation {
  village_id: string
  name: string
  population: number
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
