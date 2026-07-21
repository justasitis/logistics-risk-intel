import type {
  GeoJsonFeatureCollection,
  TransportRecord,
} from '@/types/dashboard'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export interface StopbyRouteSummary {
  total: number
  generated: number
  preserved: number
  errors: number
  explicit_stopby: number
  europe_default_stopby: number
  default_europe_passage: string
  cache: {
    hits: number
    misses: number
    current_size: number
  }
}

export interface StopbyRouteResponse {
  routes: GeoJsonFeatureCollection
  summary: StopbyRouteSummary
  warnings: string[]
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

export async function buildStopbyRoutes(
  routes: GeoJsonFeatureCollection,
  transports: TransportRecord[],
  signal?: AbortSignal,
): Promise<StopbyRouteResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/routes/stopby`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        routes,
        transports,
      }),
      signal,
    }),
  )
}
