<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getEtaAtaGap } from '../services/leadtimeApi'
import type { EtaAtaGapResponse, GapGroupSummary, GapLevel } from '../types/gap'

const gap = ref<EtaAtaGapResponse | null>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    gap.value = await getEtaAtaGap()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Gap 집계 조회 실패'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const LEVEL_LABELS: Record<GapLevel, string> = {
  OK: '정상',
  WATCH: '주의',
  WARN: '경고',
}

const REGION_ORDER = ['유럽', '미주', '아시아']

interface RegionGroup {
  name: string
  groups: GapGroupSummary[]
}

const regionGroups = computed<RegionGroup[]>(() => {
  if (!gap.value) return []
  const byRegion = new Map<string, GapGroupSummary[]>()
  for (const group of gap.value.groups) {
    const region = group.region || '기타'
    if (!byRegion.has(region)) byRegion.set(region, [])
    byRegion.get(region)?.push(group)
  }
  return [...byRegion.entries()]
    .sort((a, b) => {
      const ia = REGION_ORDER.indexOf(a[0])
      const ib = REGION_ORDER.indexOf(b[0])
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
    })
    .map(([name, groups]) => ({ name, groups }))
})

const weekKeys = computed<string[]>(() =>
  (gap.value?.overall.weekly ?? []).map((w) => w.week),
)

function weekOf(group: GapGroupSummary, week: string) {
  return group.weekly.find((w) => w.week === week)
}

function formatGap(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value > 0 ? `+${value}` : String(value)
}

function gapClass(value: number | null | undefined): string {
  if (value === null || value === undefined) return ''
  if (value > (gap.value?.params.warn_days ?? 5)) return 'bad'
  if (value > 0) return 'mid'
  return 'good'
}
</script>

