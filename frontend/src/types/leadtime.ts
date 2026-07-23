// 항로별 리드타임 리포트 타입

export interface LeadtimeMonthColumn {
  key: string // YYYY-MM
  label: string // Oct. 등
  kind: 'actual' | 'forecast' | string
}

export interface LeadtimeRow {
  country: string
  country_label: string
  stat: string // Avg | Min | Max
  cells: Record<string, number>
}

export interface LeadtimeGroup {
  group_id: string
  name: string
  rows: LeadtimeRow[]
}

export interface LeadtimeReport {
  generated_at: string
  source: string
  definitions: Record<string, string>
  month_columns: LeadtimeMonthColumn[]
  groups: LeadtimeGroup[]
  cache_hit?: boolean
}
