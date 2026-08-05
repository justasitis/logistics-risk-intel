// ETA-ATA Gap 주차별 집계 타입
export interface GapWeek {
  week: string // 2026-W31
  avg_gap?: number
  count: number
  delayed_count?: number
  delayed_ratio?: number
}

export type GapLevel = 'OK' | 'WATCH' | 'WARN'

export interface GapGroupSummary {
  group_id: string
  name: string
  region: string
  weekly: GapWeek[]
  latest_avg_gap: number | null
  consecutive_increases: number
  slope_per_week: number
  level: GapLevel
  level_reasons: string[]
}

export interface GapOverall {
  weekly: GapWeek[]
  latest_avg_gap: number | null
  consecutive_increases: number
  slope_per_week: number
  level: GapLevel
  level_reasons: string[]
}

export interface EtaAtaGapResponse {
  generated_at: string
  params: {
    weeks: number
    warn_days: number
    watch_consecutive: number
    current_week: string
  }
  definitions: Record<string, string>
  overall: GapOverall
  groups: GapGroupSummary[]
}
