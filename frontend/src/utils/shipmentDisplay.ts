type ShipmentIdentity = {
  hbl_no?: unknown
  trpr_no?: unknown
  transport_key?: unknown
}

function text(value: unknown): string {
  return value === null || value === undefined
    ? ''
    : String(value).trim()
}

export function shipmentDisplayId(
  value: ShipmentIdentity | null | undefined,
): string {
  if (!value) return '-'

  return (
    text(value.hbl_no)
    || text(value.trpr_no)
    || text(value.transport_key)
    || '-'
  )
}

export function shipmentDisplayType(
  value: ShipmentIdentity | null | undefined,
): 'HBL' | 'TR' | 'TRANSPORT_KEY' | 'NONE' {
  if (!value) return 'NONE'
  if (text(value.hbl_no)) return 'HBL'
  if (text(value.trpr_no)) return 'TR'
  if (text(value.transport_key)) return 'TRANSPORT_KEY'
  return 'NONE'
}

export function shipmentSystemId(
  value: ShipmentIdentity | null | undefined,
): string {
  if (!value) return '-'

  return (
    text(value.trpr_no)
    || text(value.transport_key)
    || '-'
  )
}
