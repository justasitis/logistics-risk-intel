<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getInventoryItems, postInventorySimulate } from '../services/inventoryApi'
import { INVENTORY_RISK_COLORS, INVENTORY_RISK_LABELS } from '../theme/inventoryRisk'
import type {
  InventoryItem,
  InventoryRiskLevel,
  SimulateResponse,
} from '../types/inventory'
import InventoryCurveChart from './InventoryCurveChart.vue'

// Pinia 없이 동작하는 독립 패널 — 상태를 컴포넌트 낸부에서 관리
const items = ref<InventoryItem[]>([])
const riskByItem = ref<Record<string, InventoryRiskLevel>>({})
const selectedId = ref<string | null>(null)
const extraDelay = ref(0)
const result = ref<SimulateResponse | null>(null)
const loading = ref(false)
const simLoading = ref(false)
const error = ref('')

const selectedItem = computed(
  () => items.value.find((i) => i.item_id === selectedId.value) ?? null,
)

async function runSim() {
  const id = selectedId.value
  if (!id) return
  simLoading.value = true
  error.value = ''
  try {
    result.value = await postInventorySimulate(id, extraDelay.value)
    riskByItem.value[id] = result.value.metrics.risk_level
  } catch (e) {
    error.value = e instanceof Error ? e.message : '시뮬레이션 실패'
  } finally {
    simLoading.value = false
  }
}

function riskColorOf(itemId: string): string {
  const level = riskByItem.value[itemId]
  return level ? INVENTORY_RISK_COLORS[level] : INVENTORY_RISK_COLORS.OK
}

function riskLabelOf(itemId: string): string {
  const level = riskByItem.value[itemId]
  return level ? INVENTORY_RISK_LABELS[level] : ''
}

const resultRiskColor = computed(() =>
  result.value
    ? INVENTORY_RISK_COLORS[result.value.metrics.risk_level]
    : INVENTORY_RISK_COLORS.OK,
)

const firstBelowMinWindowText = computed(() => {
  const win = result.value?.metrics.below_min_windows[0]
  return win ? `${win.start} ~ (${win.days}일)` : '없음'
})

async function refreshRisks() {
  await Promise.all(
    items.value.map(async (item) => {
      try {
        const res = await postInventorySimulate(item.item_id, 0)
        riskByItem.value[item.item_id] = res.metrics.risk_level
      } catch {
        // 배지 실패는 무시 (상세 시뮬레이션에서 에러 표시)
      }
    }),
  )
}

async function select(itemId: string) {
  selectedId.value = itemId
  extraDelay.value = 0
  await runSim()
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await getInventoryItems()
    items.value = res.items
    const first = res.items[0]
    if (first) selectedId.value = first.item_id
    await Promise.all([refreshRisks(), runSim()])
  } catch (e) {
    error.value = e instanceof Error ? e.message : '품목 조회 실패'
  } finally {
    loading.value = false
  }
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null
function onSlider(e: Event) {
  extraDelay.value = Number((e.target as HTMLInputElement).value)
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => void runSim(), 150)
}
</script>

