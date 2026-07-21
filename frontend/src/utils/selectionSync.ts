export type TransportSelectionSource =
  | 'INIT'
  | 'EVENT'
  | 'AIS'
  | 'ROUTE'
  | 'MANUAL'

export interface EventSelectionLike {
  event_id?: unknown
  transport_key?: unknown
  trpr_no?: unknown
  event_type?: unknown
  detected_at?: unknown
}

export interface TransportSelectionLike {
  transport_key?: unknown
  trpr_no?: unknown
}

export interface AisSelectionLike {
  ais_id?: unknown
  matched_transport_key?: unknown
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

export function eventSelectionKey(
  event: EventSelectionLike,
): string {
  return [
    event.event_id,
    event.transport_key,
    event.trpr_no,
    event.event_type,
    event.detected_at,
  ]
    .map(text)
    .filter(Boolean)
    .join('|')
}

export function findTransportForEvent<
  T extends TransportSelectionLike,
>(
  event: EventSelectionLike,
  transports: readonly T[],
): T | undefined {
  const transportKey = text(event.transport_key)

  if (transportKey) {
    const matchedByKey = transports.find(
      (transport) =>
        text(transport.transport_key) === transportKey,
    )

    if (matchedByKey) return matchedByKey
  }

  const trprNo = text(event.trpr_no)

  if (!trprNo) return undefined

  return transports.find(
    (transport) =>
      text(transport.trpr_no) === trprNo,
  )
}

export function findLinkedAisForTransport<
  T extends AisSelectionLike,
>(
  transportKey: unknown,
  aisItems: readonly T[],
): T | undefined {
  const key = text(transportKey)

  if (!key) return undefined

  return aisItems.find(
    (item) =>
      text(item.matched_transport_key) === key,
  )
}

export function aisSelectionId(
  item: AisSelectionLike | null | undefined,
): string {
  return text(item?.ais_id)
}

export function matchedTransportKey(
  item: AisSelectionLike | null | undefined,
): string {
  return text(item?.matched_transport_key)
}

export function createLatestRequestGuard() {
  let sequence = 0

  return {
    begin(): number {
      sequence += 1
      return sequence
    },

    isCurrent(token: number): boolean {
      return token === sequence
    },

    invalidate(): void {
      sequence += 1
    },

    current(): number {
      return sequence
    },
  }
}
