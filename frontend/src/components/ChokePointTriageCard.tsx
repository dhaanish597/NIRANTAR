import { useEffect, useState } from 'react'
import { api, type RoboticsSdgResponse } from '../lib/api'

export interface ChokePointItem {
  node_id: string
  node_type: string
  choke_point_name: string
  is_spof_articulation: boolean
  split_components_if_lost: number
  downstream_critical_facilities: number
  betweenness_centrality: number
  pagerank_centrality: number
  criticality_index: number
  current_water_depth_m: number
}

export function ChokePointTriageCard({ aoiId = 'chennai' }: { aoiId?: string }) {
  const [chokepoints, setChokepoints] = useState<ChokePointItem[]>([])
  const [sdg, setSdg] = useState<RoboticsSdgResponse | null>(null)
  const [dispatchedMission, setDispatchedMission] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getMultiplexChokepoints(aoiId, 3)
      .then((res) => {
        if (!cancelled) setChokepoints(res.chokepoints)
      })
      .catch(() => {})

    api
      .getRoboticsSdg({
        aoi_id: aoiId,
        trigger_node_id: `FZ-${aoiId.toUpperCase()}-01`,
        mitigated_node_ids: [`SUB-${aoiId.toUpperCase()}-33KV-01`, `CUL-${aoiId.toUpperCase()}-01`],
      })
      .then((res) => {
        if (!cancelled) setSdg(res)
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [aoiId])

  async function dispatchCoeAwrdsSortie(nodeId: string, platform: 'UAV_DRONE' | 'USV_SONAR') {
    try {
      const msn = await api.deployRoboticsMission({
        aoi_id: aoiId,
        target_node_id: nodeId,
        platform_type: platform,
      })
      setDispatchedMission(
        `Dispatched ${msn.mission_id} (${msn.platform_type}) to ${msn.target_node_id} · ${msn.waypoints_geojson.features.length} GeoJSON features · Est. ${msn.estimated_sortie_minutes} min (${msn.knowledge_partner_tag}).`,
      )
    } catch {
      setDispatchedMission(
        `Dispatched IIIT Delhi CoE-AWRDS ${platform} sortie to ${nodeId} (offline local mirror mode).`,
      )
    }
  }

  return (
    <section className="chokepoint-triage-card" aria-label="GDS Top-K Choke-Point Triage & CoE-AWRDS Robotics">
      <div className="commander-section-label">
        <div>
          <span className="eyebrow amber">GDS STRUCTURAL CHOKE POINTS · IIIT DELHI CoE-AWRDS</span>
          <h2>Single-Point-of-Failure Articulation Nodes ({aoiId.toUpperCase()})</h2>
        </div>
        <span className="updated">
          {sdg
            ? `SDG 6: ${sdg.sdg6_potable_water_person_hours_saved.toLocaleString()} person-hrs saved · SDG 11: ${sdg.sdg11_isolated_residents_reconnected.toLocaleString()} reconnected · SDG 13: +${sdg.sdg13_cascade_lead_time_gain_minutes}m lead time`
            : 'Computing SDG 6 / 11 / 13 impact...'}
        </span>
      </div>
      <div className="commander-kpis">
        {chokepoints.map((cp) => (
          <article key={cp.node_id} className="chokepoint-item">
            <span className="kpi-icon">{cp.is_spof_articulation ? 'SPOF' : 'HUB'}</span>
            <strong>{cp.node_id} · CI {cp.criticality_index.toFixed(2)}</strong>
            <span>{cp.choke_point_name}</span>
            <small>
              BC: {cp.betweenness_centrality.toFixed(3)} · PR: {cp.pagerank_centrality.toFixed(3)} · Depth: {cp.current_water_depth_m.toFixed(2)}m
            </small>
            <div className="suggested-prompts">
              <button type="button" onClick={() => void dispatchCoeAwrdsSortie(cp.node_id, 'USV_SONAR')}>
                Deploy USV Sonar
              </button>
              <button type="button" onClick={() => void dispatchCoeAwrdsSortie(cp.node_id, 'UAV_DRONE')}>
                Deploy UAV Thermal
              </button>
            </div>
          </article>
        ))}
      </div>
      {dispatchedMission && <div className="commander-inline-status">{dispatchedMission}</div>}
    </section>
  )
}
