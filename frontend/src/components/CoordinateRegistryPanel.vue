<script setup lang="ts">
import {
  computed,
  reactive,
  ref,
  watch,
} from 'vue'

import {
  deleteManualCoordinate,
  saveManualCoordinate,
  type ManualCoordinateEntry,
} from '@/services/manualCoordinatesApi'

import type {
  MissingCoordinateItem,
} from '@/utils/manualCoordinates'


const props = defineProps<{
  open: boolean
  missingItems: MissingCoordinateItem[]
  registeredItems: ManualCoordinateEntry[]
}>()

const emit = defineEmits<{
  close: []
  saved: [entry: ManualCoordinateEntry]
  deleted: [
    payload: {
      locationCode: string
    },
  ]
}>()

const activeTab =
  ref<'missing' | 'registered'>('missing')
const saving = ref(false)
const deletingCode = ref('')
const errorMessage = ref('')

const form = reactive({
  locationCode: '',
  locationName: '',
  countryCode: '',
  latitude: '',
  longitude: '',
  note: '',
})

const filteredRegistered = computed(
  () => props.registeredItems,
)

function resetForm(): void {
  form.locationCode = ''
  form.locationName = ''
  form.countryCode = ''
  form.latitude = ''
  form.longitude = ''
  form.note = ''
  errorMessage.value = ''
}

function selectMissing(
  item: MissingCoordinateItem,
): void {
  form.locationCode =
    item.location_code
  form.locationName =
    item.location_name
  form.countryCode = ''
  form.latitude = ''
  form.longitude = ''
  form.note = [
    item.roles.join('/'),
    `${item.transport_count}건`,
    item.transport_numbers
      .slice(0, 5)
      .join(', '),
  ]
    .filter(Boolean)
    .join(' · ')
}

function editRegistered(
  item: ManualCoordinateEntry,
): void {
  activeTab.value = 'registered'
  form.locationCode =
    item.location_code
  form.locationName =
    item.location_name
  form.countryCode =
    item.country_code
  form.latitude =
    String(item.latitude)
  form.longitude =
    String(item.longitude)
  form.note =
    item.note
}

async function save(): Promise<void> {
  errorMessage.value = ''

  const locationCode =
    form.locationCode
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '')
  const latitude =
    Number(form.latitude)
  const longitude =
    Number(form.longitude)

  if (!locationCode) {
    errorMessage.value =
      'Location Code를 입력하세요.'
    return
  }

  if (
    !Number.isFinite(latitude)
    || latitude < -90
    || latitude > 90
  ) {
    errorMessage.value =
      '위도는 -90~90 범위로 입력하세요.'
    return
  }

  if (
    !Number.isFinite(longitude)
    || longitude < -180
    || longitude > 180
  ) {
    errorMessage.value =
      '경도는 -180~180 범위로 입력하세요.'
    return
  }

  saving.value = true

  try {
    const entry =
      await saveManualCoordinate(
        locationCode,
        {
          location_name:
            form.locationName.trim(),
          country_code:
            form.countryCode.trim(),
          latitude,
          longitude,
          note:
            form.note.trim(),
        },
      )

    emit('saved', entry)
    resetForm()
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? error.message
        : String(error)
  } finally {
    saving.value = false
  }
}

async function remove(
  item: ManualCoordinateEntry,
): Promise<void> {
  deletingCode.value =
    item.location_code
  errorMessage.value = ''

  try {
    await deleteManualCoordinate(
      item.location_code,
    )

    emit('deleted', {
      locationCode:
        item.location_code,
    })

    if (
      form.locationCode
      === item.location_code
    ) {
      resetForm()
    }
  } catch (error) {
    errorMessage.value =
      error instanceof Error
        ? error.message
        : String(error)
  } finally {
    deletingCode.value = ''
  }
}


watch(
  () => props.open,
  (open) => {
    if (open) {
      resetForm()
    }
  },
)
</script>

