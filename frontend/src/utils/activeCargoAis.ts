import type {
  AisMapItem,
  TransportRecord,
} from '@/types/dashboard'

export interface ActiveCargoAisOptions {
  /**
   * 실제 ATD가 Frontend Transport에 존재할 때만 true로 설정한다.
   * 현재 Overview 응답에 ATD가 없으면 false를 사용한다.
   */
  requireActualDeparture?: boolean

  /**
   * requireActualDeparture=false일 때 ETD가 현재보다
   * 몇 일 이전이어야 출항으로 간주할지 결정한다.
   */
  scheduledDepartureGraceDays?: number

  /**
   * 오래된 미완료 B-LAP Transport가 현재 AIS에
   * 재연결되지 않도록 하는 최대 항해일.
   */
  maxVoyageDays?: number

  /**
   * ETA가 오래 지났는데 ATA가 없는 데이터 허용 기간.
   */
  etaOverdueGraceDays?: number

  now?: Date
}

export interface TransportActivity {
  active: boolean
  reason:
    | 'ACTIVE'
    | 'COMPLETED'
    | 'NOT_DEPARTED'
    | 'MISSING_DEPARTURE'
    | 'DEPARTURE_TOO_OLD'
    | 'ETA_TOO_OLD'
    | 'INVALID_TRANSPORT'
  departureAt: string | null
  etaAt: string | null
  usedActualDeparture: boolean
}

export type ActiveCargoAisItem =
  AisMapItem & {
    ais_id: string
    linked: true
    active_cargo: true
    matched_transport_key: string
    matched_trpr_no: string
    matched_hbl_no?: string | null
    active_transport_count: number
    active_trpr_nos: string[]
    active_hbl_nos: string[]
    active_match_method:
      | 'TRANSPORT_KEY'
      | 'TRPR_NO'
      | 'HBL_NO'
      | 'MBL_NO'
      | 'VESSEL_NAME'
    source_ais_id?: string | null
  }

export interface ActiveCargoAisResult {
  items: ActiveCargoAisItem[]
  activeTransports: TransportRecord[]
  diagnostics: {
    sourceAisCount: number
    uniqueSourceVesselCount: number
    sourceTransportCount: number
    activeTransportCount: number
    displayedVesselCount: number
    excludedAisCount: number
    transportReasons: Record<string, number>
    matchMethods: Record<string, number>
  }
}

const DEFAULTS: Required<
  Omit<ActiveCargoAisOptions, 'now'>
