<script setup lang="ts">
import type {
  MiEvent,
  MiImpactSummary,
  MiTransportImpact,
} from '@/types/dashboard'

const props = defineProps<{
  events: MiEvent[]
  impacts: MiTransportImpact[]
  summary: MiImpactSummary
  selectedEventId?: string
}>()

const emit = defineEmits<{
  selectEvent: [eventId: string]
}>()

function impactsForEvent(eventId: string) {
  return new Set(
    props.impacts
      .filter((impact) => impact.event_id === eventId)
      .map((impact) => impact.transport_key),
  ).size
}

</script>

<template>
  <section class="panel-section mi-risk-section">
    <div class="section-heading">
      <div>
        <span class="eyebrow">EXTERNAL MI</span>
        <h2>외부 물류 리스크 영향권</h2>
      </div>

      <span class="event-count">{{ events.length }}</span>
    </div>

    <div class="mi-summary-grid">
      <div>
        <span>MI 이벤트</span>
        <strong>{{ summary.event_count }}</strong>
      </div>
      <div>
        <span>영향 운송</span>
        <strong>{{ summary.impacted_transport_count }}</strong>
      </div>
      <div>
        <span>접근 예상</span>
        <strong>{{ summary.approaching_count }}</strong>
      </div>
      <div>
        <span>영향권 내</span>
        <strong>{{ summary.in_zone_count }}</strong>
      </div>
    </div>

    <div class="mi-event-list">
      <button
        v-for="event in events"
        :key="event.event_id"
        type="button"
        class="mi-event-card"
        :class="[
          `severity-${event.severity.toLowerCase()}`,
          { selected: event.event_id === selectedEventId },
        ]"
        @click="emit('selectEvent', event.event_id)"
      >
        <div class="mi-event-title">
          <span>{{ event.severity }}</span>
          <strong>{{ event.headline }}</strong>
        </div>

        <p>{{ event.summary }}</p>

        <div class="mi-event-meta">
          <span>{{ event.status }}</span>
          <span>영향 운송 {{ impactsForEvent(event.event_id) }}건</span>
          <span>신뢰도 {{ Math.round(event.confidence * 100) }}%</span>
        </div>
      </button>
    </div>

    <div v-if="events.length === 0" class="empty-list">
      MI 이벤트 JSON을 업로드하면 영향권과 관련 운송건이 표시됩니다.
    </div>
  </section>
</template>

<style scoped>
.mi-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  margin-bottom: 11px;
}

.mi-summary-grid > div {
  padding: 9px 5px;
  border: 1px solid rgba(255, 97, 132, 0.13);
  border-radius: 7px;
  background: rgba(55, 12, 30, 0.34);
  text-align: center;
}

.mi-summary-grid span {
  display: block;
  margin-bottom: 4px;
  color: #9a6c7a;
  font-size: 11px;
}

.mi-summary-grid strong {
  color: #ffd5df;
  font-size: 15px;
}

.mi-event-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 270px;
  overflow-y: auto;
}

.mi-event-card {
  width: 100%;
  padding: 10px;
  border: 1px solid rgba(255, 108, 139, 0.15);
  border-left-width: 3px;
  border-radius: 7px;
  background: rgba(38, 10, 23, 0.38);
  color: inherit;
  text-align: left;
}

.mi-event-card.selected {
  border-color: rgba(255, 111, 146, 0.55);
  background: rgba(79, 16, 41, 0.55);
}

.mi-event-title {
  display: flex;
  align-items: flex-start;
  gap: 7px;
}

.mi-event-title span {
  flex: 0 0 auto;
  color: #ff8da6;
  font-size: 11px;
  font-weight: 800;
}

.mi-event-title strong {
  color: #ffe6ec;
  font-size: 11px;
  line-height: 1.35;
}

.mi-event-card p {
  display: -webkit-box;
  margin: 6px 0;
  overflow: hidden;
  color: #a5828e;
  font-size: 11px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mi-event-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 9px;
  color: #815d69;
  font-size: 11px;
}

.severity-critical { border-left-color: #ff3158; }
.severity-high { border-left-color: #ff8a28; }
.severity-medium { border-left-color: #ffd24a; }
.severity-low { border-left-color: #47d7ff; }
</style>