<template>
  <div
    v-if="open"
    class="coordinate-modal"
    role="dialog"
    aria-modal="true"
    aria-label="수동 좌표 관리"
  >
    <button
      type="button"
      class="coordinate-modal__backdrop"
      aria-label="닫기"
      @click="emit('close')"
    />

    <section class="coordinate-panel">
      <header class="coordinate-panel__header">
        <div>
          <p>GLOBAL COORDINATE REGISTRY</p>
          <h2>수동 좌표 관리</h2>
          <span>
            모든 법인이 공통 좌표를 사용합니다. ·
            미등록 {{ missingItems.length }}개 ·
            등록 {{ filteredRegistered.length }}개
          </span>
        </div>

        <button
          type="button"
          class="coordinate-panel__close"
          @click="emit('close')"
        >
          ×
        </button>
      </header>

      <nav class="coordinate-tabs">
        <button
          type="button"
          :class="{ active: activeTab === 'missing' }"
          @click="activeTab = 'missing'"
        >
          미등록 {{ missingItems.length }}
        </button>

        <button
          type="button"
          :class="{ active: activeTab === 'registered' }"
          @click="activeTab = 'registered'"
        >
          등록 좌표 {{ filteredRegistered.length }}
        </button>
      </nav>

      <div class="coordinate-panel__body">
        <div class="coordinate-list">
          <template v-if="activeTab === 'missing'">
            <button
              v-for="item in missingItems"
              :key="item.location_code"
              type="button"
              class="coordinate-item"
              @click="selectMissing(item)"
            >
              <strong>
                {{ item.location_code }}
              </strong>

              <span>
                {{ item.location_name || '명칭 없음' }}
              </span>

              <small>
                {{ item.roles.join('/') }} ·
                {{ item.transport_count }}건
              </small>
            </button>

            <p
              v-if="missingItems.length === 0"
              class="coordinate-empty"
            >
              좌표 미등록 항목이 없습니다.
            </p>
          </template>

          <template v-else>
            <article
              v-for="item in filteredRegistered"
              :key="item.location_code"
              class="coordinate-item coordinate-item--registered"
            >
              <button
                type="button"
                class="coordinate-item__main"
                @click="editRegistered(item)"
              >
                <strong>
                  {{ item.location_code }}
                </strong>

                <span>
                  {{ item.location_name || '명칭 없음' }}
                </span>

                <small>
                  {{ item.latitude }},
                  {{ item.longitude }}
                </small>
              </button>

              <button
                type="button"
                class="coordinate-item__delete"
                :disabled="
                  deletingCode ===
                  item.location_code
                "
                @click="remove(item)"
              >
                삭제
              </button>
            </article>

            <p
              v-if="filteredRegistered.length === 0"
              class="coordinate-empty"
            >
              등록된 수동 좌표가 없습니다.
            </p>
          </template>
        </div>

        <form
          class="coordinate-form"
          @submit.prevent="save"
        >
          <h3>좌표 등록·수정</h3>

          <label>
            <span>Location Code</span>
            <input
              v-model="form.locationCode"
              required
              placeholder="예: CNSHA"
            >
          </label>

          <label>
            <span>Location Name</span>
            <input
              v-model="form.locationName"
              placeholder="예: Shanghai"
            >
          </label>

          <label>
            <span>Country</span>
            <input
              v-model="form.countryCode"
              placeholder="CN"
            >
          </label>

          <div class="coordinate-form__row">
            <label>
              <span>Latitude</span>
              <input
                v-model="form.latitude"
                inputmode="decimal"
                required
                placeholder="31.2304"
              >
            </label>

            <label>
              <span>Longitude</span>
              <input
                v-model="form.longitude"
                inputmode="decimal"
                required
                placeholder="121.4737"
              >
            </label>
          </div>

          <label>
            <span>Note</span>
            <textarea
              v-model="form.note"
              rows="3"
              placeholder="좌표 출처 또는 확인 메모"
            />
          </label>

          <p
            v-if="errorMessage"
            class="coordinate-form__error"
          >
            {{ errorMessage }}
          </p>

          <div class="coordinate-form__actions">
            <button
              type="button"
              @click="resetForm"
            >
              초기화
            </button>

            <button
              type="submit"
              :disabled="saving"
              class="primary"
            >
              {{ saving ? '저장 중...' : '좌표 저장' }}
            </button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.coordinate-modal {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
}

