<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { getRouteMaster } from '../services/freightApi'
import type { RouteMasterResponse, RouteMasterRow } from '../types/routeMaster'

const DIM_OPTIONS = [
  { key: 'cmpy_nm', label: '법인명' },
  { key: 'plnt_nm', label: '사업장' },
  { key: 'lsp_nm', label: '물류사' },
  { key: 'bsns_ccd_nm', label: '사업구분' },
  { key: 'trpr_mode', label: '운송모드' },
  { key: 'dprt_pair', label: '출발지' },
  { key: 'to_stlc_pair', label: '최종사이트' },
] as const

// 쌍 묶음 구분조건 — 하나의 체크로 코드+이름 열을 동시에 그룹핑/표시
const PAIR_DIM_COLUMNS: Record<string, Array<{ key: string; label: string }>> = {
  dprt_pair: [
    { key: 'dprt', label: '출발코드' },
    { key: 'dprt_nm', label: '출발항' },
  ],
  to_stlc_pair: [
    { key: 'to_stlc_cd', label: '최종사이트코드' },
    { key: 'to_stlc_nm', label: '최종사이트명' },
  ],
}

// 도착지는 항상 표시 (경로 마스터의 기본축)
const BASE_COLUMNS = [
  { key: 'arvl', label: '도착코드' },
  { key: 'arvl_nm', label: '도착항' },
]

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

// 컬럼별 멀티선택 필터 — key: 선택된 값 목록 (빈 배열 = 전체)
const columnFilters = reactive<Record<string, string[]>>({})

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
    // 새 조회 결과에 맞지 않는 필터 선택값은 초기화
    for (const key of Object.keys(columnFilters)) delete columnFilters[key]
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

// 표시 열: 일반 구분조건 → 출발지 쌍 → 도착지 기본 열 → 최종사이트 쌍 순
const visibleColumns = computed<Array<{ key: string; label: string }>>(() => {
  const plain: Array<{ key: string; label: string }> = []
  let dprtCols: Array<{ key: string; label: string }> = []
  let stlcCols: Array<{ key: string; label: string }> = []
  for (const dim of selectedDims.value) {
    if (dim === 'dprt_pair') {
      dprtCols = PAIR_DIM_COLUMNS[dim] ?? []
    } else if (dim === 'to_stlc_pair') {
      stlcCols = PAIR_DIM_COLUMNS[dim] ?? []
    } else {
      plain.push({
        key: dim,
        label: DIM_OPTIONS.find((o) => o.key === dim)?.label ?? dim,
      })
    }
  }
  return [...plain, ...dprtCols, ...BASE_COLUMNS, ...stlcCols]
})

// ---------- 컬럼별 멀티선택 필터 ----------
const filterColumns = visibleColumns

function cellValue(row: RouteMasterRow, key: string): string {
  return dimValue(row, key)
}

function distinctValues(key: string): string[] {
  if (!result.value) return []
  const values = new Set(result.value.rows.map((row) => cellValue(row, key)))
  return [...values].sort((a, b) => a.localeCompare(b))
}

function isFilterActive(key: string): boolean {
  return (columnFilters[key]?.length ?? 0) > 0
}

function toggleFilterValue(key: string, value: string) {
  const selected = columnFilters[key] ?? []
  const idx = selected.indexOf(value)
  if (idx >= 0) selected.splice(idx, 1)
  else selected.push(value)
  columnFilters[key] = selected
}

function clearFilter(key: string) {
  columnFilters[key] = []
}

const filteredRows = computed<RouteMasterRow[]>(() => {
  if (!result.value) return []
  return result.value.rows.filter((row) =>
    filterColumns.value.every(({ key }) => {
      const selected = columnFilters[key]
      if (!selected || !selected.length) return true
      return selected.includes(cellValue(row, key))
    }),
  )
})

