<script setup lang="ts">
import { computed } from 'vue'
import type { ThresholdsData } from '../../types/config'

// 임계치 필드 한국어 라벨 — 매핑에 없는 키는 키 이름을 그대로 표시
const FIELD_LABELS: Record<string, string> = {
  // delay_thresholds
  iqr_tight: 'IQR 타이트 기준',
  median_small_abs: '중앙값 절대 최소(일)',
  median_late: '중앙값 지연 기준(일)',
  iqr_volatile: 'IQR 변동 기준',
  tail_burst: '테일 버스트 기준',
  min_sample: '최소 표본 수',
  coverage_warn: '커버리지 경고 기준',
  // gap_thresholds
  warn_days: '경고 일수',
  watch_consecutive: '연속 관찰 주 수',
  weeks: '조회 주 수',
  etd_lookback_days: 'ETD 조회 기간(일)',
}

const props = defineProps<{
  model: ThresholdsData
}>()

const entries = computed(() =>
  Object.entries(props.model).map(([key, value]) => ({
    key,
    value,
    label: FIELD_LABELS[key] || key,
  })),
)
</script>

<template>
  <div class="thresholds-form">
    <div v-for="entry in entries" :key="entry.key" class="field-row">
      <label class="field-label" :for="`th-${entry.key}`">{{ entry.label }}</label>
      <input
        :id="`th-${entry.key}`"
        v-model.number="model[entry.key]"
        type="number"
        step="any"
        class="field-input"
      />
    </div>
    <p class="field-hint">키 목록은 서버 응답 기준으로 자동 표시됩니다.</p>
  </div>
</template>

<style scoped>
.thresholds-form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px 16px;
}
.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
}
.field-label { font-size: 12px; color: var(--li-text-soft); }
.field-input {
  width: 110px;
  padding: 5px 8px;
  border: 1px solid var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  font-size: 12px;
  color: var(--li-text);
  text-align: right;
}
.field-hint {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 11px;
  color: var(--li-text-faint);
}
</style>
