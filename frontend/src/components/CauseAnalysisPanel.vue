<script setup lang="ts">
import { computed } from 'vue'
import { useCauseReview } from '@/composables/useCauseReview'
import type {
  CauseCandidate,
  CauseDecision,
} from '@/types/causeAnalysis'
import type { TransportRecord } from '@/types/dashboard'
import {
  shipmentDisplayId,
  shipmentSystemId,
} from '@/utils/shipmentDisplay'

const props = defineProps<{
  transport: TransportRecord | null
  candidates: CauseCandidate[]
}>()

const emit = defineEmits<{
  selectMi: [eventId: string]
}>()

const {
  applyDecision,
  setDecision,
} = useCauseReview()

const reviewedCandidates = computed(() =>
  props.candidates.map(applyDecision),
)

const confirmedCount = computed(() =>
  reviewedCandidates.value.filter(
    (candidate) => candidate.decision === 'CONFIRMED',
  ).length,
)

const excludedCount = computed(() =>
  reviewedCandidates.value.filter(
    (candidate) => candidate.decision === 'EXCLUDED',
  ).length,
)

function confidenceClass(value: string) {
  return `cause-confidence cause-confidence--${value.toLowerCase()}`
}

function decisionClass(value: CauseDecision) {
  return `cause-decision cause-decision--${value.toLowerCase()}`
}

function scoreWidth(value: number) {
  return `${Math.max(0, Math.min(100, value))}%`
}

function setCandidateDecision(
  candidateId: string,
  decision: CauseDecision,
) {
  setDecision(candidateId, decision)
}
</script>

<template>
  <section class="cause-panel">
    <header class="cause-panel__header">
      <div>
        <span class="eyebrow">ROOT CAUSE</span>
        <h3>일정 이상 원인 후보</h3>
      </div>

      <div class="cause-panel__counts">
        <span>확정 {{ confirmedCount }}</span>
        <span>제외 {{ excludedCount }}</span>
      </div>
    </header>

    <div v-if="transport" class="cause-panel__transport">
      <div class="cause-panel__transport-id">
        <strong>{{ shipmentDisplayId(transport) }}</strong>
        <span>B-LAP {{ shipmentSystemId(transport) }}</span>
      </div>
      <strong>
        {{ transport.pol_name || transport.pol || '-' }}
        →
        {{ transport.pod_name || transport.pod || '-' }}
      </strong>
    </div>

    <div
      v-if="transport && reviewedCandidates.length === 0"
      class="cause-empty"
    >
      <strong>일치하는 외부 MI 원인 후보 없음</strong>
      <p>
        내부 운영, 선복, 통관, Vendor 또는 데이터 품질 원인을
        추가 확인해야 합니다.
      </p>
    </div>

    <div class="cause-list">
      <article
        v-for="candidate in reviewedCandidates"
        :key="candidate.candidate_id"
        class="cause-card"
        :class="{
          'cause-card--confirmed': candidate.decision === 'CONFIRMED',
          'cause-card--excluded': candidate.decision === 'EXCLUDED',
        }"
      >
        <div class="cause-card__top">
          <span :class="confidenceClass(candidate.confidence_band)">
            {{ candidate.confidence_band }}
          </span>

          <strong class="cause-card__score">
            {{ candidate.total_score }}
          </strong>

          <span :class="decisionClass(candidate.decision)">
            {{ candidate.decision }}
          </span>
        </div>

        <button
          type="button"
          class="cause-card__title"
          @click="emit('selectMi', candidate.mi_event_id)"
        >
          {{ candidate.mi_headline }}
        </button>

        <p class="cause-card__schedule">
          기준 이상: {{ candidate.schedule_headline }}
        </p>

        <div class="cause-score-bar">
          <span :style="{ width: scoreWidth(candidate.total_score) }" />
        </div>

        <div class="cause-breakdown">
          <span>공간 {{ candidate.score_breakdown.spatial }}/30</span>
          <span>시간 {{ candidate.score_breakdown.temporal }}/25</span>
          <span>신호 {{ candidate.score_breakdown.signal }}/20</span>
          <span>AIS {{ candidate.score_breakdown.ais }}/15</span>
          <span>MI {{ candidate.score_breakdown.event_quality }}/10</span>
        </div>

        <ul class="cause-evidence">
          <li
            v-for="evidence in candidate.evidence.slice(0, 5)"
            :key="evidence"
          >
            {{ evidence }}
          </li>
        </ul>

        <details class="cause-actions">
          <summary>권장 조치</summary>
          <ul>
            <li
              v-for="action in candidate.recommended_actions"
              :key="action"
            >
              {{ action }}
            </li>
          </ul>
        </details>

        <div class="cause-card__buttons">
          <button
            type="button"
            class="confirm"
            :class="{ active: candidate.decision === 'CONFIRMED' }"
            @click="
              setCandidateDecision(
                candidate.candidate_id,
                'CONFIRMED',
              )
            "
          >
            원인 확정
          </button>

          <button
            type="button"
            class="exclude"
            :class="{ active: candidate.decision === 'EXCLUDED' }"
            @click="
              setCandidateDecision(
                candidate.candidate_id,
                'EXCLUDED',
              )
            "
          >
            제외
          </button>

          <button
            type="button"
            :class="{ active: candidate.decision === 'PENDING' }"
            @click="
              setCandidateDecision(
                candidate.candidate_id,
                'PENDING',
              )
            "
          >
            대기
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.cause-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  color: var(--li-text, #122033);
  border: 1px solid var(
    --li-border,
    rgba(16, 42, 67, 0.11)
  );
  border-radius: 18px;
  background: var(
    --li-surface,
    rgba(255, 255, 255, 0.74)
  );
  box-shadow: var(
    --li-shadow-card,
    0 12px 28px rgba(15, 32, 54, 0.08)
  );
  backdrop-filter: blur(18px);
}

