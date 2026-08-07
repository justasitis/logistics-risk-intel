<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  fetchConfigCatalog,
  fetchConfigSection,
  resetConfigSection,
  saveConfigSection,
} from '../services/configApi'
import {
  isCarrierInferenceData,
  isCompaniesData,
  isLocationMasterData,
  isRouteGroupsData,
  isThresholdsData,
  type CarrierInferenceData,
  type CompanyEntry,
  type ConfigSection,
  type ConfigSectionMeta,
  type LocationMasterEditRow,
  type RouteGroup,
  type RouteGroupEdit,
  type RouteGroupsData,
  type ThresholdsData,
} from '../types/config'
import ThresholdsEditor from './settings/ThresholdsEditor.vue'
import CompaniesEditor from './settings/CompaniesEditor.vue'
import CarrierInferenceEditor from './settings/CarrierInferenceEditor.vue'
import LocationMasterEditor from './settings/LocationMasterEditor.vue'
import RouteGroupsEditor from './settings/RouteGroupsEditor.vue'

const catalog = ref<ConfigSectionMeta[]>([])
const catalogLoading = ref(false)
const catalogError = ref('')

const activeMeta = ref<ConfigSectionMeta | null>(null)
const sectionLoading = ref(false)
const saving = ref(false)
const resetting = ref(false)
const errorMessage = ref('')
const noticeMessage = ref('')

// kind별 편집 모델 (활성 섹션의 것만 채워진다)
const thresholdsModel = ref<ThresholdsData | null>(null)
const companyRows = ref<CompanyEntry[]>([])
const carrierModel = ref<CarrierInferenceData | null>(null)
const locationRows = ref<LocationMasterEditRow[]>([])
const routeGroupRows = ref<RouteGroupEdit[]>([])

const snapshot = ref('')

const editJson = computed(() => {
  const kind = activeMeta.value?.kind
  if (kind === 'thresholds') return JSON.stringify(thresholdsModel.value)
  if (kind === 'companies') return JSON.stringify(companyRows.value)
  if (kind === 'carrier_inference') return JSON.stringify(carrierModel.value)
  if (kind === 'location_master') return JSON.stringify(locationRows.value)
  if (kind === 'route_groups') return JSON.stringify(routeGroupRows.value)
  return ''
})

