import type {
  InsightDraft,
  InsightDraftResponse,
  LeadtimeReport,
  ReportSnapshot,
  ReportSnapshotResponse,
} from '../types/leadtime'

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

// 게시본(스냅샷) — 조회는 전원, 게시는 지정 사용자만(서버가 username 검사)
export async function getReportSnapshot(): Promise<ReportSnapshotResponse> {
  return parseResponse(await fetch(`${API_BASE}/api/report/snapshot`))
}

export async function publishReportSnapshot(): Promise<ReportSnapshot> {
  return parseResponse(
    await fetch(`${API_BASE}/api/report/snapshot/publish`, { method: 'POST' }),
  )
}

export async function postInsightDraft(
  month: string,
  includeLeadtime: boolean,
  regenerate: boolean,
): Promise<InsightDraftResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/report/insight-draft`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        month,
        include_leadtime: includeLeadtime,
        regenerate,
      }),
    }),
  )
}

export async function getInsightDraft(month: string): Promise<InsightDraftResponse | null> {
  const response = await fetch(
    `${API_BASE}/api/report/insight-draft/${encodeURIComponent(month)}`,
  )
  if (response.status === 404) return null
  return parseResponse(response)
}

export async function putInsightDraft(
  month: string,
  draft: InsightDraft,
): Promise<InsightDraftResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/report/insight-draft/${encodeURIComponent(month)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft }),
    }),
  )
}

export async function putLeadtimeOverrides(
  overrides: Record<string, number>,
): Promise<void> {
  await parseResponse(
    await fetch(`${API_BASE}/api/report/leadtime/overrides`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ overrides }),
    }),
  )
}

export async function deleteLeadtimeOverrides(): Promise<void> {
  await parseResponse(
    await fetch(`${API_BASE}/api/report/leadtime/overrides`, { method: 'DELETE' }),
  )
}
