import type {
  AisMapItem,
  TransportRecord,
} from '@/types/dashboard'

export type VesselMmsiSource =
  | 'MANUAL'
  | 'CSV_IMPORT'
  | 'JSON_IMPORT'
  | 'AIS_UPLOAD'

export type VesselMmsiStatus =
  | 'MAPPED'
  | 'AIS_DETECTED'
  | 'MISSING'

export interface VesselMmsiMapping {
  vessel_name: string
  /**
   * Compatibility field.
   * This is NOT normalized. It equals the trimmed IF vessel_name exactly.
   */
  normalized_vessel_name: string
  mmsi_no: string
  source: VesselMmsiSource
  notes: string
  updated_at: string
}

export interface VesselUsageRow {
  vessel_name: string
  /**
   * Exact IF vessel-name key after leading/trailing trim only.
   */
  normalized_vessel_name: string
  shipment_count: number
  transport_keys: string[]
  trpr_nos: string[]
  companies: string[]
  lanes: string[]
  earliest_etd: string | null
  latest_eta: string | null
  mapped_mmsi_no: string | null
  mapping_source: VesselMmsiSource | null
  status: VesselMmsiStatus
}

export interface VesselInventorySummary {
  transport_count: number
  valid_vessel_transport_count: number
  unique_vessel_count: number
  mapped_vessel_count: number
  ais_detected_count: number
  missing_vessel_count: number
  missing_shipment_count: number
}

export interface VesselInventoryResult {
  rows: VesselUsageRow[]
  summary: VesselInventorySummary
}

export interface VesselInventoryInput {
  transports: TransportRecord[]
  mappings: VesselMmsiMapping[]
  aisItems?: AisMapItem[]
}

export interface VesselMappingImportResult {
  mappings: VesselMmsiMapping[]
  warnings: string[]
}
