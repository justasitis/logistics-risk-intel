<script setup lang="ts">
import {
  computed,
  reactive,
  ref,
  watch,
} from 'vue'

import { useVesselMmsiMaster } from '@/composables/useVesselMmsiMaster'
import {
  buildVesselInventory,
  downloadTextFile,
  fetchVesselInventory,
  isValidMmsi,
  mappingsFromAisItems,
  mappingsToJson,
  normalizeMmsi,
  parseVesselMappingFile,
  vesselRowsToCsv,
} from '@/services/vesselMmsi'
import type {
  AisMapItem,
} from '@/types/dashboard'
import type {
  VesselInventoryApiResponse,
  VesselMmsiStatus,
  VesselUsageRow,
} from '@/types/vesselMmsi'

const props = defineProps<{
  aisItems: AisMapItem[]
}>()

const {
  mappings,
  storageError,
  upsert,
  upsertMany,
  remove,
} = useVesselMmsiMaster()

const searchText = ref('')
const statusFilter = ref<'ALL' | VesselMmsiStatus>(
  'MISSING',
)
const importInput = ref<HTMLInputElement | null>(null)
const message = ref('')
const errorMessage = ref('')
const draftMmsi = reactive<Record<string, string>>({})

// 대시보드 조회와 무관하게 전용 API를 명시 조회한다 (자동 조회 금지).
const inventoryData = ref<VesselInventoryApiResponse | null>(null)
const inventoryLoading = ref(false)

const inventory = computed(() =>
  buildVesselInventory({
    vessels: inventoryData.value?.vessels ?? [],
    transportCount: inventoryData.value?.transport_count ?? 0,
    mappings: mappings.value,
    aisItems: props.aisItems,
  }),
)

const filteredRows = computed(() => {
  const query = searchText.value.trim().toUpperCase()

  return inventory.value.rows.filter((row) => {
    if (
      statusFilter.value !== 'ALL'
      && row.status !== statusFilter.value
    ) {
      return false
    }

    if (!query) return true

    return [
      row.vessel_name,
      row.mapped_mmsi_no ?? '',
      row.lanes.join(' '),
      row.trpr_nos.join(' '),
    ].some(
      (value) => value.toUpperCase().includes(query),
    )
  })
})

const missingRows = computed(() =>
  inventory.value.rows.filter(
    (row) => row.status === 'MISSING',
  ),
)

watch(
  () => inventory.value.rows,
  (rows) => {
    for (const row of rows) {
      draftMmsi[row.vessel_name] = (
        row.mapped_mmsi_no ?? ''
      )
    }
  },
  { immediate: true },
)

