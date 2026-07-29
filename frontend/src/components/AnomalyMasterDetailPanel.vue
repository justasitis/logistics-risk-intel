<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import CauseAnalysisPanel from '@/components/CauseAnalysisPanel.vue'
import WatchToggle from '@/components/WatchToggle.vue'
import ScheduleTimeline from '@/components/ScheduleTimeline.vue'
import type { CauseCandidate } from '@/types/causeAnalysis'
import type {
  ScheduleEvent,
  ScheduleTimelineResponse,
  TransportRecord,
} from '@/types/dashboard'
import type { RefinedMiEvent } from '@/types/mi'
import type { MiTransportImpact } from '@/types/miImpact'
import {
  eventSelectionKey,
} from '@/utils/selectionSync'
import {
  shipmentDisplayId,
  shipmentSystemId,
} from '@/utils/shipmentDisplay'

type DetailTab = 'SUMMARY' | 'TIMELINE' | 'MI' | 'CAUSE'
type SeverityFilter = 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

const props = defineProps<{
  events: ScheduleEvent[]
  transports: TransportRecord[]
  selectedTransport: TransportRecord | null
  selectedEventKey?: string
  timeline: ScheduleTimelineResponse | null
  timelineLoading: boolean
  timelineError: string
  miEvents: RefinedMiEvent[]
  miImpacts: MiTransportImpact[]
  causeCandidates: CauseCandidate[]
}>()

const emit = defineEmits<{
  selectEvent: [event: ScheduleEvent]
  selectMi: [eventId: string]
}>()

const searchText = ref('')
const severityFilter = ref<SeverityFilter>('ALL')
const activeTab = ref<DetailTab>('SUMMARY')

const tabs: Array<{ value: DetailTab; label: string }> = [
  { value: 'SUMMARY', label: '요약' },
  { value: 'TIMELINE', label: 'Timeline' },
  { value: 'MI', label: 'MI 영향' },
  { value: 'CAUSE', label: '원인 후보' },
]

const severityOptions: Array<{ value: SeverityFilter; label: string }> = [
  { value: 'ALL', label: '전체 위험도' },
  { value: 'CRITICAL', label: 'CRITICAL' },
  { value: 'HIGH', label: 'HIGH' },
  { value: 'MEDIUM', label: 'MEDIUM' },
  { value: 'LOW', label: 'LOW' },
]

function normalized(value: unknown): string {
  return String(value ?? '')
    .normalize('NFKC')
    .replace(/[\s-]+/g, '')
    .toUpperCase()
}

function searchableEventText(event: ScheduleEvent): string {
  // 공급업체/품목 검색은 transports의 확장 필드(선택키로 조인)를 통해 매칭
  const transport = transportByKey.value.get(event.transport_key)
  return normalized([
    event.hbl_no,
    event.trpr_no,
    event.headline,
    event.pol,
    event.pol_name,
    event.pod,
    event.pod_name,
    event.vessel_name,
    event.primary_signal,
    ...(event.signals ?? []),
    transport?.sppl_names,
    transport?.item_names,
    ...(transport?.item_cds ?? []),
  ].join('|'))
}

const transportByKey = computed(
  () => new Map(props.transports.map((t) => [t.transport_key, t])),
)

const filteredEvents = computed(() => {
  const query = normalized(searchText.value)

  return props.events.filter((event) => {
    const severityMatches = severityFilter.value === 'ALL'
      || String(event.severity ?? '').toUpperCase() === severityFilter.value

    const queryMatches = !query || searchableEventText(event).includes(query)

    return severityMatches && queryMatches
  })
})

const selectedFilteredIndex = computed(() => {
  if (props.selectedEventKey) {
    const exactIndex = filteredEvents.value.findIndex(
      (event) => eventSelectionKey(event) === props.selectedEventKey,
    )
    if (exactIndex >= 0) return exactIndex
  }

  const transportKey = props.selectedTransport?.transport_key ?? ''
  return filteredEvents.value.findIndex(
    (event) => event.transport_key === transportKey,
  )
})

