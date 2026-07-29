<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getFreightIndices } from '../services/freightApi'
import type { FreightSeries } from '../types/routeMaster'

const emit = defineEmits<{ loaded: [series: FreightSeries[] | null] }>()

const series = ref<FreightSeries[] | null>(null)
const missing = ref(false)
const error = ref('')
const svgRef = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)

const W = 720
const H = 240
const M = { top: 14, right: 16, bottom: 26, left: 56 }
const COLORS = ['#2563eb', '#06b6d4', '#f97316', '#10b981', '#8b5cf6', '#ef4444']

onMounted(async () => {
  try {
    const result = await getFreightIndices()
    if (result === null || !result.series.length) {
      missing.value = true
      series.value = null
      emit('loaded', null)
      return
    }
    series.value = result.series
    emit('loaded', result.series)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '운임지수 조회 실패'
  }
})

// 모든 시리즈의 날짜를 정렬 유니크로 합침 (x축 공유)
const dates = computed(() => {
  const all = new Set<string>()
  for (const s of series.value ?? []) for (const p of s.points) all.add(p.date)
  return [...all].sort()
})

const yMax = computed(() => {
  let max = 0
  for (const s of series.value ?? []) for (const p of s.points) max = Math.max(max, p.value)
  return max > 0 ? max * 1.08 : 1
})

function x(date: string): number {
  const idx = dates.value.indexOf(date)
  const n = Math.max(dates.value.length - 1, 1)
  return M.left + (idx / n) * (W - M.left - M.right)
}
function y(v: number): number {
  return M.top + (1 - v / yMax.value) * (H - M.top - M.bottom)
}

function seriesPath(s: FreightSeries): string {
  return s.points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`)
    .join(' ')
}

function seriesColor(index: number): string {
  return COLORS[index % COLORS.length] ?? '#2563eb'
}

// x축 연도 라벨 (연도가 바뀌는 첫 지점)
const yearTicks = computed(() => {
  const ticks: { date: string; year: string }[] = []
  let prevYear = ''
  for (const d of dates.value) {
    const year = d.slice(0, 4)
    if (year !== prevYear) {
      ticks.push({ date: d, year })
      prevYear = year
    }
  }
  return ticks
})

function latestPoint(s: FreightSeries) {
  return s.points.length ? s.points[s.points.length - 1] : null
}

// 최신값 강조 점 (null 안전 좌표 사전 계산)
const latestDots = computed(() =>
  (series.value ?? [])
    .map((s, i) => {
      const point = latestPoint(s)
      return point
        ? { key: s.key, cx: x(point.date), cy: y(point.value), color: seriesColor(i) }
        : null
    })
    .filter((d): d is { key: string; cx: number; cy: number; color: string } => d !== null),
)

const hoverDate = computed(() =>
  hoverIndex.value === null ? null : dates.value[hoverIndex.value] ?? null,
)

function valueAt(s: FreightSeries, date: string): number | null {
  const point = s.points.find((p) => p.date === date)
  return point ? point.value : null
}

function onMove(e: MouseEvent) {
  if (!dates.value.length) return
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const px = ((e.clientX - rect.left) / rect.width) * W
  const step = (W - M.left - M.right) / Math.max(dates.value.length - 1, 1)
  const idx = Math.round((px - M.left) / step)
  hoverIndex.value = Math.max(0, Math.min(dates.value.length - 1, idx))
}

/** HTML 낙출력용 인라인 SVG */
function getSvgHtml(): string {
  return svgRef.value?.outerHTML ?? ''
}
defineExpose({ getSvgHtml })
</script>

<template>
  <section class="freight">
    <div class="freight-head">
      <h3 class="title">시황 (운임지수, USD/40')</h3>
      <div v-if="series" class="legend">
        <span v-for="(s, i) in series" :key="s.key" class="legend-item">
          <span class="swatch" :style="{ background: seriesColor(i) }"></span>
          {{ s.label }}
          <b v-if="latestPoint(s)">{{ latestPoint(s)?.value.toLocaleString() }}</b>
        </span>
      </div>
    </div>

    <p v-if="missing" class="hint">운임지수 파일 없음 — 시황 데이터가 준비되면 표시됩니다.</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-if="series">
      <div class="chart-wrap">
        <svg
          ref="svgRef"
          :viewBox="`0 0 ${W} ${H}`"
          class="chart"
          role="img"
          aria-label="운임지수 추이 차트"
          @mousemove="onMove"
          @mouseleave="hoverIndex = null"
        >
          <line :x1="M.left" :x2="W - M.right" :y1="y(0)" :y2="y(0)" class="axis" />
          <text :x="M.left - 6" :y="y(yMax / 1.08)" class="y-label" text-anchor="end">
            {{ Math.round(yMax / 1.08).toLocaleString() }}
          </text>
          <text
            v-for="tick in yearTicks"
            :key="tick.date"
            :x="x(tick.date)"
            :y="H - 8"
            class="x-label"
            text-anchor="middle"
          >
            {{ tick.year }}
          </text>

          <path
            v-for="(s, i) in series"
            :key="s.key"
            :d="seriesPath(s)"
            fill="none"
            :stroke="seriesColor(i)"
            stroke-width="2"
          />
          <circle
            v-for="dot in latestDots"
            :key="`latest-${dot.key}`"
            :cx="dot.cx"
            :cy="dot.cy"
            r="4"
            :fill="dot.color"
          />

          <line
            v-if="hoverDate"
            :x1="x(hoverDate)"
            :x2="x(hoverDate)"
            :y1="M.top"
            :y2="H - M.bottom"
            class="crosshair"
          />
        </svg>

        <div v-if="hoverDate" class="tooltip" :style="{ left: `${(x(hoverDate) / W) * 100}%` }">
          <div class="tt-date">{{ hoverDate }}</div>
          <div v-for="(s, i) in series" :key="s.key" class="tt-row">
            <span class="swatch" :style="{ background: seriesColor(i) }"></span>
            {{ s.label }} {{ valueAt(s, hoverDate)?.toLocaleString() ?? '-' }}
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.freight {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 14px;
  box-shadow: var(--li-shadow-card);
}
.freight-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.title {
  margin: 0;
  font-size: 13px;
  color: var(--li-text);
}
.legend {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--li-text-muted);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.swatch {
  display: inline-block;
  width: 10px;
  height: 3px;
  border-radius: 2px;
}
.chart-wrap {
  position: relative;
}
.chart {
  width: 100%;
  height: auto;
  display: block;
}
.axis {
  stroke: var(--li-border-strong);
}
.y-label,
.x-label {
  font-size: 12px;
  fill: var(--li-text-muted);
}
.crosshair {
  stroke: var(--li-text-muted);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}
.tooltip {
  position: absolute;
  top: 8px;
  transform: translateX(-50%);
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  padding: 6px 10px;
  font-size: 12px;
  pointer-events: none;
  white-space: nowrap;
  box-shadow: var(--li-shadow-card);
}
.tt-date {
  font-weight: 700;
  margin-bottom: 2px;
}
.tt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--li-text);
}
.hint {
  color: var(--li-text-muted);
  font-size: 12px;
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>
