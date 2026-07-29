<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  deleteLeadtimeOverrides,
  getLeadtimeReport,
  putLeadtimeOverrides,
} from '../services/leadtimeApi'
import type {
  InsightDraftResponse,
  LeadtimeGroup,
  LeadtimeReport,
  LeadtimeRow,
} from '../types/leadtime'
import FreightIndicesChart from './FreightIndicesChart.vue'
import MiInsightDraftPanel from './MiInsightDraftPanel.vue'

const freightChart = ref<InstanceType<typeof FreightIndicesChart> | null>(null)

const report = ref<LeadtimeReport | null>(null)
const insight = ref<InsightDraftResponse | null>(null)
const loading = ref(false)
const error = ref('')

// 셀 수동 편집 (서버 override 파일에 명시 저장)
const editMode = ref(false)
const editValues = ref<Record<string, string>>({})
const savingCells = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await getLeadtimeReport()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '리포트 조회 실패'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function cellKey(groupId: string, country: string, stat: string, month: string): string {
  return `${groupId}|${country}|${stat}|${month}`
}

function isEdited(key: string): boolean {
  return (report.value?.edited_cells ?? []).includes(key)
}

function onCellInput(key: string, e: Event) {
  editValues.value[key] = (e.target as HTMLInputElement).value
}

async function saveCells() {
  const overrides: Record<string, number> = {}
  for (const [key, value] of Object.entries(editValues.value)) {
    const num = Number(value)
    if (value.trim() !== '' && Number.isFinite(num)) overrides[key] = num
  }
  savingCells.value = true
  error.value = ''
  try {
    if (Object.keys(overrides).length) await putLeadtimeOverrides(overrides)
    editValues.value = {}
    editMode.value = false
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '편집값 저장 실패'
  } finally {
    savingCells.value = false
  }
}

async function resetCells() {
  savingCells.value = true
  error.value = ''
  try {
    await deleteLeadtimeOverrides()
    editValues.value = {}
    editMode.value = false
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '편집값 초기화 실패'
  } finally {
    savingCells.value = false
  }
}

const STATS = ['Avg', 'Min', 'Max'] as const

interface CountryBlock {
  country: string
  label: string
  fixed: boolean
  rowsByStat: Record<string, LeadtimeRow | undefined>
}

/** 그룹의 행을 국가(또는 고정 행) 단위 블록으로 묶기 — 고정 행(훼리 등) 포함 범용 처리 */
function countryBlocks(group: LeadtimeGroup): CountryBlock[] {
  const blocks: CountryBlock[] = []
  for (const row of group.rows) {
    let block = blocks.find((b) => b.country === row.country)
    if (!block) {
      block = {
        country: row.country,
        label: row.country_label,
        fixed: row.fixed === true,
        rowsByStat: {},
      }
      blocks.push(block)
    }
    block.rowsByStat[row.stat] = row
  }
  return blocks
}