<template>
  <div class="gap-pane">
    <section class="hero">
      <div>
        <p class="eyebrow">ETA vs ATA GAP</p>
        <h2 class="hero-title">지연 추이 (ETA-ATA Gap)</h2>
        <p v-if="gap" class="hero-meta">
          Gap = ATA − ETA(최신 계획) · 주차별 집계 · 생성 {{ gap.generated_at }}
        </p>
      </div>
      <button class="btn" :disabled="loading" @click="load">
        {{ loading ? '집계 중...' : '새로고침' }}
      </button>
    </section>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="gap">
      <div class="kpi-grid">
        <div class="kpi-card kpi-blue">
          <div class="kpi-label">전체 최근 주 평균 Gap</div>
          <div class="kpi-value">
            {{ formatGap(gap.overall.latest_avg_gap) }}<span class="kpi-unit">일</span>
          </div>
          <div class="kpi-sub">{{ gap.params.current_week }}(당주) 제외, 완료 주 기준</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">연속 증가</div>
          <div class="kpi-value">{{ gap.overall.consecutive_increases }}<span class="kpi-unit">주</span></div>
          <div class="kpi-sub">기울기 {{ gap.overall.slope_per_week }}일/주</div>
        </div>
        <div class="kpi-card" :class="`level-${gap.overall.level.toLowerCase()}`">
          <div class="kpi-label">전체 판정</div>
          <div class="kpi-value">{{ LEVEL_LABELS[gap.overall.level] }}</div>
          <div class="kpi-sub">{{ gap.overall.level_reasons.join(' · ') || '기준 이내' }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">판정 기준</div>
          <div class="kpi-value kpi-text">
            주의: {{ gap.params.watch_consecutive }}주 연속 증가<br />
            경고: 평균 Gap &gt; {{ gap.params.warn_days }}일
          </div>
        </div>
      </div>

      <section v-for="region in regionGroups" :key="region.name" class="panel">
        <div class="panel-head">
          <h3 class="panel-title">{{ region.name }} 권역</h3>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>항로</th>
                <th>판정</th>
                <th v-for="w in weekKeys" :key="w" :class="{ current: w === gap.params.current_week }">
                  {{ w.slice(5) }}
                  <span v-if="w === gap.params.current_week" class="current-note">진행중</span>
                </th>
                <th>추세</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="group in region.groups" :key="group.group_id">
                <tr>
                  <td class="group-name" rowspan="2">{{ group.name }}</td>
                  <td rowspan="2">
                    <span class="level-badge" :class="`level-${group.level.toLowerCase()}`">
                      {{ LEVEL_LABELS[group.level] }}
                    </span>
                    <div v-if="group.level_reasons.length" class="reasons">
                      {{ group.level_reasons.join(' · ') }}
                    </div>
                  </td>
                  <td
                    v-for="w in weekKeys"
                    :key="w"
                    class="num"
                    :class="gapClass(weekOf(group, w)?.avg_gap)"
                  >
                    {{ formatGap(weekOf(group, w)?.avg_gap) }}
                  </td>
                  <td class="trend" rowspan="2">
                    {{ group.consecutive_increases }}주 연속 증가 · {{ group.slope_per_week }}일/주
                  </td>
                </tr>
                <tr class="sub-row">
                  <td v-for="w in weekKeys" :key="w" class="num sub">
                    <template v-if="weekOf(group, w)?.count">
                      지연 {{ weekOf(group, w)?.delayed_count }}/{{ weekOf(group, w)?.count }}
                    </template>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel definitions">
        <div class="panel-head">
          <h3 class="panel-title">정의</h3>
        </div>
        <ul>
          <li v-for="(text, key) in gap.definitions" :key="key">{{ text }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.gap-pane {
  max-width: 1160px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 20px 22px;
  border-radius: var(--li-radius-lg);
  background: linear-gradient(135deg, #1e3a8a 0%, var(--li-blue) 55%, var(--li-cyan) 100%);
  box-shadow: var(--li-shadow-float);
  color: #fff;
}
.eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: rgba(255, 255, 255, 0.85);
}
.hero-title {
  margin: 0;
  font-size: 19px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: #fff;
}
.hero-meta {
  margin: 8px 0 0;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.82);
}
.btn {
  padding: 7px 14px;
  border: 1px solid rgba(255, 255, 255, 0.34);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 980px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.kpi-card {
  min-height: 96px;
  padding: 14px 16px;
  border-radius: var(--li-radius-md);
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  box-shadow: var(--li-shadow-card);
}
.kpi-blue {
  background: var(--li-accent-gradient-soft), var(--li-surface-strong);
  border-color: rgba(37, 99, 235, 0.22);
}
.kpi-card.level-watch {
  border-color: var(--li-risk-high-border);
  background: var(--li-risk-high-bg), var(--li-surface-strong);
}
.kpi-card.level-warn {
  border-color: var(--li-risk-critical-border);
  background: var(--li-risk-critical-bg), var(--li-surface-strong);
}
.kpi-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--li-text-muted);
}
.kpi-value {
  margin-top: 8px;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--li-text);
}
.kpi-value.kpi-text {
  font-size: 12px;
  line-height: 1.5;
  letter-spacing: 0;
}
.kpi-unit {
  font-size: 12px;
  font-weight: 600;
  color: var(--li-text-muted);
  margin-left: 3px;
}
.kpi-sub {
  margin-top: 4px;
  font-size: 11px;
  color: var(--li-text-faint);
}
.panel {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-lg);
  padding: 16px 18px;
  box-shadow: var(--li-shadow-card);
}
.panel-head {
  margin-bottom: 10px;
}
.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--li-text);
}
.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  padding: 6px 8px;
  text-align: center;
  color: var(--li-text);
  border-bottom: 1px solid var(--li-border);
  border-right: 1px solid var(--li-border);
}
tr:last-child td {
  border-bottom: none;
}
th:last-child,
td:last-child {
  border-right: none;
}
th {
  background: var(--li-bg-app-2);
  color: var(--li-text-soft);
  font-size: 11px;
  font-weight: 800;
}
th.current {
  background: var(--li-surface-blue);
  color: var(--li-blue);
}
.current-note {
  display: block;
  font-size: 11px;
  font-weight: 400;
}
td.group-name {
  text-align: left;
  font-weight: 700;
  background: var(--li-bg-app-2);
}
.num {
  font-weight: 600;
}
.num.bad {
  color: var(--li-risk-critical);
}
.num.mid {
  color: var(--li-risk-high);
}
.num.good {
  color: var(--li-risk-low);
}
.sub-row td {
  border-top: none;
}
.num.sub {
  font-weight: 400;
  font-size: 11px;
  color: var(--li-text-muted);
}
td.trend {
  font-size: 11px;
  color: var(--li-text-muted);
  white-space: nowrap;
}
.level-badge {
  display: inline-block;
  padding: 1px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid transparent;
}
.level-badge.level-ok {
  background: var(--li-risk-low-bg);
  color: var(--li-risk-low);
  border-color: var(--li-risk-low-border);
}
.level-badge.level-watch {
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border-color: var(--li-risk-high-border);
}
.level-badge.level-warn {
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
  border-color: var(--li-risk-critical-border);
}
.reasons {
  margin-top: 4px;
  font-size: 11px;
  color: var(--li-text-muted);
  max-width: 180px;
  text-align: left;
}
.definitions ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--li-text-muted);
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>
