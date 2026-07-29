<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { addWatchlist, getWatchlist, removeWatchlist } from '../services/watchlistApi'

const props = defineProps<{ hblNo: string; label?: string }>()

const watched = ref(false)
const busy = ref(false)
// stale 응답 가드: 빠른 운송 전환 시 이전 조회 결과가 나중에 도착해
// 다른 HBL의 등록 상태를 덮어쓰는 것을 막는다.
let requestSeq = 0

function norm(value: string): string {
  return value.replace(/\s+/g, '').toUpperCase()
}

async function sync() {
  const seq = ++requestSeq
  const hbl = props.hblNo
  watched.value = false // 이전 HBL 상태가 새 HBL에 이어지지 않게 초기화
  try {
    const res = await getWatchlist()
    if (seq !== requestSeq || hbl !== props.hblNo) return // stale 응답 폐기
    watched.value = res.items.some(
      (i) => i.type === 'hbl' && norm(i.id) === norm(hbl),
    )
  } catch {
    // 조회 실패 시 false 유지 (이전 상태를 공유하지 않음)
  }
}

async function toggle() {
  busy.value = true
  try {
    if (watched.value) {
      await removeWatchlist(props.hblNo)
    } else {
      await addWatchlist(props.hblNo, props.label ?? '')
    }
    await sync() // 서버 상태 기준으로 재확인
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
