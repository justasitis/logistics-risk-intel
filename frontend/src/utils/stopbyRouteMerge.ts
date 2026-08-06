import type {
  GeoJsonFeatureCollection,
  TransportRecord,
} from '@/types/dashboard'

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value).trim()
}

function propertiesOf(
  feature: Record<string, unknown>,
): Record<string, unknown> {
  const properties = feature.properties

  return properties
    && typeof properties === 'object'
    ? properties as Record<string, unknown>
    : {}
}

function routeKeys(
  feature: Record<string, unknown>,
): string[] {
  const properties = propertiesOf(feature)

  return [
    properties.transport_key,
    properties.trpr_no,
    properties.system_trpr_no,
    properties.hbl_no,
    properties.display_id,
  ]
    .map(text)
    .filter(Boolean)
}

function transportKeys(
  transport: TransportRecord,
): string[] {
  return [
    transport.transport_key,
    transport.trpr_no,
    transport.hbl_no,
  ]
    .map(text)
    .filter(Boolean)
}

export function mergeStopbyRoutes(
  original:
    | GeoJsonFeatureCollection
    | null
    | undefined,
  generated:
    | GeoJsonFeatureCollection
    | null
    | undefined,
): GeoJsonFeatureCollection {
  const base = original ?? {
    type: 'FeatureCollection',
    features: [],
  }

  if (
    !generated
    || generated.features.length === 0
  ) {
    return base
  }

  const generatedByKey = new Map<
    string,
    Record<string, unknown>
  >()

  for (const feature of generated.features) {
    for (const key of routeKeys(feature)) {
      generatedByKey.set(key, feature)
    }
  }

  const used = new Set<
    Record<string, unknown>
  >()

  const merged = base.features.map(
    (feature) => {
      const replacement = routeKeys(
        feature,
      )
        .map(
          (key) =>
            generatedByKey.get(key),
        )
        .find(Boolean)

      if (replacement) {
        used.add(replacement)
        return replacement
      }

      return feature
    },
  )

  for (
    const feature
    of generated.features
  ) {
    if (!used.has(feature)) {
      merged.push(feature)
    }
  }

  return {
    type: 'FeatureCollection',
    features: merged,
  }
}

function lineCoordinates(
  feature:
    | Record<string, unknown>
    | undefined,
): unknown[][] {
  if (!feature) return []

  const geometry = feature.geometry

  if (
    !geometry
    || typeof geometry !== 'object'
  ) {
    return []
  }

  const geometryRecord =
    geometry as Record<string, unknown>

  if (
    geometryRecord.type !== 'LineString'
    && geometryRecord.type !== 'MultiLineString'
  ) {
    return []
  }

  if (!Array.isArray(geometryRecord.coordinates)) {
    return []
  }

  if (geometryRecord.type === 'LineString') {
    return geometryRecord.coordinates
      .filter(Array.isArray)
  }

  return geometryRecord.coordinates
    .filter(Array.isArray)
    .flatMap((line) => line)
    .filter(Array.isArray)
}

export interface StopbyRouteDiagnostic {
  found: boolean
  trprNo: string
  stopbyRaw: string
  stopbyEffective: string
  stopbySource: string
  routeStatus: string
  transportMatchMethod: string
  pointCount: number
  minLatitude: number | null
  passesCapeLatitude: boolean
}

export function inspectTransportRoute(
  routes: GeoJsonFeatureCollection,
  transport:
    | TransportRecord
    | null
    | undefined,
): StopbyRouteDiagnostic {
  const empty: StopbyRouteDiagnostic = {
    found: false,
    trprNo: text(transport?.trpr_no),
    stopbyRaw: '',
    stopbyEffective: '',
    stopbySource: '',
    routeStatus: '',
    transportMatchMethod: '',
    pointCount: 0,
    minLatitude: null,
    passesCapeLatitude: false,
  }

  if (!transport) return empty

  const keys = new Set(
    transportKeys(transport),
  )

  const feature = routes.features.find(
    (candidate) =>
      routeKeys(candidate).some(
        (key) => keys.has(key),
      ),
  )

  if (!feature) return empty

  const properties = propertiesOf(feature)
  const coordinates = lineCoordinates(
    feature,
  )

  const latitudes = coordinates
    .map((coordinate) =>
      Number(coordinate[1]),
    )
    .filter(Number.isFinite)

  const minLatitude = latitudes.length
    ? Math.min(...latitudes)
    : null

  return {
    found: true,
    trprNo: (
      text(properties.trpr_no)
      || text(transport.trpr_no)
    ),
    stopbyRaw: text(
      properties.stopby_raw,
    ),
    stopbyEffective: text(
      properties.stopby_effective,
    ),
    stopbySource: text(
      properties.stopby_source,
    ),
    routeStatus: text(
      properties.route_geometry_status,
    ),
    transportMatchMethod: text(
      properties.transport_match_method,
    ),
    pointCount: coordinates.length,
    minLatitude,
    passesCapeLatitude:
      minLatitude !== null
      && minLatitude <= -30,
  }
}