const selectedMiImpacts = computed(() => {
  const transportKey = props.selectedTransport?.transport_key ?? ''
  if (!transportKey) return []

  return props.miImpacts.filter(
    (impact) => impact.transport_key === transportKey,
  )
})

const miEventById = computed(() => new Map(
  props.miEvents.map((event) => [event.event_id, event]),
))

const selectedDisplayId = computed(() =>
  shipmentDisplayId(props.selectedTransport),
)

const selectedSystemId = computed(() =>
  shipmentSystemId(props.selectedTransport),
)

const selectedPositionLabel = computed(() => {
  if (!filteredEvents.value.length) return '0 / 0'
  if (selectedFilteredIndex.value < 0) return `- / ${filteredEvents.value.length}`
  return `${selectedFilteredIndex.value + 1} / ${filteredEvents.value.length}`
})

watch(
  () => props.selectedTransport?.transport_key,
  () => {
    activeTab.value = 'SUMMARY'
  },
)

function formatDate(value?: string | null): string {
  if (!value) return '-'

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(parsed)
}

function signedDays(value?: number | null): string {
  if (value === null || value === undefined) return '-'
  if (value > 0) return `+${value}일`
  return `${value}일`
}

function deliveryBreachLabel(value?: number | null): string {
  if (value === null || value === undefined) return '-'
  if (value > 0) return `초과 +${value}일`
  return '정상'
}

function severityClass(value?: string): string {
  return `severity-${String(value ?? 'NORMAL').toLowerCase()}`
}

function displayRoute(
  source: ScheduleEvent | TransportRecord | null,
): string {
  if (!source) return '- → -'

  const pol = source.pol_name || source.pol || '-'
  const pod = source.pod_name || source.pod || '-'
  return `${pol} → ${pod}`
}

function selectEvent(event: ScheduleEvent): void {
  emit('selectEvent', event)
}

function navigateEvent(offset: number): void {
  if (!filteredEvents.value.length) return

  const current = selectedFilteredIndex.value
  const nextIndex = current < 0
    ? 0
    : Math.min(
        filteredEvents.value.length - 1,
        Math.max(0, current + offset),
      )

  const event = filteredEvents.value[nextIndex]
  if (event) emit('selectEvent', event)
}

function miHeadline(impact: MiTransportImpact): string {
  return miEventById.value.get(impact.event_id)?.headline
    ?? impact.event_id
}

function miStatus(impact: MiTransportImpact): string {
  return miEventById.value.get(impact.event_id)?.status ?? '-'
}

function miValidPeriod(impact: MiTransportImpact): string {
  const event = miEventById.value.get(impact.event_id)
  if (!event) return '-'
  return `${formatDate(event.valid_from)} ~ ${formatDate(event.valid_to)}`
}
</script>

