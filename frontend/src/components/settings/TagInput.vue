<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  modelValue: string[]
  placeholder?: string
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: string[]): void
}>()

const draft = ref('')

function addTag() {
  const value = draft.value.trim()
  if (!value) return
  if (!props.modelValue.includes(value)) {
    emit('update:modelValue', [...props.modelValue, value])
  }
  draft.value = ''
}

function removeTag(index: number) {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ',') {
    event.preventDefault()
    addTag()
  }
}
</script>

<template>
  <div class="tag-input">
    <span v-for="(tag, index) in modelValue" :key="`${tag}-${index}`" class="tag">
      {{ tag }}
      <button type="button" class="tag-remove" title="삭제" @click="removeTag(index)">×</button>
    </span>
    <input
      v-model="draft"
      type="text"
      class="tag-field"
      :placeholder="placeholder || '입력 후 Enter'"
      @keydown="onKeydown"
      @blur="addTag"
    />
  </div>
</template>

<style scoped>
.tag-input {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border: 1px solid var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--li-surface-blue);
  border: 1px solid var(--li-border);
  color: var(--li-text-soft);
  font-size: 11px;
}
.tag-remove {
  border: 0;
  background: transparent;
  color: var(--li-text-faint);
  cursor: pointer;
  font-size: 11px;
  padding: 0 1px;
}
.tag-remove:hover { color: var(--li-risk-critical); }
.tag-field {
  flex: 1;
  min-width: 90px;
  border: 0;
  background: transparent;
  font-size: 12px;
  color: var(--li-text);
  outline: none;
  padding: 3px 2px;
}
</style>
