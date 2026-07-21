// L2 수급 영향도 시뮬레이션 타입 (v2 백포트)

export type InventoryRiskLevel = 'OK' | 'WATCH' | 'SHORTAGE_RISK' | 'STOCKOUT'

export interface InventoryShipment {
  shipment_id: string
  vessel_name: string
  qty: number
  eta_plan: string
  eta_current: string
}

export interface InventoryItem {
  item_id: string
  name: string
  destination: string
  corridor: string
  pol: string
  unit: string
  daily_usage: number
  on_hand_units: number
  min_level_units: number
  shipments: InventoryShipment[]
  source?: 'blap' | 'sample'
  params_missing?: boolean
}

export interface InventoryItemsResponse {
  items: InventoryItem[]
}

export interface SimSeriesPoint {
  day: number
  date: string
  balance: number
}

export interface SimWindow {
  start: string
  end: string
  days: number
}

export interface SimMetrics {
  min_balance: number
  min_balance_date: string
  below_min_windows: SimWindow[]
  stockout_windows: SimWindow[]
  gap_qty: number
  max_delay_days: number
  risk_level: InventoryRiskLevel
}

export interface SimAction {
  type: string // AIR_UPGRADE | PULL_FORWARD_ORDER
  qty?: number
  days?: number
  text_ko: string
}

export interface SimulateResponse {
  item_id: string
  params: {
    extra_delay_days: number
    horizon_days: number
    today: string
    min_level_units: number
    unit: string
  }
  series_plan: SimSeriesPoint[]
  series_current: SimSeriesPoint[]
  metrics: SimMetrics
  actions: SimAction[]
  warning?: string
}