const isDirty = computed(() => Boolean(activeMeta.value) && editJson.value !== snapshot.value)

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function splitCsv(text: string): string[] {
  return text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function joinCsv(values: string[] | undefined): string {
  return (values ?? []).join(', ')
}

function toEditGroup(group: RouteGroup): RouteGroupEdit {
  return {
    group_id: group.group_id,
    isNew: false,
    name: group.name,
    region: group.region || '유럽',
    arvl_codes: [...(group.arvl_codes ?? [])],
    stopby_match: [...(group.stopby_match ?? [])],
    stopby_exclude: [...(group.stopby_exclude ?? [])],
    delay_target: Boolean(group.delay_target),
    metric_inland: group.metric === 'inland',
    row_label: group.row_label ?? '',
    fixed_rows: group.fixed_rows ? [...group.fixed_rows] : undefined,
    rows: (group.row_groups ?? []).map((row) => ({
      row_id: row.row_id,
      label: row.label,
      field: row.field,
      codesText: joinCsv(row.codes),
      exclude_field: row.exclude_field ?? '',
      exclude_codesText: joinCsv(row.exclude_codes),
    })),
  }
}

function applySection(section: ConfigSection): void {
  const meta: ConfigSectionMeta = {
    key: section.key,
    title: section.title,
    kind: section.kind,
    source: section.source,
    updated_at: section.updated_at,
  }

  thresholdsModel.value = null
  companyRows.value = []
  carrierModel.value = null
  locationRows.value = []
  routeGroupRows.value = []

  switch (section.kind) {
    case 'thresholds':
      if (!isThresholdsData(section.data)) {
        throw new Error('응답 데이터 형식이 예상과 다릅니다. 백엔드 구현을 확인하세요.')
      }
      thresholdsModel.value = { ...section.data }
      break
    case 'companies':
      if (!isCompaniesData(section.data)) {
        throw new Error('응답 데이터 형식이 예상과 다릅니다. 백엔드 구현을 확인하세요.')
      }
      companyRows.value = section.data.companies.map((company) => ({ ...company }))
      break
    case 'carrier_inference':
      if (!isCarrierInferenceData(section.data)) {
        throw new Error('응답 데이터 형식이 예상과 다릅니다. 백엔드 구현을 확인하세요.')
      }
      carrierModel.value = {
        adria_arrival_ports: [...(section.data.adria_arrival_ports ?? [])],
        vessel_carrier_rules: (section.data.vessel_carrier_rules ?? []).map((rule) => ({
          keyword: rule.keyword,
          carrier_cd: rule.carrier_cd,
          carrier_nm: rule.carrier_nm,
        })),
        carrier_via_rules: (section.data.carrier_via_rules ?? []).map((rule) => ({
          carrier_cd: rule.carrier_cd,
          carrier_nm_contains: rule.carrier_nm_contains,
          via: rule.via,
        })),
      }
      break
    case 'location_master':
      if (!isLocationMasterData(section.data)) {
        throw new Error('응답 데이터 형식이 예상과 다릅니다. 백엔드 구현을 확인하세요.')
      }
      locationRows.value = Object.entries(section.data).map(([code, entry]) => ({
        code,
        name: entry.name,
        location_type: entry.location_type,
        lat: entry.lat,
        lon: entry.lon,
        default_radius_km: entry.default_radius_km,
        aliasesText: joinCsv(entry.aliases),
      }))
      break
    case 'route_groups':
      if (!isRouteGroupsData(section.data)) {
        throw new Error('응답 데이터 형식이 예상과 다릅니다. 백엔드 구현을 확인하세요.')
      }
      routeGroupRows.value = section.data.groups.map(toEditGroup)
      break
    default:
      throw new Error(`지원하지 않는 섹션 종류입니다: ${section.kind}`)
  }

  activeMeta.value = meta
  const catalogEntry = catalog.value.find((entry) => entry.key === meta.key)
  if (catalogEntry) {
    catalogEntry.source = meta.source
    catalogEntry.updated_at = meta.updated_at
  }
  snapshot.value = editJson.value
}

async function loadSection(key: string): Promise<void> {
  sectionLoading.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    applySection(await fetchConfigSection(key))
  } catch (error) {
    activeMeta.value = null
    errorMessage.value = errorText(error)
  } finally {
    sectionLoading.value = false
  }
}

async function selectSection(key: string): Promise<void> {
  if (key === activeMeta.value?.key) return
  if (
    isDirty.value
    && !window.confirm(
      '저장하지 않은 변경 사항이 있습니다. 다른 섹션으로 이동하면 변경 내용이 사라집니다. 계속하시겠습니까?',
    )
  ) {
    return
  }
  await loadSection(key)
}

function buildPayload(): unknown {
  const kind = activeMeta.value?.kind
  if (kind === 'thresholds') {
    return { ...(thresholdsModel.value ?? {}) }
  }
  if (kind === 'companies') {
    return {
      companies: companyRows.value
        .filter((row) => row.code.trim())
        .map((row) => ({
          code: row.code.trim(),
          label: row.label.trim(),
          lap_code: row.lap_code.trim(),
        })),
    }
  }
  if (kind === 'carrier_inference') {
    const model = carrierModel.value
    return {
      adria_arrival_ports: [...(model?.adria_arrival_ports ?? [])],
      vessel_carrier_rules: (model?.vessel_carrier_rules ?? [])
        .filter((rule) => rule.keyword.trim())
        .map((rule) => ({
          keyword: rule.keyword.trim(),
          carrier_cd: rule.carrier_cd.trim(),
          carrier_nm: rule.carrier_nm.trim(),
        })),
      carrier_via_rules: (model?.carrier_via_rules ?? [])
        .filter((rule) => rule.carrier_cd.trim())
        .map((rule) => ({
          carrier_cd: rule.carrier_cd.trim(),
          carrier_nm_contains: rule.carrier_nm_contains.trim(),
          via: rule.via,
        })),
    }
  }
  if (kind === 'location_master') {
    const data: Record<string, unknown> = {}
    for (const row of locationRows.value) {
      const code = row.code.trim()
      if (!code) continue
      data[code] = {
        name: row.name.trim(),
        location_type: row.location_type,
        lat: row.lat,
        lon: row.lon,
        default_radius_km: row.default_radius_km,
        aliases: splitCsv(row.aliasesText),
      }
    }
    return data
  }
  if (kind === 'route_groups') {
    const data: RouteGroupsData = {
      groups: routeGroupRows.value
        .filter((group) => group.group_id.trim())
        .map((group) => {
          const wire: RouteGroup = {
            group_id: group.group_id.trim(),
            region: group.region,
            name: group.name.trim(),
            arvl_codes: [...group.arvl_codes],
            stopby_match: [...group.stopby_match],
            stopby_exclude: [...group.stopby_exclude],
          }
          if (group.delay_target) wire.delay_target = true
          if (group.metric_inland) wire.metric = 'inland'
          if (group.row_label.trim()) wire.row_label = group.row_label.trim()
          if (group.rows.length) {
            wire.row_groups = group.rows.map((row) => {
              const wireRow: {
                row_id: string
                label: string
                field: string
                codes: string[]
                exclude_field?: string
                exclude_codes?: string[]
              } = {
                row_id: row.row_id.trim(),
                label: row.label.trim(),
                field: row.field.trim(),
                codes: splitCsv(row.codesText),
              }
              if (row.exclude_field.trim()) wireRow.exclude_field = row.exclude_field.trim()
              const excludeCodes = splitCsv(row.exclude_codesText)
              if (excludeCodes.length) wireRow.exclude_codes = excludeCodes
              return wireRow
            })
          }
          if (group.fixed_rows) wire.fixed_rows = group.fixed_rows
          return wire
        }),
    }
    return data
  }
  return null
}