.coordinate-modal__backdrop {
  position: absolute;
  inset: 0;
  border: 0;
  background: rgb(4 10 18 / 65%);
}

.coordinate-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(980px, calc(100vw - 40px));
  height: min(760px, calc(100vh - 40px));
  min-height: 0;
  overflow: hidden;
  border: 1px solid rgb(71 184 255 / 35%);
  border-radius: 18px;
  background: #0d1724;
  box-shadow: 0 24px 80px rgb(0 0 0 / 45%);
  color: #eaf6ff;
}

.coordinate-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 22px 24px 18px;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
}

.coordinate-panel__header p {
  margin: 0 0 4px;
  color: #51d4ff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .14em;
}

.coordinate-panel__header h2 {
  margin: 0 0 5px;
  font-size: 22px;
}

.coordinate-panel__header span {
  color: #9db1c5;
  font-size: 12px;
}

.coordinate-panel__close {
  width: 36px;
  height: 36px;
  border: 1px solid rgb(255 255 255 / 12%);
  border-radius: 10px;
  background: rgb(255 255 255 / 5%);
  color: #fff;
  font-size: 24px;
}

.coordinate-tabs {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
  padding: 14px 24px;
}

.coordinate-tabs button {
  padding: 9px 14px;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 999px;
  background: transparent;
  color: #9db1c5;
}

.coordinate-tabs button.active {
  border-color: #39c8ff;
  background: rgb(57 200 255 / 14%);
  color: #71dcff;
}

.coordinate-panel__body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, .9fr) minmax(360px, 1.1fr);
  overflow: hidden;
}

.coordinate-list {
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding: 0 14px 20px 24px;
  border-right: 1px solid rgb(255 255 255 / 8%);
}

.coordinate-list::-webkit-scrollbar,
.coordinate-form::-webkit-scrollbar {
  width: 10px;
}

.coordinate-list::-webkit-scrollbar-thumb,
.coordinate-form::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: rgb(113 220 255 / 45%);
  background-clip: padding-box;
}

.coordinate-item {
  display: grid;
  width: 100%;
  margin-bottom: 8px;
  padding: 12px 14px;
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 12px;
  background: rgb(255 255 255 / 3%);
  color: inherit;
  text-align: left;
}

.coordinate-item:hover {
  border-color: rgb(57 200 255 / 45%);
  background: rgb(57 200 255 / 7%);
}

.coordinate-item strong {
  color: #72ddff;
}

.coordinate-item span {
  margin-top: 3px;
  color: #e9f4fb;
}

.coordinate-item small {
  margin-top: 5px;
  color: #8098ad;
}

.coordinate-item--registered {
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.coordinate-item__main {
  display: grid;
  min-width: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
}

.coordinate-item__delete {
  align-self: center;
  border: 0;
  background: transparent;
  color: #ff8c9c;
}

.coordinate-empty {
  padding: 40px 12px;
  color: #7890a5;
  text-align: center;
}

.coordinate-form {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px 24px 24px;
}

.coordinate-form h3 {
  margin: 0 0 18px;
}

.coordinate-form label {
  display: grid;
  gap: 7px;
  margin-bottom: 14px;
}

.coordinate-form label span {
  color: #9fb5c8;
  font-size: 12px;
}

.coordinate-form input,
.coordinate-form textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 10px;
  background: #111f2e;
  color: #f4fbff;
  padding: 11px 12px;
}

.coordinate-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.coordinate-form__error {
  color: #ff9bab;
  font-size: 12px;
}

.coordinate-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: 9px;
}

.coordinate-form__actions button {
  padding: 10px 16px;
  border: 1px solid rgb(255 255 255 / 12%);
  border-radius: 10px;
  background: transparent;
  color: #cbdbe8;
}

.coordinate-form__actions .primary {
  border-color: #39c8ff;
  background: #1da7d7;
  color: #fff;
}

@media (max-width: 760px) {
  .coordinate-panel__body {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(220px, .8fr) minmax(320px, 1.2fr);
  }

  .coordinate-list {
    border-right: 0;
    border-bottom: 1px solid rgb(255 255 255 / 8%);
  }
}
</style>
