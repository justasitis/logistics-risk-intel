import type {
  ManualCoordinateEntry,
} from '@/services/manualCoordinatesApi'

export interface MissingCoordinateItem {
  location_code: string
  location_name: string
  roles: Array<'POL' | 'POD'>
  transport_count: number
  transport_numbers: string[]
}

interface TransportLike {
  trpr_no?: unknown

  pol?: unknown
  pol_code?: unknown
  pol_cd?: unknown
  pol_name?: unknown
  pol_nm?: unknown

  pod?: unknown
  pod_code?: unknown
  pod_cd?: unknown
  pod_name?: unknown
  pod_nm?: unknown
}

interface FeatureCollectionLike {
  type?: unknown
  features?: unknown[]
}

function text(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }

  return String(value).trim()
}

export function normalizeLocationCode(
  value: unknown,
): string {
  return text(value)
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
}

function propertiesOf(
  feature: unknown,
): Record<string, unknown> {
  if (!feature || typeof feature !== 'object') {
    return {}
  }

  const properties =
    (feature as Record<string, unknown>)
      .properties

  return (
    properties
    && typeof properties === 'object'
  )
    ? properties as Record<string, unknown>
    : {}
}

function coordinateOf(
  feature: unknown,
): [number, number] | null {
  if (!feature || typeof feature !== 'object') {
    return null
  }

  const geometry =
    (feature as Record<string, unknown>)
      .geometry

  if (!geometry || typeof geometry !== 'object') {
    return null
  }

  const coordinates =
    (geometry as Record<string, unknown>)
      .coordinates

  if (
    !Array.isArray(coordinates)
    || coordinates.length < 2
  ) {
    return null
  }

  const longitude = Number(coordinates[0])
  const latitude = Number(coordinates[1])

  return (
    Number.isFinite(longitude)
    && Number.isFinite(latitude)
  )
    ? [longitude, latitude]
    : null
}

function featureCode(
  feature: unknown,
): string {
  const properties = propertiesOf(feature)

  return normalizeLocationCode(
    properties.location_code
    ?? properties.unlocode
    ?? properties.un_locode
    ?? properties.port_code
    ?? properties.port_cd
    ?? properties.code
    ?? properties.loc_cd
    ?? properties.location_cd
    ?? properties.id,
  )
}

function manualByCode(
  manual: readonly ManualCoordinateEntry[],
): Map<string, ManualCoordinateEntry> {
  return new Map(
    manual
      .map(
        (item) => [
          normalizeLocationCode(
            item.location_code,
          ),
          item,
        ] as const,
      )
      .filter(([code]) => Boolean(code)),
  )
}

function knownCoordinateCodes(
  ports: FeatureCollectionLike,
  manual: readonly ManualCoordinateEntry[],
): Set<string> {
  const result = new Set<string>()

  for (const feature of ports.features ?? []) {
    const itemCode = featureCode(feature)

    if (
      itemCode
      && coordinateOf(feature)
    ) {
      result.add(itemCode)
    }
  }

  for (
    const code
    of manualByCode(manual).keys()
  ) {
    result.add(code)
  }

  return result
}

export function deriveMissingCoordinateItems(
  transports: readonly TransportLike[],
  ports: FeatureCollectionLike,
  manual: readonly ManualCoordinateEntry[],
): MissingCoordinateItem[] {
  const known = knownCoordinateCodes(
    ports,
    manual,
  )

  const grouped = new Map<
    string,
    MissingCoordinateItem
  >()

  const add = (
    transport: TransportLike,
    role: 'POL' | 'POD',
    locationCode: unknown,
    locationName: unknown,
  ) => {
    const normalizedCode =
      normalizeLocationCode(locationCode)

    if (
      !normalizedCode
      || known.has(normalizedCode)
    ) {
      return
    }

    const trprNo = text(
      transport.trpr_no,
    )

    const current = grouped.get(
      normalizedCode,
    ) ?? {
      location_code: normalizedCode,
      location_name: text(locationName),
      roles: [],
      transport_count: 0,
      transport_numbers: [],
    }

    if (!current.location_name) {
      current.location_name =
        text(locationName)
    }

    if (!current.roles.includes(role)) {
      current.roles.push(role)
    }

    current.transport_count += 1

    if (
      trprNo
      && !current.transport_numbers
        .includes(trprNo)
    ) {
      current.transport_numbers.push(
        trprNo,
      )
    }

    grouped.set(
      normalizedCode,
      current,
    )
  }

  for (const transport of transports) {
    add(
      transport,
      'POL',
      transport.pol_code
      ?? transport.pol_cd
      ?? transport.pol,
      transport.pol_name
      ?? transport.pol_nm,
    )

    add(
      transport,
      'POD',
      transport.pod_code
      ?? transport.pod_cd
      ?? transport.pod,
      transport.pod_name
      ?? transport.pod_nm,
    )
  }

  return [...grouped.values()].sort(
    (left, right) =>
      right.transport_count
      - left.transport_count
      || left.location_code.localeCompare(
        right.location_code,
      ),
  )
}

function manualFeature(
  item: ManualCoordinateEntry,
): Record<string, unknown> {
  return {
    type: 'Feature',
    id: `MANUAL:${item.location_code}`,
    geometry: {
      type: 'Point',
      coordinates: [
        Number(item.longitude),
        Number(item.latitude),
      ],
    },
    properties: {
      location_code:
        item.location_code,
      unlocode:
        item.location_code,
      port_code:
        item.location_code,
      code:
        item.location_code,
      name:
        item.location_name
        || item.location_code,
      location_name:
        item.location_name,
      country_code:
        item.country_code,
      coordinate_source: 'MANUAL',
      note:
        item.note,
    },
  }
}

export function applyManualCoordinatesToPorts<
  T extends FeatureCollectionLike,
>(
  ports: T,
  manual: readonly ManualCoordinateEntry[],
): T {
  const manualMap = manualByCode(manual)
  const consumed = new Set<string>()

  const mergedFeatures = (
    ports.features ?? []
  ).map((feature) => {
    const code = featureCode(feature)
    const manualItem = manualMap.get(code)

    if (!manualItem) {
      return feature
    }

    consumed.add(code)

    // 기존 Master 좌표가 유효하면 Master를 유지한다.
    if (coordinateOf(feature)) {
      return feature
    }

    // Port Feature는 있지만 geometry가 없으면
    // 수동 좌표로 geometry를 보완한다.
    const properties = propertiesOf(feature)

    return {
      ...(feature as Record<string, unknown>),
      geometry: {
        type: 'Point',
        coordinates: [
          Number(manualItem.longitude),
          Number(manualItem.latitude),
        ],
      },
      properties: {
        ...properties,
        location_code:
          manualItem.location_code,
        unlocode:
          manualItem.location_code,
        port_code:
          manualItem.location_code,
        code:
          manualItem.location_code,
        name:
          manualItem.location_name
          || text(properties.name)
          || manualItem.location_code,
        location_name:
          manualItem.location_name,
        country_code:
          manualItem.country_code,
        coordinate_source: 'MANUAL',
        note:
          manualItem.note,
      },
    }
  })

  for (
    const [code, item]
    of manualMap.entries()
  ) {
    if (!consumed.has(code)) {
      mergedFeatures.push(
        manualFeature(item),
      )
    }
  }

  return {
    ...ports,
    type: 'FeatureCollection',
    features: mergedFeatures,
  } as T
}
