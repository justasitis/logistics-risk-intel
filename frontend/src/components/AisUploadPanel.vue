<script setup lang="ts">
import { ref } from 'vue'

import { parseAisUploadFile } from '@/services/aisUpload'
import type { AisUploadResult } from '@/types/dashboard'

const props = defineProps<{
  result: AisUploadResult | null
}>()

const emit = defineEmits<{
  loaded: [result: AisUploadResult]
  cleared: []
}>()

const input = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const errorMessage = ref('')

function openFileDialog() {
  input.value?.click()
}

async function handleFile(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''

  if (!file) return

  loading.value = true
  errorMessage.value = ''
  try {
    emit('loaded', await parseAisUploadFile(file))
  } catch (error) {
    errorMessage.value =
      error instanceof Error ? error.message : 'AIS 파일 업로드에 실패했습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="ais-uploader">
    <input
      ref="input"
      type="file"
      accept=".json,application/json"
      hidden
      @change="handleFile"
    >

    <button
      type="button"
      class="ais-upload-button"
      :disabled="loading"
      @click="openFileDialog"
    >
      <span class="ais-upload-icon">⌖</span>
      {{ loading ? 'AIS 분석 중' : 'AIS JSON 업로드' }}
    </button>

    <div v-if="result" class="ais-upload-status">
      <span class="ais-upload-live"></span>
      <strong>{{ result.summary.mappable }}척</strong>
      <span>{{ result.file_name }}</span>
      <button type="button" title="AIS 데이터 지우기" @click="emit('cleared')">
        ×
      </button>
    </div>

    <div v-if="errorMessage" class="ais-upload-error">
      {{ errorMessage }}
    </div>
  </div>
</template>

<style scoped>
.ais-uploader {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ais-upload-button {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border: 1px solid rgba(53, 211, 255, 0.34);
  border-radius: 7px;
  background: rgba(8, 72, 102, 0.46);
  color: #aeeaff;
  font-size: 12px;
  font-weight: 700;
}

.ais-upload-button:hover:not(:disabled) {
  border-color: rgba(81, 226, 255, 0.7);
  background: rgba(10, 91, 126, 0.62);
}

.ais-upload-icon {
  color: #41e7b2;
  font-size: 15px;
}

.ais-upload-status {
  display: flex;
  align-items: center;
  max-width: 210px;
  gap: 5px;
  padding: 7px 8px;
  border: 1px solid rgba(46, 221, 169, 0.22);
  border-radius: 7px;
  background: rgba(7, 57, 47, 0.28);
  color: #759cad;
  font-size: 10px;
}

.ais-upload-status strong {
  color: #72e8c0;
  white-space: nowrap;
}

.ais-upload-status > span:not(.ais-upload-live) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ais-upload-live {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: #3ae6b0;
  box-shadow: 0 0 7px #3ae6b0;
}

.ais-upload-status button {
  border: 0;
  background: transparent;
  color: #6d95a8;
  font-size: 15px;
  line-height: 1;
}

.ais-upload-error {
  position: absolute;
  top: calc(100% + 7px);
  right: 0;
  z-index: 20;
  width: 270px;
  padding: 8px 10px;
  border: 1px solid rgba(255, 89, 116, 0.45);
  border-radius: 6px;
  background: rgba(42, 9, 18, 0.96);
  color: #ff9bae;
  font-size: 10px;
}
</style>
