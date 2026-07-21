import type {
  AisMapItem,
  TransportRecord,
} from '@/types/dashboard'

export type AisLinkedMapItem = AisMapItem & {
  matched_hbl_no?: string | null
  linked: boolean
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function identifier(value: unknown): string {
  return text(value)
    .toUpperCase()
    .replace(/\s+/g, '')
}

function exactVesselName(value: unknown): string {
  // IF 원문 정책: 앞뒤 공백만 제거한다.
  // 대소문자, 기호, M/V, 내부 공백은 변경하지 않는다.
  return text(value)
}

function splitIdentifiers(value: unknown): string[] {
  return text(value)
    .split(/[,;|]/)
    .map(identifier)
    .filter(Boolean)
}

function propertyText(
  value: unknown,
  key: string,
): string {
  if (!value || typeof value !== 'object') return ''

  return text(
    (value as Record<string, unknown>)[key],
  )
}

function addCandidate(
  index: Map<string, TransportRecord[]>,
  key: string,
  transport: TransportRecord,
): void {
  if (!key) return

  const candidates = index.get(key) ?? []
  candidates.push(transport)
  index.set(key, candidates)
}

function uniqueCandidate(
  index: Map<string, TransportRecord[]>,
  key: string,
): TransportRecord | undefined {
  if (!key) return undefined

  const candidates = index.get(key) ?? []
  return candidates.length === 1
    ? candidates[0]
    : undefined
}

function resolveExistingTransport(
  item: AisMapItem,
  byKey: Map<string, TransportRecord>,
): TransportRecord | undefined {
  const existingKey = text(
    item.matched_transport_key,
  )

  if (existingKey) {
    return byKey.get(existingKey)
  }

  const rawTransportKey = propertyText(
    item,
    'transport_key',
  )

  return rawTransportKey
    ? byKey.get(rawTransportKey)
    : undefined
}

export function ensureAisTransportLinks(
  sourceItems: readonly AisMapItem[],
  transports: readonly TransportRecord[],
): AisLinkedMapItem[] {
  const byKey = new Map<
    string,
    TransportRecord
  >()
  const byTrpr = new Map<
    string,
    TransportRecord[]
  >()
  const byHbl = new Map<
    string,
    TransportRecord[]
  >()
  const byMbl = new Map<
    string,
    TransportRecord[]
  >()
  const byVessel = new Map<
    string,
    TransportRecord[]
  >()

  for (const transport of transports) {
    const transportKey = text(
      transport.transport_key,
    )

    if (transportKey) {
      byKey.set(transportKey, transport)
    }

    addCandidate(
      byTrpr,
      identifier(transport.trpr_no),
      transport,
    )

    for (
      const value
      of splitIdentifiers(transport.hbl_no)
    ) {
      addCandidate(byHbl, value, transport)
    }

    for (
      const value
      of splitIdentifiers(transport.mbl_no)
    ) {
      addCandidate(byMbl, value, transport)
    }

    addCandidate(
      byVessel,
      exactVesselName(
        transport.vessel_name,
      ),
      transport,
    )
  }

  return sourceItems.map((item) => {
    let match = resolveExistingTransport(
      item,
      byKey,
    )

    let method = item.match_method ?? null

    if (!match) {
      const matchedTrpr = identifier(
        item.matched_trpr_no,
      )
      const directTrpr = identifier(
        item.trpr_no,
      )
      const shipmentId = identifier(
        item.shipment_id,
      )
      const hblNo = identifier(
        item.hbl_no,
      )
      const mblNo = identifier(
        item.mbl_no,
      )

      if (matchedTrpr) {
        match = uniqueCandidate(
          byTrpr,
          matchedTrpr,
        )
        if (match) method = 'TRPR_NO'
      }

      if (!match && directTrpr) {
        match = uniqueCandidate(
          byTrpr,
          directTrpr,
        )
        if (match) method = 'TRPR_NO'
      }

      if (
        !match
        && shipmentId
        && shipmentId.startsWith('TR')
      ) {
        match = uniqueCandidate(
          byTrpr,
          shipmentId,
        )
        if (match) method = 'SHIPMENT_ID'
      }

      if (!match && hblNo) {
        match = uniqueCandidate(byHbl, hblNo)
        if (match) method = 'HBL_NO'
      }

      if (!match && mblNo) {
        match = uniqueCandidate(byMbl, mblNo)
        if (match) method = 'MBL_NO'
      }

      if (!match) {
        const vesselName = exactVesselName(
          item.vessel_name,
        )

        match = uniqueCandidate(
          byVessel,
          vesselName,
        )

        if (match) {
          method = 'VESSEL_NAME'
        }
      }
    }

    const matchedTransportKey =
      text(match?.transport_key)
      || text(item.matched_transport_key)
      || null

    const matchedTrprNo =
      text(match?.trpr_no)
      || text(item.matched_trpr_no)
      || text(item.trpr_no)
      || null

    const matchedHblNo =
      text(match?.hbl_no)
      || text(item.hbl_no)
      || null

    return {
      ...item,
      matched_transport_key:
        matchedTransportKey,
      matched_trpr_no: matchedTrprNo,
      matched_hbl_no: matchedHblNo,
      match_method:
        matchedTransportKey
          ? method
          : null,
      linked: Boolean(
        matchedTransportKey
        || matchedTrprNo,
      ),
    }
  })
}

export interface AisPopupLinkState {
  linked: boolean
  transportationNo: string
  hblNo: string
  transportKey: string
}

export function aisPopupLinkState(
  properties: Record<string, unknown>,
): AisPopupLinkState {
  const transportKey = (
    text(properties.matched_transport_key)
    || text(properties.transport_key)
  )

  const shipmentId = text(
    properties.shipment_id,
  )

  const transportationNo = (
    text(properties.matched_trpr_no)
    || text(properties.trpr_no)
    || (
      shipmentId.toUpperCase().startsWith('TR')
        ? shipmentId
        : ''
    )
  )

  const hblNo = (
    text(properties.matched_hbl_no)
    || text(properties.hbl_no)
  )

  return {
    linked: Boolean(
      transportKey
      || transportationNo
      || hblNo,
    ),
    transportationNo:
      transportationNo || '-',
    hblNo: hblNo || '-',
    transportKey,
  }
}
