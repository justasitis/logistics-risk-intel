// MI 이벤트 레지스트리 타입

export type RegistryStatus = 'ACTIVE' | 'IMPROVING' | 'RESOLVED'

export interface RegistryEvent {
  event_id: string
  status: RegistryStatus
  first_seen: string
  last_seen: string
  sighting_count: number
  sighting_dates: string[]
  headline: string
  summary: string
  severity: string
  locations: string[]
  corridors: string[]
  keywords: string[]
  source_candidate_ids: string[]
  evidence: Array<Record<string, unknown>>
  reactivated: boolean
}

export interface RegistryResponse {
  reference_date: string | null
  events: RegistryEvent[]
}

export interface RegistryRebuildResponse {
  files_processed: number
  reference_date: string | null
  event_count: number
  registry_file: string
}

export interface RegistryReviewProposal {
  event_id: string
  suggested_status: string
  suggested_severity: string
  merge_with: string | null
  reason: string
}

export interface RegistryReviewResponse {
  reviews: RegistryReviewProposal[]
  notes: string
}
