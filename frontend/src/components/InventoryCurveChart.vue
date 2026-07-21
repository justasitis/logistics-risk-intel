<script setup lang="ts">
import { computed, ref } from 'vue'
import { INVENTORY_RISK_COLORS } from '../theme/inventoryRisk'
import type { InventoryRiskLevel, SimSeriesPoint } from '../types/inventory'

const props = defineProps<{
  seriesPlan: SimSeriesPoint[]
  seriesCurrent: SimSeriesPoint[]
  minLevel: number
  riskLevel: InventoryRiskLevel
  unit: string
}>()

// SVG 레이아웃 (viewBox 반응형)
const W = 640
const H = 260
const M = { top: 16, right: 16, bottom: 24, left: 52 }

const hoverDay = ref<number | null>(null)

const allPoints = computed(() => [...props.seriesPlan, ...props.seriesCurrent])

const yMax = computed(() => {
  const maxBal = Math.max(...allPoints.value.map((p) => p.balance), props.minLevel)
  return maxBal * 1.05
})
const yMin = computed(() => {
  const minBal = Math.min(...allPoints.value.map((p) => p.balance), 0)
  return minBal < 0 ? minBal * 1.1 : 0
})

const maxDay = computed(() => Math.max(...allPoints.value.map((p) => p.day), 1))

function x(day: number): number {
  return M.left + (day / maxDay.value) * (W - M.left - M.right)
}
function y(v: number): number {
  return M.top + ((yMax.value - v) / (yMax.value - yMin.value)) * (H - M.top - M.bottom)
}

