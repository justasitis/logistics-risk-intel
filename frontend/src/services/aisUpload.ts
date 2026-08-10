import type {
  AisMapItem,
  AisPositionStatus,
  AisUploadResult,
  GeoJsonFeatureCollection,
  TransportRecord,
} from '@/types/dashboard'
import { canonicalVesselName } from '@/services/vesselMmsi'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const MAX_ITEMS = 5000

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function optionalText(value: unknown): string | null {
  const result = text(value)
  return result || null
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const result = Number(value)
  return Number.isFinite(result) ? result : null
}

function validCoordinate(
  latitude: number | null,
  longitude: number | null,
): boolean {
  return (
    latitude !== null
    && longitude !== null
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180
  )
}

function normalizeStatus(value: unknown): AisPositionStatus {
  const status = text(value).toUpperCase()
  if (status === 'LIVE') return 'LIVE'
  if (status === 'STALE') return 'STALE'
  if (status === 'NO_SIGNAL') return 'NO_SIGNAL'
  if (status === 'ERROR') return 'ERROR'
  return 'UNKNOWN'
}

function normalizedIdentifier(value: unknown): string {
  return text(value).toUpperCase().replace(/\s+/g, '')
}

function normalizedVesselName(value: unknown): string {
  // 매칭 전용 키: canonical(끝의 항차 토큰 제거) 후
  // 대문자·영숫자만 남긴다. 표시용 원문은 변경하지 않는다.
  return canonicalVesselName(value)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
}

function splitIdentifiers(value: unknown): string[] {
  return text(value)
    .split(/[,;|]/)
    .map((item) => normalizedIdentifier(item))
    .filter(Boolean)
}

function readRawItems(root: unknown): {
  generatedAt: string | null
  rows: unknown[]
} {
  if (Array.isArray(root)) {
    return { generatedAt: null, rows: root }
  }

  if (!root || typeof root !== 'object') {
    throw new Error('JSON 최상위 구조가 객체 또는 배열이 아닙니다.')
  }

  const objectRoot = root as Record<string, unknown>
  const rows = objectRoot.map_items

  if (!Array.isArray(rows)) {
    throw new Error('JSON에서 map_items 배열을 찾지 못했습니다.')
  }

  return {
    generatedAt: optionalText(objectRoot.generated_at),
    rows,
  }
}

function normalizeRawItem(
  raw: unknown,
  index: number,
  warnings: string[],
): AisMapItem | null {
  if (!raw || typeof raw !== 'object') {
    warnings.push(`${index + 1}번째 항목이 객체가 아니어서 제외했습니다.`)
    return null
  }

  const row = raw as Record<string, unknown>
  const latitude = finiteNumber(row.current_lat)
  const longitude = finiteNumber(row.current_lon)
  const shipmentId = text(row.shipment_id)
  const vesselName = text(row.vessel_name)
  const mmsiNo = optionalText(row.mmsi_no)
  const imoNo = optionalText(row.imo_no)
  const fallbackId = shipmentId || mmsiNo || imoNo || vesselName || `AIS-${index + 1}`
  const coordinateValid = validCoordinate(latitude, longitude)

  if ((latitude !== null || longitude !== null) && !coordinateValid) {
    warnings.push(
      `${fallbackId}: 위도/경도 범위를 벗어나 지도에서는 제외했습니다.`,
    )
  }

  return {
    ais_id: `${fallbackId}-${index}`,
    shipment_id: shipmentId,
    trpr_no: optionalText(row.trpr_no),
    hbl_no: optionalText(row.hbl_no),
    mbl_no: optionalText(row.mbl_no),
    vessel_name: vesselName || '(선명 없음)',
    mmsi_no: mmsiNo,
    imo_no: imoNo,
    call_sign: optionalText(row.call_sign),
    position_status: normalizeStatus(row.position_status),
    current_lat: coordinateValid ? latitude : null,
    current_lon: coordinateValid ? longitude : null,
    speed: finiteNumber(row.speed),
    heading: finiteNumber(row.heading),
    last_seen_at: optionalText(row.last_seen_at),
    next_port: optionalText(row.next_port),
    eta_ais: optionalText(row.eta_ais),
    source: optionalText(row.source),
    collected_at: optionalText(row.collected_at),
    error: optionalText(row.error),
    matched_transport_key: null,
    matched_trpr_no: null,
    match_method: null,
  }
}

