export interface DashboardSummary {
  active_transports: number
  etd_repeated_delay: number
  eta_repeated_delay: number
  lead_time_anomaly: number
  high_critical: number
  anomaly_transports: number
}

export interface ScheduleEvent {
  event_id: string
  event_type: string
  primary_signal: string
  signals: string[]
  severity: string
  risk_score: number
  transport_key: string
  trpr_no: string
  hbl_no?: string | null
  pol?: string | null
  pol_name?: string | null
  pod?: string | null
  pod_name?: string | null
  vessel_name?: string | null
  voyage_no?: string | null
  etd_delay_count_recent?: number | null
  eta_delay_count_recent?: number | null
  etd_net_delay_days?: number | null
  eta_net_delay_days?: number | null
  planned_lead_time_days?: number | null
  projected_lead_time_days?: number | null
  lead_time_variance_days?: number | null
  delivery_req_breach_days?: number | null
  po_count?: number | null
  item_count?: number | null
  quantity_sum?: number | null
  quantity_unit?: string | null
  headline: string
  status: string
  detected_at: string
}

export interface TransportRecord {
  transport_key: string
  cmpy_cd?: string | null
  cmpy_nm?: string | null
  plnt_cd?: string | null
  trpr_no: string
  hbl_no?: string | null
  mbl_no?: string | null
  pol?: string | null
  pol_name?: string | null
  pod?: string | null
  pod_name?: string | null
  stopby?: string | null
  vessel_name?: string | null
  voyage_no?: string | null
  current_etd?: string | null
  current_eta?: string | null
  delivery_request_date?: string | null
  delivery_eta?: string | null
  delivery_req_breach_days?: number | null
  /** 공급업첪명 유니크 목록 — 최대 3개 + "외 N개" (없으면 빈 문자열) */
  sppl_names?: string
  /** 품목명 유니크 목록 — 최대 3개 + "외 N개" (없으면 빈 문자열) */
  item_names?: string
  /** 품목 코드 유니크 전체 목록 (정렬됨, 없으면 빈 배열) */
  item_cds?: string[]
  etd_initial?: string | null
  eta_initial?: string | null
  po_count?: number | null
  item_count?: number | null
  quantity_sum?: number | null
  quantity_unit?: string | null
  etd_delay_count_recent?: number | null
  eta_delay_count_recent?: number | null
  etd_net_delay_days?: number | null
  eta_net_delay_days?: number | null
  planned_lead_time_days?: number | null
  projected_lead_time_days?: number | null
  lead_time_variance_days?: number | null
  severity: string
  risk_score: number
  anomaly_signals: string[]
}

export interface GeoJsonFeatureCollection {
  type: 'FeatureCollection'
  features: Array<Record<string, unknown>>
}

export interface DashboardResponse {
  generated_at: string
  cache_hit: boolean
  filters: Record<string, unknown>
  source_counts: {
    info_rows: number
    active_transports: number
    history_rows: number
    map_routes: number
    missing_port_count: number
  }
  summary: DashboardSummary
  events: ScheduleEvent[]
  transports: TransportRecord[]
  map: {
    routes: GeoJsonFeatureCollection
    ports: GeoJsonFeatureCollection
    missing_ports: string[]
    route_count: number
  }
}

export interface TimelineEvent {
  history_no: string
  schedule_type: 'ETD' | 'ETA'
  previous_date: string | null
  revised_date: string | null
  change_days: number
  direction: 'DELAYED' | 'ADVANCED' | 'NO_CHANGE'
  changed_at: string | null
  changed_by: string
  is_actual_change: boolean
}

export interface TimelineTypeSummary {
  schedule_type: 'ETD' | 'ETA'
  initial_date: string | null
  current_date: string | null
  change_count: number
  delay_count: number
  advance_count: number
  gross_delay_days: number
  gross_advance_days: number
  net_change_days: number
  last_changed_at: string | null

  source_row_count?: number
  initial_record_count?: number

  events: TimelineEvent[]
}

