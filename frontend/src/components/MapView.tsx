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

// Bottom -> top. Async layers (terrain/cells/roads read sources that load after `load`) are
// added against a fixed anchor, then this exact order is re-imposed with moveLayer once both
// async sources have resolved — see enforceLayerOrder.
const LAYER_ORDER = [
  'offline-terrain',
  'aoi-scrim',
  'risk-cells-fill',
  'risk-heatmap',
  'roads-base',
  'road-risks-line',
  'hotspots-glow',
  'hotspots-halo',
  'hotspots-core',
  'villages-cluster',
  'villages-cluster-count',
  'villages-selected-ring',
  'villages-circle',
  'villages-label',
  'evac-route-line',
]

function ensurePmtilesProtocol(): void {
  if (protocolReady) return
  addProtocol('pmtiles', protocol.tile)
  protocolReady = true
}

function enforceLayerOrder(map: MapLibreMap): void {
  if (typeof map.moveLayer !== 'function' || typeof map.getLayer !== 'function') return
  for (let i = 0; i < LAYER_ORDER.length; i++) {
    if (!map.getLayer(LAYER_ORDER[i])) continue
    const above = LAYER_ORDER.slice(i + 1).find((id) => map.getLayer(id))
    try { map.moveLayer(LAYER_ORDER[i], above) } catch { /* layer briefly absent — next pass fixes it */ }
  }
}

type LngLatBounds = [[number, number], [number, number]]

function aoiBounds(bbox: [number, number, number, number] | undefined): LngLatBounds {
  const [minLon, minLat, maxLon, maxLat] = bbox ?? AIZAWL_BBOX
  return [[minLon, minLat], [maxLon, maxLat]]
}

/** Keep the AOI *covering* the viewport (fill, not letterbox) and lock panning to it, so a
 * stray scroll or drag can never leave the offline hillshade stranded in the background void.
 * Every call is guarded — the jsdom MapLibre mock only implements a handful of methods. */
function frameToAoi(map: MapLibreMap, bounds: LngLatBounds, container: HTMLElement | null, force = false): void {
  if (typeof map.setMaxBounds === 'function') map.setMaxBounds(bounds)
  if (typeof map.fitBounds !== 'function' || typeof map.getZoom !== 'function') return
  map.fitBounds(bounds, { padding: 0, animate: false })
  const fitZoom = map.getZoom()
  const w = container?.clientWidth ?? 0
  const h = container?.clientHeight ?? 0
  const coverZoom = w > 0 && h > 0 ? fitZoom + Math.log2(Math.max(w / h, h / w)) : fitZoom
  if (typeof map.setMinZoom === 'function') map.setMinZoom(coverZoom - 0.15)
  if (typeof map.setZoom === 'function' && (force || map.getZoom() < coverZoom)) {
    map.setZoom(coverZoom)
  }
}

/** Rough centroid (mean of exterior-ring vertices) — good enough for a 500 m cell and for a
 * heatmap point/hotspot marker; not a claim of the true polygon centroid. */
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

/** Fills a `cell_id -> centroid` cache from the real cell polygons already tiled into
 * offline-tiles (queried, not invented). Only re-queries when a scored cell this tick is still
 * missing a centroid — so it converges over the first few ticks then stops. */
function ensureCellCentroids(map: MapLibreMap, cellRisks: CellRisk[], cache: Map<string, [number, number]>): void {
  if (typeof map.querySourceFeatures !== 'function') return
  const missing = cellRisks.some((c) => !cache.has(c.cell_id))
  if (!missing) return
  const features = map.querySourceFeatures('offline-tiles', { sourceLayer: 'cells' })
  for (const feature of features) {
    // promoteId ('cell_id') moves the id onto feature.id — it may or may not survive in
    // properties depending on the GL version, so read both.
    const id = (typeof feature.id === 'string' ? feature.id : undefined) ?? feature.properties?.cell_id
    if (typeof id !== 'string' || cache.has(id)) continue
    const centroid = feature.geometry ? polygonCentroid(feature.geometry as Polygon | MultiPolygon) : null
    if (centroid) cache.set(id, centroid)
  }
}

/** One heatmap point per SCORED cell, at that cell's real centroid, carrying real `p_fail`. The
 * MapLibre `heatmap` layer blends these on the GPU into one continuous hazard field — no
 * fabricated geometry, no per-cell DOM element, no hard rectangular edges. A cell whose centroid
 * is not cached yet contributes nothing this tick (self-heals). */
