import type { RefinedMiEvent } from '@/types/mi'

export type MiExposureStatus =
  | 'IN_ZONE'
  | 'APPROACHING'
  | 'PASSED'
  | 'ROUTE_EXPOSED'

export interface MiTransportImpact {
  event_id: string
  transport_key: string
  trpr_no: string
  severity: RefinedMiEvent['severity']
  match_score: number
  match_methods: Array<'IMPACT_ZONE' | 'LANE'>
  exposure_status: MiExposureStatus
  distance_to_zone_km: number | null
  matched_location_codes: string[]
}

export interface MiImpactSummary {
  event_count: number
  mappable_event_count: number
  impacted_transport_count: number
  approaching_count: number
  in_zone_count: number
}

export interface MiImpactAnalysis {
  impacts: MiTransportImpact[]
  impactedRoutes: import('@/types/dashboard').GeoJsonFeatureCollection
  summary: MiImpactSummary
}
