export type RiskSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'WATCH' | string

export const riskToneClass = (severity?: RiskSeverity): string => {
  const key = String(severity || 'WATCH').toUpperCase()
  if (key === 'CRITICAL') return 'risk-badge--critical'
  if (key === 'HIGH') return 'risk-badge--high'
  if (key === 'MEDIUM') return 'risk-badge--medium'
  if (key === 'LOW') return 'risk-badge--low'
  return 'risk-badge--watch'
}

export const eventCardToneClass = (severity?: RiskSeverity): string => {
  const key = String(severity || 'WATCH').toUpperCase()
  if (key === 'CRITICAL') return 'event-card--critical'
  if (key === 'HIGH') return 'event-card--high'
  return ''
}

export const riskLabel = (severity?: RiskSeverity): string => {
  const key = String(severity || 'WATCH').toUpperCase()
  const labels: Record<string, string> = { CRITICAL: '긴급', HIGH: '높음', MEDIUM: '주의', LOW: '낮음', WATCH: '관찰' }
  return labels[key] || key
}

export const riskDotColor = (severity?: RiskSeverity): string => {
  const key = String(severity || 'WATCH').toUpperCase()
  const colors: Record<string, string> = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308', LOW: '#10b981', WATCH: '#06b6d4' }
  return colors[key] || colors.WATCH
}
