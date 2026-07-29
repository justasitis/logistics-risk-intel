<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getMiRegistry,
  postRegistryApply,
  postRegistryReview,
  rebuildMiRegistry,
} from '../../services/miRegistryApi'
import type {
  RegistryResponse,
  RegistryReviewProposal,
  RegistryStatus,
} from '../../types/miRegistry'

const registry = ref<RegistryResponse | null>(null)
const loading = ref(false)
const rebuilding = ref(false)
const error = ref('')
const statusFilter = ref<'' | RegistryStatus>('')

const STATUS_LABELS: Record<RegistryStatus, string> = {
  ACTIVE: 'ACTIVE',
  IMPROVING: 'IMPROVING',
  RESOLVED: 'RESOLVED',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    registry.value = await getMiRegistry(statusFilter.value || undefined)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '레지스트리 조회 실패'
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  rebuilding.value = true
  error.value = ''
  try {
    await rebuildMiRegistry()
    window.dispatchEvent(new CustomEvent('mi-registry-changed'))
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '레지스트리 재구축 실패'
  } finally {
    rebuilding.value = false
  }
}

// ---------- 종합 정제 검토 (Actify 제안 → 건당 수락/무시, HITL) ----------
const reviewing = ref(false)
const reviewNotes = ref('')
const proposals = ref<RegistryReviewProposal[]>([])
const applyingId = ref<string | null>(null)

async function review() {
  reviewing.value = true
  error.value = ''
  try {
    const result = await postRegistryReview()
    proposals.value = result.reviews
    reviewNotes.value = result.notes
  } catch (e) {
    error.value = e instanceof Error ? e.message : '종합 정제 검토 실패'
  } finally {
    reviewing.value = false
  }
}

async function accept(proposal: RegistryReviewProposal) {
  applyingId.value = proposal.event_id
  error.value = ''
  try {
    await postRegistryApply({
      event_id: proposal.event_id,
      suggested_status: proposal.suggested_status,
      suggested_severity: proposal.suggested_severity,
      merge_with: proposal.merge_with,
    })
    proposals.value = proposals.value.filter(
      (p) => p.event_id !== proposal.event_id,
    )
    window.dispatchEvent(new CustomEvent('mi-registry-changed'))
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '제안 반영 실패'
  } finally {
    applyingId.value = null
  }
}

function ignore(proposal: RegistryReviewProposal) {
  proposals.value = proposals.value.filter(
    (p) => p.event_id !== proposal.event_id,
  )
}

onMounted(load)
</script>

<template>
  <section class="registry">
    <div class="head">
      <div>
        <h3 class="title">이벤트 레지스트리</h3>
        <p v-if="registry" class="meta">기준일 {{ registry.reference_date ?? '-' }} · {{ registry.events.length }}건</p>
      </div>
      <div class="controls">
        <select v-model="statusFilter" class="filter" @change="load">
          <option value="">전체 상태</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="IMPROVING">IMPROVING</option>
          <option value="RESOLVED">RESOLVED</option>
        </select>
        <button class="btn" :disabled="rebuilding" @click="rebuild">
          {{ rebuilding ? '재구축 중...' : '일자별 파일 재인입' }}
        </button>
        <button class="btn" :disabled="reviewing" @click="review">
          {{ reviewing ? 'Actify 검토 중... (수 분 소요 가능)' : '종합 정제 검토' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="hint">조회 중...</p>
    <p v-if="registry && !registry.events.length && !loading" class="hint">
      등록된 이벤트가 없습니다. 일자별 파일을 재인입하세요.
    </p>

    <section v-if="proposals.length || reviewNotes" class="review">
      <div class="review-head">
        <span class="review-title">종합 정제 제안 (검토용 — 자동 반영 없음)</span>
      </div>
      <p v-if="reviewNotes" class="review-notes">{{ reviewNotes }}</p>
      <div v-for="p in proposals" :key="p.event_id" class="proposal">
        <div class="proposal-main">
          <span class="proposal-id">{{ p.event_id }}</span>
          <span class="chip">{{ p.suggested_status }}</span>
          <span class="chip sev">{{ p.suggested_severity }}</span>
          <span v-if="p.merge_with" class="chip merge">병합 ← {{ p.merge_with }}</span>
        </div>
        <p class="proposal-reason">{{ p.reason }}</p>
        <div class="proposal-actions">
          <button
            class="btn primary"
            :disabled="applyingId === p.event_id"
            @click="accept(p)"
          >
            {{ applyingId === p.event_id ? '반영 중...' : '수락' }}
          </button>
          <button class="btn" @click="ignore(p)">무시</button>
        </div>
      </div>
    </section>

    <ul v-if="registry" class="list">
      <li v-for="event in registry.events" :key="event.event_id" class="card">
        <div class="card-head">
          <span class="status" :class="event.status.toLowerCase()">
            {{ STATUS_LABELS[event.status] }}
          </span>
          <span v-if="event.reactivated" class="reactivated">재활성화</span>
          <span class="severity">{{ event.severity }}</span>
          <span class="id">{{ event.event_id }}</span>
        </div>
        <div class="headline">{{ event.headline }}</div>
        <div class="meta">
          최초 {{ event.first_seen }} · 최종 {{ event.last_seen }} · 목격 {{ event.sighting_count }}회
        </div>
        <div v-if="event.locations.length" class="locs">
          <span v-for="loc in event.locations" :key="loc" class="chip">{{ loc }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.registry {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 16px;
  box-shadow: var(--li-shadow-card);
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.title {
  margin: 0;
  font-size: 14px;
  color: var(--li-text);
}
.meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--li-text-muted);
}
.controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.filter {
  padding: 5px 8px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
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
  opacity: 0.6;
  cursor: not-allowed;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card {
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.status {
  font-size: 12px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}
.status.active {
  background: rgba(16, 185, 129, 0.14);
  color: #10b981;
}
.status.improving {
  background: rgba(234, 179, 8, 0.14);
  color: #eab308;
}
.status.resolved {
  background: rgba(100, 116, 139, 0.14);
  color: #64748b;
}
.reactivated {
  font-size: 12px;
  color: var(--li-blue);
}
.severity {
  font-size: 12px;
  color: var(--li-text-soft);
}
.id {
  margin-left: auto;
  font-size: 12px;
  color: var(--li-text-faint);
  font-family: monospace;
}
.headline {
  font-size: 13px;
  font-weight: 700;
  color: var(--li-text);
}
.locs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.chip {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--li-surface-blue);
  color: var(--li-blue);
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
.review {
  border: 1px solid var(--li-blue);
  border-radius: var(--li-radius-sm);
  padding: 10px;
  margin-bottom: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.review-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--li-blue);
}
.review-notes {
  margin: 0;
  font-size: 12px;
  color: var(--li-text-muted);
}
.proposal {
  border-top: 1px solid var(--li-border);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.proposal-main {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.proposal-id {
  font-size: 12px;
  font-family: monospace;
  color: var(--li-text-faint);
}
.proposal-reason {
  margin: 0;
  font-size: 12px;
  color: var(--li-text);
}
.proposal-actions {
  display: flex;
  gap: 8px;
}
.chip {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--li-surface-blue);
  color: var(--li-blue);
}
.chip.sev {
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
}
.chip.merge {
  background: var(--li-bg-app-2);
  color: var(--li-text-muted);
}
.btn.primary {
  background: var(--li-blue);
  border-color: transparent;
  color: #fff;
}
</style>
