import type { Feature, FeatureCollection, Geometry, Point, Polygon, MultiPolygon } from 'geojson'
import { addProtocol, type GeoJSONSource, MapLibreMap, Popup } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { PMTiles, Protocol } from 'pmtiles'
import { useEffect, useRef, useState } from 'react'
import { colorForPFail, escalationStage } from '../lib/escalation'
import { loadAoiExposure } from '../lib/exposure'
import { loadOfflineTileSource } from '../lib/offlineTiles'
import { villagesToFeatureCollection } from '../lib/villages'
import { useTickStore } from '../store/useTickStore'
import type { CellRisk, RoadSegmentRisk, VillageExposure } from '../types/schemas'
import { MapControls, type MapLayerKey, type MapLayerState } from './MapControls'
import { MapLegend } from './MapLegend'
import './map-workspace.css'

const CENTER: [number, number] = [92.7173, 23.7307]
// Matches AOIS['aizawl'].bbox in backend/app/config.py — the fallback when the AOI payload
// (which carries the real per-AOI bbox) has not loaded yet.
const AIZAWL_BBOX: [number, number, number, number] = [92.6, 23.6, 92.85, 23.85]
const HOTSPOT_COUNT = 6
const HOTSPOT_MIN_P_FAIL = 0.5
const protocol = new Protocol()
let protocolReady = false
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }

function ensurePmtilesProtocol(): void {
  if (protocolReady) return
  addProtocol('pmtiles', protocol.tile)
  protocolReady = true
}

type LngLatBounds = [[number, number], [number, number]]

function aoiBounds(bbox: [number, number, number, number] | undefined): LngLatBounds {
  const [minLon, minLat, maxLon, maxLat] = bbox ?? AIZAWL_BBOX
  return [[minLon, minLat], [maxLon, maxLat]]
}

/** Keep the AOI *covering* the viewport (fill, not letterbox) and lock panning to it, so a
 * stray scroll or drag can never leave the offline hillshade stranded in the background void.
 * Every call is guarded — the jsdom MapLibre mock only implements a handful of methods, same
 * tradeoff the layer-visibility effect below already lives with. */
function frameToAoi(map: MapLibreMap, bounds: LngLatBounds, container: HTMLElement | null, force = false): void {
  if (typeof map.setMaxBounds === 'function') map.setMaxBounds(bounds)
  if (typeof map.fitBounds !== 'function' || typeof map.getZoom !== 'function') return
  map.fitBounds(bounds, { padding: 0, animate: false })
  const fitZoom = map.getZoom()
  const w = container?.clientWidth ?? 0
  const h = container?.clientHeight ?? 0
  // fitBounds fits the *tighter* axis; nudging in by the aspect ratio makes the (near-square)
  // AOI fill the wider axis instead, so background never shows on the long edge.
  const coverZoom = w > 0 && h > 0 ? fitZoom + Math.log2(Math.max(w / h, h / w)) : fitZoom
  if (typeof map.setMinZoom === 'function') map.setMinZoom(coverZoom - 0.15)
  if (typeof map.setZoom === 'function' && (force || map.getZoom() < coverZoom)) {
    map.setZoom(coverZoom)
  }
}

/** Rough centroid (mean of exterior-ring vertices) — good enough for a near-square 500 m cell;
 * not a claim of the true polygon centroid for an irregular shape. */
function polygonCentroid(geometry: Polygon | MultiPolygon): [number, number] | null {
  const ring = geometry.type === 'Polygon' ? geometry.coordinates[0] : geometry.coordinates[0]?.[0]
  if (!ring || ring.length === 0) return null
  let sumLon = 0
  let sumLat = 0
  for (const [lon, lat] of ring) {
    sumLon += lon
    sumLat += lat
  }
  return [sumLon / ring.length, sumLat / ring.length]
}

/** Real-geometry risk surface: joins live `CellRisk`/`RoadSegmentRisk` scores onto the already-
 * tiled real cell/road geometry (data/tiles/<aoi>.pmtiles, scripts/build_tiles.py) via MapLibre
 * `feature-state`, keyed by the SAME `cell_id`/`edge_id` the PMTiles vector layers carry as
 * properties (source `promoteId`, set where `offline-tiles` is added). This is what replaced the
 * fabricated squares/lines: no geometry is invented here, only score+colour is attached to a real
 * polygon/line already on the map. A cell/road with no live score this tick keeps
 * `hasData: false` and renders as bare reference geometry, not a fabricated "zero risk".
 *
 * Returns the sets of ids just written, so the caller can clear ids that drop out on a later
 * tick (`removeFeatureState`) instead of leaving stale colour on a cell no longer reported. */
