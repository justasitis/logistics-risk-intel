// 시황(운임지수) + 경로 마스터 타입

export interface FreightPoint {
  date: string
  value: number
}

export interface FreightSeries {
  key: string
  label: string
  points: FreightPoint[]
}

export interface FreightIndicesResponse {
  series: FreightSeries[]
}

export interface RouteMasterRow {
  cmpy_nm?: string
  plnt_nm?: string
  lsp_nm?: string
  bsns_ccd_nm?: string
  trpr_mode?: string
  dprt: string
  dprt_nm: string
  arvl: string
  arvl_nm: string
  to_stlc_cd: string
  to_stlc_nm: string
  shipment_count: number
  trpr_mode_label?: string
}

export interface RouteMasterResponse {
  total_rows: number
  truncated: boolean
  rows: RouteMasterRow[]
}
