import type {
  AisMapItem,
  ScheduleEvent,
  TransportRecord,
} from '@/types/dashboard'
import type { RefinedMiEvent } from '@/types/mi'
import type {
  MiExposureStatus,
  MiTransportImpact,
} from '@/types/miImpact'

export type CauseConfidenceBand = 'HIGH' | 'MEDIUM' | 'LOW'
export type CauseDecision = 'PENDING' | 'CONFIRMED' | 'EXCLUDED'

export type CauseTimeRelation =
  | 'OVERLAP'
  | 'NEAR'
  | 'BEFORE'
  | 'AFTER'
  | 'UNKNOWN'

export interface CauseScoreBreakdown {
  spatial: number
  temporal: number
  signal: number
  ais: number
  event_quality: number
}

export interface CauseCandidate {
  candidate_id: string
  schedule_event_id: string
  transport_key: string
  trpr_no: string
  schedule_headline: string
  schedule_severity: string
  schedule_detected_at: string
  actual_delay_days: number

  mi_event_id: string
  mi_headline: string
  mi_event_type: string
  mi_severity: RefinedMiEvent['severity']
  mi_status: RefinedMiEvent['status']
  mi_valid_from: string
  mi_valid_to: string | null

  total_score: number
  confidence_band: CauseConfidenceBand
  score_breakdown: CauseScoreBreakdown
  time_relation: CauseTimeRelation
  match_methods: MiTransportImpact['match_methods']
  exposure_status: MiExposureStatus
  distance_to_zone_km: number | null

  evidence: string[]
  recommended_actions: string[]
  decision: CauseDecision
}

export interface CauseAnalysisSummary {
  anomaly_event_count: number
  anomaly_transport_count: number
  candidate_count: number
  candidate_transport_count: number
  high_confidence_count: number
  medium_confidence_count: number
  no_candidate_transport_count: number
}

export interface CauseAnalysisResult {
  candidates: CauseCandidate[]
  summary: CauseAnalysisSummary
}

export interface CauseAnalysisInput {
  scheduleEvents: ScheduleEvent[]
  transports: TransportRecord[]
  miEvents: RefinedMiEvent[]
  miImpacts: MiTransportImpact[]
  aisItems: AisMapItem[]
}

export interface CauseDecisionRecord {
  decision: CauseDecision
  updated_at: string
}
