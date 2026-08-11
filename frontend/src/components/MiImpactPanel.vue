<script setup lang="ts">
import RiskBadge from '@/components/ui/RiskBadge.vue'
import type { RefinedMiEvent } from '@/types/mi'
import type {
  MiImpactSummary,
  MiTransportImpact,
} from '@/types/miImpact'

const props = defineProps<{
  events: RefinedMiEvent[]
  impacts: MiTransportImpact[]
  summary: MiImpactSummary
  selectedEventId?: string
}>()

const emit = defineEmits<{
  selectEvent: [eventId: string]
}>()

function impactCount(eventId: string): number {
  return new Set(
    props.impacts
      .filter((impact) => impact.event_id === eventId)
      .map((impact) => impact.transport_key),
  ).size
}
</script>

<template>
  <section class="mi-impact-panel">
    <div class="mi-impact-heading">
      <div>
        <span class="eyebrow">APPROVED MI</span>
        <h2>외부 물류 리스크 영향</h2>
      </div>
      <span class="mi-impact-count">{{ events.length }}</span>
    </div>

    <div class="mi-impact-summary">
      <div>
        <span>MI Event</span>
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

    <div class="mi-impact-list">
      <button
        v-for="event in events"
        :key="event.event_id"
        type="button"
        class="mi-impact-card"
        :class="{ selected: event.event_id === selectedEventId }"
        @click="emit('selectEvent', event.event_id)"
      >
        <div class="mi-impact-card__head">
          <RiskBadge :severity="event.severity" />
          <span>{{ Math.round(event.confidence * 100) }}%</span>
        </div>

        <strong>{{ event.headline }}</strong>
        <p>{{ event.summary }}</p>

        <div class="mi-impact-card__meta">
          <span>{{ event.status }}</span>
          <span>위치 {{ event.affected_locations.length }}</span>
          <span>영향 운송 {{ impactCount(event.event_id) }}</span>
        </div>
      </button>
    </div>

    <div v-if="events.length === 0" class="mi-impact-empty">
      외부 MI 정제 화면에서 Event를 승인하고 검토 결과를 저장하세요.
    </div>
  </section>
</template>

<style scoped>
.mi-impact-panel {
  margin: 12px;
  padding: 14px;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 18px;
  background: var(--li-surface, rgba(255, 255, 255, 0.76));
  box-shadow: var(--li-shadow-card, 0 12px 28px rgba(15, 32, 54, 0.08));
  backdrop-filter: blur(18px);
}

.mi-impact-heading,
.mi-impact-card__head,
.mi-impact-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mi-impact-heading {
  margin-bottom: 12px;
}

.mi-impact-heading h2 {
  margin: 3px 0 0;
  color: var(--li-text, #122033);
  font-size: 14px;
}

.mi-impact-count {
  display: grid;
  min-width: 28px;
  height: 26px;
  place-items: center;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 850;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
}

.mi-impact-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  margin-bottom: 11px;
}

.mi-impact-summary > div {
  padding: 9px 5px;
  text-align: center;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.6);
}

.mi-impact-summary span {
  display: block;
  margin-bottom: 4px;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
}

.mi-impact-summary strong {
  color: var(--li-text, #122033);
  font-size: 14px;
}

.mi-impact-list {
  display: grid;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.mi-impact-card {
  width: 100%;
  padding: 11px;
  color: var(--li-text, #122033);
  text-align: left;
  border: 1px solid var(--li-border, rgba(16, 42, 67, 0.11));
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.62);
  cursor: pointer;
}

.mi-impact-card:hover,
.mi-impact-card.selected {
  border-color: rgba(37, 99, 235, 0.35);
  background: rgba(232, 244, 255, 0.78);
  box-shadow: 0 9px 20px rgba(37, 99, 235, 0.1);
}

.mi-impact-card__head > span:last-child {
  color: var(--li-text-muted, #607086);
  font-size: 12px;
  font-weight: 750;
}

.mi-impact-card > strong {
  display: block;
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.38;
}

.mi-impact-card p {
  display: -webkit-box;
  margin: 6px 0;
  overflow: hidden;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.mi-impact-card__meta {
  justify-content: flex-start;
  flex-wrap: wrap;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
}

.mi-impact-empty {
  padding: 18px 8px;
  color: var(--li-text-muted, #607086);
  font-size: 12px;
  line-height: 1.5;
  text-align: center;
}
</style>