export interface ScheduleTimelineResponse {
  generated_at: string
  transport_key: string
  header: {
    cmpy_cd: string
    cmpy_nm: string
    plnt_cd: string
    plnt_nm: string
    trpr_no: string
    hbl_no: string
    mbl_no: string
    pol: string
    pol_name: string
    pod: string
    pod_name: string
    vessel_name: string
    voyage_no: string
    current_etd: string | null
    current_eta: string | null
  }
  etd: TimelineTypeSummary
  eta: TimelineTypeSummary
  history_source_row_count?: number
  history_row_count: number
  include_no_change: boolean
}

export type AisPositionStatus =
  | 'LIVE'
  | 'STALE'
  | 'NO_SIGNAL'
  | 'ERROR'
  | 'UNKNOWN'

export interface AisMapItem {
  ais_id: string
  shipment_id: string
  trpr_no?: string | null
  hbl_no?: string | null
  mbl_no?: string | null
  vessel_name: string
  mmsi_no?: string | null
  imo_no?: string | null
  call_sign?: string | null
  position_status: AisPositionStatus
  current_lat: number | null
  current_lon: number | null
  speed: number | null
  heading: number | null
  last_seen_at?: string | null
  next_port?: string | null
  eta_ais?: string | null
  source?: string | null
  collected_at?: string | null
  error?: string | null
  matched_transport_key?: string | null
  matched_trpr_no?: string | null
  matched_hbl_no?: string | null
  linked?: boolean
  match_method?: 'TRPR_NO' | 'SHIPMENT_ID' | 'HBL_NO' | 'MBL_NO' | 'VESSEL_NAME' | null
}

export interface AisUploadSummary {
  total: number
  live: number
  stale: number
  no_signal: number
  mappable: number
  linked: number
  unlinked: number
}

export interface AisUploadResult {
  generated_at: string | null
  file_name: string
  items: AisMapItem[]
  summary: AisUploadSummary
  warnings: string[]
}

export type MiSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type MiStatus = 'ACTIVE' | 'WATCH' | 'IMPROVING' | 'RESOLVED'

export interface MiAffectedLocation {
  location_type:
    | 'CHOKEPOINT'
    | 'PORT'
    | 'SEA_AREA'
    | 'AIRPORT'
    | 'COUNTRY'
    | 'REGION'
  code: string
  name: string
  lat: number
  lon: number
  radius_km: number
}

export interface MiAffectedLane {
  pol_codes?: string[]
  pod_codes?: string[]
  origin_regions?: string[]
  destination_regions?: string[]
  corridor?: string | null
}

export interface MiEvidence {
  title: string
  url: string
  source: string
  published_at?: string | null
}

export interface MiEvent {
  event_id: string
  cluster_key: string
  source_type: 'EXTERNAL_MI' | 'INTERNAL_MI'
  status: MiStatus
  event_type: string
  severity: MiSeverity
  confidence: number
  headline: string
  summary: string
  first_seen_at: string
  last_updated_at: string
  valid_from: string
  valid_to?: string | null
  transport_modes: string[]
  affected_corridors: string[]
  affected_locations: MiAffectedLocation[]
  affected_lanes: MiAffectedLane[]
  expected_delay_days?: {
    min: number
    max: number
  } | null
  impact_types: string[]
  cause_keywords: string[]
  evidence: MiEvidence[]
}

export interface MiUploadResult {
  schema_version: string
  generated_at: string | null
  file_name: string
  events: MiEvent[]
  warnings: string[]
}

export type MiExposureStatus =
  | 'IN_ZONE'
  | 'APPROACHING'
  | 'PASSED'
  | 'ROUTE_EXPOSED'

export interface MiTransportImpact {
  event_id: string
  transport_key: string
  trpr_no: string
  severity: MiSeverity
  match_score: number
  match_methods: string[]
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

export interface MiCauseCandidate {
  event: MiEvent
  impact: MiTransportImpact
  cause_score: number
  reasons: string[]
}

