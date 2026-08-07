// 기준정보 관리(/api/config) 섹션별 데이터 타입과 타입 가드
// 서버 응답 data는 unknown으로 받고, 아래 가드로 좁혀서만 사용한다.

export type ConfigKind =
  | 'route_groups'
  | 'location_master'
  | 'thresholds'
  | 'companies'
  | 'carrier_inference'

export type ConfigSource = 'custom' | 'default'

export interface ConfigSectionMeta {
  key: string
  title: string
  kind: ConfigKind
  source: ConfigSource
  updated_at: string
}

export interface ConfigCatalog {
  sections: ConfigSectionMeta[]
}

export interface ConfigSection extends ConfigSectionMeta {
  data: unknown
}

// --- route_groups ---
export interface RouteGroupRow {
  row_id: string
  label: string
  field: string
  codes: string[]
  exclude_field?: string
  exclude_codes?: string[]
}

export interface RouteGroup {
  group_id: string
  region: string
  name: string
  arvl_codes: string[]
  stopby_match: string[]
  stopby_exclude: string[]
  delay_target?: boolean
  metric?: string
  row_label?: string
  row_groups?: RouteGroupRow[]
  fixed_rows?: unknown[]
}

export interface RouteGroupsData {
  groups: RouteGroup[]
}

// --- location_master ---
export interface LocationMasterEntry {
  name: string
  location_type: string
  lat: number
  lon: number
  default_radius_km: number
  aliases: string[]
}

export type LocationMasterData = Record<string, LocationMasterEntry>

// --- thresholds (delay/gap/anomaly 공통: 평면 숫자 객체) ---
export type ThresholdsData = Record<string, number>

// --- companies ---
export interface CompanyEntry {
  code: string
  label: string
  lap_code: string
}

export interface CompaniesData {
  companies: CompanyEntry[]
}

// --- carrier_inference ---
export interface VesselCarrierRule {
  keyword: string
  carrier_cd: string
  carrier_nm: string
}

export interface CarrierViaRule {
  carrier_cd: string
  carrier_nm_contains: string
  via: string
}

export interface CarrierInferenceData {
  adria_arrival_ports: string[]
  vessel_carrier_rules: VesselCarrierRule[]
  carrier_via_rules: CarrierViaRule[]
}

// --- 타입 가드 ---
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

export function isRouteGroupsData(value: unknown): value is RouteGroupsData {
  if (!isRecord(value) || !Array.isArray(value.groups)) return false
  return value.groups.every((group: unknown) => {
    if (!isRecord(group)) return false
    return (
      typeof group.group_id === 'string'
      && typeof group.name === 'string'
      && isStringArray(group.arvl_codes ?? [])
      && isStringArray(group.stopby_match ?? [])
      && isStringArray(group.stopby_exclude ?? [])
    )
  })
}

export function isLocationMasterData(value: unknown): value is LocationMasterData {
  if (!isRecord(value)) return false
  return Object.values(value).every((entry) => {
    if (!isRecord(entry)) return false
    return (
      typeof entry.name === 'string'
      && typeof entry.location_type === 'string'
      && typeof entry.lat === 'number'
      && typeof entry.lon === 'number'
      && typeof entry.default_radius_km === 'number'
      && isStringArray(entry.aliases ?? [])
    )
  })
}

export function isThresholdsData(value: unknown): value is ThresholdsData {
  if (!isRecord(value)) return false
  return Object.values(value).every((item) => typeof item === 'number')
}

export function isCompaniesData(value: unknown): value is CompaniesData {
  if (!isRecord(value) || !Array.isArray(value.companies)) return false
  return value.companies.every((company: unknown) => {
    if (!isRecord(company)) return false
    return (
      typeof company.code === 'string'
      && typeof company.label === 'string'
      && typeof company.lap_code === 'string'
    )
  })
}

export function isCarrierInferenceData(value: unknown): value is CarrierInferenceData {
  if (!isRecord(value)) return false
  if (!isStringArray(value.adria_arrival_ports ?? [])) return false
  if (!Array.isArray(value.vessel_carrier_rules ?? [])) return false
  if (!Array.isArray(value.carrier_via_rules ?? [])) return false
  return true
}

// --- SettingsPanel 편집 폼 전용 shape (저장 시 wire 형식으로 변환) ---
export interface LocationMasterEditRow {
  code: string
  name: string
  location_type: string
  lat: number
  lon: number
  default_radius_km: number
  aliasesText: string
}

export interface RouteGroupEditRow {
  row_id: string
  label: string
  field: string
  codesText: string
  exclude_field: string
  exclude_codesText: string
}

export interface RouteGroupEdit {
  group_id: string
  isNew: boolean
  name: string
  region: string
  arvl_codes: string[]
  stopby_match: string[]
  stopby_exclude: string[]
  delay_target: boolean
  metric_inland: boolean
  row_label: string
  fixed_rows?: unknown[]
  rows: RouteGroupEditRow[]
}