<template>
  <section class="anomaly-master-detail">
    <aside class="anomaly-master-detail__master">
      <header class="anomaly-master-detail__master-header">
        <div>
          <span class="eyebrow">EARLY WARNING</span>
          <h2>일정 이상 화물</h2>
        </div>
        <span class="anomaly-master-detail__count">
          {{ filteredEvents.length }} / {{ events.length }}
        </span>
      </header>

      <div class="anomaly-master-detail__filters">
        <label class="anomaly-master-detail__search">
          <span class="sr-only">HBL, TR, 선박 검색</span>
          <input
            v-model="searchText"
            type="search"
            placeholder="HBL · TR · 선박 · 공급업체 · 품목 검색"
          />
        </label>

        <select v-model="severityFilter">
          <option
            v-for="option in severityOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </div>

      <div v-if="filteredEvents.length" class="anomaly-master-detail__list">
        <button
          v-for="event in filteredEvents"
          :key="eventSelectionKey(event)"
          type="button"
          class="anomaly-event-card"
          :class="[
            severityClass(event.severity),
            {
              selected: selectedEventKey
                ? selectedEventKey === eventSelectionKey(event)
                : event.transport_key === selectedTransport?.transport_key,
            },
          ]"
          @click="selectEvent(event)"
        >
          <div class="anomaly-event-card__top">
            <strong>{{ shipmentDisplayId(event) }}</strong>
            <span class="anomaly-event-card__score">
              {{ event.risk_score }}
            </span>
          </div>

          <div class="anomaly-event-card__route">
            {{ displayRoute(event) }}
          </div>

          <div class="anomaly-event-card__headline">
            {{ event.headline }}
          </div>

          <div class="anomaly-event-card__meta">
            <span>{{ event.severity }}</span>
            <span>ETA {{ signedDays(event.eta_net_delay_days) }}</span>
            <span>LT {{ signedDays(event.lead_time_variance_days) }}</span>
            <span
              v-if="(event.delivery_req_breach_days ?? 0) > 0"
              class="anomaly-event-card__breach"
            >
              납기 초과 {{ signedDays(event.delivery_req_breach_days) }}
            </span>
          </div>

          <div class="anomaly-event-card__system-id">
            B-LAP {{ event.trpr_no || '-' }}
          </div>
        </button>
      </div>

      <div v-else class="anomaly-master-detail__empty">
        검색 또는 필터 조건에 맞는 일정 이상 화물이 없습니다.
      </div>
    </aside>

    <article class="anomaly-master-detail__detail">
      <template v-if="selectedTransport">
        <header class="anomaly-master-detail__detail-header">
          <div class="anomaly-master-detail__identity">
            <span class="eyebrow">SELECTED SHIPMENT</span>
            <h2>{{ selectedDisplayId }}</h2>
            <WatchToggle
              v-if="selectedTransport.hbl_no"
              :key="selectedTransport.transport_key"
              :hbl-no="selectedTransport.hbl_no"
              :label="selectedDisplayId"
            />
            <p>
              {{ displayRoute(selectedTransport) }}
              <span>·</span>
              B-LAP {{ selectedSystemId }}
            </p>
          </div>

          <div class="anomaly-master-detail__navigation">
            <button
              type="button"
              :disabled="selectedFilteredIndex <= 0"
              aria-label="이전 화물"
              @click="navigateEvent(-1)"
            >
              ‹ 이전
            </button>
            <span>{{ selectedPositionLabel }}</span>
            <button
              type="button"
              :disabled="selectedFilteredIndex < 0
                || selectedFilteredIndex >= filteredEvents.length - 1"
              aria-label="다음 화물"
              @click="navigateEvent(1)"
            >
              다음 ›
            </button>
          </div>
        </header>

        <nav class="anomaly-master-detail__tabs" aria-label="선택 화물 상세 탭">
          <button
            v-for="tab in tabs"
            :key="tab.value"
            type="button"
            :class="{ active: activeTab === tab.value }"
            @click="activeTab = tab.value"
          >
            {{ tab.label }}
            <span v-if="tab.value === 'MI'">
              {{ selectedMiImpacts.length }}
            </span>
            <span v-else-if="tab.value === 'CAUSE'">
              {{ causeCandidates.length }}
            </span>
          </button>
        </nav>

        <div class="anomaly-master-detail__detail-body">
          <section v-if="activeTab === 'SUMMARY'" class="shipment-summary-tab">
            <div class="shipment-summary-tab__status">
              <span
                class="shipment-summary-tab__severity"
                :class="severityClass(selectedTransport.severity)"
              >
                {{ selectedTransport.severity }}
              </span>
              <strong>Risk {{ selectedTransport.risk_score }}</strong>
            </div>

            <dl class="shipment-summary-tab__grid">
              <div class="shipment-summary-tab__primary-id">
                <dt>HBL No.</dt>
                <dd>{{ selectedTransport.hbl_no || 'HBL 미등록' }}</dd>
              </div>
              <div>
                <dt>B-LAP 운송번호</dt>
                <dd>{{ selectedTransport.trpr_no || '-' }}</dd>
              </div>
              <div>
                <dt>법인 / Plant</dt>
                <dd>
                  {{ selectedTransport.cmpy_nm || selectedTransport.cmpy_cd || '-' }}
                  /
                  {{ selectedTransport.plnt_cd || '-' }}
                </dd>
              </div>
              <div>
                <dt>Route</dt>
                <dd>{{ displayRoute(selectedTransport) }}</dd>
              </div>
              <div>
                <dt>Vessel</dt>
                <dd>{{ selectedTransport.vessel_name || '-' }}</dd>
              </div>
              <div>
                <dt>Voyage</dt>
                <dd>{{ selectedTransport.voyage_no || '-' }}</dd>
              </div>
              <div>
                <dt>ETD</dt>
                <dd>
                  {{ formatDate(selectedTransport.etd_initial) }}
                  →
                  {{ formatDate(selectedTransport.current_etd) }}
                </dd>
              </div>
              <div>
                <dt>ETA</dt>
                <dd class="danger-text">
                  {{ formatDate(selectedTransport.eta_initial) }}
                  →
                  {{ formatDate(selectedTransport.current_eta) }}
                </dd>
              </div>
              <div>
                <dt>ETD 순지연</dt>
                <dd>{{ signedDays(selectedTransport.etd_net_delay_days) }}</dd>
              </div>
              <div>
                <dt>ETA 순지연</dt>
                <dd class="danger-text">
                  {{ signedDays(selectedTransport.eta_net_delay_days) }}
                </dd>
              </div>
              <div>
                <dt>ETA 반복지연</dt>
                <dd>{{ selectedTransport.eta_delay_count_recent ?? 0 }}회</dd>
              </div>
              <div>
                <dt>Lead Time 변화</dt>
                <dd class="danger-text">
                  {{ signedDays(selectedTransport.lead_time_variance_days) }}
                </dd>
              </div>
              <div>
                <dt>납품 요청일</dt>
                <dd>{{ formatDate(selectedTransport.delivery_request_date) }}</dd>
              </div>
              <div>
                <dt>납품 예정일</dt>
                <dd>{{ formatDate(selectedTransport.delivery_eta) }}</dd>
              </div>
              <div>
                <dt>납기 초과</dt>
                <dd
                  :class="(selectedTransport.delivery_req_breach_days ?? 0) > 0
                    ? 'danger-text'
                    : ''"
                >
                  {{ deliveryBreachLabel(selectedTransport.delivery_req_breach_days) }}
                </dd>
              </div>
              <div>
                <dt>PO</dt>
                <dd>
                  <details v-if="selectedTransport.po_nos" class="inline-list">
                    <summary>{{ selectedTransport.po_count ?? 0 }}건</summary>
                    <div class="inline-list__body">
                      <span
                        v-for="po in selectedTransport.po_nos.split(',')"
                        :key="po"
                        class="inline-list__item"
                      >{{ po.trim() }}</span>
                    </div>
                  </details>
                  <template v-else>{{ selectedTransport.po_count ?? 0 }}건</template>
                </dd>
              </div>
              <div>
                <dt>Item</dt>
                <dd>
                  <details v-if="(selectedTransport.item_cds?.length ?? 0) > 0" class="inline-list">
                    <summary>{{ selectedTransport.item_count ?? 0 }}개</summary>
                    <div class="inline-list__body">
                      <span
                        v-for="cd in selectedTransport.item_cds ?? []"
                        :key="cd"
                        class="inline-list__item"
                      >{{ cd }}</span>
                      <span
                        v-if="selectedTransport.item_names"
                        class="inline-list__names"
                      >{{ selectedTransport.item_names }}</span>
                    </div>
                  </details>
                  <template v-else>{{ selectedTransport.item_count ?? 0 }}개</template>
                </dd>
              </div>
            </dl>

            <div class="shipment-summary-tab__signals">
              <span
                v-for="signal in selectedTransport.anomaly_signals"
                :key="signal"
              >
                {{ signal }}
              </span>
            </div>
          </section>

          <section v-else-if="activeTab === 'TIMELINE'" class="shipment-tab-panel">
            <ScheduleTimeline
              :timeline="timeline"
              :loading="timelineLoading"
              :error="timelineError"
            />
          </section>

          <section v-else-if="activeTab === 'MI'" class="shipment-mi-tab">
            <article
              v-for="impact in selectedMiImpacts"
              :key="`${impact.event_id}:${impact.transport_key}`"
              class="shipment-mi-card"
            >
              <div class="shipment-mi-card__head">
                <span>{{ impact.severity }}</span>
                <strong>{{ impact.match_score }}</strong>
              </div>

              <button
                type="button"
                @click="emit('selectMi', impact.event_id)"
              >
                {{ miHeadline(impact) }}
              </button>

              <dl>
                <div>
                  <dt>상태</dt>
                  <dd>{{ miStatus(impact) }}</dd>
                </div>
                <div>
                  <dt>유효기간</dt>
                  <dd>{{ miValidPeriod(impact) }}</dd>
                </div>
                <div>
                  <dt>연결 방식</dt>
                  <dd>{{ impact.match_methods.join(' + ') }}</dd>
                </div>
                <div>
                  <dt>AIS 노출</dt>
                  <dd>{{ impact.exposure_status }}</dd>
                </div>
                <div>
                  <dt>영향권 거리</dt>
                  <dd>
                    {{ impact.distance_to_zone_km === null
                      ? '-'
                      : `${impact.distance_to_zone_km.toFixed(1)} km` }}
                  </dd>
                </div>
              </dl>
            </article>

            <div v-if="selectedMiImpacts.length === 0" class="anomaly-master-detail__empty">
              선택 화물과 연결된 승인 MI 영향이 없습니다.
            </div>
          </section>

          <section v-else class="shipment-tab-panel">
            <CauseAnalysisPanel
              :transport="selectedTransport"
              :candidates="causeCandidates"
              @select-mi="emit('selectMi', $event)"
            />
          </section>
        </div>
      </template>

      <div v-else class="anomaly-master-detail__empty anomaly-master-detail__empty--detail">
        일정 이상 화물 또는 지도 Route를 선택하세요.
      </div>
    </article>
  </section>
