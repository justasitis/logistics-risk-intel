<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import maplibregl, {
  type GeoJSONSource,
  type MapGeoJSONFeature,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import type { GeoJsonFeatureCollection } from '@/types/dashboard'
import { aisPopupLinkState } from '@/utils/aisTransportLink'

const props = defineProps<{
  routes: GeoJsonFeatureCollection
  ports: GeoJsonFeatureCollection
  selectedTransportKey?: string
  loading?: boolean
  aisVessels: GeoJsonFeatureCollection
  selectedAisId?: string
  miZones: GeoJsonFeatureCollection
  miImpactedRoutes: GeoJsonFeatureCollection
  selectedMiEventId?: string
  /** 레지스트리(미승인, 추적 중) 영향권 — 승인 영향권과 스타일 구분 */
  registryZones?: GeoJsonFeatureCollection
  showRegistryZones?: boolean
}>()

const emit = defineEmits<{
  selectTransport: [transportKey: string]
  selectAis: [payload: { aisId: string; transportKey?: string }]
  selectMi: [eventId: string]
}>()

const mapContainer = ref<HTMLDivElement | null>(null)
let map: maplibregl.Map | null = null
let hasFittedInitialRoutes = false

const emptyFeatureCollection: GeoJsonFeatureCollection = {
  type: 'FeatureCollection',
  features: [],
}

function routeColorExpression(): maplibregl.ExpressionSpecification {
  return [
    'match',
    ['get', 'severity'],
    'CRITICAL',
    '#ff3158',
    'HIGH',
    '#ff8a28',
    'MEDIUM',
    '#ffd24a',
    'LOW',
    '#47d7ff',
    '#32cfa3',
  ]
}

function routeDisplayId(
  properties: Record<string, unknown>,
): string {
  return String(
    properties.display_id
    || properties.hbl_no
    || properties.trpr_no
    || properties.transport_key
    || '-',
  )
}

function popupHtml(properties: Record<string, unknown>) {
  const severity = String(properties.severity ?? 'NORMAL')
  const displayId = routeDisplayId(properties)
  const pol = String(properties.pol ?? '-')
  const pod = String(properties.pod ?? '-')
  const stopbyLabel = String(
    properties.stopby_label
    || '최단항로',
  )
  const routeStatus = String(
    properties.route_geometry_status
    || '',
  )
  const etaDelay = Number(properties.eta_net_delay_days ?? 0)
  const ltVariance = Number(properties.lead_time_variance_days ?? 0)
  const signals = String(properties.signals_label ?? '정상')

  return `
    <div class="route-popup">
      <div class="route-popup__severity">${escapeHtml(severity)}</div>
      <strong>${escapeHtml(displayId)}</strong>
      <div>${escapeHtml(pol)} → ${escapeHtml(pod)}</div>
      <div>경유: ${escapeHtml(stopbyLabel)}</div>
      <div>Route: ${escapeHtml(routeStatus)}</div>
      <hr>
      <div>ETA 누적 지연: ${etaDelay > 0 ? '+' : ''}${etaDelay}일</div>
      <div>Lead Time 변화: ${ltVariance > 0 ? '+' : ''}${ltVariance}일</div>
      <div class="route-popup__signals">${escapeHtml(signals)}</div>
    </div>
  `
}

function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function aisPopupHtml(properties: Record<string, unknown>) {
  const link = aisPopupLinkState(properties)
  const speed = properties.speed === null || properties.speed === undefined
    ? '-'
    : `${escapeHtml(properties.speed)} kn`

  const connectionText = link.linked
    ? `B-LAP 연결: ${escapeHtml(link.transportationNo)}`
    : 'B-LAP 미연결'

  const hblText = link.hblNo !== '-'
    ? `<div>HBL: ${escapeHtml(link.hblNo)}</div>`
    : ''

  return `
    <div class="route-popup ais-popup">
      <div class="route-popup__severity">${escapeHtml(properties.position_status)}</div>
      <strong>${escapeHtml(properties.vessel_name || '(선명 없음)')}</strong>
      <div>${escapeHtml(properties.current_lat)}, ${escapeHtml(properties.current_lon)}</div>
      <hr>
      <div>속도: ${speed} · Heading: ${escapeHtml(properties.heading ?? '-')}°</div>
      <div>다음 항만: ${escapeHtml(properties.next_port || '-')}</div>
      <div>AIS ETA: ${escapeHtml(properties.eta_ais || '-')}</div>
      <div>마지막 수신: ${escapeHtml(properties.last_seen_at || '-')}</div>
      ${hblText}
      <div class="route-popup__signals">${connectionText}</div>
    </div>
  `
}

function miPopupHtml(properties: Record<string, unknown>) {
  return `
    <div class="route-popup mi-popup">
      <div class="route-popup__severity">${escapeHtml(properties.severity)}</div>
      <strong>${escapeHtml(properties.headline)}</strong>
      <div>${escapeHtml(properties.location_name)}</div>
      <hr>
      <div>영향 반경: ${escapeHtml(properties.radius_km)}km</div>
      <div>예상 지연: ${escapeHtml(properties.expected_delay_min)}~${escapeHtml(properties.expected_delay_max)}일</div>
      <div class="route-popup__signals">${escapeHtml(properties.status)}</div>
    </div>
  `
}

function createVesselArrow(): ImageData {
  const canvas = document.createElement('canvas')
  canvas.width = 32
  canvas.height = 32
  const context = canvas.getContext('2d')
  if (!context) throw new Error('AIS 아이콘을 생성할 수 없습니다.')

  context.clearRect(0, 0, 32, 32)
  context.fillStyle = '#ffffff'
  context.beginPath()
  context.moveTo(16, 3)
  context.lineTo(23, 24)
  context.lineTo(16, 20)
  context.lineTo(9, 24)
  context.closePath()
  context.fill()
  return context.getImageData(0, 0, 32, 32)
}

function updateGeoJsonSource(
  sourceId: string,
  data: GeoJsonFeatureCollection,
) {
  if (!map?.isStyleLoaded()) return

  const source = map.getSource(sourceId) as GeoJSONSource | undefined
  source?.setData(data as unknown as GeoJSON.FeatureCollection)
}

function updateSelectedFilter() {
  if (!map?.getLayer('selected-route-line')) return

  const key = props.selectedTransportKey ?? '__NO_SELECTION__'
  map.setFilter('selected-route-line', [
    '==',
    ['get', 'transport_key'],
    key,
  ])
}

function updateSelectedAisFilter() {
  if (!map?.getLayer('selected-ais-vessel')) return
  map.setFilter('selected-ais-vessel', [
    '==',
    ['get', 'ais_id'],
    props.selectedAisId ?? '__NO_SELECTION__',
  ])
}


function updateSelectedMiFilter() {
  if (!map?.getLayer('selected-mi-zone')) return
  map.setFilter('selected-mi-zone', [
    '==',
    ['get', 'event_id'],
    props.selectedMiEventId ?? '__NO_SELECTION__',
  ])
}

function fitRoutesOnce() {
  if (!map || hasFittedInitialRoutes || props.routes.features.length === 0) {
    return
  }

  const bounds = new maplibregl.LngLatBounds()
  let pointCount = 0

  for (const feature of props.routes.features) {
    const geometry = feature.geometry as
      | { type?: string; coordinates?: unknown }
      | undefined

    if (
      geometry?.type !== 'LineString'
      || !Array.isArray(geometry.coordinates)
    ) {
      continue
    }

    for (const coordinate of geometry.coordinates) {
      if (
        Array.isArray(coordinate)
        && coordinate.length >= 2
        && Number.isFinite(Number(coordinate[0]))
        && Number.isFinite(Number(coordinate[1]))
      ) {
        bounds.extend([
          Number(coordinate[0]),
          Number(coordinate[1]),
        ])
        pointCount += 1
      }
    }
  }

  if (pointCount > 0) {
    map.fitBounds(bounds, {
      padding: 60,
      maxZoom: 4.2,
      duration: 700,
    })
    hasFittedInitialRoutes = true
  }
}

onMounted(() => {
  if (!mapContainer.value) return

  map = new maplibregl.Map({
    container: mapContainer.value,
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          maxzoom: 19,
          attribution: '© OpenStreetMap contributors',
        },
      },
      layers: [
        {
          id: 'osm-background',
          type: 'raster',
          source: 'osm',
          paint: {
            'raster-saturation': -0.62,
            'raster-brightness-min': 0.12,
            'raster-brightness-max': 0.72,
            'raster-contrast': 0.15,
          },
        },
      ],
    },
    center: [104, 24],
    zoom: 2.1,
    minZoom: 1.2,
    maxZoom: 12,
    pitch: 0,
    bearing: 0,
    renderWorldCopies: true,
  })

  map.addControl(
    new maplibregl.NavigationControl({
      showCompass: false,
      showZoom: true,
    }),
    'bottom-left',
  )

  map.on('load', () => {
    if (!map) return

    map.addSource('schedule-routes', {
      type: 'geojson',
      data: props.routes as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })

    map.addSource('schedule-ports', {
      type: 'geojson',
      data: props.ports as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })


    map.addSource('ais-vessels', {
      type: 'geojson',
      data: props.aisVessels as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })


    map.addSource('mi-zones', {
      type: 'geojson',
      data: props.miZones as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })

    map.addSource('mi-impacted-routes', {
      type: 'geojson',
      data: props.miImpactedRoutes as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })

    map.addSource('registry-zones', {
      type: 'geojson',
      data: (props.registryZones ?? emptyFeatureCollection) as unknown as GeoJSON.FeatureCollection,
      generateId: true,
    })

    if (!map.hasImage('vessel-arrow')) {
      map.addImage('vessel-arrow', createVesselArrow(), { pixelRatio: 2 })
    }

    map.addLayer({
      id: 'schedule-route-glow',
      type: 'line',
      source: 'schedule-routes',
      paint: {
        'line-color': routeColorExpression(),
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          1,
          5,
          6,
          12,
        ],
        'line-opacity': 0.17,
      },
    })

    map.addLayer({
      id: 'schedule-route-line',
      type: 'line',
      source: 'schedule-routes',
      paint: {
        'line-color': routeColorExpression(),
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          1,
          1.4,
          6,
          3.4,
        ],
        'line-opacity': [
          'match',
          ['get', 'severity'],
          'NORMAL',
          0.36,
          0.88,
        ],
      },
    })

    map.addLayer({
      id: 'selected-route-line',
      type: 'line',
      source: 'schedule-routes',
      filter: [
        '==',
        ['get', 'transport_key'],
        props.selectedTransportKey ?? '__NO_SELECTION__',
      ],
      paint: {
        'line-color': '#ffffff',
        'line-width': 5,
        'line-opacity': 0.92,
      },
    })

    map.addLayer({
      id: 'schedule-ports',
      type: 'circle',
      source: 'schedule-ports',
      paint: {
        'circle-radius': [
          'match',
          ['get', 'role'],
          'POL',
          4,
          3,
        ],
        'circle-color': [
          'match',
          ['get', 'role'],
          'POL',
          '#77e2ff',
          '#a9ffcf',
        ],
        'circle-stroke-color': '#061425',
        'circle-stroke-width': 1.5,
      },
    })

    map.addLayer({
      id: 'mi-zone-fill',
      type: 'fill',
      source: 'mi-zones',
      paint: {
        'fill-color': [
          'match',
          ['get', 'severity'],
          'CRITICAL', '#ff3158',
          'HIGH', '#ff8a28',
          'MEDIUM', '#ffd24a',
          '#47d7ff',
        ],
        'fill-opacity': 0.13,
      },
    })

    map.addLayer({
      id: 'mi-zone-line',
      type: 'line',
      source: 'mi-zones',
      paint: {
        'line-color': [
          'match',
          ['get', 'severity'],
          'CRITICAL', '#ff3158',
          'HIGH', '#ff8a28',
          'MEDIUM', '#ffd24a',
          '#47d7ff',
        ],
        'line-width': 2,
        'line-opacity': 0.82,
      },
    })

    map.addLayer({
      id: 'registry-zone-fill',
      type: 'fill',
      source: 'registry-zones',
      layout: {
        visibility: (props.showRegistryZones ?? true) ? 'visible' : 'none',
      },
      paint: {
        'fill-color': [
          'match',
          ['get', 'severity'],
          'CRITICAL', '#ff3158',
          'HIGH', '#ff8a28',
          'MEDIUM', '#ffd24a',
          '#47d7ff',
        ],
        'fill-opacity': 0.06,
      },
    })

    map.addLayer({
      id: 'registry-zone-line',
      type: 'line',
      source: 'registry-zones',
      layout: {
        visibility: (props.showRegistryZones ?? true) ? 'visible' : 'none',
      },
      paint: {
        'line-color': [
          'match',
          ['get', 'severity'],
          'CRITICAL', '#ff3158',
          'HIGH', '#ff8a28',
          'MEDIUM', '#ffd24a',
          '#47d7ff',
        ],
        'line-width': 1.5,
        'line-opacity': 0.6,
        'line-dasharray': [3, 2],
      },
    })

    map.addLayer({
      id: 'selected-mi-zone',
      type: 'line',
      source: 'mi-zones',
      filter: [
        '==',
        ['get', 'event_id'],
        props.selectedMiEventId ?? '__NO_SELECTION__',
      ],
      paint: {
        'line-color': '#ffffff',
        'line-width': 4,
        'line-opacity': 0.95,
      },
    })

    map.addLayer({
      id: 'mi-impacted-route-glow',
      type: 'line',
      source: 'mi-impacted-routes',
      paint: {
        'line-color': '#ff4f88',
        'line-width': 10,
        'line-opacity': 0.2,
      },
    })

    map.addLayer({
      id: 'mi-impacted-route-line',
      type: 'line',
      source: 'mi-impacted-routes',
      paint: {
        'line-color': [
          'match',
          ['get', 'mi_exposure_status'],
          'IN_ZONE', '#ff3158',
          'APPROACHING', '#ff8a28',
          'PASSED', '#7c6b75',
          '#ff5ca0',
        ],
        'line-width': 4,
        'line-opacity': 0.9,
        'line-dasharray': [2, 1],
      },
    })

    map.addLayer({
      id: 'ais-vessel-halo',
      type: 'circle',
      source: 'ais-vessels',
      paint: {
        'circle-radius': 14,
        'circle-color': [
          'match',
          ['get', 'position_status'],
          'LIVE', '#31e2ad',
          'STALE', '#ffb84d',
          '#7f94a2',
        ],
        'circle-opacity': 0.18,
      },
    })

    map.addLayer({
      id: 'ais-vessel-core',
      type: 'circle',
      source: 'ais-vessels',
      paint: {
        'circle-radius': 7,
        'circle-color': [
          'match',
          ['get', 'position_status'],
          'LIVE', '#31e2ad',
          'STALE', '#ffb84d',
          '#7f94a2',
        ],
        'circle-stroke-color': [
          'case',
          ['boolean', ['get', 'linked'], false],
          '#ffffff',
          '#183141',
        ],
        'circle-stroke-width': 2,
      },
    })

    map.addLayer({
      id: 'ais-vessel-heading',
      type: 'symbol',
      source: 'ais-vessels',
      layout: {
        'icon-image': 'vessel-arrow',
        'icon-size': [
          'interpolate',
          ['linear'],
          ['zoom'],
          1, 0.75,
          4, 1.0,
          7, 1.35,
          10, 1.7,
        ],
        'icon-rotate': ['coalesce', ['to-number', ['get', 'heading']], 0],
        'icon-rotation-alignment': 'map',
        'icon-pitch-alignment': 'map',
        'icon-allow-overlap': true,
        'icon-ignore-placement': true,
        'icon-padding': 0,
      },
    })

    map.addLayer({
      id: 'selected-ais-vessel',
      type: 'circle',
      source: 'ais-vessels',
      filter: [
        '==',
        ['get', 'ais_id'],
        props.selectedAisId ?? '__NO_SELECTION__',
      ],
      paint: {
        'circle-radius': 12,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 3,
      },
    })

    map.on('click', 'schedule-route-line', (event) => {
      const feature = event.features?.[0] as MapGeoJSONFeature | undefined
      if (!feature) return

      const properties = feature.properties ?? {}
      const transportKey = String(properties.transport_key ?? '')
      if (transportKey) {
        emit('selectTransport', transportKey)
      }

      new maplibregl.Popup({
        closeButton: true,
        closeOnClick: true,
      })
        .setLngLat(event.lngLat)
        .setHTML(popupHtml(properties))
        .addTo(map!)
    })

    map.on('mouseenter', 'schedule-route-line', () => {
      if (map) map.getCanvas().style.cursor = 'pointer'
    })

    map.on('mouseleave', 'schedule-route-line', () => {
      if (map) map.getCanvas().style.cursor = ''
    })

    map.on('click', 'mi-zone-fill', (event) => {
      const feature = event.features?.[0] as MapGeoJSONFeature | undefined
      if (!feature) return
      const properties = feature.properties ?? {}
      const eventId = String(properties.event_id ?? '')
      if (eventId) emit('selectMi', eventId)

      new maplibregl.Popup({ closeButton: true, closeOnClick: true })
        .setLngLat(event.lngLat)
        .setHTML(miPopupHtml(properties))
        .addTo(map!)
    })

    map.on('mouseenter', 'mi-zone-fill', () => {
      if (map) map.getCanvas().style.cursor = 'pointer'
    })

    map.on('mouseleave', 'mi-zone-fill', () => {
      if (map) map.getCanvas().style.cursor = ''
    })

    map.on('click', 'ais-vessel-core', (event) => {
      const feature = event.features?.[0] as MapGeoJSONFeature | undefined
      if (!feature) return
      const properties = feature.properties ?? {}
      const aisId = String(properties.ais_id ?? '')
      const transportKey = String(
        properties.matched_transport_key
        ?? properties.transport_key
        ?? '',
      )

      if (aisId) {
        emit('selectAis', {
          aisId,
          transportKey: transportKey || undefined,
        })
      }

      new maplibregl.Popup({ closeButton: true, closeOnClick: true })
        .setLngLat(event.lngLat)
        .setHTML(aisPopupHtml(properties))
        .addTo(map!)
    })

    map.on('mouseenter', 'ais-vessel-core', () => {
      if (map) map.getCanvas().style.cursor = 'pointer'
    })

    map.on('mouseleave', 'ais-vessel-core', () => {
      if (map) map.getCanvas().style.cursor = ''
    })

    fitRoutesOnce()
  })
})

