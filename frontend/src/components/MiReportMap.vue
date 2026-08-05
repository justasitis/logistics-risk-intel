<script setup lang="ts">
import { computed, ref } from 'vue'
import worldLand from '../assets/world-land.json'
import type { RegistryMapZone } from '../services/miUpload'

/**
 * MI 리포트용 정적 지도 — 실시간 선박 위치 없이 레지스트리 이벤트 영향권만 표시.
 * 배경은 번들된 세계 육지 폴리곤(Natural Earth 110m 계열, 오프라인)을
 * 등거리 도법으로 투영한 인라인 SVG. 타일 서버/외부 라이브러리 불필요.
 */
const props = defineProps<{ zones: RegistryMapZone[] }>()

interface Region {
  key: string
  label: string
  bbox: [number, number, number, number] // [lon0, lat0, lon1, lat1]
}

const REGIONS: Region[] = [
  { key: 'world', label: '전체', bbox: [-180, -55, 180, 82] },
  { key: 'europe', label: '유럽 · 수에즈', bbox: [-14, 8, 66, 62] },
  { key: 'med', label: '지중해 · 아드리아', bbox: [-8, 28, 40, 48] },
  { key: 'us_east', label: '미주 동안', bbox: [-102, 8, -56, 56] },
  { key: 'asia', label: '아시아', bbox: [94, 10, 150, 54] },
]

const activeRegion = ref('world')
const region = computed<Region>(
  () => REGIONS.find((r) => r.key === activeRegion.value) ?? REGIONS[0]!,
)

const W = 960
const H = 500

const lonSpan = computed(() => region.value.bbox[2] - region.value.bbox[0])
const latSpan = computed(() => region.value.bbox[3] - region.value.bbox[1])

function x(lon: number): number {
  return ((lon - region.value.bbox[0]) / lonSpan.value) * W
}
function y(lat: number): number {
  return ((region.value.bbox[3] - lat) / latSpan.value) * H
}

const LAND = (worldLand as { polygons: number[][][] }).polygons

/** 육지 폴리곤 → SVG path 묶음 (권역 변경 시 재투영) */
const landPath = computed<string>(() => {
  const parts: string[] = []
  for (const ring of LAND) {
    let d = ''
    for (let i = 0; i < ring.length; i += 1) {
      const pt = ring[i]
      if (!pt) continue
      d += `${i === 0 ? 'M' : 'L'}${x(pt[0] ?? 0).toFixed(1)},${y(pt[1] ?? 0).toFixed(1)}`
    }
    parts.push(`${d}Z`)
  }
  return parts.join(' ')
})

/** 그리드(경위선) — 관제센터 느낌의 배경 눈금 */
const graticules = computed<{ verticals: number[]; horizontals: number[] }>(() => {
  const step = lonSpan.value > 120 ? 30 : lonSpan.value > 60 ? 20 : 10
  const verticals: number[] = []
  const horizontals: number[] = []
  for (let lon = -180; lon <= 180; lon += step) {
    if (lon > region.value.bbox[0] && lon < region.value.bbox[2]) verticals.push(lon)
  }
  for (let lat = -60; lat <= 90; lat += step) {
    if (lat > region.value.bbox[1] && lat < region.value.bbox[3]) horizontals.push(lat)
  }
  return { verticals, horizontals }
})

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#10b981',
}
const DEFAULT_ZONE_COLOR = '#06b6d4'

interface ZoneCircle {
  key: string
  eventId: string
  cx: number
  cy: number
  r: number
  color: string
  active: boolean
  severity: string
  inView: boolean
}

const zoneCircles = computed<ZoneCircle[]>(() =>
  props.zones.flatMap((zone) =>
    zone.locations.map((loc) => {
      const color = SEVERITY_COLORS[zone.severity?.toUpperCase() ?? ''] ?? DEFAULT_ZONE_COLOR
      // 경도 스케일 기준 근사 — km → px
      const r = Math.max(6, ((loc.radius_km / 111) / lonSpan.value) * W)
      const cx = x(loc.lon)
      const cy = y(loc.lat)
      return {
        key: `${zone.event_id}|${loc.code}`,
        eventId: zone.event_id,
        cx,
        cy,
        r,
        color,
        active: zone.status === 'ACTIVE',
        severity: zone.severity,
        inView: cx > -r && cx < W + r && cy > -r && cy < H + r,
      }
    }),
  ),
)

const visibleZones = computed(() => zoneCircles.value.filter((z) => z.inView))

// ---------- 이벤트 라벨 박스 (겹침 방지 배치) ----------
const SEVERITY_RANK: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
}
const LABEL_H = 22
// 앵커 주변 후보 방향 (오른쪽 우선)과 점진적 간격
const LABEL_DIRS: Array<[number, number]> = [
  [1, 0], [1, -0.8], [1, 0.8], [-1, 0], [-1, -0.8], [-1, 0.8], [0, -1], [0, 1],
]
const LABEL_GAPS = [8, 18, 32, 50, 72, 100]

