import type {
  RegistryRebuildResponse,
  RegistryResponse,
  RegistryReviewResponse,
} from '../types/miRegistry'
import type { RegistryMapZone } from './miUpload'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // Ignore JSON parsing failure and keep HTTP status.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export async function getMiRegistry(status?: string): Promise<RegistryResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return parseResponse(await fetch(`${API_BASE}/api/mi/registry${query}`))
}

export async function rebuildMiRegistry(): Promise<RegistryRebuildResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi/registry/rebuild`, { method: 'POST' }),
  )
}

/** 승인 MI 이벤트 영향권 — 레지스트리 zone 형식 + 승인 이벤트의 유효 기간 */
export type ApprovedMapZone = RegistryMapZone & {
  valid_from: string
  valid_to: string | null
  /** 대표 기사 URL (없으면 빈 문자열) */
  article_url?: string
}

export async function getApprovedMapZones(): Promise<ApprovedMapZone[]> {
  return parseResponse(await fetch(`${API_BASE}/api/mi/approved/map-zones`))
}

export async function getRegistryMapZones(): Promise<RegistryMapZone[]> {
  return parseResponse(await fetch(`${API_BASE}/api/mi/registry/map-zones`))
}

export async function postRegistryReview(): Promise<RegistryReviewResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi/registry/review`, { method: 'POST' }),
  )
}

export async function postRegistryApply(body: {
  event_id: string
  suggested_status?: string
  suggested_severity?: string
  merge_with?: string | null
}): Promise<unknown> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi/registry/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}
