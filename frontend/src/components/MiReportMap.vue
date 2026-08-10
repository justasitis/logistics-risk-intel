<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
  { key: 'us_west', label: '미주 서안', bbox: [-132, 22, -108, 56] },
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
  name: string
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
        name: loc.name,
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

// ---------- 이벤트 팝업 (권역 전환 시 기본 표시, 동그라미당 하나, X/일괄 닫기) ----------
// 앵커 주변 후보 방향 (오른쪽 우선)과 점진적 간격
const LABEL_DIRS: Array<[number, number]> = [
  [1, 0], [1, -0.8], [1, 0.8], [-1, 0], [-1, -0.8], [-1, 0.8], [0, -1], [0, 1],
]
const LABEL_GAPS = [8, 16, 26, 40, 58, 80, 108, 140]
const POPUP_H = 38

/** 라벨 문구 — Actify 간결 문구 우선, 없으면 headline 앞부분 폭 */
function labelText(zone: RegistryMapZone | undefined): string {
  const short = (zone?.short_label ?? '').trim()
  if (short) return short
  const headline = (zone?.headline ?? '').trim()
  return headline.length > 22 ? `${headline.slice(0, 22)}…` : headline
}

/**
 * 텍스트 폭 근사 (11px 기준: 한글 11.5, 대문자 7.6, 숫자 6.4, 공백 3.4, 그 외 6.6)
 * + 좌우 패딩·닫기 버튼 영역·여유분. 이전의 단일 6.6px 추정은 공백/대문자 비율에 따라
 * 실제 렌더 폭과 양방향으로 어긋나 박스 겹침/여백 과대를 유발했음.
 */
function estimateWidth(text: string): number {
  let w = 0
  for (const ch of text) {
    if (/[가-힣]/.test(ch)) w += 11.5
    else if (/[A-Z]/.test(ch)) w += 7.6
    else if (/[0-9]/.test(ch)) w += 6.4
    else if (ch === ' ') w += 3.4
    else w += 6.6
  }
  return Math.ceil(w) + 36
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

/** 두 사각형의 기하학적 겹침 면적 (0이면 비겹침) */
function overlapArea(a: LabelRect, b: LabelRect): number {
  const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  return ox > 0 && oy > 0 ? ox * oy : 0
}

/**
 * 앵커 주변 후보 위치 생성 (간격 → 방향 → 미세 시프트 순, 경계 클램프 포함).
 * 옆 배치(dx≠0)는 상하로 한 박스 높이만큼 밀어 보고, 위/아래 배치(dy≠0)는 좌우로 밀어
 * 같은 간격·방향에서 겹침 회피 기회를 늘린다.
 */
function candidatesFor(circle: ZoneCircle, w: number): LabelRect[] {
  const out: LabelRect[] = []
  for (const gap of LABEL_GAPS) {
    for (const [dx, dy] of LABEL_DIRS) {
      const bx = dx > 0
        ? circle.cx + circle.r + gap
        : dx < 0
          ? circle.cx - circle.r - gap - w
          : circle.cx - w / 2
      const by = dy < 0
        ? circle.cy - circle.r - gap - POPUP_H
        : dy > 0
          ? circle.cy + circle.r + gap
          : circle.cy - POPUP_H / 2
      const shifts: Array<[number, number]> = dx !== 0
        ? [[0, 0], [0, -(POPUP_H + 6)], [0, POPUP_H + 6]]
        : dy !== 0
          ? [[0, 0], [-24, 0], [24, 0]]
          : [[0, 0]]
      for (const [sx, sy] of shifts) {
        out.push({
          x: Math.max(4, Math.min(W - 4 - w, bx + sx)),
          y: Math.max(4, Math.min(H - 4 - POPUP_H, by + sy)),
          w,
          h: POPUP_H,
        })
      }
    }
  }
  return out
}

const openPopups = ref<string[]>([])

function togglePopup(key: string): void {
  const idx = openPopups.value.indexOf(key)
  if (idx >= 0) openPopups.value.splice(idx, 1)
  else openPopups.value.push(key)
}

function closePopup(key: string): void {
  openPopups.value = openPopups.value.filter((k) => k !== key)
}

function closeAllPopups(): void {
  openPopups.value = []
}

// ---------- 팝업 드래그 이동 (포인터 캡처 기반, 권역/데이터 변경 시 리셋) ----------
interface DragState {
  key: string
  pointerId: number
  startClientX: number
  startClientY: number
  baseX: number
  baseY: number
}

/** 팝업 키 → 드래그로 이동된 좌표 (SVG viewBox 좌표계) */
const dragOffsets = ref<Map<string, { x: number; y: number }>>(new Map())
const dragState = ref<DragState | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)

