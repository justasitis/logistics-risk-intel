<script setup lang="ts">
import { onMounted } from 'vue'
import { useMiWorkspace } from '../../composables/useMiWorkspace'
import type { CompanyCode } from '../../types/mi'

const { state, checkHealth, refine } = useMiWorkspace()
const companyOptions: CompanyCode[] = ['SKO', 'SKOH', 'SKBM', 'SKBA', 'SKOJ', 'SKOY']

onMounted(checkHealth)

function toggleCompany(company: CompanyCode) {
  const index = state.selectedCompanies.indexOf(company)
  if (index >= 0) state.selectedCompanies.splice(index, 1)
  else state.selectedCompanies.push(company)
}
</script>

<template>
  <section class="mi-card">
    <div class="header-row">
      <div class="mi-card__title">2. 사내 GPT 정제</div>
      <span :class="['health', state.apiConfigured ? 'ok' : 'bad']">
        Actify {{ state.apiConfigured ? '연결 설정됨' : '설정 확인 필요' }}
      </span>
    </div>

    <div class="company-grid">
      <label v-for="company in companyOptions" :key="company">
        <input
          type="checkbox"
          :checked="state.selectedCompanies.includes(company)"
          @change="toggleCompany(company)"
        />
        {{ company }}
      </label>
    </div>

    <textarea
      v-model="state.supplementalContext"
      rows="3"
      maxlength="12000"
      placeholder="선택: 주간 SCM 이슈, 현업 메모 등 보조 컨텍스트"
    />

    <button
      class="primary"
      :disabled="!state.candidateEnvelope || state.status === 'REFINING' || !state.apiConfigured"
      @click="refine"
    >
      {{ state.status === 'REFINING' ? 'Actify 분석 중...' : '사내 GPT 정제 실행' }}
    </button>

    <p v-if="state.error" class="error">{{ state.error }}</p>
    <p v-if="state.analysisId" class="analysis-id">Analysis ID: {{ state.analysisId }}</p>
  </section>
</template>

<style scoped>
.mi-card { padding: 16px; border: 1px solid #dbe4ee; border-radius: 10px; background: #fff; }
.header-row { display: flex; justify-content: space-between; gap: 12px; }
.mi-card__title { font-weight: 700; color: #102a43; }
.health { padding: 3px 7px; border-radius: 999px; font-size: 11px; }
.health.ok { background: #e8f5e9; color: #2e7d32; }
.health.bad { background: #ffebee; color: #c62828; }
.company-grid { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; font-size: 13px; }
textarea { width: 100%; box-sizing: border-box; margin-bottom: 10px; padding: 9px; border: 1px solid #bcccdc; border-radius: 6px; }
.primary { padding: 9px 14px; border: 0; border-radius: 7px; background: #1d5fa7; color: white; cursor: pointer; }
.primary:disabled { opacity: .45; cursor: not-allowed; }
.error { color: #c62828; font-size: 12px; }
.analysis-id { color: #627d98; font-size: 11px; }
</style>