/** 라벨 문구 — Actify 간결 문구 우선, 없으면 headline 앞부분 폭 */
function labelText(zone: RegistryMapZone | undefined): string {
  const short = (zone?.short_label ?? '').trim()
  if (short) return short
  const headline = (zone?.headline ?? '').trim()
  return headline.length > 18 ? `${headline.slice(0, 18)}…` : headline
}

/** 텍스트 폭 근사 (한글 11.5px, 그 외 6.6px) + 좌우 패딩 */
function estimateWidth(text: string): number {
  let w = 0
  for (const ch of text) w += /[가-힣]/.test(ch) ? 11.5 : 6.6
  return Math.ceil(w) + 18
}

interface LabelRect {
  x: number
  y: number
  w: number
  h: number
}

function rectsOverlap(a: LabelRect, b: LabelRect, pad: number): boolean {
  return (
    a.x - pad < b.x + b.w
    && a.x + a.w + pad > b.x
    && a.y - pad < b.y + b.h
    && a.y + a.h + pad > b.y
  )
}

interface LabelBox extends LabelRect {
  key: string
  text: string
  color: string
  anchorX: number
  anchorY: number
}

const labelBoxes = computed<LabelBox[]>(() => {
  const zoneByEvent = new Map(props.zones.map((z) => [z.event_id, z]))
  const byEvent = new Map<string, ZoneCircle[]>()
  for (const circle of visibleZones.value) {
    if (!byEvent.has(circle.eventId)) byEvent.set(circle.eventId, [])
    byEvent.get(circle.eventId)?.push(circle)
  }
  const items = [...byEvent.entries()]
    .map(([eventId, circles]) => {
      const anchor = circles.reduce((a, b) => (b.r > a.r ? b : a))
      return {
        key: eventId,
        text: labelText(zoneByEvent.get(eventId)),
        color: anchor.color,
        ax: anchor.cx,
        ay: anchor.cy,
        r: anchor.r,
        rank: SEVERITY_RANK[anchor.severity?.toUpperCase() ?? ''] ?? 4,
      }
    })
    .sort((a, b) => a.rank - b.rank)  // 심각도 높은 것부터 자리 배정

  const placed: LabelRect[] = []
  const out: LabelBox[] = []
  for (const item of items) {
    if (!item.text) continue
    const w = estimateWidth(item.text)
    let chosen: LabelRect | null = null
    outer:
    for (const gap of LABEL_GAPS) {
      for (const [dx, dy] of LABEL_DIRS) {
        let bx = dx > 0
          ? item.ax + item.r + gap
          : dx < 0
            ? item.ax - item.r - gap - w
            : item.ax - w / 2
        let by = dy < 0
          ? item.ay - item.r - gap - LABEL_H
          : dy > 0
            ? item.ay + item.r + gap
            : item.ay - LABEL_H / 2
        bx = Math.max(4, Math.min(W - 4 - w, bx))
        by = Math.max(4, Math.min(H - 4 - LABEL_H, by))
        const rect = { x: bx, y: by, w, h: LABEL_H }
        if (!placed.some((p) => rectsOverlap(p, rect, 3))) {
          chosen = rect
          break outer
        }
      }
    }
    if (!chosen) continue  // 어디에도 못 놓으면 생략 — 겹침 방지 우선
    placed.push(chosen)
    out.push({
      key: item.key,
      text: item.text,
      color: item.color,
      anchorX: item.ax,
      anchorY: item.ay,
      ...chosen,
    })
  }
  return out
})

const legendSeverities = computed(() => {
  const seen = new Map<string, string>()
  for (const z of props.zones) {
    const sev = (z.severity || 'UNKNOWN').toUpperCase()
    if (!seen.has(sev)) seen.set(sev, SEVERITY_COLORS[sev] ?? DEFAULT_ZONE_COLOR)
  }
  return [...seen.entries()].map(([label, color]) => ({ label, color }))
})

const mapRef = ref<HTMLElement | null>(null)

/** HTML 낙출력용 인라인 SVG 묶음 */
function getSvgHtml(): string {
  return mapRef.value?.innerHTML ?? ''
}
defineExpose({ getSvgHtml })
</script>

