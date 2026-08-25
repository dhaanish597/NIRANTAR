import { type GeoJSONSource, MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import { cellRisksToFeatureCollection } from '../lib/grid'
import { roadRisksToFeatureCollection } from '../lib/roads'
import { villagesToFeatureCollection } from '../lib/villages'
import { useTickStore } from '../store/useTickStore'

const SOURCE_ID = 'risk-cells'
const FILL_LAYER_ID = 'risk-cells-fill'
const OUTLINE_LAYER_ID = 'risk-cells-outline'

// BUILD_PLAN.md task 2.7: road layer coloured by p_blocked, villages as ranked pins. Both draw
// synthetic geometry (lib/roads.ts, lib/villages.ts) — see those files' docstrings for why: the
// current schemas (RoadSegmentRisk, SettlementPriority, VillageIsolation) carry no real
// geometry yet.
const ROAD_SOURCE_ID = 'road-risks'
const ROAD_LAYER_ID = 'road-risks-line'
const VILLAGE_SOURCE_ID = 'villages'
const VILLAGE_LAYER_ID = 'villages-circle'

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
  const roadRisks = useTickStore((s) => s.roadRisks)
  const priorities = useTickStore((s) => s.priorities)
  const isolations = useTickStore((s) => s.isolations)
  const selectVillage = useTickStore((s) => s.selectVillage)

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

      map.addSource(ROAD_SOURCE_ID, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: ROAD_LAYER_ID,
        type: 'line',
        source: ROAD_SOURCE_ID,
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['get', 'severed'], 5, 3],
          'line-dasharray': ['case', ['get', 'severed'], ['literal', [2, 1]], ['literal', [1, 0]]],
        },
      })

      map.addSource(VILLAGE_SOURCE_ID, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: VILLAGE_LAYER_ID,
        type: 'circle',
        source: VILLAGE_SOURCE_ID,
        paint: {
          'circle-radius': 7,
          'circle-color': ['get', 'color'],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#0b1220',
        },
      })

      // Task 2.8: clicking a village pin opens VillageDetailDrawer via the shared store action.
      map.on('click', VILLAGE_LAYER_ID, (event) => {
        const villageId = event.features?.[0]?.properties?.village_id
        if (typeof villageId === 'string') selectVillage(villageId)
      })
      map.on('mouseenter', VILLAGE_LAYER_ID, () => {
        map.getCanvas().style.cursor = 'pointer'
      })
      map.on('mouseleave', VILLAGE_LAYER_ID, () => {
        map.getCanvas().style.cursor = ''
      })
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
    // selectVillage is a stable Zustand action reference (same function identity for the
    // store's lifetime), so listing it here satisfies exhaustive-deps without ever re-running
    // this mount-only effect.
  }, [selectVillage])

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
      const cellSource = map.getSource(SOURCE_ID) as GeoJSONSource | undefined
      cellSource?.setData(cellRisksToFeatureCollection(cellRisks, aoi.center))
      const roadSource = map.getSource(ROAD_SOURCE_ID) as GeoJSONSource | undefined
      roadSource?.setData(roadRisksToFeatureCollection(roadRisks, aoi.center))
      const villageSource = map.getSource(VILLAGE_SOURCE_ID) as GeoJSONSource | undefined
      villageSource?.setData(villagesToFeatureCollection(priorities, isolations, aoi.center))
    }
    if (map.isStyleLoaded()) applyData()
    else map.once('load', applyData)
  }, [cellRisks, roadRisks, priorities, isolations, aoi])

  return <div ref={containerRef} className="h-full w-full" />
}
