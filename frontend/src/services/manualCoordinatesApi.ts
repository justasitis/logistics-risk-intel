export interface ManualCoordinateEntry {
  location_code: string
  location_name: string
  country_code: string
  company: string
  scope?: 'GLOBAL'
  latitude: number
  longitude: number
  note: string
  source: 'MANUAL'
  created_at: string
  updated_at: string
  updated_by: string
}

export interface ManualCoordinateInput {
  location_name?: string
  country_code?: string
  company?: string
  latitude: number
  longitude: number
  note?: string
  updated_by?: string
}

interface ManualCoordinateListResponse {
  scope?: 'GLOBAL'
  count: number
  items: ManualCoordinateEntry[]
}

async function apiError(
  response: Response,
  fallback: string,
): Promise<never> {
  const body = await response
    .json()
    .catch(() => null)

  const detail =
    body
    && typeof body === 'object'
    && 'detail' in body
      ? String(body.detail)
      : fallback

  throw new Error(detail)
}

export async function fetchManualCoordinates(
  companyOrSignal:
    | string
    | AbortSignal
    = '',
  signal?: AbortSignal,
): Promise<ManualCoordinateEntry[]> {
  // Step 9.13 호출부와의 하위 호환을 위해
  // company 인자는 받지만 좌표는 공통이므로 무시한다.
  const effectiveSignal =
    typeof companyOrSignal === 'string'
      ? signal
      : companyOrSignal

  const response = await fetch(
    '/api/coordinates/manual',
    { signal: effectiveSignal },
  )

  if (!response.ok) {
    return apiError(
      response,
      '수동 좌표 목록을 불러오지 못했습니다.',
    )
  }

  const result = (
    await response.json()
  ) as ManualCoordinateListResponse

  return Array.isArray(result.items)
    ? result.items
    : []
}

export async function saveManualCoordinate(
  locationCode: string,
  input: ManualCoordinateInput,
  signal?: AbortSignal,
): Promise<ManualCoordinateEntry> {
  const code = locationCode
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')

  const response = await fetch(
    `/api/coordinates/manual/${encodeURIComponent(code)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ...input,
        company: '',
      }),
      signal,
    },
  )

  if (!response.ok) {
    return apiError(
      response,
      '수동 좌표를 저장하지 못했습니다.',
    )
  }

  return response.json()
}

export async function deleteManualCoordinate(
  locationCode: string,
  companyOrSignal:
    | string
    | AbortSignal
    = '',
  signal?: AbortSignal,
): Promise<void> {
  const effectiveSignal =
    typeof companyOrSignal === 'string'
      ? signal
      : companyOrSignal

  const code = locationCode
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')

  const response = await fetch(
    `/api/coordinates/manual/${encodeURIComponent(code)}`,
    {
      method: 'DELETE',
      signal: effectiveSignal,
    },
  )

  if (!response.ok) {
    return apiError(
      response,
      '수동 좌표를 삭제하지 못했습니다.',
    )
  }
}
