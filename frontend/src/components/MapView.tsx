import type { FeatureCollection, Geometry } from 'geojson'
import { addProtocol, type GeoJSONSource, MapLibreMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { PMTiles, Protocol } from 'pmtiles'
import { useEffect, useRef, useState } from 'react'
import { cellRisksToFeatureCollection } from '../lib/grid'
import { loadOfflineTileSource } from '../lib/offlineTiles'
import { roadRisksToFeatureCollection } from '../lib/roads'
import { villagesToFeatureCollection } from '../lib/villages'
import { useTickStore } from '../store/useTickStore'
import { MapControls, type MapLayerKey, type MapLayerState } from './MapControls'
import { MapLegend } from './MapLegend'
import './map-workspace.css'

const CENTER: [number, number] = [92.7173, 23.7307]
const protocol = new Protocol()
let protocolReady = false
const empty: FeatureCollection = { type: 'FeatureCollection', features: [] }

function ensurePmtilesProtocol(): void {
  if (protocolReady) return
  addProtocol('pmtiles', protocol.tile)
  protocolReady = true
}

export function MapView({ routeGeometry = null, layers, onLayerChange }: { routeGeometry?: Geometry | null; layers?: MapLayerState; onLayerChange?: (key: MapLayerKey, enabled: boolean) => void } = {}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
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
    if (!containerRef.current || mapRef.current) return
    ensurePmtilesProtocol()
    let cancelled = false
    let terrainObjectUrl: string | null = null
    const map = new MapLibreMap({
      container: containerRef.current,
      center: aoi ? [aoi.center.lon, aoi.center.lat] : CENTER,
      zoom: 12.7,
      minZoom: 8,
      maxZoom: 18,
      attributionControl: false,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#d8e3dc' } }],
      },
    })
    mapRef.current = map
    const resizeObserver = new ResizeObserver(() => map.resize())
    resizeObserver.observe(containerRef.current)
    map.on('error', (event) => {
      const message = event.error?.message ?? 'Unknown MapLibre error'
      setMapError(`Map error: ${message}`)
    })
    map.on('load', () => {
      map.addSource('risk-cells', { type: 'geojson', data: empty })
      map.addLayer({ id: 'risk-cells-fill', type: 'fill', source: 'risk-cells', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.32, 'fill-outline-color': ['get', 'color'] } })
      map.addSource('road-risks', { type: 'geojson', data: empty })
      map.addLayer({ id: 'road-risks-line', type: 'line', source: 'road-risks', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['get', 'severed'], 4, 2.5], 'line-opacity': 0.96, 'line-dasharray': ['case', ['get', 'severed'], ['literal', [2, 1]], ['literal', [1, 0]]] } })
      map.addSource('villages', { type: 'geojson', data: empty, cluster: true, clusterMaxZoom: 11, clusterRadius: 42 })
      map.addLayer({ id: 'villages-circle', type: 'circle', source: 'villages', filter: ['!', ['has', 'point_count']], paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 13, 7, 16, 10], 'circle-color': ['get', 'color'], 'circle-stroke-width': 2, 'circle-stroke-color': '#f5fbf7' } })
      map.addLayer({ id: 'villages-label', type: 'symbol', source: 'villages', filter: ['!', ['has', 'point_count']], layout: { 'text-field': ['coalesce', ['get', 'name'], ['get', 'village_id']], 'text-size': 11, 'text-offset': [0, 1.4], 'text-anchor': 'top' }, paint: { 'text-color': '#15353b', 'text-halo-color': '#f2f8f2', 'text-halo-width': 1.2 } })
      map.addLayer({ id: 'villages-cluster', type: 'circle', source: 'villages', filter: ['has', 'point_count'], paint: { 'circle-color': '#126e70', 'circle-radius': 15, 'circle-stroke-width': 2, 'circle-stroke-color': '#f5fbf7' } })
      map.addLayer({ id: 'villages-cluster-count', type: 'symbol', source: 'villages', filter: ['has', 'point_count'], layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 11 }, paint: { 'text-color': '#ffffff' } })
      map.addSource('evac-route', { type: 'geojson', data: empty })
      map.addLayer({ id: 'evac-route-line', type: 'line', source: 'evac-route', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#087f9c', 'line-width': 5, 'line-opacity': 0.9 } })
      map.on('click', 'villages-circle', (event) => { const id = event.features?.[0]?.properties?.village_id; if (typeof id === 'string') selectVillage(id) })
      map.on('mouseenter', 'villages-circle', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'villages-circle', () => { map.getCanvas().style.cursor = '' })

      const aoiId = aoi?.id ?? 'aizawl'
      const bbox = aoi?.bbox ?? [92.60, 23.60, 92.85, 23.85]
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
          map.addLayer({ id: 'offline-terrain', type: 'raster', source: 'offline-terrain', paint: { 'raster-opacity': 0.9, 'raster-contrast': 0.12, 'raster-saturation': -1 } }, 'risk-cells-fill')
        })
        .catch(() => setMapError('Offline terrain unavailable. Run make tiles before the demo.'))

      void loadOfflineTileSource(aoiId)
        .then((source) => {
          if (cancelled || map.getSource('offline-tiles')) return
          protocol.add(new PMTiles(source))
          map.addSource('offline-tiles', { type: 'vector', url: `pmtiles://${source.getKey()}` })
          map.addLayer({ id: 'offline-cell-grid', type: 'line', source: 'offline-tiles', 'source-layer': 'cells', paint: { 'line-color': '#9aaca5', 'line-width': 0.35, 'line-opacity': 0.35 } }, 'risk-cells-fill')
          map.addLayer({ id: 'offline-roads', type: 'line', source: 'offline-tiles', 'source-layer': 'roads', paint: { 'line-color': ['step', ['zoom'], '#80958d', 12, '#667f78', 15, '#405b54'], 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.45, 12, 1.1, 16, 2.8], 'line-opacity': 0.9 } }, 'road-risks-line')
        })
        .catch(() => setMapError('Offline road/grid archive unavailable. Run make tiles before the demo.'))
    })
    return () => {
      cancelled = true
      if (terrainObjectUrl) URL.revokeObjectURL(terrainObjectUrl)
      resizeObserver.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [aoi, selectVillage])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !aoi) return
    const apply = () => {
      ;(map.getSource('risk-cells') as GeoJSONSource | undefined)?.setData(cellRisksToFeatureCollection(cellRisks, aoi.center))
      ;(map.getSource('road-risks') as GeoJSONSource | undefined)?.setData(roadRisksToFeatureCollection(roadRisks, aoi.center))
      ;(map.getSource('villages') as GeoJSONSource | undefined)?.setData(villagesToFeatureCollection(priorities, isolations, aoi.center))
    }
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [aoi, cellRisks, roadRisks, priorities, isolations])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const apply = () => (map.getSource('evac-route') as GeoJSONSource | undefined)?.setData(routeGeometry ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: routeGeometry, properties: {} }] } : empty)
    if (map.isStyleLoaded()) apply(); else map.once('load', apply)
  }, [routeGeometry])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded() || typeof map.setLayoutProperty !== 'function') return
    const visible = (enabled: boolean) => enabled ? 'visible' : 'none'
    map.setLayoutProperty('risk-cells-fill', 'visibility', visible(activeLayers.risk))
    map.setLayoutProperty('road-risks-line', 'visibility', visible(activeLayers.roads))
    for (const id of ['villages-circle', 'villages-label', 'villages-cluster', 'villages-cluster-count']) map.setLayoutProperty(id, 'visibility', visible(activeLayers.villages))
    map.setLayoutProperty('evac-route-line', 'visibility', visible(activeLayers.route && Boolean(routeGeometry)))
  }, [activeLayers, routeGeometry])

  const reset = () => mapRef.current?.flyTo({ center: aoi ? [aoi.center.lon, aoi.center.lat] : CENTER, zoom: 12.7, duration: 700 })
  const fullscreen = () => { const element = containerRef.current?.parentElement; if (element && !document.fullscreenElement) void element.requestFullscreen?.(); else void document.exitFullscreen?.() }
  return <div ref={containerRef} className="map-canvas"><MapControls onZoomIn={() => mapRef.current?.zoomIn({ duration: 350 })} onZoomOut={() => mapRef.current?.zoomOut({ duration: 350 })} onReset={reset} onLocate={reset} onFullscreen={fullscreen} onLayerChange={changeLayer} routeEnabled={Boolean(routeGeometry)} /><MapLegend showRisk={activeLayers.risk} showRoads={activeLayers.roads} />{mapError && <div className="map-error-status" role="alert">{mapError}</div>}</div>
}