function formatDate(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function statusLabel(status: VesselMmsiStatus): string {
  if (status === 'MAPPED') return '등록'
  if (status === 'AIS_DETECTED') return 'AIS 감지'
  return '미등록'
}

function clearFeedback() {
  message.value = ''
  errorMessage.value = ''
}

async function loadInventory() {
  clearFeedback()
  inventoryLoading.value = true

  try {
    inventoryData.value = await fetchVesselInventory(
      inventoryData.value !== null,
    )
    message.value = (
      `선박 ${inventory.value.summary.unique_vessel_count}척을 조회했습니다.`
    )
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : '선박 목록을 조회하지 못했습니다.'
  } finally {
    inventoryLoading.value = false
  }
}

function saveRow(row: VesselUsageRow) {
  clearFeedback()

  const mmsi = normalizeMmsi(
    draftMmsi[row.vessel_name],
  )

  if (!isValidMmsi(mmsi)) {
    errorMessage.value = (
      `${row.vessel_name}: MMSI는 숫자 9자리여야 합니다.`
    )
    return
  }

  upsert(row.vessel_name, mmsi, 'MANUAL')
  draftMmsi[row.vessel_name] = mmsi
  message.value = `${row.vessel_name} 매핑을 저장했습니다.`
}

function deleteRow(row: VesselUsageRow) {
  clearFeedback()
  remove(row.vessel_name)
  draftMmsi[row.vessel_name] = ''
  message.value = `${row.vessel_name} 매핑을 삭제했습니다.`
}

function downloadMissingCsv() {
  clearFeedback()
  downloadTextFile(
    `vessel_mmsi_missing_${new Date().toISOString().slice(0, 10)}.csv`,
    vesselRowsToCsv(missingRows.value),
    'text/csv',
    true,
  )
  message.value = (
    `MMSI 미등록 선박 ${missingRows.value.length}건을 다운로드했습니다.`
  )
}

function downloadAllCsv() {
  clearFeedback()
  downloadTextFile(
    `vessel_mmsi_inventory_${new Date().toISOString().slice(0, 10)}.csv`,
    vesselRowsToCsv(inventory.value.rows),
    'text/csv',
    true,
  )
  message.value = '전체 선박 목록을 다운로드했습니다.'
}

function downloadMappingJson() {
  clearFeedback()
  downloadTextFile(
    `vessel_mmsi_mapping_${new Date().toISOString().slice(0, 10)}.json`,
    mappingsToJson(mappings.value),
    'application/json',
  )
  message.value = (
    `MMSI 매핑 ${mappings.value.length}건을 다운로드했습니다.`
  )
}

function openImport() {
  importInput.value?.click()
}

async function importMapping(event: Event) {
  clearFeedback()
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''

  if (!file) return

  try {
    const result = await parseVesselMappingFile(file)
    const count = upsertMany(result.mappings)
    message.value = (
      `매핑 ${count}건을 가져왔습니다.`
      + (
        result.warnings.length
          ? ` 제외 경고 ${result.warnings.length}건`
          : ''
      )
    )
  } catch (error) {
    errorMessage.value = error instanceof Error
      ? error.message
      : '매핑 파일을 가져오지 못했습니다.'
  }
}

function saveAisMappings() {
  clearFeedback()
  const values = mappingsFromAisItems(props.aisItems)

  if (values.length === 0) {
    errorMessage.value = (
      '현재 AIS 업로드에서 유효한 선박명–MMSI를 찾지 못했습니다.'
    )
    return
  }

  upsertMany(values)
  message.value = (
    `AIS 업로드에서 MMSI 매핑 ${values.length}건을 반영했습니다.`
  )
}
</script>

<template>
  <main class="vessel-master">
    <header class="vessel-master__hero glass-panel glass-panel--soft">
      <div>
        <p class="eyebrow">VESSEL MASTER</p>
        <h2>운송 중 선박 MMSI 관리</h2>
        <p>
          법인 구분 없이 최근 1년 활성 운송의 IF 선박명을 원문 그대로
          집계하고 MMSI가 없는 선박을 추출합니다.
        </p>
      </div>

      <div class="vessel-master__actions">
        <button
          type="button"
          class="btn btn--primary"
          :disabled="inventoryLoading"
          @click="loadInventory"
        >
          {{ inventoryLoading
            ? '조회 중...'
            : inventoryData
              ? '선박 목록 다시 조회'
              : '선박 목록 조회' }}
        </button>
        <button
          type="button"
          class="btn"
          :disabled="!inventoryData || missingRows.length === 0"
          @click="downloadMissingCsv"
        >
          미등록 CSV
        </button>
        <button
          type="button"
          class="btn"
          :disabled="!inventoryData"
          @click="downloadAllCsv"
        >
          전체 CSV
        </button>
        <button
          type="button"
          class="btn"
          @click="downloadMappingJson"
        >
          매핑 JSON
        </button>
        <button
          type="button"
          class="btn"
          @click="openImport"
        >
          CSV/JSON 가져오기
        </button>
        <button
          type="button"
          class="btn btn--ghost"
          :disabled="aisItems.length === 0"
          @click="saveAisMappings"
        >
          AIS MMSI 반영
        </button>

        <input
          ref="importInput"
          type="file"
          accept=".csv,.json,text/csv,application/json"
          hidden
          @change="importMapping"
        >
      </div>
    </header>

    <section class="metric-grid">
      <article class="metric-card metric-card--blue">
        <div class="metric-card__label">현재 운송건</div>
        <div class="metric-card__value">
          {{ inventory.summary.transport_count }}
        </div>
        <div class="metric-card__hint">
          최근 1년 활성 운송 (전체 법인)
        </div>
      </article>

      <article class="metric-card">
        <div class="metric-card__label">고유 선박명</div>
        <div class="metric-card__value">
          {{ inventory.summary.unique_vessel_count }}
        </div>
        <div class="metric-card__hint">IF 원문 기준 중복 제거</div>
      </article>

      <article class="metric-card">
        <div class="metric-card__label">MMSI 등록</div>
        <div class="metric-card__value">
          {{ inventory.summary.mapped_vessel_count }}
        </div>
        <div class="metric-card__hint">
          AIS 감지 {{ inventory.summary.ais_detected_count }}건
        </div>
      </article>

      <article class="metric-card">
        <div class="metric-card__label">MMSI 미등록</div>
        <div class="metric-card__value">
          {{ inventory.summary.missing_vessel_count }}
        </div>
        <div class="metric-card__hint">
          영향 운송 {{ inventory.summary.missing_shipment_count }}건
        </div>
      </article>
    </section>

    <section class="vessel-table-panel glass-panel panel-pad">
      <div class="vessel-toolbar">
        <div class="vessel-filter-tabs">
          <button
            v-for="option in [
              { value: 'MISSING', label: '미등록' },
              { value: 'MAPPED', label: '등록' },
              { value: 'AIS_DETECTED', label: 'AIS 감지' },
              { value: 'ALL', label: '전체' },
            ]"
            :key="option.value"
            type="button"
            :class="{ active: statusFilter === option.value }"
            @click="
              statusFilter = option.value as
                | 'ALL'
                | VesselMmsiStatus
            "
          >
            {{ option.label }}
          </button>
        </div>

        <input
          v-model="searchText"
          class="vessel-search"
          type="search"
          placeholder="선박명·Lane·운송번호 검색"
        >
      </div>

      <div
        v-if="message"
        class="vessel-message vessel-message--ok"
      >
        {{ message }}
      </div>
      <div
        v-if="errorMessage || storageError"
        class="vessel-message vessel-message--error"
      >
        {{ errorMessage || storageError }}
      </div>

      <div
        v-if="!inventoryData"
        class="vessel-guide"
      >
        '선박 목록 조회' 버튼을 누르면 법인 구분 없이
        최근 1년 활성 운송의 선박 목록을 가져옵니다.
      </div>

      <template v-else>
        <p class="vessel-meta">
          조회 기준: {{ formatDateTime(inventoryData.generated_at) }}
          <template v-if="inventoryData.cache_hit">
            (캐시)
          </template>
        </p>

        <div class="vessel-table-wrap">
          <table class="vessel-table">
            <thead>
              <tr>
                <th>상태</th>
                <th>선박명</th>
                <th>MMSI No.</th>
                <th>운송건</th>
                <th>POL–POD</th>
                <th>최종 ETA</th>
                <th>처리</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="row in filteredRows"
                :key="row.vessel_name"
              >
                <td>
                  <span
                    class="vessel-status"
                    :class="`vessel-status--${row.status.toLowerCase()}`"
                  >
                    {{ statusLabel(row.status) }}
                  </span>
                </td>

                <td>
                  <strong>{{ row.vessel_name }}</strong>
                  <small>IF 원문 Key 그대로 사용</small>
                </td>

                <td>
                  <input
                    v-model="draftMmsi[row.vessel_name]"
                    class="mmsi-input"
                    inputmode="numeric"
                    maxlength="9"
                    placeholder="9자리"
                  >
                </td>

                <td>
                  <strong>{{ row.shipment_count }}</strong>
                  <small>
                    {{ row.trpr_nos.slice(0, 2).join(', ') }}
                  </small>
                </td>

                <td :title="row.lanes.join(', ')">
                  {{ row.lanes.slice(0, 2).join(', ') || '-' }}
                </td>

                <td>{{ formatDate(row.latest_eta) }}</td>

                <td>
                  <div class="row-actions">
                    <button
                      type="button"
                      class="save"
                      @click="saveRow(row)"
                    >
                      저장
                    </button>
                    <button
                      v-if="row.status === 'MAPPED'"
                      type="button"
                      class="delete"
                      @click="deleteRow(row)"
                    >
                      삭제
                    </button>
                  </div>
                </td>
              </tr>

              <tr v-if="filteredRows.length === 0">
                <td colspan="7" class="empty-cell">
                  조건에 맞는 선박이 없습니다.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </main>
