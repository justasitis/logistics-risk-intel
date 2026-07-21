<script setup lang="ts">
import { useMiWorkspace } from '../../composables/useMiWorkspace'

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
              <div class="small">{{ event.summary }}</div>
              <div class="small mono">{{ event.event_id }}</div>
            </td>
            <td>
              <div>{{ event.affected_locations.map((item) => item.code).join(', ') || '-' }}</div>
              <div class="small">{{ event.affected_corridors.join(', ') || '-' }}</div>
              <div v-if="event.unresolved_locations.length" class="warning">
                미해결 위치 {{ event.unresolved_locations.length }}건
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
.mono { font-family: monospace; }
.warning { color: #ef6c00; font-size: 11px; }
</style>
