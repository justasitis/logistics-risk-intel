import type {
  FreightIndicesResponse,
  RouteMasterResponse,
} from '../types/routeMaster'

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

export async function getFreightIndices(): Promise<FreightIndicesResponse | null> {
  const response = await fetch(`${API_BASE}/api/report/freight-indices`)
  if (response.status === 404) return null // 운임지수 파일 없음 — 조용히 처리
  return parseResponse(response)
}

export async function getRouteMaster(params: {
  companies: string[]
  dims: string[]
  etdDays?: number
  etdFrom?: string
  etdTo?: string
}): Promise<RouteMasterResponse> {
  const query = new URLSearchParams()
  if (params.companies.length) query.set('companies', params.companies.join(','))
  if (params.dims.length) query.set('dims', params.dims.join(','))
  // 백엔드가 from/to를 지원하면 사용, 미지원 시 etd_days로 폴�(기간 일수)
  if (params.etdFrom) query.set('etd_from', params.etdFrom)
  if (params.etdTo) query.set('etd_to', params.etdTo)
  query.set('etd_days', String(params.etdDays ?? 365))
  return parseResponse(
    await fetch(`${API_BASE}/api/routes/master?${query.toString()}`),
  )
}
