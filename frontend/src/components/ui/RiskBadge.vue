<script setup lang="ts">
import { computed } from 'vue'
import { riskLabel, riskToneClass } from '@/theme/riskTones'

const props = withDefaults(defineProps<{ severity?: string; label?: string }>(), { severity: 'WATCH', label: '' })
const className = computed(() => ['risk-badge', riskToneClass(props.severity)])
const displayLabel = computed(() => props.label || riskLabel(props.severity))
</script>

<template>
  <span :class="className"><slot>{{ displayLabel }}</slot></span>
</template>
