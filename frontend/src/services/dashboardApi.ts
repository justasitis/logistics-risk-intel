import type {
  DashboardResponse,
  ScheduleTimelineResponse,
} from '@/types/dashboard'

export interface DashboardQuery {
  companies?: string[]
  etdDays?: number
  historyDays?: number
  recentWindowDays?: number
  maxInfoRows?: number
  maxEvents?: number
  maxMapRoutes?: number
  refresh?: boolean
}

function appendNumber(
  params: URLSearchParams,
  key: string,
  value: number | undefined,
) {
  if (value !== undefined) {
    params.append(key, String(value))
  }
}

export async function fetchDashboard(
  query: DashboardQuery = {},
  signal?: AbortSignal,
): Promise<DashboardResponse> {
  const params = new URLSearchParams()

  for (const company of query.companies ?? []) {
    params.append('company', company)
  }

  appendNumber(params, 'etd_days', query.etdDays ?? 365)
  appendNumber(params, 'history_days', query.historyDays ?? 180)
  appendNumber(
    params,
    'recent_window_days',
    query.recentWindowDays ?? 14,
  )
  appendNumber(params, 'max_info_rows', query.maxInfoRows ?? 5000)
  appendNumber(params, 'max_events', query.maxEvents ?? 200)
  appendNumber(params, 'max_map_routes', query.maxMapRoutes ?? 300)

  if (query.refresh) {
    params.append('refresh', 'true')
  }

  const response = await fetch(
    `/api/schedule/overview?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal,
    },
  )

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // JSON이 아니면 HTTP 상태 메시지를 사용한다.
    }

    throw new Error(detail)
  }

  return (await response.json()) as DashboardResponse
}

export interface ScheduleTimelineQuery {
  trprNo: string
  cmpyCd?: string | null
  plntCd?: string | null
  historyDays?: number
  includeNoChange?: boolean
}

export async function fetchScheduleTimeline(
  query: ScheduleTimelineQuery,
  signal?: AbortSignal,
): Promise<ScheduleTimelineResponse> {
  const params = new URLSearchParams({
    trpr_no: query.trprNo,
    history_days: String(query.historyDays ?? 1500),
  })

  if (query.cmpyCd) {
    params.append('cmpy_cd', query.cmpyCd)
  }

  if (query.plntCd) {
    params.append('plnt_cd', query.plntCd)
  }

  if (query.includeNoChange) {
    params.append('include_no_change', 'true')
  }

  const response = await fetch(
    `/api/schedule/timeline?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
      signal,
    },
  )

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // JSON 응답이 아니면 HTTP 상태를 사용한다.
    }

    throw new Error(detail)
  }

  return (await response.json()) as ScheduleTimelineResponse
}

