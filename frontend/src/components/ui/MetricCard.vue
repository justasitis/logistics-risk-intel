<script setup lang="ts">
withDefaults(defineProps<{ label: string; value: string | number; hint?: string; accent?: boolean }>(), { hint: '', accent: false })
</script>

<template>
  <article class="metric-card" :class="accent && 'metric-card--blue'">
    <div class="metric-card__label">{{ label }}</div>
    <div class="metric-card__value">{{ value }}</div>
    <div v-if="hint" class="metric-card__hint">{{ hint }}</div>
  </article>
</template>