watch(
  () => props.routes,
  (routes) => {
    updateGeoJsonSource('schedule-routes', routes)
    fitRoutesOnce()
  },
  { deep: true },
)

watch(
  () => props.ports,
  (ports) => {
    updateGeoJsonSource('schedule-ports', ports)
  },
  { deep: true },
)

watch(
  () => props.selectedTransportKey,
  () => {
    updateSelectedFilter()
  },
)


watch(
  () => props.aisVessels,
  (vessels) => {
    updateGeoJsonSource('ais-vessels', vessels)
  },
  { deep: true },
)

watch(
  () => props.selectedAisId,
  () => {
    updateSelectedAisFilter()
  },
)


watch(
  () => props.miZones,
  (zones) => {
    updateGeoJsonSource('mi-zones', zones)
  },
  { deep: true },
)

watch(
  () => props.registryZones,
  (zones) => {
    updateGeoJsonSource(
      'registry-zones',
      zones ?? emptyFeatureCollection,
    )
  },
  { deep: true },
)

watch(
  () => props.showRegistryZones,
  (visible) => {
    if (!map) return
    const value = (visible ?? true) ? 'visible' : 'none'
    for (const layer of ['registry-zone-fill', 'registry-zone-line']) {
      if (map.getLayer(layer)) {
        map.setLayoutProperty(layer, 'visibility', value)
      }
    }
  },
)