<template>
  <section class="report-map">
    <div class="map-head">
      <div>
        <p class="eyebrow">GEOSPATIAL VIEW</p>
        <h3 class="title">물류 이벤트 지도 (권역별 포커스)</h3>
      </div>
      <div class="region-tabs">
        <button
          v-for="r in REGIONS"
          :key="r.key"
          type="button"
          class="region-tab"
          :class="{ active: activeRegion === r.key }"
          @click="activeRegion = r.key"
        >
          {{ r.label }}
        </button>
      </div>
    </div>

    <p v-if="!props.zones.length" class="hint">
      표시할 이벤트 영향권이 없습니다. 레지스트리에 위치가 등록된 이벤트가 있으면 표시됩니다.
    </p>

    <div ref="mapRef" class="map-frame">
      <svg :viewBox="`0 0 ${W} ${H}`" class="map-svg" role="img" :aria-label="`물류 이벤트 지도 — ${region.label}`">
        <defs>
          <clipPath id="report-map-clip">
            <rect x="0" y="0" :width="W" :height="H" rx="12" />
          </clipPath>
          <radialGradient id="report-map-sea" cx="30%" cy="20%" r="90%">
            <stop offset="0%" stop-color="#eaf4fd" />
            <stop offset="100%" stop-color="#d9e8f6" />
          </radialGradient>
        </defs>

        <g clip-path="url(#report-map-clip)">
          <rect x="0" y="0" :width="W" :height="H" fill="url(#report-map-sea)" />

          <g class="graticule">
            <line
              v-for="lon in graticules.verticals"
              :key="`v${lon}`"
              :x1="x(lon)" :x2="x(lon)" y1="0" :y2="H"
            />
            <line
              v-for="lat in graticules.horizontals"
              :key="`h${lat}`"
              x1="0" :x2="W" :y1="y(lat)" :y2="y(lat)"
            />
          </g>

          <path :d="landPath" class="land" />

          <g v-for="z in visibleZones" :key="z.key">
            <circle :cx="z.cx" :cy="z.cy" :r="z.r" :fill="z.color" class="zone-fill" />
            <circle
              :cx="z.cx" :cy="z.cy" :r="z.r" fill="none"
              :stroke="z.color" :stroke-width="z.active ? 2 : 1.4"
              :stroke-dasharray="z.active ? undefined : '5 4'"
              class="zone-ring"
            />
            <circle :cx="z.cx" :cy="z.cy" r="3.5" :fill="z.color" stroke="#fff" stroke-width="1.4" />
          </g>

          <g v-for="b in labelBoxes" :key="`label-${b.key}`">
            <line
              :x1="b.anchorX"
              :y1="b.anchorY"
              :x2="b.anchorX < b.x ? b.x : b.x + b.w"
              :y2="b.y + b.h / 2"
              :stroke="b.color"
              class="label-link"
            />
            <rect
              :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="7"
              :stroke="b.color"
              class="label-box"
            />
            <text :x="b.x + 9" :y="b.y + b.h / 2 + 3.5" class="label-text" :fill="b.color">
              {{ b.text }}
            </text>
          </g>
        </g>
      </svg>
    </div>

    <div class="map-footer">
      <div class="legend">
        <span v-for="s in legendSeverities" :key="s.label" class="legend-item">
          <span class="legend-dot" :style="{ background: s.color }"></span>
          {{ s.label }}
        </span>
        <span class="legend-item">
          <span class="legend-dot solid-demo"></span>
          진행 중(실선) / 완화·해소(점선)
        </span>
      </div>
      <span class="region-note">{{ region.label }} 기준 · 이벤트 {{ visibleZones.length }}개 영향권</span>
    </div>
  </section>
</template>

<style scoped>
.report-map {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-lg);
  padding: 16px 18px;
  box-shadow: var(--li-shadow-card);
}
.map-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: var(--li-blue);
}
.title {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--li-text);
}
.region-tabs {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.region-tab {
  padding: 5px 12px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface);
  color: var(--li-text-muted);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
}
.region-tab:hover:not(.active) {
  background: var(--li-surface-blue);
}
.region-tab.active {
  background: var(--li-accent-gradient);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 8px 18px rgba(37, 99, 235, 0.24);
}
.map-frame {
  border-radius: var(--li-radius-md);
  overflow: hidden;
  border: 1px solid var(--li-border-white);
  box-shadow: var(--li-shadow-card);
}
.map-svg {
  display: block;
  width: 100%;
  height: auto;
}
.graticule line {
  stroke: rgba(37, 99, 235, 0.09);
  stroke-width: 1;
}
.land {
  fill: #c9dcec;
  stroke: rgba(255, 255, 255, 0.9);
  stroke-width: 0.6;
}
.zone-fill {
  opacity: 0.16;
}
.zone-ring {
  opacity: 0.85;
}
.label-box {
  fill: rgba(255, 255, 255, 0.94);
  stroke-width: 1.2;
}
.label-text {
  font-size: 11px;
  font-weight: 700;
}
.label-link {
  stroke-width: 1;
  stroke-dasharray: 2 2;
  opacity: 0.7;
}
.map-footer {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--li-text-muted);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
}
.solid-demo {
  background: linear-gradient(90deg, var(--li-blue) 50%, transparent 50%);
  border: 1px dashed var(--li-blue);
}
.region-note {
  font-size: 11px;
  color: var(--li-text-faint);
}
.hint {
  color: var(--li-text-muted);
  font-size: 12px;
}
</style>