export async function parseAisUploadFile(
  file: File,
): Promise<AisUploadResult> {
  if (file.size > MAX_FILE_SIZE) {
    throw new Error('AIS JSON 파일은 10MB 이하만 업로드할 수 있습니다.')
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(await file.text())
  } catch {
    throw new Error('올바른 JSON 파일이 아닙니다.')
  }

  const { generatedAt, rows } = readRawItems(parsed)
  if (rows.length > MAX_ITEMS) {
    throw new Error(`AIS 항목은 최대 ${MAX_ITEMS.toLocaleString()}건까지 지원합니다.`)
  }

  const warnings: string[] = []

  if (generatedAt) {
    const generatedTime = new Date(generatedAt).getTime()
    if (Number.isFinite(generatedTime)) {
      const ageHours = (Date.now() - generatedTime) / (1000 * 60 * 60)
      if (ageHours > 24) {
        const ageDays = Math.floor(ageHours / 24)
        warnings.push(
          `AIS 파일 생성 시각이 ${ageDays.toLocaleString()}일 전입니다. 현재 위치가 아닐 수 있습니다.`,
        )
      }
    }
  }

  const items = rows
    .map((row, index) => normalizeRawItem(row, index, warnings))
    .filter((item): item is AisMapItem => item !== null)

  if (items.length === 0) {
    throw new Error('사용 가능한 AIS 항목이 없습니다.')
  }

  return {
    generated_at: generatedAt,
    file_name: file.name,
    items,
    warnings,
    summary: summarizeAisItems(items),
  }
}

export function matchAisToTransports(
  sourceItems: AisMapItem[],
  transports: TransportRecord[],
): AisMapItem[] {
  const trprMap = new Map<string, TransportRecord>()
  const hblMap = new Map<string, TransportRecord>()
  const mblMap = new Map<string, TransportRecord>()
  const vesselMap = new Map<string, TransportRecord[]>()

  for (const transport of transports) {
    const trprNo = normalizedIdentifier(transport.trpr_no)
    if (trprNo) trprMap.set(trprNo, transport)

    for (const hbl of splitIdentifiers(transport.hbl_no)) {
      hblMap.set(hbl, transport)
    }
    for (const mbl of splitIdentifiers(transport.mbl_no)) {
      mblMap.set(mbl, transport)
    }

    const vesselKey = normalizedVesselName(transport.vessel_name)
    if (vesselKey) {
      const candidates = vesselMap.get(vesselKey) ?? []
      candidates.push(transport)
      vesselMap.set(vesselKey, candidates)
    }
  }

  return sourceItems.map((item) => {
    let match: TransportRecord | undefined
    let method: AisMapItem['match_method'] = null

    const directTrpr = normalizedIdentifier(item.trpr_no)
    const shipmentId = normalizedIdentifier(item.shipment_id)
    const hbl = normalizedIdentifier(item.hbl_no)
    const mbl = normalizedIdentifier(item.mbl_no)

    if (directTrpr && trprMap.has(directTrpr)) {
      match = trprMap.get(directTrpr)
      method = 'TRPR_NO'
    } else if (shipmentId && trprMap.has(shipmentId)) {
      match = trprMap.get(shipmentId)
      method = 'SHIPMENT_ID'
    } else if (hbl && hblMap.has(hbl)) {
      match = hblMap.get(hbl)
      method = 'HBL_NO'
    } else if (mbl && mblMap.has(mbl)) {
      match = mblMap.get(mbl)
      method = 'MBL_NO'
    } else {
      const vesselKey = normalizedVesselName(item.vessel_name)
      const vesselCandidates = vesselMap.get(vesselKey) ?? []
      if (vesselKey && vesselCandidates.length === 1) {
        match = vesselCandidates[0]
        method = 'VESSEL_NAME'
      }
    }

    return {
      ...item,
      matched_transport_key: match?.transport_key ?? null,
      matched_trpr_no: match?.trpr_no ?? null,
      match_method: match ? method : null,
    }
  })
}

export function summarizeAisItems(items: AisMapItem[]) {
  const mappable = items.filter(
    (item) => item.current_lat !== null && item.current_lon !== null,
  ).length
  const linked = items.filter((item) => item.matched_transport_key).length

  return {
    total: items.length,
    live: items.filter((item) => item.position_status === 'LIVE').length,
    stale: items.filter((item) => item.position_status === 'STALE').length,
    no_signal: items.filter(
      (item) => item.position_status === 'NO_SIGNAL',
    ).length,
    mappable,
    linked,
    unlinked: items.length - linked,
  }
}

export function buildAisGeoJson(
  items: AisMapItem[],
): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: items
      .filter(
        (item) => item.current_lat !== null && item.current_lon !== null,
      )
      .map((item) => ({
        type: 'Feature',
        id: item.ais_id,
        properties: {
          ...item,
          linked: Boolean(item.matched_transport_key),
        },
        geometry: {
          type: 'Point',
          coordinates: [item.current_lon, item.current_lat],
        },
      })),
  }
}
