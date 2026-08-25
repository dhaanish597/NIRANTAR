import { type GeoJSONSource, MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import { cellRisksToFeatureCollection } from '../lib/grid'
import { useTickStore } from '../store/useTickStore'

const SOURCE_ID = 'risk-cells'
const FILL_LAYER_ID = 'risk-cells-fill'
const OUTLINE_LAYER_ID = 'risk-cells-outline'

// Fallback center matches the "aizawl" AOI's real center (api/routes.py's _STUB_AOIS) exactly —
// Phase 0 only ever runs one AOI, so this coincidence is intentional, not fragile. If AOI
// selection becomes dynamic in a later phase, this component needs a proper "center on first
// AOI load" path instead of relying on the fallback matching.
const FALLBACK_CENTER: [number, number] = [92.7173, 23.7307]

export function MapView() {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const hasCenteredOnAoiRef = useRef(false)
  const aoi = useTickStore((s) => s.aoi)
  const cellRisks = useTickStore((s) => s.cellRisks)

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      // Phase 0: no external tile requests. CLAUDE.md rule 10 ("the demo must run with the
      // network cable unplugged") applies from day one here, not just once Phase 5's PMTiles
      // offline basemap lands (BUILD_PLAN.md task 5.2) — this style is entirely self-contained.
      style: {
        version: 8,
        sources: {},
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#0b1220' } },
        ],
      },
      center: FALLBACK_CENTER,
      zoom: 13,
    })
    mapRef.current = map

    map.on('load', () => {
      map.addSource(SOURCE_ID, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: FILL_LAYER_ID,
        type: 'fill',
        source: SOURCE_ID,
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.75 },
      })
      map.addLayer({
        id: OUTLINE_LAYER_ID,
        type: 'line',
        source: SOURCE_ID,
        paint: { 'line-color': '#0b1220', 'line-width': 1 },
      })
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Re-center once, the first time the real AOI loads (in case it ever differs from the
  // fallback) — but never again, so this doesn't fight the user's pan/zoom on every tick.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !aoi || hasCenteredOnAoiRef.current) return
    map.setCenter([aoi.center.lon, aoi.center.lat])
    hasCenteredOnAoiRef.current = true
  }, [aoi])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !aoi) return
    const applyData = () => {
      const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined
      source?.setData(cellRisksToFeatureCollection(cellRisks, aoi.center))
    }
    if (map.isStyleLoaded()) applyData()
    else map.once('load', applyData)
  }, [cellRisks, aoi])

  return <div ref={containerRef} className="h-full w-full" />
}
