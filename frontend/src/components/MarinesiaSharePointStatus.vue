<script setup lang="ts">
defineProps<{
  loading: boolean
  rootExists: boolean
  fileFound: boolean
  sourceFile: string
  generatedAt: string
  message: string
  error: string
  total: number
  mappable: number
  live: number
  stale: number
}>()

const emit = defineEmits<{
  refresh: []
}>()
</script>

<template>
  <section
    class="marinesia-status"
    :class="{
      'marinesia-status--error': error,
      'marinesia-status--ok': rootExists && fileFound && !error,
    }"
  >
    <div class="marinesia-status__header">
      <div>
        <span class="eyebrow">SHAREPOINT AIS</span>
        <strong>Marinesia 최신 위치</strong>
      </div>

      <button
        type="button"
        :disabled="loading"
        @click="emit('refresh')"
      >
        {{ loading ? '읽는 중...' : 'SharePoint AIS 불러오기' }}
      </button>
    </div>

    <div class="marinesia-status__grid">
      <div>
        <span>폴더</span>
        <strong>{{ rootExists ? '연결' : '미연결' }}</strong>
      </div>
      <div>
        <span>최신 파일</span>
        <strong>{{ fileFound ? '확인' : '없음' }}</strong>
      </div>
      <div>
        <span>선박</span>
        <strong>{{ total }}</strong>
      </div>
      <div>
        <span>지도 표시</span>
        <strong>{{ mappable }}</strong>
      </div>
      <div>
        <span>LIVE</span>
        <strong>{{ live }}</strong>
      </div>
      <div>
        <span>STALE</span>
        <strong>{{ stale }}</strong>
      </div>
    </div>

    <p v-if="sourceFile" class="marinesia-status__file">
      {{ sourceFile }}
    </p>
    <p v-if="generatedAt" class="marinesia-status__time">
      수집 기준 {{ generatedAt }}
    </p>
    <p v-if="message" class="marinesia-status__message">
      {{ message }}
    </p>
    <p v-if="error" class="marinesia-status__error">
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.marinesia-status {
  display: grid;
  gap: 9px;
  padding: 13px;
  color: var(--li-text, #122033);
  border: 1px solid var(
    --li-border,
    rgba(16, 42, 67, 0.11)
  );
  border-radius: 16px;
  background: var(
    --li-surface,
    rgba(255, 255, 255, 0.74)
  );
  box-shadow: var(
    --li-shadow-card,
    0 12px 28px rgba(15, 32, 54, 0.08)
  );
}

.marinesia-status--ok {
  border-color: rgba(16, 185, 129, 0.24);
}

.marinesia-status--error {
  border-color: rgba(239, 68, 68, 0.3);
}

.marinesia-status__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.marinesia-status__header > div {
  display: grid;
  gap: 2px;
}

.marinesia-status__header strong {
  font-size: 12px;
}

.marinesia-status__header button {
  min-height: 32px;
  padding: 0 10px;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 780;
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: 9px;
  background: rgba(37, 99, 235, 0.08);
  cursor: pointer;
}

.marinesia-status__header button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.marinesia-status__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 5px;
}

.marinesia-status__grid > div {
  display: grid;
  gap: 2px;
  padding: 7px;
  border-radius: 9px;
  background: rgba(241, 245, 249, 0.72);
}

.marinesia-status__grid span {
  color: var(--li-text-muted, #607086);
  font-size: 11px;
}

.marinesia-status__grid strong {
  font-size: 11px;
}

.marinesia-status__file,
.marinesia-status__time,
.marinesia-status__message,
.marinesia-status__error {
  margin: 0;
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.marinesia-status__file,
.marinesia-status__time {
  color: var(--li-text-muted, #607086);
}

.marinesia-status__message {
  color: #047857;
}

.marinesia-status__error {
  color: #b91c1c;
}

@media (max-width: 760px) {
  .marinesia-status__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