.cause-panel__header,
.cause-card__top,
.cause-card__buttons,
.cause-panel__transport,
.cause-breakdown {
  display: flex;
  align-items: center;
}

.cause-panel__header {
  justify-content: space-between;
  gap: 10px;
}

.cause-panel__header h3 {
  margin: 2px 0 0;
  font-size: 14px;
}

.cause-panel__counts {
  display: flex;
  gap: 5px;
}

.cause-panel__counts span {
  padding: 4px 7px;
  color: var(--li-text-muted, #607086);
  font-size: 9px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.07);
}

.cause-panel__transport {
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  font-size: 10px;
  border-radius: 10px;
  background: rgba(232, 244, 255, 0.58);
}

.cause-panel__transport span {
  color: var(--li-text-muted, #607086);
}

.cause-panel__transport-id {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.cause-panel__transport-id strong {
  overflow: hidden;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cause-panel__transport-id span {
  font-size: 8px;
}

.cause-empty {
  padding: 13px;
  border: 1px dashed rgba(96, 112, 134, 0.25);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.72);
}

.cause-empty strong {
  font-size: 11px;
}

.cause-empty p {
  margin: 5px 0 0;
  color: var(--li-text-muted, #607086);
  font-size: 10px;
  line-height: 1.45;
}

.cause-list {
  display: grid;
  gap: 9px;
}

.cause-card {
  padding: 11px;
  border: 1px solid rgba(16, 42, 67, 0.09);
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.72);
  transition:
    opacity 140ms ease,
    border-color 140ms ease,
    box-shadow 140ms ease;
}

.cause-card--confirmed {
  border-color: rgba(16, 185, 129, 0.34);
  box-shadow: 0 10px 22px rgba(16, 185, 129, 0.09);
}

.cause-card--excluded {
  opacity: 0.54;
  border-color: rgba(148, 163, 184, 0.28);
}

.cause-card__top {
  gap: 7px;
}

.cause-card__score {
  color: var(--li-text, #122033);
  font-size: 18px;
}

.cause-confidence,
.cause-decision {
  padding: 3px 6px;
  font-size: 8px;
  font-weight: 850;
  border-radius: 999px;
}

.cause-confidence--high {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.11);
}

.cause-confidence--medium {
  color: #b45309;
  background: rgba(245, 158, 11, 0.13);
}

.cause-confidence--low {
  color: #0369a1;
  background: rgba(14, 165, 233, 0.11);
}

.cause-decision {
  margin-left: auto;
  color: var(--li-text-muted, #607086);
  background: rgba(100, 116, 139, 0.09);
}

.cause-decision--confirmed {
  color: #047857;
  background: rgba(16, 185, 129, 0.12);
}

.cause-decision--excluded {
  color: #64748b;
}

.cause-card__title {
  display: block;
  width: 100%;
  margin-top: 8px;
  padding: 0;
  color: var(--li-text, #122033);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.4;
  text-align: left;
  border: 0;
  background: transparent;
  cursor: pointer;
}

.cause-card__title:hover {
  color: var(--li-blue, #2563eb);
}

.cause-card__schedule {
  margin: 5px 0 0;
  color: var(--li-text-muted, #607086);
  font-size: 9px;
  line-height: 1.4;
}

.cause-score-bar {
  height: 5px;
  margin-top: 9px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.15);
}

.cause-score-bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #2563eb, #06b6d4);
}

.cause-breakdown {
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}

.cause-breakdown span {
  padding: 3px 5px;
  color: var(--li-text-muted, #607086);
  font-size: 8px;
  border-radius: 6px;
  background: rgba(241, 245, 249, 0.82);
}

.cause-evidence,
.cause-actions ul {
  margin: 8px 0 0;
  padding-left: 17px;
}

.cause-evidence li,
.cause-actions li {
  margin: 3px 0;
  color: var(--li-text-soft, #344861);
  font-size: 9px;
  line-height: 1.4;
}

.cause-actions {
  margin-top: 7px;
  color: var(--li-blue, #2563eb);
  font-size: 9px;
}

.cause-actions summary {
  cursor: pointer;
}

.cause-card__buttons {
  gap: 5px;
  margin-top: 9px;
}

.cause-card__buttons button {
  min-height: 28px;
  padding: 0 8px;
  color: var(--li-text-muted, #607086);
  font-size: 9px;
  font-weight: 760;
  border: 1px solid rgba(96, 112, 134, 0.18);
  border-radius: 8px;
  background: rgba(248, 250, 252, 0.84);
  cursor: pointer;
}

.cause-card__buttons button.confirm.active {
  color: #047857;
  border-color: rgba(16, 185, 129, 0.3);
  background: rgba(16, 185, 129, 0.11);
}

.cause-card__buttons button.exclude.active {
  color: #475569;
  border-color: rgba(100, 116, 139, 0.3);
  background: rgba(148, 163, 184, 0.12);
}

.cause-card__buttons button.active:not(.confirm):not(.exclude) {
  color: var(--li-blue, #2563eb);
  border-color: rgba(37, 99, 235, 0.25);
  background: rgba(37, 99, 235, 0.08);
}
</style>
