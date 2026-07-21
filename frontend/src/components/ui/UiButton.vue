<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'default' | 'primary' | 'ghost' | 'danger'; disabled?: boolean; type?: 'button' | 'submit' | 'reset' }>(), { variant: 'default', disabled: false, type: 'button' })
</script>

<template>
  <button class="ui-button" :class="[variant === 'primary' && 'ui-button--primary', variant === 'ghost' && 'ui-button--ghost', variant === 'danger' && 'ui-button--danger']" :type="type" :disabled="disabled">
    <slot />
  </button>
</template>
