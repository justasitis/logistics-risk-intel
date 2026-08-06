export interface DelayDecompositionGroupOption {
  group_id: string
  name: string
}

export interface DelayDecompositionHeadline {
  dep_delay_days: number | null
  voyage_delta_days: number | null
  cumulative_delay_days: number | null
  voyage_count: number
  total_count: number
  coverage: number
  coverage_warn: boolean
  first_record_gap_hours: number | null
  date_only: boolean
}

export interface DelayDecompositionVoyage {
  hbl_no: string
  vessel_nm: string
  voyage_no: string
  ata: string
  voyage_delta_days: number
}

export type DelayDecompositionVerdictTone =
  | 'ok'
  | 'steady'
  | 'hot'
  | 'warn'
  | 'hold'
  | 'neutral'

export interface DelayDecompositionCarrier {
  carrier_code: string
  carrier_name: string
  voyage_count: number
  total_count: number
  coverage: number
  coverage_warn: boolean
  p25: number | null
  p50: number | null
  p75: number | null
  p90: number | null
  iqr: number | null
  tail: number | null
  verdict: string
  verdict_tone: DelayDecompositionVerdictTone
  voyages: DelayDecompositionVoyage[]
}

export interface DelayDecompositionResponse {
  group_id: string
  group_name: string
  months: number
  available_groups: DelayDecompositionGroupOption[]
  headline: DelayDecompositionHeadline
  carriers: DelayDecompositionCarrier[]
  notes: string[]
}