</template>

<style scoped>
.vessel-master {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.vessel-master__hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 20px 22px;
}

.vessel-master__hero h2 {
  margin: 0;
  font-size: 22px;
  letter-spacing: -0.03em;
}

.vessel-master__hero p:not(.eyebrow) {
  margin: 7px 0 0;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
}

.vessel-master__actions {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 7px;
}

/* 공용 main.css의 다크 .metric-card 정의를 이 화면에서만 라이트 테마로 되돌린다. */
.metric-card {
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  background: rgba(255, 255, 255, 0.74);
  box-shadow: var(--li-shadow-card, 0 12px 28px rgba(15, 32, 54, 0.08));
}

.metric-card--blue {
  background:
    var(
      --li-accent-gradient-soft,
      linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(6, 182, 212, 0.16))
    ),
    rgba(255, 255, 255, 0.74);
}

.metric-card__label {
  color: var(--li-text-muted, #607086);
}

.metric-card__value {
  color: var(--li-text, #122033);
}

.metric-card__hint {
  color: var(--li-text-muted, #607086);
}

.vessel-table-panel {
  min-width: 0;
}

.vessel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.vessel-filter-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.72);
}

.vessel-filter-tabs button {
  min-height: 29px;
  padding: 0 10px;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
  font-weight: 760;
  border: 0;
  border-radius: 999px;
  background: transparent;
  cursor: pointer;
}

.vessel-filter-tabs button.active {
  color: #ffffff;
  background: linear-gradient(135deg, #2563eb, #06b6d4);
}

.vessel-search {
  width: min(330px, 42vw);
  min-height: 37px;
  padding: 0 12px;
}

.vessel-message {
  margin-bottom: 10px;
  padding: 9px 11px;
  font-size: 11px;
  border-radius: 9px;
}

.vessel-message--ok {
  color: #047857;
  background: rgba(16, 185, 129, 0.1);
}

.vessel-message--error {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.1);
}

.vessel-guide {
  padding: 28px 16px;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
  text-align: center;
  background: rgba(255, 255, 255, 0.73);
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 11px;
}

.vessel-meta {
  margin: 0 0 8px;
  color: var(--li-text-faint, #8a98aa);
  font-size: 11px;
  text-align: right;
}

.vessel-table-wrap {
  overflow: auto;
}

.vessel-table {
  width: 100%;
  min-width: 1040px;
  border-collapse: separate;
  border-spacing: 0 7px;
}

.vessel-table th {
  padding: 7px 9px;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
  text-align: left;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.vessel-table td {
  padding: 9px;
  color: var(--li-text-soft, #344861);
  font-size: 11px;
  vertical-align: middle;
  background: rgba(255, 255, 255, 0.73);
  border-top: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-bottom: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
}

.vessel-table td:first-child {
  border-left: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 11px 0 0 11px;
}

.vessel-table td:last-child {
  border-right: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 0 11px 11px 0;
}

.vessel-table td strong,
.vessel-table td small {
  display: block;
}

.vessel-table td small {
  max-width: 220px;
  margin-top: 3px;
  overflow: hidden;
  color: var(--li-text-faint, #8a98aa);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vessel-status {
  display: inline-flex;
  padding: 3px 6px;
  font-size: 11px;
  font-weight: 850;
  border-radius: 999px;
}

.vessel-status--missing {
  color: #c2410c;
  background: rgba(249, 115, 22, 0.12);
}

.vessel-status--mapped {
  color: #047857;
  background: rgba(16, 185, 129, 0.12);
}

.vessel-status--ais_detected {
  color: #0369a1;
  background: rgba(14, 165, 233, 0.12);
}

.mmsi-input {
  width: 112px;
  min-height: 33px;
  padding: 0 9px;
  font-family: var(--li-font-mono, Consolas, monospace);
}

.row-actions {
  display: flex;
  gap: 5px;
}

.row-actions button {
  min-height: 29px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 760;
  border-radius: 8px;
  cursor: pointer;
}

.row-actions .save {
  color: #1d4ed8;
  border: 1px solid rgba(37, 99, 235, 0.23);
  background: rgba(37, 99, 235, 0.08);
}

.row-actions .delete {
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.22);
  background: rgba(239, 68, 68, 0.07);
}

.vessel-table td.empty-cell {
  padding: 24px;
  color: var(--li-text-muted, #607086);
  text-align: center;
}

@media (max-width: 900px) {
  .vessel-master__hero,
  .vessel-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .vessel-master__actions {
    justify-content: flex-start;
  }

  .vessel-search {
    width: 100%;
  }
}
</style>
