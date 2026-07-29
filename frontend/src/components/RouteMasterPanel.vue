<script setup lang="ts">
import { ref } from 'vue'
import { getRouteMaster } from '../services/freightApi'
import type { RouteMasterResponse, RouteMasterRow } from '../types/routeMaster'

const DIM_OPTIONS = [
  { key: 'cmpy_nm', label: '법인명' },
  { key: 'plnt_nm', label: '사업장' },
  { key: 'lsp_nm', label: '물류사' },
  { key: 'bsns_ccd_nm', label: '사업구분' },
  { key: 'trpr_mode', label: '운송모드' },
] as const

const COMPANY_OPTIONS = ['SKO', 'SKOH', 'SKBM', 'SKBA', 'SKOJ', 'SKOY']

const selectedDims = ref<string[]>(['cmpy_nm'])
const selectedCompanies = ref<string[]>([])
// 기간 기본값: 올해 1월 1일 ~ 오늘 (조회 버튼 클릭 시에만 조회)
const etdFrom = ref(`${new Date().getFullYear()}-01-01`)
const etdTo = ref(new Date().toISOString().slice(0, 10))
const result = ref<RouteMasterResponse | null>(null)
const loading = ref(false)
const error = ref('')
const queried = ref(false)

function toggleDim(key: string) {
  const idx = selectedDims.value.indexOf(key)
  if (idx >= 0) selectedDims.value.splice(idx, 1)
  else selectedDims.value.push(key)
}

function toggleCompany(code: string) {
  const idx = selectedCompanies.value.indexOf(code)
  if (idx >= 0) selectedCompanies.value.splice(idx, 1)
  else selectedCompanies.value.push(code)
}

async function query() {
  loading.value = true
  error.value = ''
  queried.value = true
  try {
    const days = Math.max(
      1,
      Math.round(
        (new Date(etdTo.value).getTime() - new Date(etdFrom.value).getTime()) / 86_400_000,
      ),
    )
    result.value = await getRouteMaster({
      companies: selectedCompanies.value,
      dims: selectedDims.value,
      etdFrom: etdFrom.value,
      etdTo: etdTo.value,
      etdDays: days,
    })
  } catch (e) {
    result.value = null
    error.value = e instanceof Error ? e.message : '경로 조회 실패'
  } finally {
    loading.value = false
  }
}

function dimValue(row: RouteMasterRow, key: string): string {
  if (key === 'trpr_mode') {
    return row.trpr_mode_label ?? row.trpr_mode ?? '-'
  }
  const value = row[key as keyof RouteMasterRow]
  return value === undefined || value === null || value === '' ? '-' : String(value)
}
</script>

<template>
  <div class="routes-pane">
    <section class="card controls">
      <div class="row">
        <span class="label">구분조건</span>
        <label v-for="d in DIM_OPTIONS" :key="d.key" class="chk">
          <input
            type="checkbox"
            :checked="selectedDims.includes(d.key)"
            @change="toggleDim(d.key)"
          />
          {{ d.label }}
        </label>
      </div>
      <div class="row">
        <span class="label">법인</span>
        <label v-for="c in COMPANY_OPTIONS" :key="c" class="chk">
          <input
            type="checkbox"
            :checked="selectedCompanies.includes(c)"
            @change="toggleCompany(c)"
          />
          {{ c }}
        </label>
        <span class="hint-inline">(미선택 시 전체)</span>
      </div>
      <div class="row">
        <span class="label">기간</span>
        <input v-model="etdFrom" type="date" class="date-input" />
        <span class="hint-inline">~</span>
        <input v-model="etdTo" type="date" class="date-input" />
      </div>
      <div class="row">
        <button class="btn primary" :disabled="loading" @click="query">
          {{ loading ? '조회 중...' : '조회' }}
        </button>
        <span v-if="result" class="meta">
          {{ result.total_rows.toLocaleString() }}건
          <span v-if="result.truncated" class="warn">(상한 초과로 일부만 표시)</span>
        </span>
      </div>
    </section>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="queried && !loading && result && !result.rows.length" class="hint">
      조건에 맞는 경로가 없습니다.
    </p>
    <p v-if="!queried" class="hint">구분조건과 법인을 선택하고 조회를 누르세요.</p>

    <section v-if="result && result.rows.length" class="card table-card">
      <table>
        <thead>
          <tr>
            <th v-for="d in selectedDims" :key="d">
              {{ DIM_OPTIONS.find((o) => o.key === d)?.label ?? d }}
            </th>
            <th>출발코드</th>
            <th>출발항</th>
            <th>도착코드</th>
            <th>도착항</th>
            <th>최종사이트코드</th>
            <th>최종사이트명</th>
            <th class="num">운송건수</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in result.rows" :key="i">
            <td v-for="d in selectedDims" :key="d">{{ dimValue(row, d) }}</td>
            <td>{{ row.dprt }}</td>
            <td>{{ row.dprt_nm }}</td>
            <td>{{ row.arvl }}</td>
            <td>{{ row.arvl_nm }}</td>
            <td>{{ row.to_stlc_cd }}</td>
            <td>{{ row.to_stlc_nm }}</td>
            <td class="num">{{ row.shipment_count.toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.routes-pane {
  max-width: 1100px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 14px;
  box-shadow: var(--li-shadow-card);
}
.controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.label {
  font-size: 12px;
  font-weight: 700;
  color: var(--li-text-soft);
  min-width: 52px;
}
.chk {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--li-text);
}
.hint-inline {
  font-size: 12px;
  color: var(--li-text-faint);
}
.date-input {
  padding: 5px 8px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
}
.btn {
  padding: 6px 16px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
  cursor: pointer;
}
.btn.primary {
  background: var(--li-blue);
  border-color: transparent;
  color: #fff;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.meta {
  font-size: 12px;
  color: var(--li-text-muted);
}
.warn {
  color: var(--li-risk-high);
}
.table-card {
  overflow-x: auto;
  padding: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  border-bottom: 1px solid var(--li-border);
  padding: 6px 8px;
  text-align: left;
  color: var(--li-text);
  white-space: nowrap;
}
th {
  background: var(--li-bg-app-2);
  color: var(--li-text-soft);
}
.num {
  text-align: right;
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
