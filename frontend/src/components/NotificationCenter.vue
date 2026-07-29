<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getNotifications, removeWatchlist } from '../services/watchlistApi'
import type { NotificationsResponse } from '../types/watchlist'

const emit = defineEmits<{ selectHbl: [hblNo: string] }>()

const LAST_SEEN_KEY = 'lri-notifications-last-seen'

const data = ref<NotificationsResponse | null>(null)
const open = ref(false)
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

const alertCount = computed(() =>
  (data.value?.items ?? []).reduce((sum, item) => sum + item.alerts.length, 0),
)

// 마지막 확인 이후 새 계산분이 있으면 배지 강조 (클이언트 localStorage 처리)
const hasNew = computed(() => {
  if (!data.value || alertCount.value === 0) return false
  const lastSeen = localStorage.getItem(LAST_SEEN_KEY) ?? ''
  return data.value.computed_at > lastSeen
})

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getNotifications()
  } catch (e) {
    // 에러 시 이전 데이터로 빈 상태를 렌더하지 않고 에러를 표시
    data.value = null
    error.value = e instanceof Error ? e.message : '알림 조회 실패'
  } finally {
    loading.value = false
  }
}

function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    void refresh()
    localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString())
  }
}

async function unwatch(hblNo: string) {
  await removeWatchlist(hblNo)
  await refresh()
}

onMounted(() => {
  void refresh()
  timer = setInterval(() => void refresh(), 60_000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="noti">
    <button type="button" class="bell" :class="{ fresh: hasNew }" title="알림 센터" @click="toggleOpen">
      🔔
      <span v-if="alertCount" class="badge">{{ alertCount }}</span>
    </button>

    <div v-if="open" class="dropdown">
      <div class="drop-head">
        <span class="drop-title">관심화물 알림</span>
        <span v-if="data" class="meta">{{ data.computed_at.slice(0, 16).replace('T', ' ') }} 기준</span>
      </div>
      <p v-if="loading" class="hint">알림을 확인하는 중...</p>
      <p v-else-if="error" class="error">알림 조회 실패: {{ error }}</p>
      <p v-else-if="data && !data.items.length" class="hint">
        관심화물이 없습니다. 운송 상세에서 ☆ 관심을 등록하세요.
      </p>

      <template v-if="!loading && !error && data">
        <div v-for="item in data.items" :key="item.hbl_no" class="item">
        <div class="item-head">
          <button type="button" class="hbl-link" @click="emit('selectHbl', item.hbl_no)">
            {{ item.label || item.hbl_no }}
          </button>
          <button type="button" class="unwatch" title="관심 해제" @click="unwatch(item.hbl_no)">✕</button>
        </div>
        <ul v-if="item.alerts.length" class="alerts">
          <li
            v-for="(alert, i) in item.alerts"
            :key="i"
            class="alert"
            :class="alert.severity.toLowerCase()"
          >
            {{ alert.message }}
          </li>
        </ul>
        <p v-else class="ok">이상 없음</p>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.noti {
  position: relative;
}
.bell {
  position: relative;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  padding: 5px 10px;
  cursor: pointer;
  font-size: 13px;
}
.bell.fresh {
  border-color: var(--li-risk-high);
}
.badge {
  position: absolute;
  top: -6px;
  right: -6px;
  background: var(--li-risk-critical);
  color: #fff;
  font-size: 12px;
  border-radius: 999px;
  padding: 0 5px;
  min-width: 16px;
  text-align: center;
}
.dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  width: 340px;
  max-height: 420px;
  overflow-y: auto;
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  box-shadow: var(--li-shadow-float);
  padding: 12px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.drop-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.drop-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--li-text);
}
.meta {
  font-size: 12px;
  color: var(--li-text-muted);
}
.item {
  border-top: 1px solid var(--li-border);
  padding-top: 8px;
}
.item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.hbl-link {
  border: none;
  background: none;
  color: var(--li-blue);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  padding: 0;
  text-align: left;
}
.unwatch {
  border: none;
  background: none;
  color: var(--li-text-faint);
  cursor: pointer;
  font-size: 12px;
}
.alerts {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.alert {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: var(--li-radius-sm);
}
.alert.critical,
.alert.high {
  background: var(--li-risk-critical-bg);
  color: var(--li-risk-critical);
}
.alert.medium {
  background: var(--li-risk-high-bg);
  color: var(--li-risk-high);
}
.alert.low {
  background: var(--li-bg-app-2);
  color: var(--li-text-muted);
}
.ok {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--li-mint);
}
.hint {
  color: var(--li-text-muted);
  font-size: 12px;
  margin: 0;
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>
