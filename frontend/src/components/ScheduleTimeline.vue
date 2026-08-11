<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import type {
  ScheduleTimelineResponse,
  TimelineEvent,
  TimelineTypeSummary,
} from '@/types/dashboard'

const props = defineProps<{
  timeline: ScheduleTimelineResponse | null
  loading: boolean
  error?: string
}>()

const activeType = ref<'ETA' | 'ETD'>('ETA')

const activeTimeline = computed<TimelineTypeSummary | null>(() => {
  if (!props.timeline) return null

  return activeType.value === 'ETA'
    ? props.timeline.eta
    : props.timeline.etd
})

const hasSourceHistory = computed(() =>
  (props.timeline?.history_row_count ?? 0) > 0,
)

watch(
  () => props.timeline,
  (timeline) => {
    if (!timeline) return

    if (timeline.eta.events.length > 0) {
      activeType.value = 'ETA'
    } else if (timeline.etd.events.length > 0) {
      activeType.value = 'ETD'
    }
  },
)

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function signedDays(value: number) {
  if (value > 0) return `+${value}일`
  return `${value}일`
}

function eventClass(event: TimelineEvent) {
  return `direction-${event.direction.toLowerCase()}`
}
</script>

<template>
  <div class="timeline-shell">
    <div class="timeline-heading">
      <div>
        <span class="timeline-eyebrow">SCHEDULE HISTORY</span>
        <strong>ETD·ETA 변경 Timeline</strong>
        <small v-if="timeline">
          ETD {{ timeline.etd.source_row_count ?? 0 }}건 ·
          ETA {{ timeline.eta.source_row_count ?? 0 }}건
        </small>
      </div>

      <div class="timeline-tabs">
        <button
          type="button"
          :class="{ active: activeType === 'ETA' }"
          @click="activeType = 'ETA'"
        >
          ETA
          <span>{{ timeline?.eta.change_count ?? 0 }}</span>
        </button>

        <button
          type="button"
          :class="{ active: activeType === 'ETD' }"
          @click="activeType = 'ETD'"
        >
          ETD
          <span>{{ timeline?.etd.change_count ?? 0 }}</span>
        </button>
      </div>
    </div>

    <div v-if="loading" class="timeline-state">
      <span class="timeline-spinner"></span>
      변경이력을 조회하는 중입니다.
    </div>

    <div v-else-if="error" class="timeline-state error">
      {{ error }}
    </div>

    <template v-else-if="activeTimeline">
      <div
        v-if="!hasSourceHistory"
        class="timeline-state"
      >
        데이터레이크에서 ETD·ETA 변경 이력을 찾지 못했습니다.
      </div>

      <template v-else>
      <div class="timeline-route">
        <div>
          <span>최초</span>
          <strong>{{ formatDate(activeTimeline.initial_date) }}</strong>
        </div>

        <div class="timeline-route-line">
          <span></span>
        </div>

        <div>
          <span>현재</span>
          <strong>{{ formatDate(activeTimeline.current_date) }}</strong>
        </div>
      </div>

      <div class="timeline-summary">
        <div>
          <span>변경</span>
          <strong>{{ activeTimeline.change_count }}회</strong>
        </div>
        <div>
          <span>지연</span>
          <strong>{{ activeTimeline.delay_count }}회</strong>
        </div>
        <div>
          <span>누적 지연</span>
          <strong>
            {{ signedDays(activeTimeline.gross_delay_days) }}
          </strong>
        </div>
        <div>
          <span>순변화</span>
          <strong
            :class="{
              delayed: activeTimeline.net_change_days > 0,
              advanced: activeTimeline.net_change_days < 0,
            }"
          >
            {{ signedDays(activeTimeline.net_change_days) }}
          </strong>
        </div>
      </div>

      <div
        v-if="activeTimeline.events.length"
        class="timeline-list"
      >
        <article
          v-for="event in activeTimeline.events"
          :key="event.history_no"
          class="timeline-event"
          :class="eventClass(event)"
        >
          <div class="timeline-axis">
            <span class="timeline-dot"></span>
            <span class="timeline-stem"></span>
          </div>

          <div class="timeline-event-body">
            <div class="timeline-event-meta">
              <time>{{ formatDateTime(event.changed_at) }}</time>
              <span class="change-badge">
                {{ signedDays(event.change_days) }}
              </span>
            </div>

            <div class="timeline-date-change">
              <span>{{ formatDate(event.previous_date) }}</span>
              <span class="arrow">→</span>
              <strong>{{ formatDate(event.revised_date) }}</strong>
            </div>

            <div v-if="event.changed_by" class="timeline-actor">
              {{ event.changed_by }}
            </div>
          </div>
        </article>
      </div>

      <div v-else class="timeline-state">
        원천 이력은 있지만 실제 날짜 변경은 없습니다.
      </div>
      </template>
    </template>

    <div v-else class="timeline-state">
      운송건을 선택하면 변경이력이 표시됩니다.
    </div>
  </div>
</template>

<style scoped>
.timeline-shell {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(93, 171, 215, 0.14);
}