watch(
  () => props.miImpactedRoutes,
  (routes) => {
    updateGeoJsonSource('mi-impacted-routes', routes)
  },
  { deep: true },
)

watch(
  () => props.selectedMiEventId,
  () => {
    updateSelectedMiFilter()
  },
)

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>

    <div class="map-title">
      <span class="status-dot"></span>
      Global Schedule Risk Map
    </div>

    <div class="map-counter">
      {{ routes.features.length.toLocaleString() }} routes · {{ aisVessels.features.length.toLocaleString() }} vessels · {{ miZones.features.length.toLocaleString() }} MI zones
    </div>

    <div class="map-legend">
      <div><span class="legend-line critical"></span>CRITICAL</div>
      <div><span class="legend-line high"></span>HIGH</div>
      <div><span class="legend-line medium"></span>MEDIUM</div>
      <div><span class="legend-line normal"></span>NORMAL</div>
      <div><span class="legend-circle ais-live"></span>AIS LIVE</div>
      <div><span class="legend-circle ais-stale"></span>AIS STALE</div>
      <div><span class="legend-zone mi-zone"></span>MI ZONE</div>
      <div><span class="legend-line mi-impact"></span>MI IMPACT</div>
    </div>

    <div v-if="loading" class="map-loading">
      <span class="spinner"></span>
      B-LAP 일정 데이터를 분석하는 중입니다.
    </div>

    <div
      v-else-if="routes.features.length === 0 && aisVessels.features.length === 0 && miZones.features.length === 0"
      class="map-empty"
    >
      지도에 표시할 수 있는 POL/POD 경로가 없습니다.
    </div>
  </div>