function applyRiskFeatureState(
  map: MapLibreMap,
  cellRisks: CellRisk[],
  roadRisks: RoadSegmentRisk[],
  previous: { cells: Set<string>; roads: Set<string> },
): { cells: Set<string>; roads: Set<string> } {
  const nextCells = new Set<string>()
  const nextRoads = new Set<string>()
  if (typeof map.setFeatureState !== 'function') return { cells: nextCells, roads: nextRoads }

  for (const risk of cellRisks) {
    map.setFeatureState(
      { source: 'offline-tiles', sourceLayer: 'cells', id: risk.cell_id },
      { hasData: true, p_fail: risk.p_fail, color: colorForPFail(risk.p_fail), stage: escalationStage(risk.p_fail) },
    )
    nextCells.add(risk.cell_id)
  }
  for (const road of roadRisks) {
    map.setFeatureState(
      { source: 'offline-tiles', sourceLayer: 'roads', id: road.edge_id },
      { hasData: true, p_blocked: road.p_blocked, severed: road.severed, color: colorForPFail(road.p_blocked) },
    )
    nextRoads.add(road.edge_id)
  }
  if (typeof map.removeFeatureState === 'function') {
    for (const id of previous.cells) if (!nextCells.has(id)) map.removeFeatureState({ source: 'offline-tiles', sourceLayer: 'cells', id })
    for (const id of previous.roads) if (!nextRoads.has(id)) map.removeFeatureState({ source: 'offline-tiles', sourceLayer: 'roads', id })
  }
  return { cells: nextCells, roads: nextRoads }
}

export interface HotspotFeatureProperties {
  cell_id: string
  p_fail: number
  stage: string
  color: string
  driver: string
}

/** Top-N REAL cells above the hotspot threshold, positioned at their real polygon's centroid
 * (queried from the already-loaded PMTiles source, not invented) — changes with whatever
 * scenario/tick is live, never a fixed set. A cell whose tile has not rendered yet at the
 * current view is simply skipped this tick (self-heals once its tile loads), not fabricated a
 * position. */
function computeHotspots(map: MapLibreMap, cellRisks: CellRisk[]): FeatureCollection<Point, HotspotFeatureProperties> {
  if (typeof map.querySourceFeatures !== 'function') return { type: 'FeatureCollection', features: [] }
  const ranked = cellRisks
    .filter((c) => c.p_fail >= HOTSPOT_MIN_P_FAIL)
    .sort((a, b) => b.p_fail - a.p_fail)
    .slice(0, HOTSPOT_COUNT)

  const features: Feature<Point, HotspotFeatureProperties>[] = []
  for (const cell of ranked) {
    const rendered = map.querySourceFeatures('offline-tiles', {
      sourceLayer: 'cells',
      filter: ['==', ['get', 'cell_id'], cell.cell_id],
    })
    const centroid = rendered[0]?.geometry ? polygonCentroid(rendered[0].geometry as Polygon | MultiPolygon) : null
    if (!centroid) continue
    const driver = cell.attributions[0]?.plain_language ?? 'elevated model signal'
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: centroid },
      properties: { cell_id: cell.cell_id, p_fail: cell.p_fail, stage: escalationStage(cell.p_fail), color: colorForPFail(cell.p_fail), driver },
    })
  }
  return { type: 'FeatureCollection', features }
}

function cellPopupHtml(cell: CellRisk): string {
  const drivers = cell.attributions
    .slice(0, 3)
    .map((a) => `<li>${a.plain_language}</li>`)
    .join('')
  return `
    <div class="map-popup">
      <strong>${escalationStage(cell.p_fail)} · ${Math.round(cell.p_fail * 100)}%</strong>
      <p>Failure probability · confidence ${Math.round(cell.confidence * 100)}%</p>
      ${drivers ? `<p class="map-popup-label">Why</p><ul>${drivers}</ul>` : '<p class="map-popup-label">No attribution reported for this cell.</p>'}
      <p class="map-popup-meta">${cell.cell_id} · ${cell.model_version}</p>
    </div>
  `
}

