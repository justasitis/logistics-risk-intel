export type CompanyCode = 'SKO' | 'SKOH' | 'SKBM' | 'SKBA' | 'SKOJ' | 'SKOY'
export type ReviewStatus = 'PENDING' | 'APPROVED' | 'EDITED' | 'REJECTED'

export interface Evidence {
  article_id: string
  title: string
  url: string
  source: string
  published_at: string
}

export interface ExternalMiCandidate {
  candidate_id: string
  cluster_hint: string
  headline: string
  short_summary: string
  published_from: string
  valid_to_hint: string | null
  location_mentions: string[]
  corridor_mentions: string[]
  transport_mode_hints: string[]
  risk_keyword_hints: string[]
  evidence: Evidence[]
}

export interface ExternalMiCandidateEnvelope {
  schema_version: string
  generated_at: string
  source_stage: 'EXTERNAL_GEMINI_CANDIDATES'
  generation_status: string
  warnings: string[]
  input_summary: Record<string, unknown>
  candidates: ExternalMiCandidate[]
}

export interface AffectedLocation {
  code: string
  name: string
  location_type: string
  lat: number
  lon: number
  radius_km: number
}

export interface RefinedMiEvent {
  event_id: string
  source_type: string
  source_candidate_ids: string[]
  cluster_key: string
  status: 'ACTIVE' | 'WATCH' | 'IMPROVING' | 'RESOLVED'
  event_type: string
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  confidence: number
  headline: string
  summary: string
  first_seen_at: string
  last_updated_at: string
  valid_from: string
  valid_to: string | null
  transport_modes: string[]
  affected_corridors: string[]
  location_refs: Array<Record<string, unknown>>
  affected_locations: AffectedLocation[]
  unresolved_locations: Array<Record<string, unknown>>
  affected_lanes: Array<Record<string, unknown>>
  expected_delay_days: { min: number; max: number } | null
  impact_types: string[]
  cause_keywords: string[]
  recommended_actions: string[]
  evidence: Evidence[]
  review_status: ReviewStatus
}

export interface RefineResponse {
  analysis_id: string
  generated_at: string
  model_service: 'ACTIFY'
  source_candidate_count: number
  events: RefinedMiEvent[]
  warnings: string[]
}

export interface ReviewResponse {
  analysis_id: string
  approved_count: number
  rejected_count: number
  canonical_payload: {
    schema_version: string
    generated_at: string
    source_type: string
    analysis_id: string
    events: RefinedMiEvent[]
  }
}