<template>
  <div class="inventory-pane">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading && !items.length" class="hint">품목 불러오는 중...</p>
    <p v-if="!loading && !items.length" class="hint">품목 마스터가 없습니다.</p>

    <div class="item-cards">
      <button
        v-for="item in items"
        :key="item.item_id"
        class="item-card"
        :class="{ selected: selectedId === item.item_id }"
        @click="select(item.item_id)"
      >
        <div class="item-head">
          <span class="item-name">{{ item.name }}</span>
          <span
            v-if="riskByItem[item.item_id]"
            class="risk-badge"
            :style="{ background: riskColorOf(item.item_id) }"
          >
            {{ riskLabelOf(item.item_id) }}
          </span>
        </div>
        <div class="item-meta">
          {{ item.destination || item.item_id }} · {{ item.source === 'blap' ? 'B-LAP 실데이터' : '샘플 데이터' }}
        </div>
        <div class="item-meta">
          재고 {{ item.on_hand_units.toLocaleString() }} / 미니멈 {{ item.min_level_units.toLocaleString() }}
          <span v-if="item.params_missing" class="params-missing">기준값 미설정(가정값)</span>
        </div>
      </button>
    </div>

    <template v-if="result && selectedItem">
      <p v-if="result.warning" class="warning-banner">{{ result.warning }}</p>

      <section class="whatif card">
        <div class="whatif-head">
          <span class="whatif-label">What-if: 추가 지연일</span>
          <span class="whatif-value" :style="{ color: resultRiskColor }">
            +{{ extraDelay }}일
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="30"
          step="1"
          :value="extraDelay"
          class="slider"
          @input="onSlider"
        />
      </section>

      <section class="card chart-section" :class="{ stale: simLoading }">
        <InventoryCurveChart
          :series-plan="result.series_plan"
          :series-current="result.series_current"
          :min-level="selectedItem.min_level_units"
          :risk-level="result.metrics.risk_level"
          :unit="selectedItem.unit"
        />
      </section>

      <section class="chips">
        <div class="chip-card">
          <div class="chip-label">최저 재고</div>
          <div class="chip-value">{{ result.metrics.min_balance.toLocaleString() }}</div>
          <div class="chip-sub">{{ result.metrics.min_balance_date }}</div>
        </div>
        <div class="chip-card">
          <div class="chip-label">미니멈 하회 구간</div>
          <div class="chip-value">{{ result.metrics.below_min_windows.length }}건</div>
          <div class="chip-sub">{{ firstBelowMinWindowText }}</div>
        </div>
        <div class="chip-card">
          <div class="chip-label">부족 예상 수량</div>
          <div class="chip-value">{{ result.metrics.gap_qty.toLocaleString() }}</div>
          <div class="chip-sub">{{ selectedItem.unit }}</div>
        </div>
        <div class="chip-card">
          <div class="chip-label">최대 지연일</div>
          <div class="chip-value">{{ result.metrics.max_delay_days }}일</div>
          <div class="chip-sub">계획 대비</div>
        </div>
      </section>

      <section v-if="result.actions.length" class="actions">
        <div v-for="a in result.actions" :key="a.type" class="action-card">
          <div class="action-head">
            <span class="action-type">
              {{ a.type === 'AIR_UPGRADE' ? '항공 전환 검토' : '발주 앞당김' }}
            </span>
            <span v-if="a.qty" class="action-emph">{{ a.qty.toLocaleString() }}{{ selectedItem.unit }}</span>
            <span v-if="a.days" class="action-emph">{{ a.days }}일</span>
          </div>
          <p class="action-text">{{ a.text_ko }}</p>
        </div>
      </section>

      <section class="card shipments">
        <h4>선적 현황 (ETA 계획 → 현재)</h4>
        <div v-for="s in selectedItem.shipments" :key="s.shipment_id" class="shipment-row">
          <span class="shipment-vessel">{{ s.vessel_name }}</span>
          <span class="shipment-meta">
            {{ s.qty.toLocaleString() }}{{ selectedItem.unit }} · {{ s.eta_plan }} → {{ s.eta_current }}
          </span>
        </div>
      </section>
    </template>

    <p class="hitl-note">본 시뮬레이션은 참고용 계산이며 최종 판단은 수급 담당자가 수행합니다.</p>
  </div>
</template>

<style scoped>
.inventory-pane {
  max-width: 720px;
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
.item-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.item-card {
  flex: 1;
  min-width: 200px;
  text-align: left;
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-shadow: var(--li-shadow-card);
}
.item-card.selected {
  border-color: var(--li-blue);
  box-shadow: 0 0 0 1px var(--li-blue);
}
.item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.item-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--li-text);
}
.risk-badge {
  font-size: 12px;
  color: #fff;
  border-radius: 999px;
  padding: 1px 8px;
  flex-shrink: 0;
}
.item-meta {
  font-size: 12px;
  color: var(--li-text-muted);
}
.whatif-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}
.whatif-label {
  font-size: 12px;
  color: var(--li-text-muted);
}
.whatif-value {
  font-size: 22px;
  font-weight: 800;
  transition: color 0.3s;
}
.slider {
  width: 100%;
  accent-color: var(--li-blue);
}
.chart-section {
  transition: opacity 0.2s;
}
.chart-section.stale {
  opacity: 0.5;
}
.chips {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}
.chip-card {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 10px 12px;
}
.chip-label {
  font-size: 12px;
  color: var(--li-text-muted);
}
.chip-value {
  font-size: 18px;
  font-weight: 800;
  color: var(--li-text);
}
.chip-sub {
  font-size: 12px;
  color: var(--li-text-muted);
}
.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.action-card {
  background: var(--li-risk-high-bg);
  border: 1px solid var(--li-risk-high-border);
  border-radius: var(--li-radius-md);
  padding: 12px;
}
.action-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.action-type {
  font-size: 13px;
  font-weight: 700;
  color: var(--li-text);
}
.action-emph {
  font-size: 16px;
  font-weight: 800;
  color: var(--li-risk-high);
}
.action-text {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--li-text-soft);
}
.shipments h4 {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--li-text-muted);
}
.shipment-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 0;
  border-top: 1px solid var(--li-border);
  font-size: 12px;
}
.shipment-vessel {
  font-weight: 700;
  color: var(--li-text);
}
.shipment-meta {
  color: var(--li-text-muted);
}
.hitl-note {
  font-size: 12px;
  color: var(--li-text-faint);
}
.params-missing {
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border: 1px solid var(--li-risk-high-border);
}
.warning-banner {
  margin: 0;
  padding: 8px 12px;
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
  border: 1px solid var(--li-risk-high-border);
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