</template>

<style scoped>
.anomaly-master-detail {
  display: grid;
  grid-template-columns: minmax(270px, 0.86fr) minmax(390px, 1.4fr);
  min-height: 610px;
  height: min(760px, calc(100vh - 164px));
  margin: 12px;
  overflow: hidden;
  color: var(--li-text, #122033);
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 20px;
  background: var(--li-surface, rgba(255, 255, 255, 0.78));
  box-shadow: var(--li-shadow-card, 0 14px 32px rgba(15, 32, 54, 0.09));
  backdrop-filter: blur(20px);
}

.anomaly-master-detail__master,
.anomaly-master-detail__detail {
  min-width: 0;
  min-height: 0;
}

.anomaly-master-detail__master {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  border-right: 1px solid var(--li-border, rgba(16, 42, 67, 0.1));
  background: rgba(248, 250, 252, 0.68);
}

.anomaly-master-detail__master-header,
.anomaly-master-detail__detail-header,
.anomaly-event-card__top,
.anomaly-event-card__meta,
.anomaly-master-detail__navigation,
.shipment-summary-tab__status,
.shipment-mi-card__head {
  display: flex;
  align-items: center;
}

.anomaly-master-detail__master-header {
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 12px;
}

.anomaly-master-detail h2 {
  margin: 3px 0 0;
  font-size: 17px;
  line-height: 1.25;
}

.anomaly-master-detail__count {
  padding: 6px 9px;
  color: var(--li-blue, #2563eb);
  font-size: 10px;
  font-weight: 800;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
}

.anomaly-master-detail__filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 112px;
  gap: 8px;
  padding: 0 14px 12px;
}

.anomaly-master-detail__filters input,
.anomaly-master-detail__filters select {
  width: 100%;
  min-height: 38px;
  padding: 0 10px;
  color: var(--li-text, #122033);
  font: inherit;
  font-size: 11px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.13));
  border-radius: 10px;
  outline: none;
  background: rgba(255, 255, 255, 0.82);
}