// ---------- 엑셀(CSV) 다운로드 — 현재 열 필터가 적용된 표시 행 기준 ----------
function exportCsv() {
  if (!result.value) return
  const cols = visibleColumns.value
  const esc = (value: string) => `"${value.replace(/"/g, '""')}"`
  const header = cols.map((c) => c.label).concat(['운송건수'])
  const lines = [header.map(esc).join(',')]
  for (const row of filteredRows.value) {
    const cells = [
      ...cols.map((c) => dimValue(row, c.key)),
      String(row.shipment_count),
    ]
    lines.push(cells.map(esc).join(','))
  }
  // BOM 포함 — 엑셀에서 한글 깨짐 없이 바로 열린다
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], {
    type: 'text/csv;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `route-master-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
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
        <button
          class="btn"
          :disabled="!result || !result.rows.length"
          title="현재 열 필터가 적용된 표시 행을 CSV로 납니다 (엑셀에서 바로 열림)"
          @click="exportCsv"
        >
          엑셀(CSV) 다운로드
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
      <div class="filter-bar">
        <span class="label">열 필터</span>
        <details
          v-for="col in filterColumns"
          :key="col.key"
          class="col-filter"
          :class="{ active: isFilterActive(col.key) }"
        >
          <summary>
            {{ col.label }}
            <span v-if="isFilterActive(col.key)" class="filter-count">
              {{ (columnFilters[col.key] ?? []).length }}
            </span>
          </summary>
          <div class="filter-list">
            <div class="filter-actions">
              <button type="button" class="mini-btn" @click="clearFilter(col.key)">전체 해제</button>
            </div>
            <label v-for="v in distinctValues(col.key)" :key="v" class="chk">
              <input
                type="checkbox"
                :checked="(columnFilters[col.key] ?? []).includes(v)"
                @change="toggleFilterValue(col.key, v)"
              />
              {{ v }}
            </label>
          </div>
        </details>
        <span v-if="filteredRows.length !== result.rows.length" class="meta">
          표시 {{ filteredRows.length.toLocaleString() }} / {{ result.rows.length.toLocaleString() }}건
        </span>
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th v-for="c in visibleColumns" :key="c.key">{{ c.label }}</th>
              <th class="num">운송건수</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in filteredRows" :key="i">
              <td v-for="c in visibleColumns" :key="c.key">{{ dimValue(row, c.key) }}</td>
              <td class="num">{{ row.shipment_count.toLocaleString() }}</td>
            </tr>
            <tr v-if="!filteredRows.length">
              <td :colspan="visibleColumns.length + 1" class="empty-cell">
                열 필터 조건에 맞는 행이 없습니다.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
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
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
/* 구분조건을 많이 선택필수록 열이 늘어나므로 가로 스크롤을 명시적으로 보장 */
.table-scroll {
  overflow-x: auto;
  max-width: 100%;
}
table {
  width: max-content;
  min-width: 100%;
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
  position: sticky;
  top: 0;
}
.num {
  text-align: right;
}
.empty-cell {
  text-align: center;
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

/* ---------- 컬럼별 멀티선택 필터 ---------- */
.filter-bar {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
  padding: 4px 4px 0;
}
.col-filter {
  position: relative;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  font-size: 12px;
}
.col-filter.active {
  border-color: var(--li-blue);
  background: var(--li-surface-blue);
}
.col-filter summary {
  padding: 4px 12px;
  cursor: pointer;
  color: var(--li-text-soft);
  list-style: none;
  user-select: none;
}
.col-filter summary::-webkit-details-marker {
  display: none;
}
.filter-count {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  border-radius: 999px;
  background: var(--li-blue);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.col-filter[open] {
  border-radius: var(--li-radius-sm);
  z-index: 20;
}
.filter-list {
  position: absolute;
  top: 100%;
  left: 0;
  min-width: 180px;
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  box-shadow: var(--li-shadow-float);
}
.filter-actions {
  display: flex;
  justify-content: flex-end;
  border-bottom: 1px solid var(--li-border);
  padding-bottom: 4px;
}
.mini-btn {
  border: none;
  background: transparent;
  color: var(--li-blue);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
}
</style>
