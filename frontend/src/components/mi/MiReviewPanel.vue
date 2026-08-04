<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMiWorkspace } from '../../composables/useMiWorkspace'
import { getMiLocationMaster } from '../../services/miAiApi'
import type {
  MiLocationMasterEntry,
  RefinedMiEvent,
} from '../../types/mi'

const {
  state,
  approvedEvents,
  submitReview,
  setAllReviewStatuses,
  downloadCanonicalPayload,
} = useMiWorkspace()

const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
const statuses = ['ACTIVE', 'WATCH', 'IMPROVING', 'RESOLVED'] as const
const reviewStatuses = ['PENDING', 'APPROVED', 'EDITED', 'REJECTED'] as const

// ---------- 위치 마스터 (드롭다운 선택지) ----------
const locationMaster = ref<MiLocationMasterEntry[]>([])

onMounted(async () => {
  try {
    locationMaster.value = (await getMiLocationMaster()).locations
  } catch {
    locationMaster.value = []
  }
})

const masterByCode = computed(
  () => new Map(locationMaster.value.map((entry) => [entry.code, entry])),
)

// ---------- 위치 추가/제거 (이벤트별 로컬 선택 상태) ----------
const addLocationSel = reactive<Record<string, string>>({})

function availableLocations(event: RefinedMiEvent): MiLocationMasterEntry[] {
  const used = new Set(event.affected_locations.map((loc) => loc.code))
  return locationMaster.value.filter((entry) => !used.has(entry.code))
}

function addLocation(event: RefinedMiEvent): void {
  const code = addLocationSel[event.event_id]
  const entry = code ? masterByCode.value.get(code) : undefined
  if (!entry) return
  event.affected_locations.push({
    code: entry.code,
    name: entry.name,
    location_type: entry.location_type,
    lat: entry.lat,
    lon: entry.lon,
    radius_km: entry.default_radius_km,
  })
  addLocationSel[event.event_id] = ''
}

function removeLocation(event: RefinedMiEvent, code: string): void {
  event.affected_locations = event.affected_locations.filter(
    (loc) => loc.code !== code,
  )
}

// ---------- Lane(corridor) 추가/제거 ----------
// 회랑은 자유 텍스트라 대표 회랑 + 현재 이벤트들에 등장한 값을 합쳐 선택지로 만든다.
const CANONICAL_CORRIDORS = [
  'ASIA_EUROPE',
  'ASIA_US_EAST',
  'ASIA_US_WEST',
  'INTRA_ASIA',
  'EUROPE_US',
]

const corridorOptions = computed<string[]>(() => {
  const found = state.refinedEvents.flatMap((event) => event.affected_corridors)
  return [...new Set([...CANONICAL_CORRIDORS, ...found])]
})

const addCorridorSel = reactive<Record<string, string>>({})

function availableCorridors(event: RefinedMiEvent): string[] {
  return corridorOptions.value.filter(
    (corridor) => !event.affected_corridors.includes(corridor),
  )
}

function addCorridor(event: RefinedMiEvent): void {
  const corridor = addCorridorSel[event.event_id]
  if (!corridor) return
  if (!event.affected_corridors.includes(corridor)) {
    event.affected_corridors.push(corridor)
  }
  addCorridorSel[event.event_id] = ''
}

function removeCorridor(event: RefinedMiEvent, corridor: string): void {
  event.affected_corridors = event.affected_corridors.filter(
    (value) => value !== corridor,
  )
}

// ---------- 미해결 위치 멀티선택 → 마스터 매칭 해결 ----------
interface UnresolvedSelection {
  checked: boolean
  code: string
}

const unresolvedSel = reactive<Record<string, UnresolvedSelection>>({})

function unresolvedKey(event: RefinedMiEvent, index: number): string {
  return `${event.event_id}|${index}`
}

function unresolvedLabel(ref: Record<string, unknown>): string {
  const name = String(ref.name || '').trim()
  const code = String(ref.code || '').trim()
  if (name && code) return `${name} (${code})`
  return name || code || '(이름 없음)'
}

/** 코드/이름/별칭으로 마스터 코드를 추정 — 못 찾으면 빈 문자열(수동 선택) */
function guessMasterCode(ref: Record<string, unknown>): string {
  const code = String(ref.code || '').trim().toUpperCase()
  if (code && masterByCode.value.has(code)) return code
  const name = String(ref.name || '').trim().toLowerCase()
  if (!name) return ''
  const hit = locationMaster.value.find(
    (entry) =>
      entry.name.toLowerCase() === name
      || entry.aliases.some((alias) => alias.trim().toLowerCase() === name),
  )
  return hit?.code ?? ''
}

