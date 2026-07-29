<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getFreightIndices } from '../services/freightApi'
import type { FreightPoint, FreightSeries } from '../types/routeMaster'

const emit = defineEmits<{ loaded: [series: FreightSeries[] | null] }>()

const series = ref<FreightSeries[] | null>(null)
const missing = ref(false)
const error = ref('')

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

// ---------- 날짜 → 주차 변환 (명세: 주차 = ceil(연중 일수 / 7), 1~53) ----------
function weekOfYear(isoDate: string): number {
  const d = new Date(`${isoDate}T00:00:00`)
  const start = new Date(d.getFullYear(), 0, 1)
  const dayOfYear = Math.floor((d.getTime() - start.getTime()) / 86_400_000) + 1
  return Math.ceil(dayOfYear / 7)
}

interface WeekLine {
  key: string
  label: string
  color: string
  dash: boolean
  weeks: (number | null)[]
}
interface WeekChart {
  title: string
  lines: WeekLine[]
}

const YEAR_COLORS = ['#94a3b8', '#06b6d4', '#2563eb', '#f97316', '#10b981', '#8b5cf6']
const WEEK_COUNT = 53

function yearColor(index: number): string {
  return YEAR_COLORS[index % YEAR_COLORS.length] ?? '#2563eb'
}

function buildLines(targetSeries: FreightSeries[]): WeekLine[] {
  const years = [...new Set(
    targetSeries.flatMap((s) => s.points.map((p) => p.date.slice(0, 4))),
  )].sort()
  const lines: WeekLine[] = []
  for (const s of targetSeries) {
    for (const year of years) {
      const points = s.points.filter((p) => p.date.startsWith(year))
      if (!points.length) continue
      const weeks: (number | null)[] = Array.from({ length: WEEK_COUNT }, () => null)
      for (const p of points) {
        const w = weekOfYear(p.date)
        if (w >= 1 && w <= WEEK_COUNT) weeks[w - 1] = p.value
      }
      lines.push({
        key: `${s.key}-${year}`,
        label: `${s.label} ${year}`,
        color: yearColor(years.indexOf(year)),
        dash: targetSeries.length > 1 && s !== targetSeries[0],
        weeks,
      })
    }
  }
  return lines
}

const charts = computed<WeekChart[]>(() => {
  const all = series.value ?? []
  const byKey = (keys: string[]) => all.filter((s) => keys.includes(s.key))
  const left = buildLines(byKey(['scfi', 'kcci']))
  const right = buildLines(byKey(['kcci_usec', 'kcci_med']))
  const out: WeekChart[] = []
  if (left.length) out.push({ title: 'SCFI + KCCI 종합 (주차별)', lines: left })
  if (right.length) out.push({ title: 'KCCI 세부항로 (주차별)', lines: right })
  // 키가 다륵게 들어오는 경우 전체를 하나로 폴�
  if (!out.length && all.length) {
    out.push({ title: '운임지수 (주차별)', lines: buildLines(all) })
  }
  return out
})

// ---------- 스케일 ----------
const W = 460
const H = 220
const M = { top: 14, right: 10, bottom: 24, left: 52 }

function x(week: number): number {
  return M.left + ((week - 1) / (WEEK_COUNT - 1)) * (W - M.left - M.right)
}

function chartYMax(chart: WeekChart): number {
  let max = 0
  for (const line of chart.lines) {
    for (const v of line.weeks) if (v !== null) max = Math.max(max, v)
  }
  return max > 0 ? max * 1.08 : 1
}

function yOf(max: number, v: number): number {
  return M.top + (1 - v / max) * (H - M.top - M.bottom)
}

function linePath(max: number, weeks: (number | null)[]): string {
  let d = ''
  let started = false
  weeks.forEach((v, i) => {
    if (v === null) return
    d += `${started ? 'L' : 'M'}${x(i + 1).toFixed(1)},${yOf(max, v).toFixed(1)}`
    started = true
  })
  return d
}

