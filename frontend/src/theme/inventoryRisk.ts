import type { InventoryRiskLevel } from '../types/inventory'

// 재고 위험등급 색상 — riskTones.ts 팔레트(LOW/HIGH/MEDIUM/CRITICAL)와 동일 계열
export const INVENTORY_RISK_COLORS: Record<InventoryRiskLevel, string> = {
  OK: '#10b981',
  WATCH: '#eab308',
  SHORTAGE_RISK: '#f97316',
  STOCKOUT: '#ef4444',
}

export const INVENTORY_RISK_LABELS: Record<InventoryRiskLevel, string> = {
  OK: '정상',
  WATCH: '주의',
  SHORTAGE_RISK: '미니멈 하회 위험',
  STOCKOUT: '재고 소진 위험',
}