/** 화면 px → SVG viewBox 단위 환산 비율 (SVG가 width:100%로 스케일됨) */
function svgScale(): number {
  const el = svgRef.value
  if (!el) return 1
  const rectW = el.getBoundingClientRect().width
  return rectW > 0 ? rectW / W : 1
}

function onPopupPointerDown(box: PopupBox, e: PointerEvent): void {
  if (e.button !== 0) return
  e.preventDefault()
  ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  dragState.value = {
    key: box.key,
    pointerId: e.pointerId,
    startClientX: e.clientX,
    startClientY: e.clientY,
    baseX: box.x,
    baseY: box.y,
  }
}

function onPopupPointerMove(box: PopupBox, e: PointerEvent): void {
  const st = dragState.value
  if (!st || st.key !== box.key || st.pointerId !== e.pointerId) return
  const scale = svgScale()
  const dx = (e.clientX - st.startClientX) / scale
  const dy = (e.clientY - st.startClientY) / scale
  const nx = Math.max(4, Math.min(W - 4 - box.w, st.baseX + dx))
  const ny = Math.max(4, Math.min(H - 4 - box.h, st.baseY + dy))
  const next = new Map(dragOffsets.value)
  next.set(box.key, { x: nx, y: ny })
  dragOffsets.value = next
}

function onPopupPointerUp(box: PopupBox, e: PointerEvent): void {
  const st = dragState.value
  if (!st || st.key !== box.key || st.pointerId !== e.pointerId) return
  dragState.value = null
}

// 권역 전환(및 최초 표시) 시 팝업 상태를 리셋하고 해당 권역의 모든 이벤트 팝업을 기본 표시
// 드래그로 옮긴 위치도 함께 리셋해 기본 배치로 복귀
watch(
  activeRegion,
  () => {
    dragOffsets.value = new Map()
    openPopups.value = visibleZones.value.map((z) => z.key)
  },
  { immediate: true },
)

// 레지스트리 데이터 변경 시 드래그 위치만 리셋 (기본 배치 복귀)
watch(
  () => props.zones,
  () => {
    dragOffsets.value = new Map()
  },
)

interface PopupBox extends LabelRect {
  key: string
  title: string
  sub: string
  color: string
  anchorX: number
  anchorY: number
}