.anomaly-master-detail__filters input:focus,
.anomaly-master-detail__filters select:focus {
  border-color: rgba(37, 99, 235, 0.42);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
}

.anomaly-master-detail__list {
  display: grid;
  align-content: start;
  gap: 8px;
  min-height: 0;
  padding: 0 12px 14px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.anomaly-event-card {
  width: 100%;
  padding: 12px;
  color: var(--li-text, #122033);
  text-align: left;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.1));
  border-left-width: 4px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.76);
  cursor: pointer;
  transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
}

.anomaly-event-card:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow: 0 9px 20px rgba(15, 32, 54, 0.07);
}

.anomaly-event-card.selected {
  border-color: rgba(37, 99, 235, 0.52);
  background: rgba(232, 244, 255, 0.88);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.11);
}

.anomaly-event-card.severity-critical { border-left-color: #dc2626; }
.anomaly-event-card.severity-high { border-left-color: #ea580c; }
.anomaly-event-card.severity-medium { border-left-color: #d97706; }
.anomaly-event-card.severity-low,
.anomaly-event-card.severity-normal { border-left-color: #0284c7; }

.anomaly-event-card__top {
  justify-content: space-between;
  gap: 8px;
}

.anomaly-event-card__top strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.anomaly-event-card__score {
  display: grid;
  flex: 0 0 auto;
  min-width: 30px;
  height: 27px;
  padding: 0 6px;
  place-items: center;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 850;
  border-radius: 8px;
  background: rgba(37, 99, 235, 0.09);
}

.anomaly-event-card__route {
  margin-top: 6px;
  overflow: hidden;
  color: var(--li-text-muted, #607086);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.anomaly-event-card__headline {
  display: -webkit-box;
  margin-top: 7px;
  overflow: hidden;
  font-size: 11px;
  font-weight: 750;
  line-height: 1.4;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.anomaly-event-card__meta {
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.anomaly-event-card__meta span {
  padding: 3px 6px;
  color: var(--li-text-muted, #607086);
  font-size: 8px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.08);
}

.anomaly-event-card__meta span.anomaly-event-card__breach {
  color: #b45309;
  font-weight: 800;
  background: rgba(245, 158, 11, 0.14);
}

.anomaly-event-card__system-id {
  margin-top: 7px;
  color: var(--li-text-faint, #8a98aa);
  font-size: 8px;
}

.anomaly-master-detail__detail {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  background: rgba(255, 255, 255, 0.72);
}

.anomaly-master-detail__detail-header {
  position: relative;
  z-index: 2;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--li-border, rgba(16, 42, 67, 0.09));
  background: rgba(255, 255, 255, 0.92);
}

.anomaly-master-detail__identity {
  min-width: 0;
}

.anomaly-master-detail__identity h2 {
  overflow: hidden;
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.anomaly-master-detail__identity p {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 0;
  color: var(--li-text-muted, #607086);
  font-size: 10px;
}

.anomaly-master-detail__navigation {
  flex: 0 0 auto;
  gap: 7px;
}

.anomaly-master-detail__navigation button {
  min-height: 32px;
  padding: 0 9px;
  color: var(--li-text, #122033);
  font-size: 10px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.12));
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.92);
  cursor: pointer;
}

.anomaly-master-detail__navigation button:disabled {
  opacity: 0.38;
  cursor: default;
}

.anomaly-master-detail__navigation span {
  min-width: 42px;
  color: var(--li-text-muted, #607086);
  font-size: 9px;
  text-align: center;
}

.anomaly-master-detail__tabs {
  display: flex;
  gap: 4px;
  padding: 9px 14px;
  overflow-x: auto;
  border-bottom: 1px solid var(--li-border, rgba(16, 42, 67, 0.09));
  background: rgba(248, 250, 252, 0.84);
}

.anomaly-master-detail__tabs button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 34px;
  padding: 0 11px;
  color: var(--li-text-muted, #607086);
  font-size: 10px;
  font-weight: 750;
  white-space: nowrap;
  border: 0;
  border-radius: 9px;
  background: transparent;
  cursor: pointer;
}

.anomaly-master-detail__tabs button.active {
  color: var(--li-blue, #2563eb);
  background: rgba(37, 99, 235, 0.1);
}

.anomaly-master-detail__tabs span {
  display: grid;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  place-items: center;
  font-size: 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
}

.anomaly-master-detail__detail-body {
  min-height: 0;
  padding: 16px 18px 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.shipment-summary-tab {
  display: grid;
  gap: 15px;
}

.shipment-summary-tab__status {
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.88);
}

.shipment-summary-tab__status strong {
  font-size: 12px;
}

.shipment-summary-tab__severity {
  padding: 5px 9px;
  font-size: 9px;
  font-weight: 850;
  border-radius: 999px;
}

.shipment-summary-tab__severity.severity-critical {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.12);
}
.shipment-summary-tab__severity.severity-high {
  color: #c2410c;
  background: rgba(249, 115, 22, 0.12);
}
.shipment-summary-tab__severity.severity-medium {
  color: #b45309;
  background: rgba(245, 158, 11, 0.13);
}
.shipment-summary-tab__severity.severity-low,
.shipment-summary-tab__severity.severity-normal {
  color: #0369a1;
  background: rgba(14, 165, 233, 0.11);
}

.shipment-summary-tab__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.shipment-summary-tab__grid > div {
  min-width: 0;
  padding: 11px 12px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.09));
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.8);
}

.shipment-summary-tab__grid dt {
  margin-bottom: 5px;
  color: var(--li-text-muted, #607086);
  font-size: 9px;
}

.shipment-summary-tab__grid dd {
  margin: 0;
  overflow-wrap: anywhere;
  font-size: 11px;
  font-weight: 750;
  line-height: 1.4;
}

.shipment-summary-tab__primary-id {
  border-color: rgba(37, 99, 235, 0.2) !important;
  background: rgba(232, 244, 255, 0.72) !important;
}

.shipment-summary-tab__primary-id dd {
  color: var(--li-blue, #2563eb);
  font-size: 14px;
}

.shipment-summary-tab__signals {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.shipment-summary-tab__signals span {
  padding: 6px 8px;
  color: #0369a1;
  font-size: 9px;
  border-radius: 8px;
  background: rgba(14, 165, 233, 0.09);
}

.shipment-tab-panel {
  min-height: 100%;
}

.shipment-mi-tab {
  display: grid;
  gap: 10px;
}

.shipment-mi-card {
  padding: 13px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.1));
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.78);
}

.shipment-mi-card__head {
  justify-content: space-between;
  gap: 8px;
}

.shipment-mi-card__head span {
  padding: 4px 7px;
  color: #b45309;
  font-size: 8px;
  font-weight: 850;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.12);
}

.shipment-mi-card__head strong {
  color: var(--li-blue, #2563eb);
  font-size: 16px;
}

.shipment-mi-card > button {
  width: 100%;
  margin: 9px 0 11px;
  padding: 0;
  color: var(--li-text, #122033);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.45;
  text-align: left;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.shipment-mi-card dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  margin: 0;
}

.shipment-mi-card dl > div {
  padding: 8px;
  border-radius: 9px;
  background: rgba(248, 250, 252, 0.82);
}

.shipment-mi-card dt {
  margin-bottom: 3px;
  color: var(--li-text-muted, #607086);
  font-size: 8px;
}

.shipment-mi-card dd {
  margin: 0;
  font-size: 9px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.anomaly-master-detail__empty {
  display: grid;
  min-height: 130px;
  padding: 24px;
  place-items: center;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
  line-height: 1.55;
  text-align: center;
}

.anomaly-master-detail__empty--detail {
  min-height: 100%;
}

.inline-list summary {
  cursor: pointer;
}

.inline-list__body {
  display: flex;
  max-height: 72px;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  overflow-y: auto;
}

.inline-list__item {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--li-bg-app-2);
  font-size: 12px;
}

.inline-list__names {
  width: 100%;
  color: var(--li-text-muted);
  font-size: 12px;
}

.danger-text {
  color: #dc2626;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@media (max-width: 1380px) {
  .anomaly-master-detail {
    grid-template-columns: minmax(250px, 0.82fr) minmax(370px, 1.28fr);
  }

  .anomaly-master-detail__detail-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .anomaly-master-detail__navigation {
    align-self: stretch;
    justify-content: flex-end;
  }
}
</style>
