import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export interface CascadeAssetItem {
  asset_type: string
  asset_id: string
  asset_name: string
  blast_radius_hop: number
  cascade_probability: number
  primary_cascade_path: string[]
  primary_edge_types: string[]
  survival_window_hrs: number
  critical_human_exposure: number
}

export interface MultiplexGraphOverlayProps {
  aoiId: string
  triggerNodeId?: string
  assets?: CascadeAssetItem[]
}

export function MultiplexGraphOverlay({
  aoiId,
  triggerNodeId,
  assets: propAssets,
}: MultiplexGraphOverlayProps) {
  const resolvedTrigger = triggerNodeId ?? `FZ-${aoiId.toUpperCase()}-01`
  const [selectedHop, setSelectedHop] = useState<number | 'ALL'>('ALL')
  const [liveAssets, setLiveAssets] = useState<CascadeAssetItem[]>(propAssets ?? [])
  const [latencyMs, setLatencyMs] = useState<number | null>(null)

  useEffect(() => {
    if (propAssets && propAssets.length > 0) {
      setLiveAssets(propAssets)
      return
    }
    let cancelled = false
    api
      .getMultiplexCascade(resolvedTrigger, 3)
      .then((res) => {
        if (!cancelled) {
          setLiveAssets(res.impacted_assets)
          setLatencyMs(res.traversal_latency_ms)
        }
      })
      .catch(() => {
        // Fallback when backend is offline during static preview
      })
    return () => {
      cancelled = true
    }
  }, [aoiId, resolvedTrigger, propAssets])

  const visibleAssets = selectedHop === 'ALL'
    ? liveAssets
    : liveAssets.filter((item) => item.blast_radius_hop === selectedHop)

  return (
    <section className="multiplex-graph-overlay" aria-label="4-Layer Multiplex Cascade Blast Radius">
      <div className="commander-section-label">
        <div>
          <span className="eyebrow teal">NEO4J 4-LAYER MULTIPLEX GRAPH</span>
          <h2>
            Cascading Dependency Blast Radius ({resolvedTrigger} · {aoiId.toUpperCase()})
            {latencyMs !== null ? ` · ${latencyMs.toFixed(1)} ms` : ''}
          </h2>
        </div>
        <div className="hop-filter-group">
          {(['ALL', 1, 2, 3] as const).map((hop) => (
            <button
              key={String(hop)}
              type="button"
              className={`button secondary ${selectedHop === hop ? 'active' : ''}`}
              onClick={() => setSelectedHop(hop)}
            >
              {hop === 'ALL' ? 'All Hops (1–3)' : `Hop ${hop}`}
            </button>
          ))}
        </div>
      </div>
      <div className="commander-kpis">
        {visibleAssets.map((asset) => (
          <article key={asset.asset_id} className="multiplex-asset-card">
            <span className="kpi-icon">H{asset.blast_radius_hop}</span>
            <strong>{asset.asset_id}</strong>
            <span>{asset.asset_name} ({asset.asset_type})</span>
            <small>
              Path: {asset.primary_cascade_path.join(' → ')} · Survival: {asset.survival_window_hrs.toFixed(2)}h · Exposure: {asset.critical_human_exposure}
            </small>
          </article>
        ))}
      </div>
    </section>
  )
}
