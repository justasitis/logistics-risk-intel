<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMiWorkspace } from '../../composables/useMiWorkspace'

const {
  state,
  restoreLatestReview,
  restoreReviewByAnalysisId,
  clearSavedReview,
} = useMiWorkspace()

const analysisIdInput = ref(
  state.savedAnalysisId || state.analysisId,
)

watch(
  () => state.savedAnalysisId || state.analysisId,
  (value) => {
    if (value) analysisIdInput.value = value
  },
)

async function restoreSaved() {
  try {
    await restoreLatestReview(false)
  } catch {
    // The composable exposes the error through recoveryMessage.
  }
}

async function restoreInput() {
  try {
    await restoreReviewByAnalysisId(
      analysisIdInput.value,
      true,
      false,
    )
  } catch {
    // The composable exposes the error through recoveryMessage.
  }
}
</script>

<template>
  <section
    class="mi-recovery"
    :class="{
      'mi-recovery--ok': state.recoveryStatus === 'RESTORED',
      'mi-recovery--error': state.recoveryStatus === 'ERROR',
    }"
  >
    <div class="mi-recovery__header">
      <div>
        <span class="eyebrow">PERSISTED MI RUN</span>
        <strong>승인 MI Run 복구</strong>
      </div>

      <span class="mi-recovery__status">
        {{ state.recoveryStatus }}
      </span>
    </div>

    <p>
      검토 결과 저장 시 Analysis ID를 이 브라우저에 보관하고,
      새로고침 후 서버 Run을 다시 불러옵니다.
    </p>

    <div class="mi-recovery__form">
      <input
        v-model.trim="analysisIdInput"
        type="text"
        placeholder="MI-RUN-XXXXXXXXXXXX"
        autocomplete="off"
      >

      <button
        type="button"
        :disabled="
          !analysisIdInput
          || state.recoveryStatus === 'RESTORING'
        "
        @click="restoreInput"
      >
        입력 ID 복구
      </button>

      <button
        type="button"
        :disabled="
          !state.savedAnalysisId
          || state.recoveryStatus === 'RESTORING'
        "
        @click="restoreSaved"
      >
        마지막 Run 다시 복구
      </button>

      <button
        type="button"
        class="danger"
        :disabled="
          !state.savedAnalysisId
          && !state.reviewResult
        "
        @click="clearSavedReview"
      >
        저장정보 삭제
      </button>
    </div>

    <div
      v-if="state.recoveryMessage"
      class="mi-recovery__message"
    >
      {{ state.recoveryMessage }}
    </div>

    <div
      v-if="state.reviewResult"
      class="mi-recovery__summary"
    >
      <span>Analysis ID</span>
      <strong>{{ state.reviewResult.analysis_id }}</strong>
      <span>승인 Event</span>
      <strong>{{ state.reviewResult.approved_count }}</strong>
    </div>
  </section>
</template>

<style scoped>
.mi-recovery {
  padding: 14px 16px;
  color: var(--li-text, #122033);
  border: 1px solid var(
    --li-border,
    rgba(16, 42, 67, 0.11)
  );
  border-radius: 17px;
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

.mi-recovery--ok {
  border-color: rgba(16, 185, 129, 0.28);
}

.mi-recovery--error {
  border-color: rgba(239, 68, 68, 0.32);
}

.mi-recovery__header,
.mi-recovery__form,
.mi-recovery__summary {
  display: flex;
  align-items: center;
  gap: 9px;
}

.mi-recovery__header {
  justify-content: space-between;
}

.mi-recovery__header > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.mi-recovery__header strong {
  font-size: 14px;
}

.mi-recovery__status {
  padding: 4px 8px;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 850;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.09);
}

.mi-recovery p {
  margin: 8px 0 12px;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
  line-height: 1.5;
}

.mi-recovery__form {
  flex-wrap: wrap;
}

.mi-recovery input {
  flex: 1 1 230px;
  min-height: 36px;
  padding: 0 11px;
  color: var(--li-text, #122033);
  border: 1px solid var(
    --li-border,
    rgba(16, 42, 67, 0.11)
  );
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.78);
}

.mi-recovery button {
  min-height: 35px;
  padding: 0 11px;
  color: var(--li-blue, #2563eb);
  font-size: 11px;
  font-weight: 760;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 10px;
  background: rgba(232, 244, 255, 0.72);
  cursor: pointer;
}

.mi-recovery button.danger {
  color: #dc2626;
  border-color: rgba(220, 38, 38, 0.2);
  background: rgba(254, 226, 226, 0.58);
}

.mi-recovery button:disabled {
  cursor: not-allowed;
  opacity: 0.44;
}

.mi-recovery__message {
  margin-top: 10px;
  color: var(--li-text-muted, #607086);
  font-size: 11px;
}

.mi-recovery__summary {
  flex-wrap: wrap;
  margin-top: 9px;
  padding-top: 9px;
  border-top: 1px solid var(
    --li-border,
    rgba(16, 42, 67, 0.11)
  );
}

.mi-recovery__summary span {
  color: var(--li-text-faint, #8a98aa);
  font-size: 11px;
}

.mi-recovery__summary strong {
  color: var(--li-text, #122033);
  font-size: 12px;
}

@media (max-width: 760px) {
  .mi-recovery__form {
    align-items: stretch;
    flex-direction: column;
  }

  .mi-recovery input {
    flex-basis: auto;
    width: 100%;
  }
}
</style>
