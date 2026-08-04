<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { getInsightDraft, postInsightDraft, putInsightDraft } from '../services/leadtimeApi'
import type { InsightDraftResponse } from '../types/leadtime'

const props = defineProps<{ draft: InsightDraftResponse | null }>()
const emit = defineEmits<{ 'update:draft': [value: InsightDraftResponse | null] }>()

// 대상 월 기본값: 이번 달 (YYYY-MM)
const month = ref(new Date().toISOString().slice(0, 7))
const includeLeadtime = ref(true)
const generating = ref(false)
const saving = ref(false)
const error = ref('')

/** 저장된 초안 자동 복원 (탭 진입/월 변경 시, 없으면 조용히 비움) */
async function restore() {
  try {
    const existing = await getInsightDraft(month.value)
    emit('update:draft', existing)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '초안 복원 실패'
  }
}

onMounted(restore)
watch(month, restore)

async function generate() {
  generating.value = true
  error.value = ''
  try {
    // 동일 월 기존 초안이 있으면 재생성(덮어쓰기)
    const result = await postInsightDraft(
      month.value,
      includeLeadtime.value,
      props.draft !== null,
    )
    emit('update:draft', result)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '초안 생성 실패'
  } finally {
    generating.value = false
  }
}

/** 편집본 명시 저장 (자동저장 없음 — HITL) */
async function save() {
  if (!props.draft) return
  saving.value = true
  error.value = ''
  try {
    const result = await putInsightDraft(month.value, props.draft.draft)
    emit('update:draft', result)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '초안 저장 실패'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="insight panel">
    <div class="insight-head">
      <div>
        <p class="eyebrow">AI INSIGHT DRAFT</p>
        <h3 class="panel-title">월간 인사이트 초안</h3>
      </div>
      <div class="controls">
        <input v-model="month" type="month" class="month-input" :disabled="generating || saving" />
        <label class="chk">
          <input v-model="includeLeadtime" type="checkbox" :disabled="generating || saving" />
          리드타임 포함
        </label>
        <button class="btn primary" :disabled="generating || saving" @click="generate">
          {{ generating
            ? '초안 생성 중... (수 분 소요 가능)'
            : props.draft ? '재생성 (덮어쓰기)' : '인사이트 초안 생성' }}
        </button>
        <button v-if="props.draft" class="btn" :disabled="generating || saving" @click="save">
          {{ saving ? '저장 중...' : '편집본 저장' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="props.draft">
      <p class="materials">
        {{ props.draft.draft_id ?? '' }}
        · 재료: 승인 MI 이벤트 {{ props.draft.materials_summary.events_used }}건
        · 리드타임 {{ props.draft.materials_summary.leadtime_used ? '포함' : '미포함/실패' }}
        · 스케줄 요약 {{ props.draft.materials_summary.summary_used ? '포함' : '미포함/실패' }}
        · 생성 {{ props.draft.generated_at }}
        <span v-if="props.draft.revised_at">· 편집 저장 {{ props.draft.revised_at }}</span>
      </p>

      <div v-if="props.draft.draft.key_changes?.length" class="kc-block">
        <h4 class="block-title">핵심 변화 (Executive Summary)</h4>
        <div class="kc-grid">
          <div
            v-for="(change, i) in props.draft.draft.key_changes"
            :key="i"
            class="kc-card"
          >
            <span class="kc-num">{{ i + 1 }}</span>
            <span class="kc-text">{{ change }}</span>
          </div>
        </div>
      </div>

      <div v-for="section in props.draft.draft.sections" :key="section.key" class="section-card">
        <h4 class="section-title">{{ section.title }}</h4>
        <textarea
          v-model="section.body"
          rows="4"
          class="section-body"
        ></textarea>
      </div>

      <div v-if="props.draft.draft.monitoring_points.length" class="section-card">
        <h4 class="section-title">익월 체크 포인트</h4>
        <ul class="points">
          <li v-for="(point, i) in props.draft.draft.monitoring_points" :key="i">{{ point }}</li>
        </ul>
      </div>

      <p class="hitl">
        {{ props.draft.draft.disclaimer || '이 초안은 검토용이며 최종 문서는 담당자가 확정합니다.' }}
      </p>
    </template>
    <p v-else class="hint">저장된 초안이 없습니다. 대상 월을 선택하고 초안을 생성하세요.</p>
  </section>
</template>

<style scoped>
.panel {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-lg);
  padding: 16px 18px;
  box-shadow: var(--li-shadow-card);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.insight-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: var(--li-blue);
}
.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--li-text);
}
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.month-input {
  padding: 6px 10px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
}
.chk {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--li-text-muted);
}
.btn {
  padding: 7px 14px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.14s ease, box-shadow 0.14s ease;
}
.btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--li-shadow-card);
}
.btn.primary {
  background: var(--li-accent-gradient);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.24);
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.materials {
  margin: 0;
  font-size: 11px;
  color: var(--li-text-faint);
}

/* ---------- 핵심 변화 카드 ---------- */
.kc-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.block-title {
  margin: 0;
  font-size: 12px;
  font-weight: 800;
  color: var(--li-text-soft);
}
.kc-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
@media (max-width: 980px) {
  .kc-grid {
    grid-template-columns: 1fr;
  }
}
.kc-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--li-radius-md);
  background: var(--li-accent-gradient-soft), var(--li-surface);
  border: 1px solid rgba(37, 99, 235, 0.2);
  box-shadow: var(--li-shadow-card);
}
.kc-num {
  display: inline-grid;
  place-items: center;
  min-width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--li-accent-gradient);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.28);
}
.kc-text {
  font-size: 12px;
  line-height: 1.55;
  color: var(--li-text);
  font-weight: 600;
}

/* ---------- 섹션 ---------- */
.section-card {
  border-top: 1px solid var(--li-border);
  padding-top: 10px;
}
.section-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 800;
  color: var(--li-text-soft);
  border-left: 3px solid var(--li-blue);
  padding-left: 8px;
}
.section-body {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  line-height: 1.6;
  color: var(--li-text);
  background: var(--li-surface);
  resize: vertical;
}
.points {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--li-text);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hitl {
  margin: 0;
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  color: #b45309;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(180, 83, 9, 0.28);
  border-radius: 999px;
  padding: 4px 12px;
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
