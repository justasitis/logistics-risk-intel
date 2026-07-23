<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getLeadtimeReport } from '../services/leadtimeApi'
import type { InsightDraftResponse, LeadtimeGroup, LeadtimeReport } from '../types/leadtime'
import MiInsightDraftPanel from './MiInsightDraftPanel.vue'

const report = ref<LeadtimeReport | null>(null)
const insight = ref<InsightDraftResponse | null>(null)
const loading = ref(false)
const error = ref('')

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

function cellText(group: LeadtimeGroup, country: string, stat: string, month: string): string {
  const row = group.rows.find((r) => r.country === country && r.stat === stat)
  const value = row?.cells[month]
  return value === undefined ? '' : String(value)
}

const STATS = ['Avg', 'Min', 'Max'] as const
const COUNTRIES = [
  { code: 'KR', label: '한국' },
  { code: 'CN', label: '중국' },
  { code: 'JP', label: '일본' },
] as const

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
      const body = COUNTRIES.map((c) => {
        const rows = STATS.map((stat, i) => {
          const cells = r.month_columns
            .map((m) => `<td class="${m.kind}">${escapeHtml(cellText(g, c.code, stat, m.key))}</td>`)
            .join('')
          const labelCell = i === 0 ? `<td rowspan="3">${c.label}</td>` : ''
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
        <button class="btn" :disabled="loading" @click="load">새로고침</button>
        <button class="btn" :disabled="!report" @click="exportHtml">HTML 낙출력</button>
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
            <template v-for="c in COUNTRIES" :key="c.code">
              <tr v-for="(stat, i) in STATS" :key="`${c.code}-${stat}`">
                <td v-if="i === 0" :rowspan="3" class="country">{{ c.label }}</td>
                <td class="stat">{{ stat }}</td>
                <td
                  v-for="m in report.month_columns"
                  :key="m.key"
                  :class="{ forecast: m.kind === 'forecast' }"
                >
                  {{ cellText(group, c.code, stat, m.key) }}
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
td.country {
  font-weight: 700;
  background: var(--li-bg-app-2);
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