async function save(): Promise<void> {
  const meta = activeMeta.value
  if (!meta) return
  saving.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    await saveConfigSection(meta.key, buildPayload())
    // 서버 정규화 결과와 source/updated_at 배지를 맞추기 위해 다시 조회
    applySection(await fetchConfigSection(meta.key))
    noticeMessage.value = '저장됐습니다. 각 화면은 다음 조회(새로고침/재집계)부터 반영됩니다.'
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    saving.value = false
  }
}

async function resetSection(): Promise<void> {
  const meta = activeMeta.value
  if (!meta) return
  if (
    !window.confirm(
      `'${meta.title}'을(를) 기본값으로 되돌리시겠습니까? 저장된 사용자 지정 값이 삭제됩니다.`,
    )
  ) {
    return
  }
  resetting.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    await resetConfigSection(meta.key)
    applySection(await fetchConfigSection(meta.key))
    noticeMessage.value = '기본값으로 되돌렸습니다. 각 화면은 다음 조회(새로고침/재집계)부터 반영됩니다.'
  } catch (error) {
    errorMessage.value = errorText(error)
  } finally {
    resetting.value = false
  }
}

async function loadCatalog(): Promise<void> {
  catalogLoading.value = true
  catalogError.value = ''
  try {
    const response = await fetchConfigCatalog()
    catalog.value = response.sections
  } catch (error) {
    catalogError.value = errorText(error)
  } finally {
    catalogLoading.value = false
  }
}

onMounted(loadCatalog)
</script>

