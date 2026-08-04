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
  fixed?: boolean
  fixed_note?: string
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
  edited_cells?: string[]
  cache_hit?: boolean
}

// 월간 인사이트 초안 (Actify)
export interface InsightSection {
  key: string
  title: string
  body: string
}

export interface InsightDraft {
  key_changes: string[]
  sections: InsightSection[]
  monitoring_points: string[]
  disclaimer: string
}

export interface InsightDraftResponse {
  draft: InsightDraft
  materials_summary: {
    events_used: number
    leadtime_used: boolean
    summary_used: boolean
  }
  month: string
  generated_at: string
  draft_id?: string
  regenerated?: boolean
  revised_at?: string
}
