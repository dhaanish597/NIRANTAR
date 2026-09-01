/** Compact operational legend: a continuous risk gradient (matching MapView's heatmap ramp)
 * rather than four disconnected swatches, plus the road-status key. Spec §12. */
export function MapLegend({ showRisk, showRoads }: { showRisk: boolean; showRoads: boolean }) {
  return (
    <div className="map-legend">
      <div className="map-legend-title">Map key <span>current view</span></div>
      {showRisk && (
        <div className="legend-section">
          <strong>Landslide risk (model / scenario)</strong>
          <div className="legend-gradient" aria-hidden="true" />
          <div className="legend-gradient-labels"><span>Low</span><span>Moderate</span><span>High</span><span>Critical</span></div>
        </div>
      )}
      {showRoads && (
        <div className="legend-section">
          <strong>Roads</strong>
          <span><i className="legend-line normal" />Open</span>
          <span><i className="legend-line hazard" />High blockage risk</span>
          <span><i className="legend-line blocked" />Severed</span>
        </div>
      )}
      <p className="legend-note">Risk is model/scenario probability, not certainty.</p>
    </div>
  )
}
