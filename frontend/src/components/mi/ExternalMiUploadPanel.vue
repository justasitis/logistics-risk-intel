<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMiWorkspace } from '../../composables/useMiWorkspace'

const {
  state,
  loadCandidateFile,
  loadSharePointCandidates,
  applyPendingSharePointCandidates,
} = useMiWorkspace()

const isLocalLoading = ref(false)

const isSharePointLoading = computed(
  () => state.sharePointStatus === 'LOADING',
)

const sourceLabel = computed(() => {
  if (state.candidateSource === 'SHAREPOINT') {
    return 'SharePoint 자동 반입'
  }
  if (state.candidateSource === 'LOCAL_FILE') {
    return '로컬 JSON 선택'
  }
  return '미반입'
})

function formatDate(value: string): string {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('ko-KR')
}

function formatBytes(value: number): string {
  if (!value) return '0 KB'
  if (value < 1024 * 1024) {
    return `${Math.max(1, Math.round(value / 1024))} KB`
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

async function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  isLocalLoading.value = true
  try {
    await loadCandidateFile(file)
  } catch (error) {
    state.error = error instanceof Error
      ? error.message
      : String(error)
  } finally {
    isLocalLoading.value = false
    input.value = ''
  }
}

async function refreshSharePoint() {
  try {
    await loadSharePointCandidates(false, false)
  } catch {
    // Error details are already stored in the shared workspace state.
  }
}

function replaceWithPendingSharePoint() {
  try {
    applyPendingSharePointCandidates()
  } catch (error) {
    state.error = error instanceof Error
      ? error.message
      : String(error)
  }
}

onMounted(() => {
  void loadSharePointCandidates(false, true)
    .catch(() => undefined)
})
</script>

<template>
  <section class="mi-card">
    <div class="mi-card__header">
      <div>
        <div class="mi-card__title">1. 외부 MI 후보 반입</div>
        <p class="mi-help">
          SharePoint의 external_mi_candidates.json을 화면 진입 시 자동으로 읽습니다.
          기존 로컬 JSON 선택도 계속 사용할 수 있습니다.
        </p>
      </div>
      <span class="source-pill">{{ sourceLabel }}</span>
    </div>

    <div class="sharepoint-box">
      <div class="sharepoint-box__top">
        <div>
          <b>SharePoint 자동 반입</b>
          <div class="file-name">
            {{ state.sharePointSourceFileName || 'external_mi_candidates.json' }}
          </div>
        </div>

        <button
          type="button"
          class="secondary-button"
          :disabled="isSharePointLoading"
          @click="refreshSharePoint"
        >
          {{ isSharePointLoading ? '확인 중...' : 'SharePoint 새로고침' }}
        </button>
      </div>

      <dl v-if="state.sharePointSourceFile" class="file-meta">
        <div>
          <dt>후보</dt>
          <dd>{{ state.sharePointCandidateCount }}건</dd>
        </div>
        <div>
          <dt>수정일</dt>
          <dd>{{ formatDate(state.sharePointModifiedAt) }}</dd>
        </div>
        <div>
          <dt>크기</dt>
          <dd>{{ formatBytes(state.sharePointSizeBytes) }}</dd>
        </div>
      </dl>

      <p
        v-if="state.sharePointMessage"
        class="status-message"
        :class="{
          warning: state.sharePointStatus === 'UPDATE_AVAILABLE',
          error: state.sharePointStatus === 'ERROR',
        }"
      >
        {{ state.sharePointMessage }}
      </p>

      <p v-if="state.sharePointError" class="status-message error">
        {{ state.sharePointError }}
      </p>

      <button
        v-if="state.sharePointStatus === 'UPDATE_AVAILABLE'"
        type="button"
        class="replace-button"
        @click="replaceWithPendingSharePoint"
      >
        새 SharePoint 파일로 교체
      </button>
    </div>

    <div class="divider"><span>또는</span></div>

    <label class="mi-upload">
      <input
        type="file"
        accept="application/json,.json"
        @change="onFileChange"
      />
      <span>{{ isLocalLoading ? '읽는 중...' : '다른 JSON 직접 선택' }}</span>
    </label>

    <div v-if="state.candidateEnvelope" class="mi-summary">
      <b>{{ state.candidateEnvelope.candidates.length }}건</b>
      <span>{{ state.candidateEnvelope.generation_status }}</span>
      <span>{{ state.candidateEnvelope.generated_at }}</span>
    </div>
  </section>
</template>

<style scoped>
.mi-card {
  padding: 16px;
  border: 1px solid var(--li-border, #dbe4ee);
  border-radius: 12px;
  background: var(--li-panel, #fff);
}

.mi-card__header,
.sharepoint-box__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.mi-card__title {
  font-weight: 700;
  color: var(--li-text, #102a43);
}

.mi-help {
  margin: 6px 0 12px;
  color: var(--li-text-muted, #627d98);
  font-size: 13px;
  line-height: 1.5;
}

.source-pill {
  flex: 0 0 auto;
  padding: 5px 9px;
  border-radius: 999px;
  background: #eaf2fb;
  color: #245b8f;
  font-size: 11px;
  font-weight: 700;
}

.sharepoint-box {
  padding: 13px;
  border: 1px solid #d8e5f1;
  border-radius: 10px;
  background: #f8fbfe;
}

.file-name {
  margin-top: 3px;
  color: #486581;
  font-size: 12px;
  word-break: break-all;
}

.secondary-button,
.replace-button {
  border: 0;
  border-radius: 7px;
  cursor: pointer;
  font-weight: 700;
}

.secondary-button {
  padding: 8px 10px;
  background: #e5edf5;
  color: #334e68;
}

.secondary-button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.replace-button {
  margin-top: 10px;
  padding: 8px 11px;
  background: #b45309;
  color: #fff;
}

.file-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0 0;
}

.file-meta div {
  min-width: 0;
}

.file-meta dt {
  color: #829ab1;
  font-size: 11px;
}

.file-meta dd {
  margin: 2px 0 0;
  color: #334e68;
  font-size: 12px;
  font-weight: 700;
}

.status-message {
  margin: 10px 0 0;
  color: #486581;
  font-size: 12px;
  line-height: 1.45;
}

.status-message.warning {
  color: #9a4d00;
}

.status-message.error {
  color: #b42318;
}

.divider {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0;
  color: #9fb3c8;
  font-size: 11px;
}

.divider::before,
.divider::after {
  height: 1px;
  flex: 1;
  background: #dbe4ee;
  content: '';
}

.mi-upload {
  display: inline-flex;
  padding: 9px 14px;
  border-radius: 7px;
  background: #1d5fa7;
  color: white;
  cursor: pointer;
}

.mi-upload input {
  display: none;
}

.mi-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
  color: #486581;
  font-size: 12px;
}

@media (max-width: 640px) {
  .mi-card__header,
  .sharepoint-box__top {
    flex-direction: column;
  }

  .file-meta {
    grid-template-columns: 1fr;
  }
}
</style>