<template>
  <div class="settings-panel">
    <aside class="settings-nav">
      <h3 class="nav-title">기준정보 섹션</h3>
      <p v-if="catalogLoading" class="nav-hint">목록 조회 중...</p>
      <p v-else-if="catalogError" class="nav-error">{{ catalogError }}</p>
      <template v-else>
        <button
          v-for="section in catalog"
          :key="section.key"
          type="button"
          class="nav-item"
          :class="{ active: section.key === activeMeta?.key }"
          @click="selectSection(section.key)"
        >
          <span class="nav-item-title">{{ section.title }}</span>
          <span
            class="source-badge"
            :class="section.source === 'custom' ? 'custom' : 'default'"
          >
            {{ section.source === 'custom' ? '사용자 지정' : '기본값' }}
          </span>
        </button>
      </template>
    </aside>

    <section class="settings-editor">
      <p v-if="!activeMeta && !sectionLoading && !errorMessage" class="empty-hint">
        좌측에서 편집할 섹션을 선택하세요. 섹션 데이터는 선택할 때만 조회됩니다.
      </p>
      <p v-if="sectionLoading" class="empty-hint">섹션 조회 중...</p>

      <template v-if="activeMeta">
        <header class="editor-header">
          <div class="editor-heading">
            <h3 class="editor-title">
              {{ activeMeta.title }}
              <span
                class="source-badge"
                :class="activeMeta.source === 'custom' ? 'custom' : 'default'"
              >
                {{ activeMeta.source === 'custom' ? '사용자 지정' : '기본값' }}
              </span>
            </h3>
            <p class="editor-meta">
              {{ activeMeta.key }} · 최종 수정 {{ activeMeta.updated_at || '-' }}
              <span v-if="isDirty" class="dirty-mark">저장되지 않은 변경 있음</span>
            </p>
          </div>
          <div class="editor-actions">
            <button
              type="button"
              class="action-secondary"
              :disabled="saving || resetting"
              @click="resetSection"
            >
              {{ resetting ? '되돌리는 중...' : '기본값으로 되돌리기' }}
            </button>
            <button
              type="button"
              class="action-primary"
              :disabled="saving || resetting || !isDirty"
              @click="save"
            >
              {{ saving ? '저장 중...' : '저장' }}
            </button>
          </div>
        </header>

        <p v-if="errorMessage" class="banner error">{{ errorMessage }}</p>
        <p v-if="noticeMessage" class="banner notice">{{ noticeMessage }}</p>

        <div class="editor-body">
          <ThresholdsEditor
            v-if="activeMeta.kind === 'thresholds' && thresholdsModel"
            :model="thresholdsModel"
          />
          <CompaniesEditor
            v-else-if="activeMeta.kind === 'companies'"
            :rows="companyRows"
          />
          <CarrierInferenceEditor
            v-else-if="activeMeta.kind === 'carrier_inference' && carrierModel"
            :model="carrierModel"
          />
          <LocationMasterEditor
            v-else-if="activeMeta.kind === 'location_master'"
            :rows="locationRows"
          />
          <RouteGroupsEditor
            v-else-if="activeMeta.kind === 'route_groups'"
            :groups="routeGroupRows"
          />
        </div>
      </template>
      <p v-else-if="errorMessage" class="banner error">{{ errorMessage }}</p>
    </section>
  </div>
</template>

<style scoped>
.settings-panel {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 14px;
  align-items: start;
  padding: 14px;
}
.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  background: var(--li-surface);
}
.nav-title {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--li-text-muted);
}
.nav-hint { margin: 0; font-size: 12px; color: var(--li-text-faint); }
.nav-error { margin: 0; font-size: 12px; color: var(--li-risk-critical); }
.nav-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  cursor: pointer;
  text-align: left;
}
.nav-item.active {
  border-color: var(--li-blue);
  background: var(--li-surface-blue);
}
.nav-item-title { font-size: 12px; color: var(--li-text); }
.source-badge {
  flex-shrink: 0;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 11px;
}
.source-badge.custom {
  background: var(--li-risk-low-bg);
  border: 1px solid var(--li-risk-low-border);
  color: var(--li-risk-low);
}
.source-badge.default {
  background: var(--li-bg-app-2);
  border: 1px solid var(--li-border);
  color: var(--li-text-muted);
}
.settings-editor {
  min-height: 320px;
  padding: 14px;
  border: 1px solid var(--li-border);
  border-radius: var(--li-radius-md);
  background: var(--li-surface);
}
.empty-hint { margin: 0; font-size: 12px; color: var(--li-text-faint); }
.editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.editor-title {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--li-text);
}
.editor-meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--li-text-faint);
}
.dirty-mark { margin-left: 8px; color: var(--li-risk-high); }
.editor-actions { display: flex; gap: 8px; flex-shrink: 0; }
.action-primary {
  padding: 7px 16px;
  border: 0;
  border-radius: var(--li-radius-sm);
  background: var(--li-blue);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}
.action-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.action-secondary {
  padding: 7px 12px;
  border: 1px solid var(--li-border-strong);
  border-radius: var(--li-radius-sm);
  background: var(--li-surface-strong);
  color: var(--li-text-soft);
  font-size: 12px;
  cursor: pointer;
}
.action-secondary:disabled { opacity: 0.45; cursor: not-allowed; }
.banner {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: var(--li-radius-sm);
  font-size: 12px;
}
.banner.error {
  background: var(--li-risk-critical-bg);
  border: 1px solid var(--li-risk-critical-border);
  color: var(--li-risk-critical);
}
.banner.notice {
  background: var(--li-risk-low-bg);
  border: 1px solid var(--li-risk-low-border);
  color: var(--li-risk-low);
}
.editor-body { margin-top: 4px; }
</style>
