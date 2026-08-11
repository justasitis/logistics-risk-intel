<script setup lang="ts">
import { ref } from 'vue'

import { parseMiUpload } from '@/services/miUpload'
import type { MiUploadResult } from '@/types/dashboard'

defineProps<{
  result: MiUploadResult | null
}>()

const emit = defineEmits<{
  loaded: [result: MiUploadResult]
  cleared: []
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const error = ref('')

function openFilePicker() {
  fileInput.value?.click()
}

async function handleFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  loading.value = true
  error.value = ''

  try {
    emit('loaded', await parseMiUpload(file))
  } catch (reason) {
    error.value =
      reason instanceof Error
        ? reason.message
        : 'MI 파일을 읽지 못했습니다.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="mi-upload">
    <input
      ref="fileInput"
      type="file"
      accept=".json,application/json"
      hidden
      @change="handleFile"
    >

    <button
      v-if="!result"
      type="button"
      class="mi-upload-button"
      :disabled="loading"
      @click="openFilePicker"
    >
      {{ loading ? 'MI 분석 중' : 'MI JSON 업로드' }}
    </button>

    <div v-else class="mi-upload-loaded">
      <button
        type="button"
        class="mi-loaded-main"
        @click="openFilePicker"
      >
        <span class="mi-live-dot"></span>
        {{ result.events.length }}건
        <small>{{ result.file_name }}</small>
      </button>

      <button
        type="button"
        class="mi-clear"
        title="MI 데이터 지우기"
        @click="emit('cleared')"
      >
        ×
      </button>
    </div>

    <div v-if="error" class="mi-upload-error">
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.mi-upload {
  position: relative;
}

.mi-upload-button,
.mi-loaded-main,
.mi-clear {
  border: 1px solid rgba(255, 107, 139, 0.32);
  background: rgba(90, 20, 45, 0.24);
  color: #ffb2c3;
}

.mi-upload-button {
  padding: 8px 11px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 700;
}

.mi-upload-loaded {
  display: flex;
  align-items: stretch;
}

.mi-loaded-main {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 210px;
  padding: 7px 9px;
  border-radius: 7px 0 0 7px;
  font-size: 11px;
  font-weight: 700;
}

.mi-loaded-main small {
  max-width: 95px;
  overflow: hidden;
  color: #a87b8a;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mi-live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #ff5579;
  box-shadow: 0 0 8px rgba(255, 85, 121, 0.85);
}

.mi-clear {
  width: 28px;
  border-left: 0;
  border-radius: 0 7px 7px 0;
  font-size: 15px;
}

.mi-upload-error {
  position: absolute;
  right: 0;
  top: calc(100% + 7px);
  z-index: 50;
  width: 310px;
  padding: 9px 10px;
  border: 1px solid rgba(255, 77, 111, 0.4);
  border-radius: 7px;
  background: rgba(40, 8, 19, 0.97);
  color: #ff9eb2;
  font-size: 11px;
  line-height: 1.45;
}
</style>
