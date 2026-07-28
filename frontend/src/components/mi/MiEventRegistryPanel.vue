<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getMiRegistry, rebuildMiRegistry } from '../../services/miRegistryApi'
import type { RegistryResponse, RegistryStatus } from '../../types/miRegistry'

const registry = ref<RegistryResponse | null>(null)
const loading = ref(false)
const rebuilding = ref(false)
const error = ref('')
const statusFilter = ref<'' | RegistryStatus>('')

const STATUS_LABELS: Record<RegistryStatus, string> = {
  ACTIVE: 'ACTIVE',
  IMPROVING: 'IMPROVING',
  RESOLVED: 'RESOLVED',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    registry.value = await getMiRegistry(statusFilter.value || undefined)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '레지스트리 조회 실패'
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  rebuilding.value = true
  error.value = ''
  try {
    await rebuildMiRegistry()
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '레지스트리 재구축 실패'
  } finally {
    rebuilding.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="registry">
    <div class="head">
      <div>
        <h3 class="title">이벤트 레지스트리</h3>
        <p v-if="registry" class="meta">기준일 {{ registry.reference_date ?? '-' }} · {{ registry.events.length }}건</p>
      </div>
      <div class="controls">
        <select v-model="statusFilter" class="filter" @change="load">
          <option value="">전체 상태</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="IMPROVING">IMPROVING</option>
          <option value="RESOLVED">RESOLVED</option>
        </select>
        <button class="btn" :disabled="rebuilding" @click="rebuild">
          {{ rebuilding ? '재구축 중...' : '일자별 파일 재인입' }}
        </button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="hint">조회 중...</p>
    <p v-if="registry && !registry.events.length && !loading" class="hint">
      등록된 이벤트가 없습니다. 일자별 파일을 재인입하세요.
    </p>

    <ul v-if="registry" class="list">
      <li v-for="event in registry.events" :key="event.event_id" class="card">
        <div class="card-head">
          <span class="status" :class="event.status.toLowerCase()">
            {{ STATUS_LABELS[event.status] }}
          </span>
          <span v-if="event.reactivated" class="reactivated">재활성화</span>
          <span class="severity">{{ event.severity }}</span>
          <span class="id">{{ event.event_id }}</span>
        </div>
        <div class="headline">{{ event.headline }}</div>
        <div class="meta">
          최초 {{ event.first_seen }} · 최종 {{ event.last_seen }} · 목격 {{ event.sighting_count }}회
        </div>
        <div v-if="event.locations.length" class="locs">
          <span v-for="loc in event.locations" :key="loc" class="chip">{{ loc }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.registry {
  background: var(--li-surface-strong);
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  padding: 16px;
  box-shadow: var(--li-shadow-card);
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.title {
  margin: 0;
  font-size: 14px;
  color: var(--li-text);
}
.meta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--li-text-muted);
}
.controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.filter {
  padding: 5px 8px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
}
.btn {
  padding: 6px 14px;
  border: 1px solid var(--li-border);
  border-radius: 999px;
  background: var(--li-surface-strong);
  color: var(--li-text);
  font-size: 12px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card {
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.status {
  font-size: 12px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}
.status.active {
  background: rgba(16, 185, 129, 0.14);
  color: #10b981;
}
.status.improving {
  background: rgba(234, 179, 8, 0.14);
  color: #eab308;
}
.status.resolved {
  background: rgba(100, 116, 139, 0.14);
  color: #64748b;
}
.reactivated {
  font-size: 12px;
  color: var(--li-blue);
}
.severity {
  font-size: 12px;
  color: var(--li-text-soft);
}
.id {
  margin-left: auto;
  font-size: 12px;
  color: var(--li-text-faint);
  font-family: monospace;
}
.headline {
  font-size: 13px;
  font-weight: 700;
  color: var(--li-text);
}
.locs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.chip {
  font-size: 12px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--li-surface-blue);
  color: var(--li-blue);
}
.hint {
  color: var(--li-text-muted);
  font-size: 12px;
}
.error {
  color: var(--li-risk-critical);
  margin: 0;
  font-size: 12px;
}
</style>