function selFor(
  event: RefinedMiEvent,
  index: number,
  ref: Record<string, unknown>,
): UnresolvedSelection {
  const key = unresolvedKey(event, index)
  if (!unresolvedSel[key]) {
    unresolvedSel[key] = { checked: false, code: guessMasterCode(ref) }
  }
  return unresolvedSel[key]
}

/** 체크+매칭된 미해결 위치를 affected_locations로 승격 (반경은 resolver와 같은 0.5~2배 클램프) */
function resolveSelected(event: RefinedMiEvent): void {
  const remaining: Array<Record<string, unknown>> = []
  event.unresolved_locations.forEach((ref, index) => {
    const key = unresolvedKey(event, index)
    const sel = unresolvedSel[key]
    const entry = sel?.checked && sel.code
      ? masterByCode.value.get(sel.code)
      : undefined
    if (!entry) {
      remaining.push(ref)
      return
    }
    if (!event.affected_locations.some((loc) => loc.code === entry.code)) {
      const base = entry.default_radius_km
      const requested = typeof ref.radius_km === 'number' ? ref.radius_km : base
      const radius = Math.max(base * 0.5, Math.min(requested, base * 2))
      event.affected_locations.push({
        code: entry.code,
        name: entry.name,
        location_type: entry.location_type,
        lat: entry.lat,
        lon: entry.lon,
        radius_km: Math.round(radius * 10) / 10,
      })
    }
    delete unresolvedSel[key]
  })
  event.unresolved_locations = remaining
}
</script>

<template>
  <section v-if="state.refinedEvents.length" class="mi-card">
    <div class="toolbar">
      <div>
        <div class="mi-card__title">3. Event 검토·승인</div>
        <div class="small">승인·수정된 Event만 기존 지도 및 영향화물 계산에 사용됩니다.</div>
      </div>
      <div class="toolbar-actions">
        <button @click="setAllReviewStatuses('APPROVED')">전체 승인</button>
        <button @click="setAllReviewStatuses('REJECTED')">전체 제외</button>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>검토</th>
            <th>위험도</th>
            <th>상태</th>
            <th>Event</th>
            <th>위치/Lane</th>
            <th>신뢰도</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="event in state.refinedEvents" :key="event.event_id">
            <td>
              <select v-model="event.review_status">
                <option v-for="value in reviewStatuses" :key="value" :value="value">{{ value }}</option>
              </select>
            </td>
            <td>
              <select v-model="event.severity">
                <option v-for="value in severities" :key="value" :value="value">{{ value }}</option>
              </select>
            </td>
            <td>
              <select v-model="event.status">
                <option v-for="value in statuses" :key="value" :value="value">{{ value }}</option>
              </select>
            </td>
            <td>
              <b>{{ event.headline }}</b>
              <div class="badges">
                <span class="badge" :class="event.direction === 'RISK_DECREASE' ? 'decrease' : 'increase'">
                  {{ event.direction === 'RISK_DECREASE' ? '리스크 감소' : '리스크 증가' }}
                </span>
                <span class="badge" :class="event.impact_path === 'INDIRECT' ? 'indirect' : 'direct'">
                  {{ event.impact_path === 'INDIRECT' ? '간접(전이)' : '직접' }}
                </span>
              </div>
              <div class="small">{{ event.summary }}</div>
              <div class="small mono">{{ event.event_id }}</div>
            </td>
            <td class="loc-cell">
              <div class="chips">
                <span v-for="loc in event.affected_locations" :key="loc.code" class="chip">
                  {{ loc.code }}
                  <button
                    type="button"
                    class="chip-x"
                    :title="`${loc.name} 제거`"
                    @click="removeLocation(event, loc.code)"
                  >×</button>
                </span>
                <span v-if="!event.affected_locations.length" class="small">위치 없음</span>
              </div>
              <div v-if="locationMaster.length" class="add-row">
                <select v-model="addLocationSel[event.event_id]">
                  <option value="">위치 추가...</option>
                  <option
                    v-for="opt in availableLocations(event)"
                    :key="opt.code"
                    :value="opt.code"
                  >{{ opt.code }} — {{ opt.name }}</option>
                </select>
                <button
                  type="button"
                  :disabled="!addLocationSel[event.event_id]"
                  @click="addLocation(event)"
                >추가</button>
              </div>

              <div class="chips">
                <span v-for="corridor in event.affected_corridors" :key="corridor" class="chip lane">
                  {{ corridor }}
                  <button
                    type="button"
                    class="chip-x"
                    :title="`${corridor} 제거`"
                    @click="removeCorridor(event, corridor)"
                  >×</button>
                </span>
                <span v-if="!event.affected_corridors.length" class="small">Lane 없음</span>
              </div>
              <div class="add-row">
                <select v-model="addCorridorSel[event.event_id]">
                  <option value="">Lane 추가...</option>
                  <option
                    v-for="opt in availableCorridors(event)"
                    :key="opt"
                    :value="opt"
                  >{{ opt }}</option>
                </select>
                <button
                  type="button"
                  :disabled="!addCorridorSel[event.event_id]"
                  @click="addCorridor(event)"
                >추가</button>
              </div>

              <div v-if="event.unresolved_locations.length" class="unresolved">
                <div class="warning">
                  미해결 위치 {{ event.unresolved_locations.length }}건 — 매칭할 위치를 고르고 체크하세요
                </div>
                <div
                  v-for="(ref, i) in event.unresolved_locations"
                  :key="i"
                  class="unresolved-row"
                >
                  <input
                    v-model="selFor(event, i, ref).checked"
                    type="checkbox"
                    :disabled="!selFor(event, i, ref).code"
                  />
                  <span class="unresolved-name">{{ unresolvedLabel(ref) }}</span>
                  <select v-model="selFor(event, i, ref).code">
                    <option value="">(매칭 선택)</option>
                    <option
                      v-for="opt in locationMaster"
                      :key="opt.code"
                      :value="opt.code"
                    >{{ opt.code }} — {{ opt.name }}</option>
                  </select>
                </div>
                <button type="button" class="resolve-btn" @click="resolveSelected(event)">
                  선택 위치 해결
                </button>
              </div>
            </td>
            <td>{{ Math.round(event.confidence * 100) }}%</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="footer-row">
      <span>승인 예정 {{ approvedEvents.length }}건</span>
      <button class="primary" @click="submitReview">검토 결과 저장</button>
      <button :disabled="!state.reviewResult" @click="downloadCanonicalPayload">
        승인 MI JSON 다운로드
      </button>
    </div>
  </section>