// ---------- 호버 ----------
const hoverWeek = ref<{ chartIndex: number; week: number } | null>(null)

function onMove(chartIndex: number, e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const px = ((e.clientX - rect.left) / rect.width) * W
  const step = (W - M.left - M.right) / (WEEK_COUNT - 1)
  const week = Math.round((px - M.left) / step) + 1
  hoverWeek.value = {
    chartIndex,
    week: Math.max(1, Math.min(WEEK_COUNT, week)),
  }
}

const weekTicks = [1, 8, 16, 24, 32, 40, 48, 53]

const chartsRef = ref<HTMLElement | null>(null)

/** HTML 낙출력용 인라인 SVG 묶음 */
function getSvgHtml(): string {
  return chartsRef.value?.innerHTML ?? ''
}
defineExpose({ getSvgHtml })
</script>

<template>
  <section class="freight">
    <div class="freight-head">
      <h3 class="title">시황 (운임지수, USD/40' — 주차별 연도 비교)</h3>
    </div>

    <p v-if="missing" class="hint">운임지수 파일 없음 — 시황 데이터가 준비되면 표시됩니다.</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <div v-if="charts.length" ref="chartsRef" class="split">
      <div v-for="(chart, ci) in charts" :key="chart.title" class="chart-box">
        <div class="chart-title">{{ chart.title }}</div>
        <div class="legend">
          <span v-for="line in chart.lines" :key="line.key" class="legend-item">
            <span
              class="swatch"
              :style="{
                background: line.dash
                  ? `repeating-linear-gradient(90deg, ${line.color} 0 4px, transparent 4px 7px)`
                  : line.color,
              }"
            ></span>
            {{ line.label }}
          </span>
        </div>
        <div class="chart-wrap">
          <svg
            :viewBox="`0 0 ${W} ${H}`"
            class="chart"
            role="img"
            :aria-label="chart.title"
            @mousemove="onMove(ci, $event)"
            @mouseleave="hoverWeek = null"
          >
            <line :x1="M.left" :x2="W - M.right" :y1="yOf(chartYMax(chart), 0)" :y2="yOf(chartYMax(chart), 0)" class="axis" />
            <text
              v-for="w in weekTicks"
              :key="w"
              :x="x(w)"
              :y="H - 8"
              class="x-label"
              text-anchor="middle"
            >{{ w }}W</text>

            <path
              v-for="line in chart.lines"
              :key="line.key"
              :d="linePath(chartYMax(chart), line.weeks)"
              fill="none"
              :stroke="line.color"
              :stroke-dasharray="line.dash ? '5 4' : undefined"
              stroke-width="1.8"
            />

            <line
              v-if="hoverWeek && hoverWeek.chartIndex === ci"
              :x1="x(hoverWeek.week)"
              :x2="x(hoverWeek.week)"
              :y1="M.top"
              :y2="H - M.bottom"
              class="crosshair"
            />
          </svg>

          <div
            v-if="hoverWeek && hoverWeek.chartIndex === ci"
            class="tooltip"
            :style="{ left: `${(x(hoverWeek.week) / W) * 100}%` }"
          >
            <div class="tt-date">{{ hoverWeek.week }}W</div>
            <div v-for="line in chart.lines" :key="line.key" class="tt-row">
              <span class="swatch" :style="{ background: line.color }"></span>
              {{ line.label }}
              {{ line.weeks[hoverWeek.week - 1]?.toLocaleString() ?? '-' }}
            </div>
          </div>
        </div>
      </div>
    </div>
    <p v-else-if="series" class="hint">표시할 시리즈가 없습니다.</p>
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
.title {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--li-text);
}
.split {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.chart-box {
  flex: 1;
  min-width: 320px;
}
.chart-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--li-text-soft);
  margin-bottom: 4px;
}
.legend {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--li-text-muted);
  margin-bottom: 4px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}
.swatch {
  display: inline-block;
  width: 12px;
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
  z-index: 10;
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