</template>

<style scoped>
.map-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: #06111e;
}

.map-container {
  width: 100%;
  height: 100%;
}

.map-title,
.map-counter,
.map-legend {
  position: absolute;
  border: 1px solid rgba(93, 201, 255, 0.28);
  border-radius: 8px;
  background: rgba(4, 17, 32, 0.88);
  color: #dff6ff;
  backdrop-filter: blur(10px);
}

.map-title {
  top: 18px;
  left: 18px;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 14px;
  font-size: 13px;
  font-weight: 700;
}

.map-counter {
  top: 18px;
  right: 18px;
  padding: 8px 11px;
  color: #7ddfff;
  font-size: 11px;
  font-weight: 700;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #29f0a8;
  box-shadow: 0 0 10px #29f0a8;
}

.map-legend {
  left: 18px;
  bottom: 18px;
  display: grid;
  grid-template-columns: repeat(2, auto);
  gap: 9px 18px;
  padding: 11px 14px;
  color: #bcd2e4;
  font-size: 10px;
}

.map-legend > div {
  display: flex;
  align-items: center;
  gap: 7px;
}

.legend-line {
  display: inline-block;
  width: 21px;
  height: 3px;
  border-radius: 2px;
}

.legend-line.critical {
  background: #ff3158;
  box-shadow: 0 0 8px #ff3158;
}

