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
  const usec = buildLines(byKey(['kcci_usec']))
  const med = buildLines(byKey(['kcci_med']))
  const out: WeekChart[] = []
  if (left.length) out.push({ title: 'SCFI + KCCI 종합 (주차별)', lines: left })
  if (usec.length) out.push({ title: 'KCCI 북미 동안 (주차별)', lines: usec })
  if (med.length) out.push({ title: 'KCCI 지중해 (주차별)', lines: med })
  // 키가 다륵게 들어오는 경우 전체를 하나로 폴�
  if (!out.length && all.length) {
    out.push({ title: '운임지수 (주차별)', lines: buildLines(all) })
  }
  return out
})

// ---------- 시황 수치 요약 (최신값 + MoM/YoY) ----------
interface FreightStat {
  key: string
  label: string
  latestDate: string
  latestValue: number
  mom: number | null // %
  yoy: number | null // %
}

/** 기준일(daysBack 전) 이하의 가장 최근 포인트 대비 증감률(%) */
function pctChange(pts: FreightPoint[], latest: FreightPoint, daysBack: number): number | null {
  const target = new Date(`${latest.date}T00:00:00`)
  target.setDate(target.getDate() - daysBack)
  const targetIso = target.toISOString().slice(0, 10)
  let ref: FreightPoint | null = null
  for (const p of pts) {
    if (p.date <= targetIso) ref = p
    else break
  }
  if (!ref || ref.value === 0) return null
  return Math.round(((latest.value - ref.value) / ref.value) * 1000) / 10
}

const stats = computed<FreightStat[]>(() => {
  const out: FreightStat[] = []
  for (const s of series.value ?? []) {
    const pts = [...s.points].sort((a, b) => a.date.localeCompare(b.date))
    const latest = pts[pts.length - 1]
    if (!latest) continue
    out.push({
      key: s.key,
      label: s.label,
      latestDate: latest.date,
      latestValue: latest.value,
      mom: pctChange(pts, latest, 30),
      yoy: pctChange(pts, latest, 365),
    })
  }
  return out
})

function formatPct(value: number | null): string {
  if (value === null) return '-'
  if (value === 0) return '0%'
  return `${value > 0 ? '▲' : '▼'}${Math.abs(value)}%`
}

/** 운임 상승 = 비용 증가(악화) → up, 하락 = down */
function chipClass(value: number | null): string {
  if (value === null || value === 0) return 'flat'
  return value > 0 ? 'up' : 'down'
}

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
      <p class="eyebrow">MARKET WATCH</p>
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
            <line
              v-for="w in weekTicks"
              :key="`grid-${w}`"
              :x1="x(w)"
              :x2="x(w)"
              :y1="M.top"
              :y2="H - M.bottom"
              class="grid-line"
            />
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

    <div v-if="stats.length" class="stat-grid">
      <div v-for="s in stats" :key="s.key" class="stat-card">
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-value">{{ s.latestValue.toLocaleString() }}</div>
        <div class="stat-date">{{ s.latestDate }} 기준</div>
        <div class="stat-chips">
          <span class="chip" :class="chipClass(s.mom)">MoM {{ formatPct(s.mom) }}</span>
          <span class="chip" :class="chipClass(s.yoy)">YoY {{ formatPct(s.yoy) }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.freight {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-lg);
  padding: 16px 18px;
  box-shadow: var(--li-shadow-card);
}
.eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: var(--li-blue);
}
.title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 800;
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
.grid-line {
  stroke: var(--li-border);
  stroke-width: 1;
  stroke-dasharray: 3 4;
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
.stats {
  margin-top: 10px;
  border-collapse: collapse;
  font-size: 12px;
  width: 100%;
}
.stats th,
.stats td {
  border: 1px solid var(--li-border-strong);
  padding: 4px 8px;
  text-align: center;
  color: var(--li-text);
}
.stats th {
  background: var(--li-bg-app-2);
}
.stats td.stat-label {
  text-align: left;
  font-weight: 700;
}
.stat-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 980px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.stat-card {
  padding: 12px 14px;
  border-radius: var(--li-radius-md);
  background: var(--li-surface);
  border: 1px solid var(--li-border);
  box-shadow: var(--li-shadow-card);
}
.stat-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--li-text-muted);
}
.stat-value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--li-text);
}
.stat-date {
  margin-top: 2px;
  font-size: 11px;
  color: var(--li-text-faint);
}
.stat-chips {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.chip {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid transparent;
}
.chip.up {
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
  border-color: var(--li-risk-critical-border);
}
.chip.down {
  background: var(--li-risk-low-bg);
  color: var(--li-risk-low);
  border-color: var(--li-risk-low-border);
}
.chip.flat {
  background: var(--li-bg-app-2);
  color: var(--li-text-muted);
  border-color: var(--li-border);
}
</style>
