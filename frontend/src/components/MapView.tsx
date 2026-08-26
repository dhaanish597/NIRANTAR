import type { Geometry } from 'geojson'
import { addProtocol, type GeoJSONSource, MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { PMTiles, Protocol } from 'pmtiles'
import { useEffect, useRef } from 'react'
import { cellRisksToFeatureCollection } from '../lib/grid'
import { loadOfflineTileSource } from '../lib/offlineTiles'
import { roadRisksToFeatureCollection } from '../lib/roads'
import { villagesToFeatureCollection } from '../lib/villages'
import { useTickStore } from '../store/useTickStore'

const SOURCE_ID = 'risk-cells'
const FILL_LAYER_ID = 'risk-cells-fill'
const OUTLINE_LAYER_ID = 'risk-cells-outline'

// BUILD_PLAN.md task 3.10 (Village View): "an offline map with the route drawn". Rather than
// build a second map implementation, this is an OPTIONAL extra layer on the SAME self-contained
// MapView instance every other screen already uses (CLAUDE.md rule 10 — no external tile
// requests, unchanged). Only rendered when a caller passes real route geometry
// (decision/routing.py's `EvacuationRoute.geometry`, via `ActionCard.route.geometry`).
const ROUTE_SOURCE_ID = 'evac-route'
const ROUTE_LAYER_ID = 'evac-route-line'

// BUILD_PLAN.md task 2.7: road layer coloured by p_blocked, villages as ranked pins. Both draw
// synthetic geometry (lib/roads.ts, lib/villages.ts) — see those files' docstrings for why: the
// current schemas (RoadSegmentRisk, SettlementPriority, VillageIsolation) carry no real
// geometry yet.
const ROAD_SOURCE_ID = 'road-risks'
const ROAD_LAYER_ID = 'road-risks-line'
const VILLAGE_SOURCE_ID = 'villages'
const VILLAGE_LAYER_ID = 'villages-circle'

// BUILD_PLAN.md task 5.2: a real offline PMTiles reference layer (the AOI's terrain-grid
// boundaries + real OSM road edges, scripts/build_tiles.py) rendered UNDERNEATH the live per-tick
// GeoJSON layers above — geographic context that's present even before any tick has arrived, and
// (once cached, frontend/src/lib/offlineTiles.ts) still there with the network disabled. This is
// still zero external tile requests: the archive is fetched from THIS origin's own `/tiles/`
// path (vite.config.ts's offlineTilesPlugin), never a remote tile host — MapView's Phase-0
// no-basemap-imagery choice (CLAUDE.md rule 10) is unchanged, this is a vector reference layer,
// not a photographic basemap.
const OFFLINE_SOURCE_ID = 'offline-tiles'
const OFFLINE_CELLS_LAYER_ID = 'offline-cells-outline'
const OFFLINE_ROADS_LAYER_ID = 'offline-roads-line'

// The PMTiles<->MapLibre protocol glue is process-global by design (maplibre-gl's `addProtocol`
// is a module-level registration, not per-Map) — registered once here, shared by every <MapView>
// instance (the Ops screen and Village View's route map both render one), rather than fighting
// over a single global registration from inside the component effect.
const offlinePmtilesProtocol = new Protocol()
let offlinePmtilesProtocolRegistered = false

function ensureOfflinePmtilesProtocolRegistered(): void {
  if (offlinePmtilesProtocolRegistered) return
  addProtocol('pmtiles', offlinePmtilesProtocol.tile)
  offlinePmtilesProtocolRegistered = true
}

// Only Aizawl has a real built archive today (data/static/aizawl/*, data/osm/aizawl_graph.geojson
// — the only AOI with Phase-1/2 static data at all, same scope every other AOI-specific frontend
// piece in this codebase already documents, e.g. lib/priorityDetail.ts). Keyed off the loaded
// AOI id below (falls back to this constant before the real AOI has loaded, matching
// FALLBACK_CENTER's own pattern), not hardcoded blindly — an AOI with no archive simply fails the
// fetch and the reference layer is skipped (see `addOfflineReferenceLayer`'s catch below), it
// does not render another AOI's tiles under the wrong map.
const DEFAULT_TILES_AOI_ID = 'aizawl'

async function addOfflineReferenceLayer(
  map: MapLibreMap,
  aoiId: string,
  isCancelled: () => boolean,
): Promise<void> {
  // Wrapped as one big try/catch, not several small ones: this whole function is a best-effort
  // enhancement layered on top of the always-real live risk map (task 5.2's own scope — "no
  // basemap") — any failure in it (a missing archive, a test/environment maplibre-gl mock
  // lacking `addProtocol`, the map having been torn down mid-await, ...) must degrade to "no
  // reference layer this session", never crash or surface an unhandled rejection.
  try {
    ensureOfflinePmtilesProtocolRegistered()
    const source = await loadOfflineTileSource(aoiId)
    if (isCancelled()) return

    offlinePmtilesProtocol.add(new PMTiles(source))
    const sourceUrl = `pmtiles://${source.getKey()}`

    if (map.getSource(OFFLINE_SOURCE_ID)) return // already added (e.g. React StrictMode re-run)
    map.addSource(OFFLINE_SOURCE_ID, { type: 'vector', url: sourceUrl })
    map.addLayer(
      {
        id: OFFLINE_CELLS_LAYER_ID,
        type: 'line',
        source: OFFLINE_SOURCE_ID,
        'source-layer': 'cells',
        paint: { 'line-color': '#334155', 'line-width': 0.5, 'line-opacity': 0.6 },
      },
      FILL_LAYER_ID, // insert BELOW the live risk-cell fill layer, not on top of it
    )
    map.addLayer(
      {
        id: OFFLINE_ROADS_LAYER_ID,
        type: 'line',
        source: OFFLINE_SOURCE_ID,
        'source-layer': 'roads',
        paint: { 'line-color': '#475569', 'line-width': 1, 'line-opacity': 0.7 },
      },
      FILL_LAYER_ID,
    )
  } catch (err) {
    // No archive built for this AOI yet, a fetch failure with nothing cached to fall back on, the
    // map having been torn down mid-await, or (in tests) a maplibre-gl mock missing `addProtocol`
    // — the map still renders correctly without this reference layer either way.
    console.warn(`offline reference tile layer unavailable for AOI ${aoiId}`, err)
  }
}

// Fallback center matches the "aizawl" AOI's real center (api/routes.py's _STUB_AOIS) exactly —
// Phase 0 only ever runs one AOI, so this coincidence is intentional, not fragile. If AOI
// selection becomes dynamic in a later phase, this component needs a proper "center on first
// AOI load" path instead of relying on the fallback matching.
const FALLBACK_CENTER: [number, number] = [92.7173, 23.7307]

export function MapView({ routeGeometry = null }: { routeGeometry?: Geometry | null } = {}) {
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
    let cancelled = false

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

      map.addSource(ROUTE_SOURCE_ID, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.addLayer({
        id: ROUTE_LAYER_ID,
        type: 'line',
        source: ROUTE_SOURCE_ID,
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#38bdf8', 'line-width': 4, 'line-dasharray': [0.2, 1.5] },
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

      void addOfflineReferenceLayer(map, DEFAULT_TILES_AOI_ID, () => cancelled)
    })

    return () => {
      cancelled = true
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

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const applyRoute = () => {
      const routeSource = map.getSource(ROUTE_SOURCE_ID) as GeoJSONSource | undefined
      routeSource?.setData({
        type: 'FeatureCollection',
        features: routeGeometry ? [{ type: 'Feature', geometry: routeGeometry, properties: {} }] : [],
      })
    }
    if (map.isStyleLoaded()) applyRoute()
    else map.once('load', applyRoute)
  }, [routeGeometry])

  return <div ref={containerRef} className="h-full w-full" />
}