export function MapView({ routeGeometry = null, layers, onLayerChange }: { routeGeometry?: Geometry | null; layers?: MapLayerState; onLayerChange?: (key: MapLayerKey, enabled: boolean) => void } = {}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const featureStateRef = useRef<{ cells: Set<string>; roads: Set<string> }>({ cells: new Set(), roads: new Set() })
  const exposureRef = useRef<Map<string, VillageExposure>>(new Map())
  const [mapError, setMapError] = useState<string | null>(null)
  const [localLayers, setLocalLayers] = useState<MapLayerState>({ risk: true, rainfall: false, villages: true, shelters: false, roads: true, route: Boolean(routeGeometry) })
  const activeLayers = layers ?? localLayers
  const aoi = useTickStore((state) => state.aoi)
  const cellRisks = useTickStore((state) => state.cellRisks)
  const roadRisks = useTickStore((state) => state.roadRisks)
  const priorities = useTickStore((state) => state.priorities)
  const isolations = useTickStore((state) => state.isolations)
  const selectVillage = useTickStore((state) => state.selectVillage)
  const changeLayer = (key: MapLayerKey, enabled: boolean) => {
    setLocalLayers((current) => ({ ...current, [key]: enabled }))
    onLayerChange?.(key, enabled)
  }

  // Real village/shelter points (GET /api/aoi/{id}/exposure) — fetched once per AOI, joined onto
  // the live priority/isolation stream by lib/villages.ts. Kept in a ref (not state) because it
  // feeds an imperative MapLibre update, not JSX.
  useEffect(() => {
    let active = true
    const aoiId = aoi?.id ?? 'aizawl'
    void loadAoiExposure(aoiId).then((exposure) => {
      if (!active) return
      exposureRef.current = new Map(exposure.villages.map((v) => [v.village_id, v]))
      const map = mapRef.current
      const source = map?.getSource('villages') as GeoJSONSource | undefined
      if (source && aoi) source.setData(villagesToFeatureCollection(priorities, isolations, aoi.center, exposureRef.current))
    }).catch(() => { /* graceful: lib/villages.ts's hash-ring fallback keeps pins on the map */ })
    return () => { active = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-fetch when the AOI changes
  }, [aoi?.id])

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    ensurePmtilesProtocol()
    let cancelled = false
    let terrainObjectUrl: string | null = null
    const bounds = aoiBounds(aoi?.bbox)
    const map = new MapLibreMap({
      container: containerRef.current,
      center: aoi ? [aoi.center.lon, aoi.center.lat] : CENTER,
      bounds,
      fitBoundsOptions: { padding: 0 },
      minZoom: 9,
      maxZoom: 17,
      maxBounds: bounds,
      attributionControl: false,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#0c1c26' } }],
      },
    })
    mapRef.current = map
    const container = containerRef.current
    let userInteracted = false
    const markInteracted = (event: { originalEvent?: unknown }) => { if (event?.originalEvent) userInteracted = true }
    map.on('dragstart', markInteracted)
    map.on('zoomstart', markInteracted)
    const resizeObserver = new ResizeObserver(() => {
      map.resize()
      // Re-cover the AOI after a layout change (e.g. fullscreen) — but only until the user has
      // panned/zoomed themselves, so we never yank the view back from where they left it.
      if (!userInteracted) frameToAoi(map, bounds, container)
    })
    resizeObserver.observe(containerRef.current)
    map.on('error', (event) => {
      const message = event.error?.message ?? 'Unknown MapLibre error'
      setMapError(`Map error: ${message}`)
    })

    let popup: Popup | null = null
    let pulsePhase = 0
    let pulseTimer: ReturnType<typeof setInterval> | undefined

    // The four layers below read the `offline-tiles` vector source (real cell/road geometry) —
    // they can only be added once that source exists, and it loads asynchronously (fetch or
    // IndexedDB, see lib/offlineTiles.ts). Defined here, called from inside that source's own
    // `.then()` below, not from the synchronous `load` handler — addLayer against a source that
    // doesn't exist yet throws in real MapLibre (the jsdom mock doesn't catch this class of bug).
    const addRiskSurfaceLayers = () => {
      // Every insertion targets the same, always-already-present `beforeId` (villages-circle,
      // added synchronously below) — inserting a run of layers against one fixed beforeId stacks
      // them in call order, so this reads top-to-bottom as bottom-to-top z-order: reference grid,
      // then the risk fill, then the base road line, then the risk-coloured road overlay, all
      // sitting below the village/hotspot/route layers regardless of which async source (this
      // one, or the hillshade below) happens to resolve first.
      map.addLayer(
        { id: 'cells-reference', type: 'line', source: 'offline-tiles', 'source-layer': 'cells', paint: { 'line-color': '#3d564e', 'line-width': 0.35, 'line-opacity': 0.3 } },
        'villages-circle',
      )
      map.addLayer(
        {
          id: 'risk-cells-fill',
          type: 'fill',
          source: 'offline-tiles',
          'source-layer': 'cells',
          paint: {
            'fill-color': ['case', ['boolean', ['feature-state', 'hasData'], false], ['feature-state', 'color'], 'transparent'],
            'fill-opacity': ['case', ['boolean', ['feature-state', 'hasData'], false], ['interpolate', ['linear'], ['coalesce', ['feature-state', 'p_fail'], 0], 0, 0.14, 0.5, 0.4, 1, 0.72], 0],
          },
        },
        'villages-circle',
      )
      map.addLayer(
        {
          id: 'roads-base',
          type: 'line',
          source: 'offline-tiles',
          'source-layer': 'roads',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': ['step', ['zoom'], '#3f5750', 12, '#33473f', 15, '#26362f'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 12, 1.6, 16, 3.4],
            'line-opacity': 1,
          },
        },
        'villages-circle',
      )
      map.addLayer(
        {
          id: 'road-risks-line',
          type: 'line',
          source: 'offline-tiles',
          'source-layer': 'roads',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': ['coalesce', ['feature-state', 'color'], 'transparent'],
            'line-width': ['case', ['boolean', ['feature-state', 'severed'], false], 4, 2.6],
            'line-opacity': ['case', ['boolean', ['feature-state', 'hasData'], false], 0.95, 0],
            'line-dasharray': ['case', ['boolean', ['feature-state', 'severed'], false], ['literal', [2, 1.4]], ['literal', [1, 0]]],
          },
        },
        'villages-circle',
      )
      for (const layerId of ['risk-cells-fill']) {
        map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
      }
      map.on('click', 'risk-cells-fill', openCellPopup)
    }

    let openCellPopup = (_event: { lngLat: { lng: number; lat: number }; features?: Array<{ properties?: Record<string, unknown> }> }) => {}

    map.on('load', () => {
      // ---- villages: real points from exposure, joined with live priority/isolation ----
      map.addSource('villages', { type: 'geojson', data: empty, cluster: true, clusterMaxZoom: 11, clusterRadius: 42 })
      map.addLayer({ id: 'villages-circle', type: 'circle', source: 'villages', filter: ['!', ['has', 'point_count']], paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 13, 7, 16, 10], 'circle-color': ['get', 'color'], 'circle-stroke-width': 2, 'circle-stroke-color': '#f5fbf7' } })
      map.addLayer({ id: 'villages-selected-ring', type: 'circle', source: 'villages', filter: ['==', ['get', 'village_id'], ''], paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 8, 13, 12, 16, 16], 'circle-color': 'transparent', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#39c8c0' } })
      map.addLayer({ id: 'villages-label', type: 'symbol', source: 'villages', filter: ['!', ['has', 'point_count']], layout: { 'text-field': ['coalesce', ['get', 'name'], ['get', 'village_id']], 'text-size': 11, 'text-offset': [0, 1.4], 'text-anchor': 'top' }, paint: { 'text-color': '#15353b', 'text-halo-color': '#f2f8f2', 'text-halo-width': 1.2 } })
      map.addLayer({ id: 'villages-cluster', type: 'circle', source: 'villages', filter: ['has', 'point_count'], paint: { 'circle-color': '#126e70', 'circle-radius': 15, 'circle-stroke-width': 2, 'circle-stroke-color': '#f5fbf7' } })
      map.addLayer({ id: 'villages-cluster-count', type: 'symbol', source: 'villages', filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11 }, paint: { 'text-color': '#ffffff' } })

      // ---- hotspots: top-N real cells above threshold, restrained pulse (Phase 5) ----
      map.addSource('hotspots', { type: 'geojson', data: empty })
      map.addLayer({ id: 'hotspots-halo', type: 'circle', source: 'hotspots', paint: { 'circle-radius': 14, 'circle-color': ['get', 'color'], 'circle-opacity': 0.22, 'circle-blur': 0.6 } })
      map.addLayer({ id: 'hotspots-core', type: 'circle', source: 'hotspots', paint: { 'circle-radius': 5, 'circle-color': ['get', 'color'], 'circle-stroke-width': 1.5, 'circle-stroke-color': '#0c1c26' } })

      map.addSource('evac-route', { type: 'geojson', data: empty })
      map.addLayer({ id: 'evac-route-line', type: 'line', source: 'evac-route', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#087f9c', 'line-width': 5, 'line-opacity': 0.9 } })

      map.on('click', 'villages-circle', (event) => { const id = event.features?.[0]?.properties?.village_id; if (typeof id === 'string') selectVillage(id) })
      for (const layerId of ['villages-circle', 'hotspots-core']) {
        map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
      }
      openCellPopup = (event) => {
        const cellId = event.features?.[0]?.properties?.cell_id
        if (typeof cellId !== 'string') return
        const cell = cellRisksRef.current.find((c) => c.cell_id === cellId)
        if (!cell || typeof Popup !== 'function') return
        popup?.remove()
        popup = new Popup({ closeButton: true, closeOnClick: true, maxWidth: '260px' }).setLngLat(event.lngLat).setHTML(cellPopupHtml(cell)).addTo(map)
      }
      map.on('click', 'hotspots-core', openCellPopup)

      // A restrained pulse on the hotspot halo — a slow radius/opacity breathe, not a neon flash.
      if (typeof map.setPaintProperty === 'function') {
        pulseTimer = setInterval(() => {
          pulsePhase = (pulsePhase + 1) % 60
          const t = Math.sin((pulsePhase / 60) * Math.PI * 2)
          map.setPaintProperty('hotspots-halo', 'circle-radius', 14 + t * 4)
          map.setPaintProperty('hotspots-halo', 'circle-opacity', 0.22 + t * 0.1)
        }, 140)
      }

      const aoiId = aoi?.id ?? 'aizawl'
      const bbox = aoi?.bbox ?? AIZAWL_BBOX
      void fetch(`/terrain/${aoiId}-hillshade.png`)
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`)
          return response.blob()
        })
        .then((blob) => {
          if (cancelled) return
          terrainObjectUrl = URL.createObjectURL(blob)
          const [minLon, minLat, maxLon, maxLat] = bbox
          map.addSource('offline-terrain', {
            type: 'image',
            url: terrainObjectUrl,
            coordinates: [[minLon, maxLat], [maxLon, maxLat], [maxLon, minLat], [minLon, minLat]],
          })
          // Below cells-reference if the risk-surface layers already exist (tiles resolved
          // first), otherwise below villages (a safe anchor that's always present by `load` —
          // addRiskSurfaceLayers, whenever it runs, inserts itself before villages too, which
          // pushes it back above terrain either way — see that function's own comment).
          const beforeId = map.getLayer('cells-reference') ? 'cells-reference' : 'villages-circle'
          map.addLayer({ id: 'offline-terrain', type: 'raster', source: 'offline-terrain', paint: { 'raster-opacity': 1, 'raster-contrast': 0.22, 'raster-brightness-min': 0.06, 'raster-brightness-max': 0.94 } }, beforeId)
        })
        .catch(() => setMapError('Offline terrain unavailable. Run make tiles before the demo.'))

      void loadOfflineTileSource(aoiId)
        .then((source) => {
          if (cancelled || map.getSource('offline-tiles')) return
          protocol.add(new PMTiles(source))
          map.addSource('offline-tiles', {
            type: 'vector',
            url: `pmtiles://${source.getKey()}`,
            // Promotes the real cell_id/edge_id property to the MapLibre feature id, so
            // setFeatureState/removeFeatureState (applyRiskFeatureState above) can address a
            // specific real polygon/line by the exact id the tick stream reports risk for.
            promoteId: { cells: 'cell_id', roads: 'edge_id' },
          })
          addRiskSurfaceLayers()
          featureStateRef.current = applyRiskFeatureState(map, cellRisksRef.current, roadRisksRef.current, featureStateRef.current)
          if (map.getSource('hotspots')) (map.getSource('hotspots') as GeoJSONSource).setData(computeHotspots(map, cellRisksRef.current))
        })
        .catch(() => setMapError('Offline road/cell reference archive unavailable. Run make tiles before the demo.'))

      frameToAoi(map, bounds, container)
    })
    return () => {
      cancelled = true
      if (pulseTimer) clearInterval(pulseTimer)
      popup?.remove()
      if (terrainObjectUrl) URL.revokeObjectURL(terrainObjectUrl)
      resizeObserver.disconnect()
      map.remove()
      mapRef.current = null
      featureStateRef.current = { cells: new Set(), roads: new Set() }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cellRisksRef/roadRisksRef below carry live data into this create-once effect
  }, [aoi, selectVillage])

  // Live tick data is read through refs inside the map-creation effect (offline-tiles loads
  // asynchronously, after the effect body has already returned) — kept in sync here so that
  // async continuation always sees the latest tick, not a stale closure over the first one.
  const cellRisksRef = useRef<CellRisk[]>(cellRisks)
  const roadRisksRef = useRef<RoadSegmentRisk[]>(roadRisks)
  useEffect(() => { cellRisksRef.current = cellRisks; roadRisksRef.current = roadRisks }, [cellRisks, roadRisks])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !aoi) return
    const apply = () => {
      if (!map.getSource('offline-tiles')) return // feature-state has nothing to attach to yet
      featureStateRef.current = applyRiskFeatureState(map, cellRisks, roadRisks, featureStateRef.current)
      const hotspotSource = map.getSource('hotspots') as GeoJSONSource | undefined
      hotspotSource?.setData(computeHotspots(map, cellRisks))
      const villageSource = map.getSource('villages') as GeoJSONSource | undefined
      villageSource?.setData(villagesToFeatureCollection(priorities, isolations, aoi.center, exposureRef.current))
    }
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [aoi, cellRisks, roadRisks, priorities, isolations])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => (map.getSource('evac-route') as GeoJSONSource | undefined)?.setData(routeGeometry ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: routeGeometry, properties: {} }] } : empty)
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [routeGeometry])

  // Selection sync (Phase 11): the SAME useTickStore.selectedVillageId a RightRail priority row
  // click sets drives a highlight ring here — one source of truth, not a second selection state.
  const selectedVillageId = useTickStore((state) => state.selectedVillageId)
  useEffect(() => {
    const map = mapRef.current
    if (!map || typeof map.setFilter !== 'function' || typeof map.getLayer !== 'function') return
    const apply = () => map.setFilter('villages-selected-ring', ['==', ['get', 'village_id'], selectedVillageId ?? ''])
    if (map.getLayer('villages-selected-ring')) apply(); else map.once('load', apply)
  }, [selectedVillageId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded() || typeof map.setLayoutProperty !== 'function' || typeof map.getLayer !== 'function') return
    const visible = (enabled: boolean): 'visible' | 'none' => enabled ? 'visible' : 'none'
    // cells-reference/risk-cells-fill/roads-base/road-risks-line are added once the offline-tiles
    // vector source finishes loading (async) — this effect can run before that, so each id is
    // guarded rather than assumed to exist (setLayoutProperty on a missing layer throws).
    const setIfPresent = (id: string, value: 'visible' | 'none') => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', value) }
    for (const id of ['risk-cells-fill', 'cells-reference']) setIfPresent(id, visible(activeLayers.risk))
    for (const id of ['road-risks-line', 'roads-base']) setIfPresent(id, visible(activeLayers.roads))
    for (const id of ['villages-circle', 'villages-label', 'villages-cluster', 'villages-cluster-count', 'villages-selected-ring']) setIfPresent(id, visible(activeLayers.villages))
    setIfPresent('evac-route-line', visible(activeLayers.route && Boolean(routeGeometry)))
  }, [activeLayers, routeGeometry])

  const reset = () => { const map = mapRef.current; if (map) frameToAoi(map, aoiBounds(aoi?.bbox), containerRef.current, true) }
  const fullscreen = () => { const element = containerRef.current?.parentElement; if (element && !document.fullscreenElement) void element.requestFullscreen?.(); else void document.exitFullscreen?.() }
  return <div ref={containerRef} className="map-canvas"><MapControls onZoomIn={() => mapRef.current?.zoomIn({ duration: 350 })} onZoomOut={() => mapRef.current?.zoomOut({ duration: 350 })} onReset={reset} onLocate={reset} onFullscreen={fullscreen} onLayerChange={changeLayer} routeEnabled={Boolean(routeGeometry)} /><MapLegend showRisk={activeLayers.risk} showRoads={activeLayers.roads} />{mapError && <div className="map-error-status" role="alert">{mapError}</div>}</div>
}