function linePath(series: SimSeriesPoint[]): string {
  return series.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.day).toFixed(1)},${y(p.balance).toFixed(1)}`).join(' ')
}
function areaPath(series: SimSeriesPoint[]): string {
  const base = y(Math.max(yMin.value, 0))
  const last = series[series.length - 1]
  const lastX = last ? x(last.day) : x(0)
  return `${linePath(series)}L${lastX.toFixed(1)},${base}L${x(0).toFixed(1)},${base}Z`
}

const planPath = computed(() => linePath(props.seriesPlan))
const currentPath = computed(() => linePath(props.seriesCurrent))
const currentArea = computed(() => areaPath(props.seriesCurrent))

const riskColor = computed(() => INVENTORY_RISK_COLORS[props.riskLevel])

// 미니멈 하회 구간 음영 (일 단위 세그먼트)
const belowMinBands = computed(() => {
  const bands: { x: number; width: number }[] = []
  const cur = props.seriesCurrent
  for (let i = 0; i < cur.length; i++) {
    const p = cur[i]
    if (!p) continue
    if (p.balance < props.minLevel) {
      const next = cur[i + 1]
      const x0 = x(p.day)
      const x1 = next ? x(next.day) : x(p.day)
      bands.push({ x: x0, width: Math.max(x1 - x0, 2) })
    }
  }
  return bands
})

// 데이터 변경 시 곡선 그룹 페이드 전환 트리거
const signature = computed(() => `${props.riskLevel}:${props.seriesCurrent.length}:${props.seriesCurrent[props.seriesCurrent.length - 1]?.balance}`)

const hoverPoint = computed(() =>
  hoverDay.value === null ? null : props.seriesCurrent.find((p) => p.day === hoverDay.value) ?? null,
)
const hoverPlanPoint = computed(() =>
  hoverDay.value === null ? null : props.seriesPlan.find((p) => p.day === hoverDay.value) ?? null,
)

function onMove(e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const px = ((e.clientX - rect.left) / rect.width) * W
  const step = (W - M.left - M.right) / maxDay.value
  const day = Math.round((px - M.left) / step)
  hoverDay.value = Math.max(0, Math.min(maxDay.value, day))
}
function onLeave() {
  hoverDay.value = null
}
</script>

<template>
  <div class="chart-wrap">
    <svg
      :viewBox="`0 0 ${W} ${H}`"
      class="chart"
      role="img"
      aria-label="재고 곡선 시뮬레이션 차트"
      @mousemove="onMove"
      @mouseleave="onLeave"
    >
      <defs>
        <linearGradient id="inv-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="riskColor" stop-opacity="0.28" />
          <stop offset="100%" :stop-color="riskColor" stop-opacity="0.02" />
        </linearGradient>
      </defs>

      <rect
        v-for="(b, i) in belowMinBands"
        :key="`band-${i}`"
        :x="b.x"
        :y="M.top"
        :width="b.width"
        :height="H - M.top - M.bottom"
        fill="rgba(239, 68, 68, 0.07)"
      />

      <line :x1="M.left" :x2="W - M.right" :y1="y(minLevel)" :y2="y(minLevel)" class="min-line" />
      <text :x="W - M.right" :y="y(minLevel) - 4" class="min-label" text-anchor="end">
        미니멈 {{ minLevel.toLocaleString() }}
      </text>

      <line v-if="yMin < 0" :x1="M.left" :x2="W - M.right" :y1="y(0)" :y2="y(0)" class="zero-line" />

      <g :key="signature" class="curves">
        <path :d="currentArea" fill="url(#inv-area)" />
        <path :d="planPath" class="plan-line" />
        <path :d="currentPath" :stroke="riskColor" class="current-line" />
      </g>

      <template v-if="hoverPoint">
        <line
          :x1="x(hoverPoint.day)"
          :x2="x(hoverPoint.day)"
          :y1="M.top"
          :y2="H - M.bottom"
          class="crosshair"
        />
        <circle :cx="x(hoverPoint.day)" :cy="y(hoverPoint.balance)" r="4" :fill="riskColor" />
        <circle
          v-if="hoverPlanPoint"
          :cx="x(hoverPlanPoint.day)"
          :cy="y(hoverPlanPoint.balance)"
          r="4"
          class="plan-dot"
        />
      </template>
    </svg>

    <div v-if="hoverPoint" class="tooltip" :style="{ left: `${(x(hoverPoint.day) / W) * 100}%` }">
      <div class="tt-date">{{ hoverPoint.date }} (D+{{ hoverPoint.day }})</div>
      <div class="tt-row">
        <span class="tt-swatch" :style="{ background: riskColor }"></span>현실
        {{ hoverPoint.balance.toLocaleString() }}{{ unit }}
      </div>
      <div v-if="hoverPlanPoint" class="tt-row">
        <span class="tt-swatch plan"></span>계획 {{ hoverPlanPoint.balance.toLocaleString() }}{{ unit }}
      </div>
    </div>

    <div class="legend">
      <span><span class="tt-swatch" :style="{ background: riskColor }"></span>현실 (ETA 현재값)</span>
      <span><span class="tt-swatch plan"></span>계획 (ETA 계획값)</span>
    </div>
  </div>
</template>

<style scoped>
.chart-wrap {
  position: relative;
}
.chart {
  width: 100%;
  height: auto;
  display: block;
}
.min-line {
  stroke: var(--li-risk-critical);
  stroke-dasharray: 4 4;
  stroke-width: 1;
}
.min-label {
  font-size: 12px;
  fill: var(--li-risk-critical);
}
.zero-line {
  stroke: var(--li-border-strong);
  stroke-width: 1;
}
.curves {
  animation: curve-in 0.35s ease-out;
}
@keyframes curve-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.plan-line {
  fill: none;
  stroke: var(--li-text-faint);
  stroke-width: 1.5;
  stroke-dasharray: 5 4;
}
.current-line {
  fill: none;
  stroke-width: 2;
}
.crosshair {
  stroke: var(--li-text-muted);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}
.plan-dot {
  fill: var(--li-text-faint);
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
.tt-swatch {
  display: inline-block;
  width: 10px;
  height: 3px;
  border-radius: 2px;
}
.tt-swatch.plan {
  background: var(--li-text-faint);
}
.legend {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--li-text-muted);
  margin-top: 4px;
}
.legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
