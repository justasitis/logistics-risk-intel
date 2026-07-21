export const logisticsMapColors = {
  routeSea: '#2563eb',
  routeAir: '#06b6d4',
  routeRail: '#14b8a6',
  routeRoad: '#64748b',
  zoneCriticalFill: 'rgba(239,68,68,.18)',
  zoneCriticalLine: 'rgba(239,68,68,.78)',
  zoneHighFill: 'rgba(249,115,22,.16)',
  zoneHighLine: 'rgba(249,115,22,.72)',
  zoneMediumFill: 'rgba(234,179,8,.14)',
  zoneMediumLine: 'rgba(234,179,8,.70)',
  zoneLowFill: 'rgba(16,185,129,.12)',
  zoneLowLine: 'rgba(16,185,129,.68)',
  aisLive: '#10b981',
  aisStale: '#f59e0b',
  aisNoSignal: '#94a3b8',
}

export const riskZonePaint = (severity?: string) => {
  const key = String(severity || 'LOW').toUpperCase()
  if (key === 'CRITICAL') return { fillColor: logisticsMapColors.zoneCriticalFill, lineColor: logisticsMapColors.zoneCriticalLine }
  if (key === 'HIGH') return { fillColor: logisticsMapColors.zoneHighFill, lineColor: logisticsMapColors.zoneHighLine }
  if (key === 'MEDIUM') return { fillColor: logisticsMapColors.zoneMediumFill, lineColor: logisticsMapColors.zoneMediumLine }
  return { fillColor: logisticsMapColors.zoneLowFill, lineColor: logisticsMapColors.zoneLowLine }
}

export const routeLineColor = (mode?: string) => {
  const key = String(mode || 'SEA').toUpperCase()
  if (key === 'AIR') return logisticsMapColors.routeAir
  if (key === 'RAIL') return logisticsMapColors.routeRail
  if (key === 'ROAD' || key === 'TRUCK') return logisticsMapColors.routeRoad
  return logisticsMapColors.routeSea
}
