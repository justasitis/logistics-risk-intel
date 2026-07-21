<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'default' | 'soft' | 'strong' | 'blue'; padded?: boolean }>(), { variant: 'default', padded: true })
</script>

<template>
  <section class="glass-panel" :class="[variant === 'soft' && 'glass-panel--soft', variant === 'strong' && 'glass-panel--strong', variant === 'blue' && 'glass-panel--blue', padded && 'panel-pad']">
    <slot />
  </section>
</template>
