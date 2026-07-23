<script setup lang="ts">
import { ref } from 'vue'
import { postInsightDraft } from '../services/leadtimeApi'
import type { InsightDraftResponse } from '../types/leadtime'

const props = defineProps<{ draft: InsightDraftResponse | null }>()
const emit = defineEmits<{ 'update:draft': [value: InsightDraftResponse | null] }>()

// 대상 월 기본값: 이번 달 (YYYY-MM)
const month = ref(new Date().toISOString().slice(0, 7))
const includeLeadtime = ref(true)
const generating = ref(false)
const error = ref('')

async function generate() {
  generating.value = true
  error.value = ''
  try {
    const result = await postInsightDraft(month.value, includeLeadtime.value)
    emit('update:draft', result)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '초안 생성 실패'
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <section class="insight">
    <div class="insight-head">
      <h3 class="insight-title">월간 인사이트 초안 (AI 생성 → 검토용)</h3>
      <div class="controls">
        <input v-model="month" type="month" class="month-input" :disabled="generating" />
        <label class="chk">
          <input v-model="includeLeadtime" type="checkbox" :disabled="generating" />
          리드타임 포함
        </label>
        <button class="btn primary" :disabled="generating" @click="generate">
          {{ generating ? '초안 생성 중... (수 분 소요 가능)' : '인사이트 초안 생성' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="props.draft">
      <p class="materials">
        재료: 승인 MI 이벤트 {{ props.draft.materials_summary.events_used }}건
        · 리드타임 {{ props.draft.materials_summary.leadtime_used ? '포함' : '미포함/실패' }}
        · 스케줄 요약 {{ props.draft.materials_summary.summary_used ? '포함' : '미포함/실패' }}
        · 대상 월 {{ props.draft.month }} · 생성 {{ props.draft.generated_at }}
      </p>

      <div v-for="section in props.draft.draft.sections" :key="section.key" class="section-card">
        <h4 class="section-title">{{ section.title }}</h4>
        <textarea
          v-model="section.body"
          rows="4"
          class="section-body"
        ></textarea>
      </div>

      <div v-if="props.draft.draft.monitoring_points.length" class="section-card">
        <h4 class="section-title">모니터링 포인트</h4>
        <ul class="points">
          <li v-for="(point, i) in props.draft.draft.monitoring_points" :key="i">{{ point }}</li>
        </ul>
      </div>

      <p class="hitl">
        {{ props.draft.draft.disclaimer || '이 초안은 검토용이며 최종 문서는 담당자가 확정합니다.' }}
      </p>
    </template>
  </section>
</template>

<style scoped>
.insight {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 14px;
  box-shadow: var(--li-shadow-card);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.insight-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.insight-title {
  margin: 0;
  font-size: 13px;
  color: var(--li-text);
}
.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.month-input {
  padding: 5px 8px;
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
  padding: 6px 14px;
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
.materials {
  margin: 0;
  font-size: 12px;
  color: var(--li-text-muted);
}
.section-card {
  border-top: 1px solid var(--li-border);
  padding-top: 8px;
}
.section-title {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--li-text-soft);
}
.section-body {
  width: 100%;
  box-sizing: border-box;
  padding: 8px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  color: var(--li-text);
  background: var(--li-surface);
  resize: vertical;
}
.points {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--li-text);
}
.hitl {
  margin: 0;
  font-size: 12px;
  color: var(--li-risk-high);
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>