function buildHeatPoints(cellRisks: CellRisk[], cache: Map<string, [number, number]>): FeatureCollection<Point, { p_fail: number }> {
  const features: Feature<Point, { p_fail: number }>[] = []
  for (const cell of cellRisks) {
    const centroid = cache.get(cell.cell_id)
    if (!centroid) continue
    features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: centroid }, properties: { p_fail: cell.p_fail } })
  }
  return { type: 'FeatureCollection', features }
}

/** Joins live scores onto the already-tiled real cell/road geometry via feature-state (keyed by
 * the real cell_id/edge_id — source promoteId). The faint per-cell fill and the risk-coloured
 * road overlay read this; nothing here invents geometry. Returns the id sets written so the
 * caller can clear ids that drop out on a later tick. */
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
      { hasData: true, p_fail: risk.p_fail, color: colorForPFail(risk.p_fail) },
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
  critical: number
}

/** Top-N real cells above the hotspot threshold, at their real centroid — changes with the
 * live scenario/tick, never a fixed set. */
function computeHotspots(cellRisks: CellRisk[], cache: Map<string, [number, number]>): FeatureCollection<Point, HotspotFeatureProperties> {
  const ranked = cellRisks
    .filter((c) => c.p_fail >= HOTSPOT_MIN_P_FAIL)
    .sort((a, b) => b.p_fail - a.p_fail)
    .slice(0, HOTSPOT_COUNT)

  const features: Feature<Point, HotspotFeatureProperties>[] = []
  for (const cell of ranked) {
    const centroid = cache.get(cell.cell_id)
    if (!centroid) continue
    const driver = cell.attributions[0]?.plain_language ?? 'elevated model signal'
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: centroid },
      properties: {
        cell_id: cell.cell_id,
        p_fail: cell.p_fail,
        stage: escalationStage(cell.p_fail),
        color: colorForPFail(cell.p_fail),
        driver,
        critical: cell.p_fail >= 0.75 ? 1 : 0,
      },
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
  const cellCentroidsRef = useRef<Map<string, [number, number]>>(new Map())
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
        layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#0a1620' } }],
      },
    })
    mapRef.current = map
    if (import.meta.env.DEV) (window as unknown as { __map?: MapLibreMap }).__map = map
    const container = containerRef.current
    let userInteracted = false
    const markInteracted = (event: { originalEvent?: unknown }) => { if (event?.originalEvent) userInteracted = true }
    map.on('dragstart', markInteracted)
    map.on('zoomstart', markInteracted)
    const resizeObserver = new ResizeObserver(() => {
      map.resize()
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
    let openCellPopup = (_event: { lngLat: { lng: number; lat: number }; features?: Array<{ properties?: Record<string, unknown> }> }) => {}

    // Added once offline-tiles (real cell/road vector geometry) finishes loading — addLayer
    // against a source that doesn't exist yet throws in real MapLibre. Anchored before
    // 'risk-heatmap' (a sync layer, always present by `load`); enforceLayerOrder fixes the final
    // z-order once both async sources are in.
    const addOfflineTileLayers = () => {
      map.addLayer(
        {
          id: 'risk-cells-fill',
          type: 'fill',
          source: 'offline-tiles',
          'source-layer': 'cells',
          // A whisper of per-cell definition UNDER the heatmap — never an outline, never opaque,
          // so the eye reads the continuous heat field, not a grid.
          paint: {
            'fill-color': ['case', ['boolean', ['feature-state', 'hasData'], false], ['feature-state', 'color'], 'transparent'],
            'fill-opacity': ['interpolate', ['linear'], ['coalesce', ['feature-state', 'p_fail'], 0], 0, 0, 0.5, 0.06, 1, 0.16],
          },
        },
        'risk-heatmap',
      )
      map.addLayer(
        {
          id: 'roads-base',
          type: 'line',
          source: 'offline-tiles',
          'source-layer': 'roads',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': ['step', ['zoom'], '#6f97a1', 12, '#7ba7b1', 15, '#8fbcc6'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.5, 12, 1.1, 16, 2.6],
            'line-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.4, 13, 0.62, 16, 0.78],
          },
        },
        'risk-heatmap',
      )
      map.addLayer(
        {
          id: 'road-risks-line',
          type: 'line',
          source: 'offline-tiles',
          'source-layer': 'roads',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            // Only roads with a MEANINGFUL blockage probability get the risk treatment — the
            // pipeline emits a RoadSegmentRisk for every edge (most at p_blocked 0), so painting
            // on `hasData` alone floods the map green. `roads-base` already carries the full
            // network; this layer is the "which roads are actually threatened" overlay.
            'line-color': ['coalesce', ['feature-state', 'color'], 'transparent'],
            'line-width': ['interpolate', ['linear'], ['coalesce', ['feature-state', 'p_blocked'], 0], 0.25, 2.2, 1, ['case', ['boolean', ['feature-state', 'severed'], false], 5, 3.6]],
            'line-opacity': ['interpolate', ['linear'], ['coalesce', ['feature-state', 'p_blocked'], 0], 0.2, 0, 0.35, 0.95],
            'line-dasharray': ['case', ['boolean', ['feature-state', 'severed'], false], ['literal', [1.6, 1.3]], ['literal', [1, 0]]],
          },
        },
        'risk-heatmap',
      )
      map.on('mouseenter', 'risk-cells-fill', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'risk-cells-fill', () => { map.getCanvas().style.cursor = '' })
      map.on('click', 'risk-cells-fill', openCellPopup)
    }

    map.on('load', () => {
      // ---- risk heat field (the hero): real cell centroids, real p_fail, GPU-blended ----
      map.addSource('risk-heat', { type: 'geojson', data: empty })
      map.addLayer({
        id: 'risk-heatmap',
        type: 'heatmap',
        source: 'risk-heat',
        paint: {
          'heatmap-weight': ['interpolate', ['linear'], ['get', 'p_fail'], 0, 0, 0.25, 0.12, 0.5, 0.42, 0.75, 0.8, 1, 1],
          'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 0.7, 13, 1.1, 16, 1.5],
          'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 14, 12, 30, 13, 42, 16, 74],
          'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.78, 15, 0.9],
          // transparent -> deep blue -> cyan -> green -> yellow -> orange -> red -> deep red.
          // Terrain stays visible through the low end; the eye is pulled to concentrated red.
          'heatmap-color': [
            'interpolate', ['linear'], ['heatmap-density'],
            0, 'rgba(12,28,42,0)',
            0.12, 'rgba(38,86,132,0.30)',
            0.26, 'rgba(46,150,180,0.5)',
            0.4, 'rgba(120,196,140,0.58)',
            0.55, 'rgba(238,204,92,0.7)',
            0.72, 'rgba(238,142,52,0.82)',
            0.87, 'rgba(220,64,44,0.9)',
            1, 'rgba(168,20,24,0.96)',
          ],
        },
      })

      // A dark scrim over the AOI so the hillshade reads as *context under* the risk field, not a
      // bright sheet — raster-brightness paint alone renders inconsistently across GL backends.
      // Pure UI chrome (a fixed rectangle at the AOI bbox), not a data layer. Sits directly under
      // the heat field.
      map.addSource('aoi-scrim', {
        type: 'geojson',
        data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[bounds[0][0], bounds[0][1]], [bounds[1][0], bounds[0][1]], [bounds[1][0], bounds[1][1]], [bounds[0][0], bounds[1][1]], [bounds[0][0], bounds[0][1]]]] } },
      })
      map.addLayer({ id: 'aoi-scrim', type: 'fill', source: 'aoi-scrim', paint: { 'fill-color': '#061019', 'fill-opacity': 0.42 } }, 'risk-heatmap')

      // ---- hotspots: soft glow -> halo -> core, restrained pulse for critical ----
      map.addSource('hotspots', { type: 'geojson', data: empty })
      map.addLayer({ id: 'hotspots-glow', type: 'circle', source: 'hotspots', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 16, 14, 30], 'circle-color': ['get', 'color'], 'circle-opacity': 0.16, 'circle-blur': 1 } })
      map.addLayer({ id: 'hotspots-halo', type: 'circle', source: 'hotspots', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 8, 14, 14], 'circle-color': ['get', 'color'], 'circle-opacity': 0.34, 'circle-blur': 0.45 } })
      map.addLayer({ id: 'hotspots-core', type: 'circle', source: 'hotspots', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 3.4, 14, 5.5], 'circle-color': ['get', 'color'], 'circle-stroke-width': 1.4, 'circle-stroke-color': '#f4fbfc' } })

      // ---- villages: real exposure points, styled by priority tier ----
      map.addSource('villages', { type: 'geojson', data: empty, cluster: true, clusterMaxZoom: 10, clusterRadius: 40 })
      map.addLayer({ id: 'villages-cluster', type: 'circle', source: 'villages', filter: ['has', 'point_count'], paint: { 'circle-color': '#0e5f6a', 'circle-radius': 14, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#8fd6d0' } })
      map.addLayer({ id: 'villages-cluster-count', type: 'symbol', source: 'villages', filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11 }, paint: { 'text-color': '#eafcff' } })
      map.addLayer({ id: 'villages-selected-ring', type: 'circle', source: 'villages', filter: ['==', ['get', 'village_id'], ''], paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 9, 14, 16], 'circle-color': 'transparent', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#4fd8d0' } })
      map.addLayer({
        id: 'villages-circle',
        type: 'circle',
        source: 'villages',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, ['match', ['get', 'tier'], 'P1', 5, 'P2', 4, 3], 14, ['match', ['get', 'tier'], 'P1', 9, 'P2', 7, 5]],
          'circle-color': ['get', 'color'],
          'circle-stroke-width': ['match', ['get', 'tier'], 'P1', 2.4, 'P2', 1.8, 1.2],
          'circle-stroke-color': '#0a1620',
          'circle-opacity': ['case', ['get', 'position_is_real'], 1, 0.5],
        },
      })
      map.addLayer({
        id: 'villages-label',
        type: 'symbol',
        source: 'villages',
        // Labels only for P1/P2 at any zoom, everything else only when zoomed in — keeps the
        // field readable at the operational overview (spec §10/§13).
        filter: ['!', ['has', 'point_count']],
        minzoom: 11,
        layout: {
          'text-field': ['coalesce', ['get', 'name'], ['get', 'village_id']],
          'text-size': ['interpolate', ['linear'], ['zoom'], 11, 10, 15, 12],
          'text-offset': [0, 1.3],
          'text-anchor': 'top',
          'text-optional': true,
          'symbol-sort-key': ['match', ['get', 'tier'], 'P1', 0, 'P2', 1, 2],
        },
        paint: { 'text-color': '#eef8fa', 'text-halo-color': '#06131b', 'text-halo-width': 1.4 },
      })

      map.addSource('evac-route', { type: 'geojson', data: empty })
      map.addLayer({ id: 'evac-route-line', type: 'line', source: 'evac-route', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#38d0ea', 'line-width': 4.5, 'line-opacity': 0.92, 'line-dasharray': [2.2, 1.4] } })

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

      // Cell centroids only become queryable once the vector tiles have actually rendered.
      // Re-arm on 'idle' until every currently-scored cell has a centroid, then stop — so the
      // heat field appears as soon as the tiles are ready, not only on the next tick, without a
      // permanent idle listener re-running setData forever.
      let centroidPasses = 0
      const fillCentroidsWhenReady = () => {
        if (cancelled || !map.getSource('offline-tiles') || !map.getSource('risk-heat')) return
        ensureCellCentroids(map, cellRisksRef.current, cellCentroidsRef.current)
        ;(map.getSource('risk-heat') as GeoJSONSource).setData(buildHeatPoints(cellRisksRef.current, cellCentroidsRef.current))
        ;(map.getSource('hotspots') as GeoJSONSource | undefined)?.setData(computeHotspots(cellRisksRef.current, cellCentroidsRef.current))
        const stillMissing = cellRisksRef.current.some((c) => !cellCentroidsRef.current.has(c.cell_id))
        if (stillMissing && centroidPasses++ < 8) map.once('idle', fillCentroidsWhenReady)
      }
      map.once('idle', fillCentroidsWhenReady)

      // Restrained pulse: only the glow ring, only when a critical hotspot is present.
      if (typeof map.setPaintProperty === 'function') {
        pulseTimer = setInterval(() => {
          pulsePhase = (pulsePhase + 1) % 66
          const t = (Math.sin((pulsePhase / 66) * Math.PI * 2) + 1) / 2
          map.setPaintProperty('hotspots-glow', 'circle-opacity', ['case', ['==', ['get', 'critical'], 1], 0.1 + t * 0.16, 0.14])
        }, 130)
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
          // Darkened relief: recognisable ridges/valleys, well below the risk field, never a
          // washed-out white sheet (spec §2).
          map.addLayer({
            id: 'offline-terrain',
            type: 'raster',
            source: 'offline-terrain',
            paint: { 'raster-opacity': 0.9, 'raster-contrast': 0.15, 'raster-brightness-min': 0.05, 'raster-brightness-max': 0.42, 'raster-saturation': -0.2 },
          }, map.getLayer('risk-heatmap') ? 'risk-heatmap' : undefined)

          enforceLayerOrder(map)
        })
        .catch(() => setMapError('Offline terrain unavailable. Run make tiles before the demo.'))

      void loadOfflineTileSource(aoiId)
        .then((source) => {
          if (cancelled || map.getSource('offline-tiles')) return
          protocol.add(new PMTiles(source))
          map.addSource('offline-tiles', {
            type: 'vector',
            url: `pmtiles://${source.getKey()}`,
            promoteId: { cells: 'cell_id', roads: 'edge_id' },
          })
          addOfflineTileLayers()
          featureStateRef.current = applyRiskFeatureState(map, cellRisksRef.current, roadRisksRef.current, featureStateRef.current)
          ensureCellCentroids(map, cellRisksRef.current, cellCentroidsRef.current)
          ;(map.getSource('risk-heat') as GeoJSONSource | undefined)?.setData(buildHeatPoints(cellRisksRef.current, cellCentroidsRef.current))
          ;(map.getSource('hotspots') as GeoJSONSource | undefined)?.setData(computeHotspots(cellRisksRef.current, cellCentroidsRef.current))

          enforceLayerOrder(map)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- live tick data is read via refs below
  }, [aoi, selectVillage])

  const cellRisksRef = useRef<CellRisk[]>(cellRisks)
  const roadRisksRef = useRef<RoadSegmentRisk[]>(roadRisks)
  useEffect(() => { cellRisksRef.current = cellRisks; roadRisksRef.current = roadRisks }, [cellRisks, roadRisks])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !aoi) return
    const apply = () => {
      const villageSource = map.getSource('villages') as GeoJSONSource | undefined
      villageSource?.setData(villagesToFeatureCollection(priorities, isolations, aoi.center, exposureRef.current))
      if (!map.getSource('offline-tiles')) return
      featureStateRef.current = applyRiskFeatureState(map, cellRisks, roadRisks, featureStateRef.current)
      ensureCellCentroids(map, cellRisks, cellCentroidsRef.current)
      ;(map.getSource('risk-heat') as GeoJSONSource | undefined)?.setData(buildHeatPoints(cellRisks, cellCentroidsRef.current))
      ;(map.getSource('hotspots') as GeoJSONSource | undefined)?.setData(computeHotspots(cellRisks, cellCentroidsRef.current))
    }
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [aoi, cellRisks, roadRisks, priorities, isolations])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => (map.getSource('evac-route') as GeoJSONSource | undefined)?.setData(routeGeometry ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: routeGeometry, properties: {} }] } : empty)
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [routeGeometry])

  // Selection sync (spec §11): the same useTickStore.selectedVillageId a RightRail priority row
  // click sets drives this highlight ring — one source of truth.
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
    const setIfPresent = (id: string, value: 'visible' | 'none') => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', value) }
    for (const id of ['risk-heatmap', 'risk-cells-fill', 'hotspots-glow', 'hotspots-halo', 'hotspots-core']) setIfPresent(id, visible(activeLayers.risk))
    for (const id of ['road-risks-line', 'roads-base']) setIfPresent(id, visible(activeLayers.roads))
    for (const id of ['villages-circle', 'villages-label', 'villages-cluster', 'villages-cluster-count', 'villages-selected-ring']) setIfPresent(id, visible(activeLayers.villages))
    setIfPresent('evac-route-line', visible(activeLayers.route && Boolean(routeGeometry)))
  }, [activeLayers, routeGeometry])

  const reset = () => { const map = mapRef.current; if (map) frameToAoi(map, aoiBounds(aoi?.bbox), containerRef.current, true) }
  const fullscreen = () => { const element = containerRef.current?.parentElement; if (element && !document.fullscreenElement) void element.requestFullscreen?.(); else void document.exitFullscreen?.() }
  return <div ref={containerRef} className="map-canvas"><MapControls onZoomIn={() => mapRef.current?.zoomIn({ duration: 350 })} onZoomOut={() => mapRef.current?.zoomOut({ duration: 350 })} onReset={reset} onLocate={reset} onFullscreen={fullscreen} onLayerChange={changeLayer} routeEnabled={Boolean(routeGeometry)} /><MapLegend showRisk={activeLayers.risk} showRoads={activeLayers.roads} />{mapError && <div className="map-error-status" role="alert">{mapError}</div>}</div>
}