const popupBoxes = computed<PopupBox[]>(() => {
  const zoneByEvent = new Map(props.zones.map((z) => [z.event_id, z]))
  const circleByKey = new Map(visibleZones.value.map((c) => [c.key, c]))
  const placed: LabelRect[] = []
  const out: PopupBox[] = []
  for (const key of openPopups.value) {
    const circle = circleByKey.get(key)
    if (!circle) continue
    const zone = zoneByEvent.get(circle.eventId)
    const title = labelText(zone)
    const sub = `${circle.name} · ${circle.severity} · ${circle.active ? '진행 중' : '완화'}`
    const w = Math.max(estimateWidth(title), estimateWidth(sub))
    // 이미 열린 팝업과 겹치지 않는 첫 자리 탐색, 모두 겹치면 겹침 면적이 가장 작은 자리에 배치
    let chosen: LabelRect | null = null
    let best: LabelRect | null = null
    let bestArea = Number.POSITIVE_INFINITY
    for (const rect of candidatesFor(circle, w)) {
      const area = placed.reduce((sum, p) => sum + overlapArea(p, rect), 0)
      if (area === 0 && !placed.some((p) => rectsOverlap(p, rect, 3))) {
        chosen = rect
        break
      }
      if (area < bestArea) {
        bestArea = area
        best = rect
      }
    }
    const rect = chosen ?? best
    if (!rect) continue
    // 드래그로 옮긴 위치가 있으면 우선 적용하고, 이후 자동 배치는 그 위치를 피함
    const off = dragOffsets.value.get(key)
    const finalRect: LabelRect = off ? { x: off.x, y: off.y, w: rect.w, h: rect.h } : rect
    placed.push(finalRect)
    out.push({
      key,
      title,
      sub,
      color: circle.color,
      anchorX: circle.cx,
      anchorY: circle.cy,
      ...finalRect,
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
      <svg ref="svgRef" :viewBox="`0 0 ${W} ${H}`" class="map-svg" role="img" :aria-label="`물류 이벤트 지도 — ${region.label}`">
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

          <g
            v-for="z in visibleZones"
            :key="z.key"
            class="zone-clickable"
            @click="togglePopup(z.key)"
          >
            <circle :cx="z.cx" :cy="z.cy" :r="z.r" :fill="z.color" class="zone-fill" />
            <circle
              :cx="z.cx" :cy="z.cy" :r="z.r" fill="none"
              :stroke="z.color" :stroke-width="z.active ? 2 : 1.4"
              :stroke-dasharray="z.active ? undefined : '5 4'"
              class="zone-ring"
            />
            <circle :cx="z.cx" :cy="z.cy" r="3.5" :fill="z.color" stroke="#fff" stroke-width="1.4" />
          </g>

          <g
            v-for="b in popupBoxes"
            :key="`popup-${b.key}`"
            class="popup"
            :class="{ dragging: dragState?.key === b.key }"
            @pointerdown="onPopupPointerDown(b, $event)"
            @pointermove="onPopupPointerMove(b, $event)"
            @pointerup="onPopupPointerUp(b, $event)"
            @pointercancel="onPopupPointerUp(b, $event)"
          >
            <line
              :x1="b.anchorX"
              :y1="b.anchorY"
              :x2="b.anchorX < b.x ? b.x : b.x + b.w"
              :y2="b.y + b.h / 2"
              :stroke="b.color"
              class="popup-link"
            />
            <rect
              :x="b.x" :y="b.y" :width="b.w" :height="b.h" rx="8"
              :stroke="b.color"
              class="popup-box"
            />
            <text :x="b.x + 9" :y="b.y + 15" class="popup-title" :fill="b.color">
              {{ b.title }}
            </text>
            <text :x="b.x + 9" :y="b.y + 29" class="popup-sub">{{ b.sub }}</text>
            <g class="popup-close" @pointerdown.stop @click.stop="closePopup(b.key)">
              <rect :x="b.x + b.w - 19" :y="b.y + 5" width="14" height="14" rx="4" class="popup-close-bg" />
              <text :x="b.x + b.w - 12" :y="b.y + 15.5" class="popup-close-x">×</text>
            </g>
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
        <span class="legend-item">팝업 기본 표시 · 동그라미 클릭으로 열기/닫기 · 팝업 드래그로 이동 가능</span>
      </div>
      <div class="footer-right">
        <span class="region-note">{{ region.label }} 기준 · 이벤트 {{ visibleZones.length }}개 영향권</span>
        <button
          v-if="openPopups.length"
          type="button"
          class="close-all"
          @click="closeAllPopups"
        >
          팝업 일괄 닫기 ({{ openPopups.length }})
        </button>
      </div>
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
.zone-clickable {
  cursor: pointer;
}
.popup-box {
  fill: rgba(255, 255, 255, 0.95);
  stroke-width: 1.2;
}
.popup {
  cursor: grab;
  user-select: none;
  touch-action: none;
}
.popup.dragging {
  cursor: grabbing;
}
/* 텍스트 위에서도 박스 드래그가 시작되도록 텍스트는 포인터 이벤트 제외 */
.popup text {
  pointer-events: none;
}
.popup-title {
  font-size: 11px;
  font-weight: 700;
}
.popup-sub {
  font-size: 11px;
  fill: var(--li-text-muted);
}
.popup-link {
  stroke-width: 1;
  stroke-dasharray: 2 2;
  opacity: 0.7;
  pointer-events: none;
}
.popup-close {
  cursor: pointer;
}
.popup-close-bg {
  fill: var(--li-bg-app-2);
  stroke: var(--li-border);
}
.popup-close:hover .popup-close-bg {
  fill: var(--li-risk-critical-bg);
}
.popup-close-x {
  font-size: 11px;
  font-weight: 700;
  fill: var(--li-text-muted);
  text-anchor: middle;
}
.footer-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.close-all {
  padding: 4px 12px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text-soft);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}
.close-all:hover {
  background: var(--li-surface-blue);
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
