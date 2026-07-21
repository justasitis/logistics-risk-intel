<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ status?: 'live' | 'ok' | 'stale' | 'warn' | 'off' | 'error' | string }>(), { status: 'ok' })
const normalized = computed(() => String(props.status || 'ok').toLowerCase())
const className = computed(() => {
  if (['live', 'ok', 'success'].includes(normalized.value)) return 'status-pill status-pill--live'
  if (['stale', 'warn', 'warning'].includes(normalized.value)) return 'status-pill status-pill--stale'
  if (['off', 'error', 'failed', 'nosignal', 'no_signal'].includes(normalized.value)) return 'status-pill status-pill--off'
  return 'status-pill'
})
</script>

<template>
  <span :class="className"><slot>{{ status }}</slot></span>
</template>
