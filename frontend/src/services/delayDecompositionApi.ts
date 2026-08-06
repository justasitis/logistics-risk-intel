import type { DelayDecompositionResponse } from '../types/delayDecomposition'

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

export async function getDelayDecomposition(params: {
  group_id?: string
  months: number
}): Promise<DelayDecompositionResponse> {
  const query = new URLSearchParams()
  if (params.group_id) query.set('group_id', params.group_id)
  query.set('months', String(params.months))
  return parseResponse(
    await fetch(`${API_BASE}/api/anomaly/delay-decomposition?${query.toString()}`),
  )
}
