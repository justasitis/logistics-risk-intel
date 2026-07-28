<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { addWatchlist, getWatchlist, removeWatchlist } from '../services/watchlistApi'

const props = defineProps<{ hblNo: string; label?: string }>()

const watched = ref(false)
const busy = ref(false)

async function sync() {
  try {
    const res = await getWatchlist()
    watched.value = res.items.some((i) => i.type === 'hbl' && i.id === props.hblNo)
  } catch {
    // 조회 실패 시 현재 상태 유지
  }
}

async function toggle() {
  busy.value = true
  try {
    if (watched.value) {
      await removeWatchlist(props.hblNo)
      watched.value = false
    } else {
      await addWatchlist(props.hblNo, props.label ?? '')
      watched.value = true
    }
  } finally {
    busy.value = false
  }
}

onMounted(sync)
watch(() => props.hblNo, sync)
</script>

<template>
  <button
    type="button"
    class="watch-toggle"
    :class="{ watched }"
    :disabled="busy"
    :title="watched ? '관심화물 해제' : '관심화물 등록'"
    @click="toggle"
  >
    {{ watched ? '★ 관심' : '☆ 관심' }}
  </button>
</template>

<style scoped>
.watch-toggle {
  padding: 4px 10px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text-muted);
  font-size: 12px;
  cursor: pointer;
}
.watch-toggle.watched {
  border-color: var(--li-risk-medium);
  color: var(--li-risk-medium);
  font-weight: 700;
}
.watch-toggle:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
