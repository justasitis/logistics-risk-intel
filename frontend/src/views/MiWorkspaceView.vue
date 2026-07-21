<script setup lang="ts">
import ExternalMiUploadPanel from '../components/mi/ExternalMiUploadPanel.vue'
import MiRefinementPanel from '../components/mi/MiRefinementPanel.vue'
import MiReviewPanel from '../components/mi/MiReviewPanel.vue'
import MiRunRecoveryPanel from '../components/mi/MiRunRecoveryPanel.vue'
</script>

<template>
  <main class="mi-workspace">
    <header>
      <h2>외부 MI 반입 및 VDI GPT 정제</h2>
      <p>
        외부 Gemini 후보를 사내 Actify/GPT가 정제하고,
        사용자가 승인한 Event만 기존 지도·AIS·영향화물 분석으로 전달합니다.
      </p>
    </header>

    <MiRunRecoveryPanel />

    <div class="grid">
      <ExternalMiUploadPanel />
      <MiRefinementPanel />
    </div>

    <MiReviewPanel />
  </main>
</template>

<style scoped>
.mi-workspace {
  display: grid;
  gap: 16px;
}

header h2 {
  margin: 0;
  color: var(--li-text, #102a43);
}

header p {
  color: var(--li-text-muted, #627d98);
  line-height: 1.55;
}

.grid {
  display: grid;
  grid-template-columns: repeat(
    2,
    minmax(0, 1fr)
  );
  gap: 16px;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
