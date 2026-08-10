import type {
  AisMapItem,
  AisUploadResult,
} from '@/types/dashboard'
import type { VesselMmsiMapping } from '@/types/vesselMmsi'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export interface MarinesiaAisItem extends AisMapItem {
  company: string
  query_mmsi_no?: string | null
  course?: number | null
  nav_status?: number | null
  position_accuracy?: boolean | null
  rate_of_turn?: number | null
  draught?: number | null
  freshness_hours?: number | null
  api_error?: boolean
  api_message?: string | null
}

export interface MarinesiaHealth {
  configured: boolean
  root: string
  root_exists: boolean
  latest_file_found: boolean
  latest_file: {
    path: string
    name: string
    size_bytes: number
    modified_at: string
  } | null
  default_company: string
  live_hours: number
  stale_warning_hours: number
}

export interface MarinesiaLatestResponse {
  source_type: 'MARINESIA_SHAREPOINT'
  source_root: string
  source_file: string
  source_file_name: string
  source_modified_at: string
  generated_at: string | null
  filters: {
    companies: string[]
  }
  items: MarinesiaAisItem[]
  summary: {
    total: number
    live: number
    stale: number
    no_signal: number
    error: number
    mappable: number
    linked: number
    unlinked: number
    companies: Record<string, number>
  }
  warnings: string[]
  ambiguous_vessels: Array<{
    company: string
    vessel_name: string
    mmsi_candidates: string[]
  }>
}

export interface MarinesiaSelectionResult {
  items: MarinesiaAisItem[]
  warnings: string[]
  mapped_count: number
  automatic_count: number
  ambiguous_count: number
}

async function parseResponse<T>(
  response: Response,
): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>
  }

  let message = `${response.status} ${response.statusText}`

  try {
    const payload = await response.json() as {
      detail?: string
    }
    message = payload.detail || message
  } catch {
    // Keep the HTTP status.
  }

  throw new Error(message)
}

export async function fetchMarinesiaHealth(
  signal?: AbortSignal,
): Promise<MarinesiaHealth> {
  return parseResponse(
    await fetch(
      `${API_BASE}/api/marinesia/health`,
      { signal },
    ),
  )
}

// 신규 AIS 포맷에는 company가 없다 — 법인 구분 없이 전체 조회
export async function fetchMarinesiaLatest(
  signal?: AbortSignal,
): Promise<MarinesiaLatestResponse> {
  return parseResponse(
    await fetch(
      `${API_BASE}/api/marinesia/latest`,
      { signal },
    ),
  )
}

function exactName(value: unknown): string {
  return String(value ?? '').trim()
}

function mmsi(value: unknown): string {
  return String(value ?? '').replace(/\D/g, '')
}

function latestItem(
  items: MarinesiaAisItem[],
): MarinesiaAisItem {
  return [...items].sort((left, right) => {
    const leftTime = new Date(
      left.collected_at || left.last_seen_at || 0,
    ).getTime()
    const rightTime = new Date(
      right.collected_at || right.last_seen_at || 0,
    ).getTime()

    return rightTime - leftTime
  })[0] as MarinesiaAisItem
}

export function selectMarinesiaByMmsiMaster(
  sourceItems: MarinesiaAisItem[],
  mappings: VesselMmsiMapping[],
): MarinesiaSelectionResult {
  const mappingByName = new Map(
    mappings.map((mapping) => [
      exactName(mapping.vessel_name),
      mmsi(mapping.mmsi_no),
    ]),
  )

  const groups = new Map<string, MarinesiaAisItem[]>()

  for (const item of sourceItems) {
    const key = `${item.company}|${exactName(item.vessel_name)}`
    const values = groups.get(key) ?? []
    values.push(item)
    groups.set(key, values)
  }

  const selected: MarinesiaAisItem[] = []
  const warnings: string[] = []
  let mappedCount = 0
  let automaticCount = 0
  let ambiguousCount = 0

  for (const values of groups.values()) {
    const sample = values[0]
    if (!sample) continue

    const vesselName = exactName(sample.vessel_name)
    const mappedMmsi = mappingByName.get(vesselName)

    if (mappedMmsi) {
      const matches = values.filter((item) => (
        mmsi(item.query_mmsi_no) === mappedMmsi
        || mmsi(item.mmsi_no) === mappedMmsi
      ))

      if (matches.length) {
        selected.push(latestItem(matches))
        mappedCount += 1
      } else {
        warnings.push(
          `${vesselName}: MMSI Master ${mappedMmsi}와 `
          + 'SharePoint AIS 후보가 일치하지 않습니다.',
        )
      }
      continue
    }

    const successful = values.filter((item) => (
      !item.api_error
      && mmsi(item.mmsi_no).length === 9
    ))

    const successfulMmsi = new Set(
      successful.map((item) => mmsi(item.mmsi_no)),
    )

    if (successfulMmsi.size === 1 && successful.length) {
      selected.push(latestItem(successful))
      automaticCount += 1
      warnings.push(
        `${vesselName}: MMSI Master 미등록 상태에서 `
        + `${[...successfulMmsi][0]}을 임시 후보로 사용했습니다.`,
      )
      continue
    }

    if (successfulMmsi.size > 1) {
      ambiguousCount += 1
      warnings.push(
        `${vesselName}: 성공한 MMSI 후보가 여러 개여서 `
        + '지도에서 제외했습니다.',
      )
      continue
    }

    // Keep one failed/no-signal record for operational visibility.
    selected.push(latestItem(values))
  }

  return {
    items: selected,
    warnings,
    mapped_count: mappedCount,
    automatic_count: automaticCount,
    ambiguous_count: ambiguousCount,
  }
}

export function toAisUploadResult(
  response: MarinesiaLatestResponse,
  selection: MarinesiaSelectionResult,
): AisUploadResult {
  return {
    generated_at: response.generated_at,
    file_name: response.source_file_name,
    items: selection.items,
    summary: {
      total: selection.items.length,
      live: selection.items.filter(
        (item) => item.position_status === 'LIVE',
      ).length,
      stale: selection.items.filter(
        (item) => item.position_status === 'STALE',
      ).length,
      no_signal: selection.items.filter(
        (item) => (
          item.position_status === 'NO_SIGNAL'
          || item.position_status === 'ERROR'
        ),
      ).length,
      mappable: selection.items.filter(
        (item) => (
          item.current_lat !== null
          && item.current_lon !== null
        ),
      ).length,
      linked: 0,
      unlinked: selection.items.length,
    },
    warnings: [
      ...response.warnings,
      ...selection.warnings,
    ],
  }
}