</template>

<style scoped>
.mi-card { padding: 16px; border: 1px solid #dbe4ee; border-radius: 10px; background: #fff; }
.mi-card__title { font-weight: 700; color: #102a43; }
.toolbar, .footer-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.toolbar-actions, .footer-row { display: flex; gap: 8px; }
.table-wrap { overflow: auto; margin: 14px 0; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 8px; border-bottom: 1px solid #e6edf3; text-align: left; vertical-align: top; }
th { background: #f5f8fb; color: #486581; }
select, button { padding: 6px 8px; border: 1px solid #bcccdc; border-radius: 5px; background: white; }
.primary { border-color: #1d5fa7; background: #1d5fa7; color: white; }
.small { color: #627d98; font-size: 11px; margin-top: 3px; }
.badges { display: flex; gap: 4px; margin-top: 3px; }
.badge { padding: 1px 7px; border-radius: 999px; font-size: 11px; }
.badge.increase { background: #ffebee; color: #c62828; }
.badge.decrease { background: #e8f5e9; color: #2e7d32; }
.badge.direct { background: #e3f2fd; color: #1565c0; }
.badge.indirect { background: #fff3e0; color: #ef6c00; }
.mono { font-family: monospace; }
.warning { color: #ef6c00; font-size: 11px; }

/* ---------- 위치/Lane 편집 ---------- */
.loc-cell { min-width: 260px; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 4px 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  background: #e3f2fd;
  color: #1565c0;
  border: 1px solid #bbdefb;
}
.chip.lane { background: #f3e8fd; color: #7b1fa2; border-color: #e1bee7; }
.chip-x {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 12px;
  line-height: 1;
  padding: 0 3px;
  cursor: pointer;
  opacity: 0.65;
}
.chip-x:hover { opacity: 1; }
.add-row { display: flex; gap: 4px; margin-top: 4px; }
.add-row select { flex: 1; min-width: 0; font-size: 11px; padding: 3px 6px; }
.add-row button { font-size: 11px; padding: 3px 8px; cursor: pointer; }
.add-row button:disabled { opacity: 0.5; cursor: not-allowed; }
.unresolved {
  margin-top: 6px;
  padding: 6px 8px;
  border: 1px dashed #ef6c00;
  border-radius: 6px;
  background: #fff8f0;
}
.unresolved-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 11px;
}
.unresolved-name { color: #102a43; font-weight: 600; }
.unresolved-row select { flex: 1; min-width: 0; font-size: 11px; padding: 3px 6px; }
.resolve-btn { margin-top: 6px; font-size: 11px; padding: 4px 10px; cursor: pointer; }
</style>