.timeline-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.timeline-heading strong {
  display: block;
  color: var(--li-text, #122033);
  font-size: 11px;
}

.timeline-heading small {
  display: block;
  margin-top: 3px;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
}

.timeline-eyebrow {
  display: block;
  margin-bottom: 3px;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

.timeline-tabs {
  display: flex;
  gap: 4px;
}

.timeline-tabs button {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 7px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.13));
  border-radius: 5px;
  background: rgba(248, 250, 252, 0.92);
  color: var(--li-text-muted, #607086);
  font-size: 11px;
}

.timeline-tabs button.active {
  border-color: rgba(37, 99, 235, 0.42);
  background: rgba(37, 99, 235, 0.1);
  color: var(--li-blue, #2563eb);
}

.timeline-tabs button span {
  display: grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  background: rgba(37, 99, 235, 0.1);
  font-size: 12px;
}

.timeline-route {
  display: grid;
  grid-template-columns: auto minmax(40px, 1fr) auto;
  align-items: center;
  gap: 8px;
  margin-top: 13px;
  padding: 9px;
  border-radius: 7px;
  background: rgba(5, 25, 43, 0.72);
}

.timeline-route > div:first-child,
.timeline-route > div:last-child {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.timeline-route > div:last-child {
  text-align: right;
}

.timeline-route span {
  color: #9fb6c6;
  font-size: 12px;
}

.timeline-route strong {
  color: #d9effb;
  font-size: 12px;
}

.timeline-route-line {
  position: relative;
  height: 2px;
  background: linear-gradient(
    90deg,
    rgba(69, 211, 255, 0.25),
    rgba(255, 105, 126, 0.7)
  );
}

.timeline-route-line::before,
.timeline-route-line::after {
  position: absolute;
  top: 50%;
  width: 6px;
  height: 6px;
  content: '';
  border-radius: 50%;
  background: #72dcff;
  transform: translateY(-50%);
}

.timeline-route-line::before {
  left: 0;
}

.timeline-route-line::after {
  right: 0;
  background: #ff7089;
}

.timeline-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 5px;
  margin-top: 8px;
}

.timeline-summary > div {
  padding: 7px 5px;
  border: 1px solid rgba(83, 164, 207, 0.12);
  border-radius: 6px;
  background: rgba(6, 25, 42, 0.58);
  text-align: center;
}

.timeline-summary span {
  display: block;
  margin-bottom: 3px;
  color: #9fb6c6;
  font-size: 12px;
}

.timeline-summary strong {
  color: #d7edf9;
  font-size: 12px;
}

.timeline-summary strong.delayed {
  color: #ff788e;
}

.timeline-summary strong.advanced {
  color: #5de4b7;
}

.timeline-list {
  max-height: 230px;
  margin-top: 10px;
  padding-right: 3px;
  overflow-y: auto;
}

.timeline-event {
  display: grid;
  grid-template-columns: 17px minmax(0, 1fr);
  min-height: 62px;
}

.timeline-axis {
  position: relative;
  display: flex;
  justify-content: center;
}

.timeline-dot {
  position: relative;
  z-index: 2;
  width: 8px;
  height: 8px;
  margin-top: 7px;
  border: 2px solid #062035;
  border-radius: 50%;
  background: #58d8ff;
  box-shadow: 0 0 8px rgba(88, 216, 255, 0.7);
}

.direction-delayed .timeline-dot {
  background: #ff5d78;
  box-shadow: 0 0 8px rgba(255, 93, 120, 0.72);
}

.direction-advanced .timeline-dot {
  background: #48dcae;
  box-shadow: 0 0 8px rgba(72, 220, 174, 0.65);
}

.timeline-stem {
  position: absolute;
  top: 14px;
  bottom: -1px;
  width: 1px;
  background: rgba(88, 174, 217, 0.2);
}

.timeline-event:last-child .timeline-stem {
  display: none;
}

.timeline-event-body {
  padding: 4px 7px 11px;
}

.timeline-event-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.timeline-event-meta time {
  color: var(--li-text-muted, #607086);
  font-size: 12px;
}

.change-badge {
  padding: 3px 7px;
  border-radius: 8px;
  background: rgba(80, 176, 221, 0.1);
  color: #8bcbe7;
  font-size: 12px;
  font-weight: 700;
}

.direction-delayed .change-badge {
  background: rgba(255, 76, 106, 0.14);
  color: #ff8397;
}

.direction-advanced .change-badge {
  background: rgba(62, 221, 169, 0.13);
  color: #6ae7bf;
}

.timeline-date-change {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
}

.timeline-date-change .arrow {
  color: #4f7890;
}

.timeline-date-change strong {
  color: var(--li-blue);
  font-weight: 800;
}

.timeline-actor {
  margin-top: 4px;
  overflow: hidden;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timeline-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 78px;
  margin-top: 10px;
  padding: 10px;
  border-radius: 7px;
  background: rgba(241, 245, 249, 0.85);
  color: var(--li-text-muted, #607086);
  font-size: 11px;
  text-align: center;
}

.timeline-state.error {
  color: #dc2626;
}

.timeline-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(93, 201, 255, 0.2);
  border-top-color: #5ed7ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
