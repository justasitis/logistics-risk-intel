import type { LeadtimeReport } from '../types/leadtime'

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

export async function getLeadtimeReport(
  months = 12,
  forecastMonths = 3,
): Promise<LeadtimeReport> {
  return parseResponse(
    await fetch(
      `${API_BASE}/api/report/leadtime?months=${months}&forecast_months=${forecastMonths}`,
    ),
  )
}