.legend-line.high {
  background: #ff8a28;
}

.legend-line.medium {
  background: #ffd24a;
}

.legend-line.normal {
  background: #32cfa3;
}

.legend-circle {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.legend-circle.ais-live {
  background: #31e2ad;
  box-shadow: 0 0 7px #31e2ad;
}

.legend-circle.ais-stale {
  background: #ffb84d;
  box-shadow: 0 0 7px rgba(255, 184, 77, 0.7);
}

.legend-zone {
  display: inline-block;
  width: 13px;
  height: 9px;
  border: 1px solid #ff5d86;
  border-radius: 4px;
  background: rgba(255, 75, 121, 0.2);
}

.legend-line.mi-impact {
  background: #ff5ca0;
  box-shadow: 0 0 7px rgba(255, 92, 160, 0.75);
}

.map-loading,
.map-empty {
  position: absolute;
  left: 50%;
  top: 50%;
  display: flex;
  align-items: center;
  gap: 10px;
  transform: translate(-50%, -50%);
  padding: 14px 18px;
  border: 1px solid rgba(93, 201, 255, 0.28);
  border-radius: 9px;
  background: rgba(3, 14, 27, 0.91);
  color: #b9d7e9;
  font-size: 12px;
}

.spinner {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(93, 201, 255, 0.25);
  border-top-color: #5ed7ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

:global(.maplibregl-popup-content) {
  border: 1px solid rgba(68, 187, 255, 0.45);
  border-radius: 8px;
  background: rgba(5, 18, 34, 0.97);
  color: #eaf7ff;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.4);
}

:global(.route-popup) {
  min-width: 210px;
  font-size: 11px;
  line-height: 1.55;
}

:global(.route-popup strong) {
  display: block;
  margin-bottom: 3px;
  color: #6edfff;
  font-size: 13px;
}

:global(.route-popup hr) {
  margin: 7px 0;
  border: 0;
  border-top: 1px solid rgba(120, 185, 220, 0.22);
}

:global(.route-popup__severity) {
  margin-bottom: 3px;
  color: #ff9170;
  font-size: 9px;
  font-weight: 800;
}

:global(.route-popup__signals) {
  margin-top: 5px;
  color: #91aec0;
}
</style>