> = {
  requireActualDeparture: false,
  scheduledDepartureGraceDays: 0,
  maxVoyageDays: 120,
  etaOverdueGraceDays: 30,
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function identifier(value: unknown): string {
  return text(value)
    .toUpperCase()
    .replace(/\s+/g, '')
    .replace(/\.0$/, '')
}

function exactVesselName(value: unknown): string {
  // 프로젝트 정책: 앞뒤 공백만 제거.
  return text(value)
}

function recordValue(
  value: unknown,
  ...keys: string[]
): unknown {
  if (!value || typeof value !== 'object') {
    return undefined
  }

  const record =
    value as Record<string, unknown>

  for (const key of keys) {
    const candidate = record[key]

    if (
      candidate !== null
      && candidate !== undefined
      && text(candidate)
    ) {
      return candidate
    }
  }

  return undefined
}

function boolValue(value: unknown): boolean {
  if (typeof value === 'boolean') return value

  return [
    'TRUE',
    'Y',
    'YES',
    '1',
    'COMPLETED',
    'DONE',
    'CLOSED',
  ].includes(text(value).toUpperCase())
}

function parseDate(value: unknown): Date | null {
  if (
    value === null
    || value === undefined
    || !text(value)
  ) {
    return null
  }

  const parsed = new Date(String(value))

  return Number.isNaN(parsed.getTime())
    ? null
    : parsed
}

function isoOrNull(value: Date | null): string | null {
  return value?.toISOString() ?? null
}

function differenceDays(
  later: Date,
  earlier: Date,
): number {
  return (
    later.getTime() - earlier.getTime()
  ) / 86_400_000
}

function splitIdentifiers(value: unknown): string[] {
  return text(value)
    .split(/[,;|]/)
    .map(identifier)
    .filter(Boolean)
}

function finiteCoordinate(value: unknown): boolean {
  if (
    value === null
    || value === undefined
    || text(value) === ''
  ) {
    return false
  }

  return Number.isFinite(Number(value))
}

function transportDeparture(
  transport: TransportRecord,
): {
  actual: Date | null
  scheduled: Date | null
} {
  return {
    actual: parseDate(
      recordValue(
        transport,
        'actual_atd',
        'atd',
        'actl_atd',
        'bl_atd',
        'b_l_atd',
        'atd_date',
        'atd_datetime',
        'departure_actual_at',
        'shpmt_atd',
      ),
    ),
    scheduled: parseDate(
      recordValue(
        transport,
        'current_etd',
        'etd',
        'etd_date',
        'planned_etd',
      ),
    ),
  }
}

function transportEta(
  transport: TransportRecord,
): Date | null {
  return parseDate(
    recordValue(
      transport,
      'current_eta',
      'eta',
      'eta_date',
      'planned_eta',
      'delivery_eta',
    ),
  )
}

function transportActualArrival(
  transport: TransportRecord,
): Date | null {
  return parseDate(
    recordValue(
      transport,
      'actual_ata',
      'ata',
      'actl_ata',
      'bl_ata',
      'b_l_ata',
      'ata_date',
      'ata_datetime',
      'delivery_actual_at',
      'dlvy_ata',
    ),
  )
}

export function evaluateTransportActivity(
  transport: TransportRecord,
  options: ActiveCargoAisOptions = {},
): TransportActivity {
  const settings = {
    ...DEFAULTS,
    ...options,
  }
  const now = options.now ?? new Date()

  const transportKey = text(
    transport.transport_key,
  )
  const trprNo = text(transport.trpr_no)

  if (!transportKey && !trprNo) {
    return {
      active: false,
      reason: 'INVALID_TRANSPORT',
      departureAt: null,
      etaAt: null,
      usedActualDeparture: false,
    }
  }

  const completed = (
    boolValue(
      recordValue(
        transport,
        'completed',
        'is_completed',
      ),
    )
    || ['Y', 'YES', 'COMPLETED', 'DONE', 'CLOSED']
      .includes(
        text(
          recordValue(
            transport,
            'cmpl_yn',
            'complete_yn',
            'status',
            'transport_status',
          ),
        ).toUpperCase(),
      )
  )

  const actualArrival =
    transportActualArrival(transport)

  if (completed || actualArrival) {
    return {
      active: false,
      reason: 'COMPLETED',
      departureAt: null,
      etaAt: null,
      usedActualDeparture: false,
    }
  }

  const departure =
    transportDeparture(transport)

  let departureAt = departure.actual
  let usedActualDeparture = true

  if (!departureAt) {
    usedActualDeparture = false

    if (settings.requireActualDeparture) {
      return {
        active: false,
        reason: 'MISSING_DEPARTURE',
        departureAt: null,
        etaAt: null,
        usedActualDeparture,
      }
    }

    departureAt = departure.scheduled
  }

  if (!departureAt) {
    return {
      active: false,
      reason: 'MISSING_DEPARTURE',
      departureAt: null,
      etaAt: null,
      usedActualDeparture,
    }
  }

  const daysSinceDeparture =
    differenceDays(now, departureAt)

  if (
    daysSinceDeparture
    < settings.scheduledDepartureGraceDays
  ) {
    return {
      active: false,
      reason: 'NOT_DEPARTED',
      departureAt: isoOrNull(departureAt),
      etaAt: null,
      usedActualDeparture,
    }
  }

  if (
    daysSinceDeparture
    > settings.maxVoyageDays
  ) {
    return {
      active: false,
      reason: 'DEPARTURE_TOO_OLD',
      departureAt: isoOrNull(departureAt),
      etaAt: null,
      usedActualDeparture,
    }
  }

  const etaAt = transportEta(transport)

  if (
    etaAt
    && differenceDays(now, etaAt)
      > settings.etaOverdueGraceDays
  ) {
    return {
      active: false,
      reason: 'ETA_TOO_OLD',
      departureAt: isoOrNull(departureAt),
      etaAt: isoOrNull(etaAt),
      usedActualDeparture,
    }
  }

  return {
    active: true,
    reason: 'ACTIVE',
    departureAt: isoOrNull(departureAt),
    etaAt: isoOrNull(etaAt),
    usedActualDeparture,
  }
}

function appendIndex(
  index: Map<string, TransportRecord[]>,
  key: string,
  transport: TransportRecord,
): void {
  if (!key) return

  const items = index.get(key) ?? []
  items.push(transport)
  index.set(key, items)
}

function transportDateScore(
  transport: TransportRecord,
): number {
  const departure =
    transportDeparture(transport)

  return (
    departure.actual
    ?? departure.scheduled
  )?.getTime() ?? 0
}

function sortCandidates(
  candidates:
    | readonly TransportRecord[]
    | undefined,
): TransportRecord[] {
  if (!candidates?.length) return []

  return [...candidates].sort(
    (left, right) =>
      transportDateScore(right)
      - transportDateScore(left),
  )
}

function aisMmsi(item: AisMapItem): string {
  return identifier(
    recordValue(
      item,
      'mmsi_no',
      'mmsi',
      'MMSI',
      'ship_mmsi',
      'vessel_mmsi',
    ),
  )
}

function stableAisId(
  item: AisMapItem,
): string {
  const mmsi = aisMmsi(item)

  if (mmsi) {
    return `MMSI:${mmsi}`
  }

  const vesselName = exactVesselName(
    item.vessel_name,
  )

  if (vesselName) {
    return `VESSEL:${vesselName}`
  }

  const existing = text(item.ais_id)

  if (existing) {
    return `AIS:${existing}`
  }

  return [
    'POSITION',
    text(item.current_lat),
    text(item.current_lon),
  ].join(':')
}

function lastSeenScore(item: AisMapItem): number {
  const parsed = parseDate(
    recordValue(
      item,
      'last_seen_at',
      'last_received_at',
      'received_at',
      'timestamp',
    ),
  )

  return parsed?.getTime() ?? 0
}

function deduplicateAisItems(
  items: readonly AisMapItem[],
): AisMapItem[] {
  const latestById = new Map<
    string,
    AisMapItem
  >()

  for (const item of items) {
    const id = stableAisId(item)
    const previous = latestById.get(id)

    if (
      !previous
      || lastSeenScore(item)
        >= lastSeenScore(previous)
    ) {
      latestById.set(id, item)
    }
  }

  return [...latestById.values()]
}

interface MatchResult {
  candidates: TransportRecord[]
  method:
    | 'TRANSPORT_KEY'
    | 'TRPR_NO'
    | 'HBL_NO'
    | 'MBL_NO'
    | 'VESSEL_NAME'
}

function matchActiveTransports(
  item: AisMapItem,
  byKey: Map<string, TransportRecord>,
  byTrpr: Map<string, TransportRecord[]>,
  byHbl: Map<string, TransportRecord[]>,
  byMbl: Map<string, TransportRecord[]>,
  byVessel: Map<string, TransportRecord[]>,
): MatchResult | null {
  const existingKey = text(
    item.matched_transport_key,
  )

  if (existingKey) {
    const existing = byKey.get(existingKey)

    if (existing) {
      return {
        candidates: [existing],
        method: 'TRANSPORT_KEY',
      }
    }
  }

  const trprValues = [
    item.matched_trpr_no,
    item.trpr_no,
    item.shipment_id,
  ]
    .map(identifier)
    .filter(Boolean)

  for (const value of trprValues) {
    const candidates = byTrpr.get(value)

    if (candidates?.length) {
      return {
        candidates:
          sortCandidates(candidates),
        method: 'TRPR_NO',
      }
    }
  }

  const hblValues = [
    item.hbl_no,
    recordValue(
      item,
      'matched_hbl_no',
    ),
  ].flatMap(splitIdentifiers)

  for (const value of hblValues) {
    const candidates = byHbl.get(value)

    if (candidates?.length) {
      return {
        candidates:
          sortCandidates(candidates),
        method: 'HBL_NO',
      }
    }
  }

  const mblValues = [
    item.mbl_no,
  ].flatMap(splitIdentifiers)

  for (const value of mblValues) {
    const candidates = byMbl.get(value)

    if (candidates?.length) {
      return {
        candidates:
          sortCandidates(candidates),
        method: 'MBL_NO',
      }
    }
  }

  const vesselName = exactVesselName(
    item.vessel_name,
  )

  const vesselCandidates =
    sortCandidates(
      byVessel.get(vesselName),
    )

  if (vesselCandidates.length) {
    return {
      candidates: vesselCandidates,
      method: 'VESSEL_NAME',
    }
  }

  return null
}

export function buildActiveCargoAisView(
  sourceItems: readonly AisMapItem[],
  transports: readonly TransportRecord[],
  options: ActiveCargoAisOptions = {},
): ActiveCargoAisResult {
  const activeTransports:
    TransportRecord[] = []

  const transportReasons:
    Record<string, number> = {}

  for (const transport of transports) {
    const activity =
      evaluateTransportActivity(
        transport,
        options,
      )

    transportReasons[activity.reason] =
      (transportReasons[activity.reason] ?? 0)
      + 1

    if (activity.active) {
      activeTransports.push(transport)
    }
  }

  const byKey =
    new Map<string, TransportRecord>()
  const byTrpr =
    new Map<string, TransportRecord[]>()
  const byHbl =
    new Map<string, TransportRecord[]>()
  const byMbl =
    new Map<string, TransportRecord[]>()
  const byVessel =
    new Map<string, TransportRecord[]>()

  for (const transport of activeTransports) {
    const key = text(
      transport.transport_key,
    )

    if (key) {
      byKey.set(key, transport)
    }

    appendIndex(
      byTrpr,
      identifier(transport.trpr_no),
      transport,
    )

    for (
      const value
      of splitIdentifiers(
        transport.hbl_no,
      )
    ) {
      appendIndex(
        byHbl,
        value,
        transport,
      )
    }

    for (
      const value
      of splitIdentifiers(
        transport.mbl_no,
      )
    ) {
      appendIndex(
        byMbl,
        value,
        transport,
      )
    }

    appendIndex(
      byVessel,
      exactVesselName(
        transport.vessel_name,
      ),
      transport,
    )
  }

  const uniqueSourceItems =
    deduplicateAisItems(sourceItems)

  const items: ActiveCargoAisItem[] = []
  const matchMethods:
    Record<string, number> = {}

  for (const item of uniqueSourceItems) {
    if (
      !finiteCoordinate(item.current_lat)
      || !finiteCoordinate(item.current_lon)
    ) {
      continue
    }

    const match = matchActiveTransports(
      item,
      byKey,
      byTrpr,
      byHbl,
      byMbl,
      byVessel,
    )

    if (!match) continue

    const primary = match.candidates[0]

    if (!primary) continue

    matchMethods[match.method] =
      (matchMethods[match.method] ?? 0)
      + 1

    const trprNos = [
      ...new Set(
        match.candidates
          .map(
            (transport) =>
              text(transport.trpr_no),
          )
          .filter(Boolean),
      ),
    ]

    const hblNos = [
      ...new Set(
        match.candidates
          .flatMap(
            (transport) =>
              splitIdentifiers(
                transport.hbl_no,
              ),
          )
          .filter(Boolean),
      ),
    ]

    items.push({
      ...item,
      source_ais_id:
        text(item.ais_id) || null,
      ais_id: stableAisId(item),
      matched_transport_key:
        text(primary.transport_key),
      matched_trpr_no:
        text(primary.trpr_no),
      matched_hbl_no:
        text(primary.hbl_no) || null,
      linked: true,
      active_cargo: true,
      active_transport_count:
        match.candidates.length,
      active_trpr_nos: trprNos,
      active_hbl_nos: hblNos,
      active_match_method:
        match.method,
    })
  }

  return {
    items,
    activeTransports,
    diagnostics: {
      sourceAisCount: sourceItems.length,
      uniqueSourceVesselCount:
        uniqueSourceItems.length,
      sourceTransportCount:
        transports.length,
      activeTransportCount:
        activeTransports.length,
      displayedVesselCount:
        items.length,
      excludedAisCount:
        uniqueSourceItems.length
        - items.length,
      transportReasons,
      matchMethods,
    },
  }
}

export function findActiveCargoAisForTransport(
  items: readonly ActiveCargoAisItem[],
  transport:
    | TransportRecord
    | null
    | undefined,
): ActiveCargoAisItem | undefined {
  if (!transport) return undefined

  const transportKey = text(
    transport.transport_key,
  )
  const trprNo = text(
    transport.trpr_no,
  )
  const vesselName = exactVesselName(
    transport.vessel_name,
  )

  if (transportKey) {
    const byKey = items.find(
      (item) =>
        text(
          item.matched_transport_key,
        ) === transportKey,
    )

    if (byKey) return byKey
  }

  if (trprNo) {
    const byTrpr = items.find(
      (item) =>
        text(item.matched_trpr_no)
          === trprNo
        || item.active_trpr_nos
          .includes(trprNo),
    )

    if (byTrpr) return byTrpr
  }

  if (vesselName) {
    return items.find(
      (item) =>
        exactVesselName(
          item.vessel_name,
        ) === vesselName,
    )
  }

  return undefined
}