function rowCellText(row: LeadtimeRow | undefined, month: string): string {
  const value = row?.cells[month]
  return value === undefined ? '' : String(value)
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function doPrint() {
  window.print()
}

/** 현재 리포트를 단독 HTML 파일로 낙출력 (메일/SharePoint 배포용) */
function exportHtml() {
  if (!report.value) return
  const r = report.value
  const sections = r.groups
    .map((g) => {
      const head = r.month_columns
        .map((m) => `<th class="${m.kind}">${m.label}</th>`)
        .join('')
      const body = countryBlocks(g).map((block) => {
        const rows = STATS.map((stat, i) => {
          const cells = r.month_columns
            .map((m) => `<td class="${m.kind}">${escapeHtml(rowCellText(block.rowsByStat[stat], m.key))}</td>`)
            .join('')
          const labelCell = i === 0
            ? `<td rowspan="3">${escapeHtml(block.label)}${block.fixed ? ' (고정값)' : ''}</td>`
            : ''
          return `<tr>${labelCell}<td>${stat}</td>${cells}</tr>`
        })
        return rows.join('')
      }).join('')
      return `<h2>${escapeHtml(g.name)}</h2><table><thead><tr><th>국가</th><th>구분</th>${head}</tr></thead><tbody>${body}</tbody></table>`
    })
    .join('')
  const defs = Object.values(r.definitions).map((d) => `<li>${escapeHtml(d)}</li>`).join('')
  const insightHtml = (() => {
    const draft = insight.value
    if (!draft) return ''
    const sectionsHtml = draft.draft.sections
      .map((s) => `<h2>${escapeHtml(s.title)}</h2><p>${escapeHtml(s.body)}</p>`)
      .join('')
    const points = draft.draft.monitoring_points
      .map((p) => `<li>${escapeHtml(p)}</li>`)
      .join('')
    return `<h1>월간 인사이트 (${escapeHtml(draft.month)})</h1>
<p class="meta">AI 생성 검토용 초안 · 생성 ${escapeHtml(draft.generated_at)}</p>
${sectionsHtml}
<h2>모니터링 포인트</h2><ul>${points}</ul>
<p class="meta">${escapeHtml(draft.draft.disclaimer)}</p>
<hr>`
  })()
  const html = `<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>물류 MI Report — 항로별 리드타임</title>
<style>
body{font-family:'Malgun Gothic',sans-serif;margin:24px;color:#122033}
h1{font-size:18px}h2{font-size:14px;margin-top:24px}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{border:1px solid #bcccdc;padding:5px 8px;text-align:center}
th{background:#f0f4f8}td.forecast,th.forecast{background:#dbeafe}
.meta{color:#607086;font-size:11px;margin:8px 0}
ul{font-size:11px;color:#607086}
</style></head><body>
<h1>물류 MI Report — 항로별 리드타임</h1>
<p class="meta">조회 시점 기준 자동 집계 · 출처: ${escapeHtml(r.source)} · 생성: ${escapeHtml(r.generated_at)}</p>
${insightHtml}
${(() => {
  const svg = freightChart.value?.getSvgHtml()
  return svg ? `<h2>시황 (운임지수, USD/40')</h2>${svg}` : ''
})()}
${sections}
<h2>정의</h2><ul>${defs}</ul>
</body></html>`
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `leadtime-report-${r.generated_at.slice(0, 10)}.html`
  a.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="leadtime-report">
    <div class="toolbar">
      <div>
        <h2 class="title">물류 MI Report — 항로별 리드타임</h2>
        <p v-if="report" class="meta">
          조회 시점 기준 자동 집계 · B-LAP 출처 · 생성 {{ report.generated_at }}
        </p>
      </div>
      <div class="actions">
        <button class="btn" :disabled="loading || savingCells" @click="load">새로고침</button>
        <button class="btn" :disabled="!report || savingCells" @click="editMode = !editMode">
          {{ editMode ? '편집 취소' : '셀 편집' }}
        </button>
        <button v-if="editMode" class="btn primary" :disabled="savingCells" @click="saveCells">
          {{ savingCells ? '저장 중...' : '편집값 저장' }}
        </button>
        <button class="btn" :disabled="!report || savingCells" @click="resetCells">편집값 되돌리기</button>
        <button class="btn" :disabled="!report" @click="exportHtml">HTML 출력</button>
        <button class="btn" :disabled="!report" @click="doPrint">인쇄</button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="hint">집계 중...</p>
    <p v-if="report && !report.month_columns.length && !loading" class="hint">
      집계된 운송 데이터가 없습니다.
    </p>

    <template v-if="report">
      <MiInsightDraftPanel v-model:draft="insight" />

      <FreightIndicesChart ref="freightChart" />

      <section v-for="group in report.groups" :key="group.group_id" class="group">
        <h3 class="group-name">{{ group.name }}</h3>
        <table>
          <thead>
            <tr>
              <th>국가</th>
              <th>구분</th>
              <th
                v-for="m in report.month_columns"
                :key="m.key"
                :class="{ forecast: m.kind === 'forecast' }"
              >
                {{ m.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="block in countryBlocks(group)" :key="block.country">
              <tr v-for="(stat, i) in STATS" :key="`${block.country}-${stat}`">
                <td v-if="i === 0" :rowspan="3" class="country">
                  {{ block.label }}
                  <span v-if="block.fixed" class="fixed-badge" title="사용자 제공 고정값 (실데이터 집계 아님)">고정값</span>
                </td>
                <td class="stat">{{ stat }}</td>
                <td
                  v-for="m in report.month_columns"
                  :key="m.key"
                  :class="{
                    forecast: m.kind === 'forecast',
                    edited: isEdited(cellKey(group.group_id, block.country, stat, m.key)),
                  }"
                >
                  <input
                    v-if="editMode"
                    type="number"
                    step="0.1"
                    class="cell-input"
                    :value="editValues[cellKey(group.group_id, block.country, stat, m.key)] ?? rowCellText(block.rowsByStat[stat], m.key)"
                    @input="onCellInput(cellKey(group.group_id, block.country, stat, m.key), $event)"
                  />
                  <template v-else>{{ rowCellText(block.rowsByStat[stat], m.key) }}</template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </section>

      <section class="definitions">
        <h3 class="group-name">정의</h3>
        <ul>
          <li v-for="(text, key) in report.definitions" :key="key">{{ text }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.leadtime-report {
  max-width: 1100px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.title {
  margin: 0;
  font-size: 16px;
  color: var(--li-text);
}
.meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--li-text-muted);
}
.actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.btn {
  padding: 6px 14px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.group {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 14px;
  box-shadow: var(--li-shadow-card);
}
.group-name {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--li-text);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  border: 1px solid var(--li-border-strong);
  padding: 5px 8px;
  text-align: center;
  color: var(--li-text);
}
th {
  background: var(--li-bg-app-2);
}
th.forecast,
td.forecast {
  background: var(--li-surface-blue);
  color: var(--li-blue);
  font-weight: 700;
}
td.edited {
  text-decoration: underline dotted var(--li-risk-high) 2px;
  text-underline-offset: 3px;
}
.cell-input {
  width: 64px;
  padding: 2px 4px;
  border: 1px solid var(--li-blue);
  border-radius: 6px;
  font-size: 12px;
  text-align: center;
  color: var(--li-text);
  background: var(--li-surface-strong);
}
.btn.primary {
  background: var(--li-blue);
  border-color: transparent;
  color: #fff;
}
td.country {
  font-weight: 700;
  background: var(--li-bg-app-2);
}

.fixed-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 400;
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border: 1px solid var(--li-risk-high-border);
}
.definitions ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--li-text-muted);
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

<style>
@media print {
  body * {
    visibility: hidden;
  }
  .leadtime-report,
  .leadtime-report * {
    visibility: visible;
  }
  .leadtime-report {
    position: absolute;
    inset: 0 auto auto 0;
    width: 100%;
  }
  .leadtime-report .toolbar .actions {
    display: none;
  }
}
</style>
