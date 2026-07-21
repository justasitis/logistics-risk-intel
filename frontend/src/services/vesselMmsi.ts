import type {
  AisMapItem,
  TransportRecord,
} from '@/types/dashboard'
import type {
  VesselInventoryInput,
  VesselInventoryResult,
  VesselMappingImportResult,
  VesselMmsiMapping,
  VesselMmsiSource,
  VesselUsageRow,
} from '@/types/vesselMmsi'

const INVALID_VESSEL_NAMES = new Set([
  '',
  '-',
  'NA',
  'N/A',
  'NONE',
  'NULL',
  'UNKNOWN',
  'UNKNOWN VESSEL',
  'TBA',
  'TBN',
  'TO BE ANNOUNCED',
  'TO BE NAMED',
  '미정',
  '선박미정',
  '선명미정',
])

interface VesselAccumulator {
  transportKeys: Set<string>
  trprNos: Set<string>
  companies: Set<string>
  lanes: Set<string>
  etds: string[]
  etas: string[]
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function uniqueSorted(values: Iterable<string>): string[] {
  return [...new Set(
    [...values].map((value) => value.trim()).filter(Boolean),
  )].sort((left, right) => left.localeCompare(right))
}

function isoTime(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : null
}

function earliestDate(values: string[]): string | null {
  let selected: string | null = null
  let selectedTime = Number.POSITIVE_INFINITY

  for (const value of values) {
    const time = isoTime(value)
    if (time === null || time >= selectedTime) continue
    selected = value
    selectedTime = time
  }

  return selected
}

function latestDate(values: string[]): string | null {
  let selected: string | null = null
  let selectedTime = Number.NEGATIVE_INFINITY

  for (const value of values) {
    const time = isoTime(value)
    if (time === null || time <= selectedTime) continue
    selected = value
    selectedTime = time
  }

  return selected
}

function laneLabel(transport: TransportRecord): string {
  const pol = text(transport.pol) || text(transport.pol_name)
  const pod = text(transport.pod) || text(transport.pod_name)

  if (!pol && !pod) return ''
  return `${pol || '?'}-${pod || '?'}`
}

/**
 * Legacy function name retained to avoid breaking imports.
 * It no longer normalizes. It only trims leading/trailing whitespace.
 */
export function normalizeVesselName(value: unknown): string {
  return text(value)
}

export function isUsableVesselName(value: unknown): boolean {
  const vesselName = text(value)
  if (vesselName.length < 2) return false

  return !INVALID_VESSEL_NAMES.has(
    vesselName.toUpperCase(),
  )
}

export function normalizeMmsi(value: unknown): string {
  return text(value).replace(/\D/g, '')
}

export function isValidMmsi(value: unknown): boolean {
  return /^\d{9}$/.test(normalizeMmsi(value))
}

export function createVesselMapping(
  vesselName: string,
  mmsiNo: string,
  source: VesselMmsiSource,
  notes = '',
): VesselMmsiMapping {
  const exactVesselName = text(vesselName)
  const normalizedMmsi = normalizeMmsi(mmsiNo)

  if (!isUsableVesselName(exactVesselName)) {
    throw new Error('유효한 선박명이 아닙니다.')
  }

  if (!isValidMmsi(normalizedMmsi)) {
    throw new Error('MMSI는 숫자 9자리여야 합니다.')
  }

  return {
    vessel_name: exactVesselName,
    normalized_vessel_name: exactVesselName,
    mmsi_no: normalizedMmsi,
    source,
    notes: text(notes),
    updated_at: new Date().toISOString(),
  }
}

function mappingIndex(
  mappings: VesselMmsiMapping[],
): Map<string, VesselMmsiMapping> {
  const result = new Map<string, VesselMmsiMapping>()

  for (const mapping of mappings) {
    const key = text(mapping.vessel_name)
    if (!key || !isValidMmsi(mapping.mmsi_no)) continue

    result.set(key, {
      ...mapping,
      vessel_name: key,
      normalized_vessel_name: key,
      mmsi_no: normalizeMmsi(mapping.mmsi_no),
    })
  }

  return result
}

function aisMmsiIndex(
  items: AisMapItem[],
): Map<string, string> {
  const result = new Map<string, string>()

  for (const item of items) {
    const key = text(item.vessel_name)
    const mmsi = normalizeMmsi(item.mmsi_no)

    if (!isUsableVesselName(key) || !isValidMmsi(mmsi)) {
      continue
    }

    result.set(key, mmsi)
  }

  return result
}

export function buildVesselInventory(
  input: VesselInventoryInput,
): VesselInventoryResult {
  const accumulators = new Map<string, VesselAccumulator>()
  let validVesselTransportCount = 0

  for (const transport of input.transports) {
    const vesselName = text(transport.vessel_name)
    if (!isUsableVesselName(vesselName)) continue

    validVesselTransportCount += 1

    const accumulator = accumulators.get(vesselName) ?? {
      transportKeys: new Set<string>(),
      trprNos: new Set<string>(),
      companies: new Set<string>(),
      lanes: new Set<string>(),
      etds: [],
      etas: [],
    }

    accumulator.transportKeys.add(transport.transport_key)

    if (transport.trpr_no) {
      accumulator.trprNos.add(transport.trpr_no)
    }
    if (transport.cmpy_cd) {
      accumulator.companies.add(transport.cmpy_cd)
    }

    const lane = laneLabel(transport)
    if (lane) accumulator.lanes.add(lane)

    if (transport.current_etd) {
      accumulator.etds.push(transport.current_etd)
    }
    if (transport.current_eta) {
      accumulator.etas.push(transport.current_eta)
    }

    accumulators.set(vesselName, accumulator)
  }

  const mappings = mappingIndex(input.mappings)
  const aisMmsi = aisMmsiIndex(input.aisItems ?? [])
  const rows: VesselUsageRow[] = []

  for (const [vesselName, accumulator] of accumulators.entries()) {
    const mapping = mappings.get(vesselName)
    const detectedMmsi = aisMmsi.get(vesselName)
    const mmsi = mapping?.mmsi_no ?? detectedMmsi ?? null

    rows.push({
      vessel_name: vesselName,
      normalized_vessel_name: vesselName,
      shipment_count: accumulator.transportKeys.size,
      transport_keys: uniqueSorted(accumulator.transportKeys),
      trpr_nos: uniqueSorted(accumulator.trprNos),
      companies: uniqueSorted(accumulator.companies),
      lanes: uniqueSorted(accumulator.lanes),
      earliest_etd: earliestDate(accumulator.etds),
      latest_eta: latestDate(accumulator.etas),
      mapped_mmsi_no: mmsi,
      mapping_source: mapping?.source ?? (
        detectedMmsi ? 'AIS_UPLOAD' : null
      ),
      status: mapping
        ? 'MAPPED'
        : detectedMmsi
          ? 'AIS_DETECTED'
          : 'MISSING',
    })
  }

  rows.sort((left, right) => {
    const statusRank = {
      MISSING: 0,
      AIS_DETECTED: 1,
      MAPPED: 2,
    } as const

    const rankDifference = (
      statusRank[left.status] - statusRank[right.status]
    )
    if (rankDifference !== 0) return rankDifference

    if (right.shipment_count !== left.shipment_count) {
      return right.shipment_count - left.shipment_count
    }

    return left.vessel_name.localeCompare(right.vessel_name)
  })

  const missingRows = rows.filter(
    (row) => row.status === 'MISSING',
  )

  return {
    rows,
    summary: {
      transport_count: input.transports.length,
      valid_vessel_transport_count: validVesselTransportCount,
      unique_vessel_count: rows.length,
      mapped_vessel_count: rows.filter(
        (row) => row.status === 'MAPPED',
      ).length,
      ais_detected_count: rows.filter(
        (row) => row.status === 'AIS_DETECTED',
      ).length,
      missing_vessel_count: missingRows.length,
      missing_shipment_count: missingRows.reduce(
        (sum, row) => sum + row.shipment_count,
        0,
      ),
    },
  }
}

function csvCell(value: unknown): string {
  const stringValue = text(value)

  if (!/[",\r\n]/.test(stringValue)) {
    return stringValue
  }

  return `"${stringValue.replace(/"/g, '""')}"`
}

function dateOnly(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toISOString().slice(0, 10)
}

export function vesselRowsToCsv(
  rows: VesselUsageRow[],
): string {
  const header = [
    'vessel_name',
    'vessel_name_key',
    'mmsi_no',
    'shipment_count',
    'companies',
    'lanes',
    'earliest_etd',
    'latest_eta',
    'notes',
  ]

  const lines = rows.map((row) => [
    row.vessel_name,
    row.vessel_name,
    row.mapped_mmsi_no ?? '',
    row.shipment_count,
    row.companies.join('|'),
    row.lanes.join('|'),
    dateOnly(row.earliest_etd),
    dateOnly(row.latest_eta),
    '',
  ].map(csvCell).join(','))

  return [header.join(','), ...lines].join('\r\n')
}

export function mappingsToJson(
  mappings: VesselMmsiMapping[],
): string {
  return JSON.stringify({
    schema_version: '1.1-exact-vessel-name',
    generated_at: new Date().toISOString(),
    matching_rule: 'EXACT_IF_VESSEL_NAME_TRIM_ONLY',
    mappings: [...mappings].sort(
      (left, right) => left.vessel_name.localeCompare(
        right.vessel_name,
      ),
    ),
  }, null, 2)
}

function parseCsvRows(content: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false

  for (let index = 0; index < content.length; index += 1) {
    const character = content[index] ?? ''
    const next = content[index + 1] ?? ''

    if (character === '"') {
      if (quoted && next === '"') {
        cell += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }

    if (character === ',' && !quoted) {
      row.push(cell)
      cell = ''
      continue
    }

    if (
      (character === '\n' || character === '\r')
      && !quoted
    ) {
      if (character === '\r' && next === '\n') {
        index += 1
      }

      row.push(cell)
      if (row.some((value) => value.trim())) {
        rows.push(row)
      }
      row = []
      cell = ''
      continue
    }

    cell += character
  }

  row.push(cell)
  if (row.some((value) => value.trim())) {
    rows.push(row)
  }

  return rows
}

function headerIndex(
  headers: string[],
  candidates: string[],
): number {
  const normalized = headers.map(
    (value) => value.trim().toLowerCase(),
  )

  for (const candidate of candidates) {
    const index = normalized.indexOf(candidate.toLowerCase())
    if (index >= 0) return index
  }

  return -1
}

function mappingFromObject(
  value: unknown,
  source: VesselMmsiSource,
): VesselMmsiMapping | null {
  if (!value || typeof value !== 'object') return null

  const row = value as Record<string, unknown>
  const vesselName = text(
    row.vessel_name
    ?? row.vesselName
    ?? row['선박명'],
  )
  const mmsi = normalizeMmsi(
    row.mmsi_no
    ?? row.mmsi
    ?? row.MMSI
    ?? row['MMSI No.'],
  )
  const notes = text(row.notes ?? row['비고'])

  if (!isUsableVesselName(vesselName) || !isValidMmsi(mmsi)) {
    return null
  }

  return createVesselMapping(
    vesselName,
    mmsi,
    source,
    notes,
  )
}

export async function parseVesselMappingFile(
  file: File,
): Promise<VesselMappingImportResult> {
  if (file.size > 5 * 1024 * 1024) {
    throw new Error('매핑 파일은 5MB 이하만 지원합니다.')
  }

  const warnings: string[] = []
  const content = (await file.text()).replace(/^\uFEFF/, '')
  const mappings: VesselMmsiMapping[] = []

  if (file.name.toLowerCase().endsWith('.json')) {
    let parsed: unknown

    try {
      parsed = JSON.parse(content)
    } catch {
      throw new Error('올바른 JSON 파일이 아닙니다.')
    }

    const rows = Array.isArray(parsed)
      ? parsed
      : (
        parsed
        && typeof parsed === 'object'
        && Array.isArray(
          (parsed as Record<string, unknown>).mappings,
        )
          ? (
            (parsed as Record<string, unknown>).mappings as unknown[]
          )
          : []
      )

    if (!Array.isArray(rows) || rows.length === 0) {
      throw new Error('JSON에서 mappings 배열을 찾지 못했습니다.')
    }

    rows.forEach((row, index) => {
      const mapping = mappingFromObject(row, 'JSON_IMPORT')
      if (mapping) mappings.push(mapping)
      else warnings.push(
        `${index + 1}번째 매핑은 선박명 또는 MMSI가 올바르지 않아 제외했습니다.`,
      )
    })
  } else {
    const rows = parseCsvRows(content)
    const headers = rows[0] ?? []

    const vesselIndex = headerIndex(
      headers,
      ['vessel_name', 'vesselname', '선박명'],
    )
    const mmsiIndex = headerIndex(
      headers,
      ['mmsi_no', 'mmsi', 'mmsi no.', 'mmsi번호'],
    )
    const notesIndex = headerIndex(
      headers,
      ['notes', '비고'],
    )

    if (vesselIndex < 0 || mmsiIndex < 0) {
      throw new Error(
        'CSV에 vessel_name과 mmsi_no 열이 필요합니다.',
      )
    }

    rows.slice(1).forEach((row, rowIndex) => {
      const vesselName = row[vesselIndex] ?? ''
      const mmsi = row[mmsiIndex] ?? ''
      const notes = notesIndex >= 0
        ? row[notesIndex] ?? ''
        : ''

      if (!text(mmsi)) return

      if (
        !isUsableVesselName(vesselName)
        || !isValidMmsi(mmsi)
      ) {
        warnings.push(
          `${rowIndex + 2}행은 선박명 또는 MMSI가 올바르지 않아 제외했습니다.`,
        )
        return
      }

      mappings.push(
        createVesselMapping(
          vesselName,
          mmsi,
          'CSV_IMPORT',
          notes,
        ),
      )
    })
  }

  if (mappings.length === 0) {
    throw new Error('가져올 수 있는 유효한 MMSI 매핑이 없습니다.')
  }

  const deduplicated = new Map<string, VesselMmsiMapping>()
  for (const mapping of mappings) {
    deduplicated.set(mapping.vessel_name, mapping)
  }

  return {
    mappings: [...deduplicated.values()],
    warnings,
  }
}

export function mappingsFromAisItems(
  items: AisMapItem[],
): VesselMmsiMapping[] {
  const result = new Map<string, VesselMmsiMapping>()

  for (const item of items) {
    if (
      !isUsableVesselName(item.vessel_name)
      || !isValidMmsi(item.mmsi_no)
    ) {
      continue
    }

    const mapping = createVesselMapping(
      item.vessel_name,
      item.mmsi_no ?? '',
      'AIS_UPLOAD',
    )
    result.set(mapping.vessel_name, mapping)
  }

  return [...result.values()]
}

export function downloadTextFile(
  fileName: string,
  content: string,
  mimeType: string,
  includeUtf8Bom = false,
): void {
  const blob = new Blob(
    [
      includeUtf8Bom ? '\uFEFF' : '',
      content,
    ],
    { type: `${mimeType};charset=utf-8` },
  )
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}
