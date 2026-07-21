import type {
  AisMapItem,
  GeoJsonFeatureCollection,
} from '@/types/dashboard'
import type { RefinedMiEvent } from '@/types/mi'
import type {
  MiImpactAnalysis,
  MiTransportImpact,
} from '@/types/miImpact'

const EARTH_RADIUS_KM = 6371.0088
const KM_PER_LAT_DEGREE = 110.574

function numberValue(value: unknown, fallback = 0): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function textValue(value: unknown): string {
  return value === null || value === undefined
    ? ''
    : String(value).trim()
}

function degreesToRadians(value: number): number {
  return value * Math.PI / 180
}

function haversineKm(
  lon1: number,
  lat1: number,
  lon2: number,
  lat2: number,
): number {
  const latitudeDistance = degreesToRadians(lat2 - lat1)
  const longitudeDistance = degreesToRadians(lon2 - lon1)
  const firstLatitude = degreesToRadians(lat1)
  const secondLatitude = degreesToRadians(lat2)

  const a =
    Math.sin(latitudeDistance / 2) ** 2
    + Math.cos(firstLatitude)
      * Math.cos(secondLatitude)
      * Math.sin(longitudeDistance / 2) ** 2

  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)))
}

function circlePolygon(
  lon: number,
  lat: number,
  radiusKm: number,
  steps = 72,
): number[][] {
  const coordinates: number[][] = []
  const angularDistance = radiusKm / EARTH_RADIUS_KM
  const latitudeRadians = degreesToRadians(lat)
  const longitudeRadians = degreesToRadians(lon)

  for (let index = 0; index <= steps; index += 1) {
    const bearing = 2 * Math.PI * index / steps
    const pointLatitude = Math.asin(
      Math.sin(latitudeRadians) * Math.cos(angularDistance)
      + Math.cos(latitudeRadians)
        * Math.sin(angularDistance)
        * Math.cos(bearing),
    )
    const pointLongitude = longitudeRadians + Math.atan2(
      Math.sin(bearing)
        * Math.sin(angularDistance)
        * Math.cos(latitudeRadians),
      Math.cos(angularDistance)
        - Math.sin(latitudeRadians) * Math.sin(pointLatitude),
    )

    coordinates.push([
      pointLongitude * 180 / Math.PI,
      pointLatitude * 180 / Math.PI,
    ])
  }

  return coordinates
}

export function buildMiZoneGeoJson(
  events: RefinedMiEvent[],
): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: events.flatMap((event) =>
      event.affected_locations
        .filter((location) => (
          Number.isFinite(Number(location.lat))
          && Number.isFinite(Number(location.lon))
        ))
        .map((location) => {
          const radiusKm = Math.max(
            10,
            Math.min(1500, numberValue(location.radius_km, 150)),
          )

          return {
            type: 'Feature',
            id: `${event.event_id}|${location.code}`,
            properties: {
              event_id: event.event_id,
              headline: event.headline,
              summary: event.summary,
              event_type: event.event_type,
              severity: event.severity,
              status: event.status,
              confidence: event.confidence,
              valid_from: event.valid_from,
              valid_to: event.valid_to ?? '',
              location_code: location.code,
              location_name: location.name,
              location_type: location.location_type,
              radius_km: radiusKm,
              expected_delay_min: event.expected_delay_days?.min ?? 0,
              expected_delay_max: event.expected_delay_days?.max ?? 0,
              transport_modes: event.transport_modes.join(', '),
              affected_corridors: event.affected_corridors.join(', '),
              recommended_actions: event.recommended_actions.join(' | '),
            },
            geometry: {
              type: 'Polygon',
              coordinates: [[
                ...circlePolygon(
                  Number(location.lon),
                  Number(location.lat),
                  radiusKm,
                ),
              ]],
            },
          }
        }),
    ),
  }
}

function routeCoordinates(feature: Record<string, unknown>): number[][] {
  if (!feature.geometry || typeof feature.geometry !== 'object') return []

  const geometry = feature.geometry as Record<string, unknown>
  if (geometry.type !== 'LineString' || !Array.isArray(geometry.coordinates)) {
    return []
  }

  return geometry.coordinates
    .filter((coordinate) => (
      Array.isArray(coordinate)
      && coordinate.length >= 2
      && Number.isFinite(Number(coordinate[0]))
      && Number.isFinite(Number(coordinate[1]))
    ))
    .map((coordinate) => [
      Number((coordinate as unknown[])[0]),
      Number((coordinate as unknown[])[1]),
    ])
}

function routeProperties(feature: Record<string, unknown>) {
  const properties = feature.properties && typeof feature.properties === 'object'
    ? feature.properties as Record<string, unknown>
    : {}

  return {
    properties,
    transportKey: textValue(properties.transport_key),
    trprNo: textValue(properties.trpr_no),
    pol: textValue(properties.pol).toUpperCase(),
    pod: textValue(properties.pod).toUpperCase(),
  }
}

function localPointKm(
  lon: number,
  lat: number,
  centerLon: number,
  centerLat: number,
): [number, number] {
  const kmPerLonDegree = 111.320 * Math.cos(degreesToRadians(centerLat))
  return [
    (lon - centerLon) * kmPerLonDegree,
    (lat - centerLat) * KM_PER_LAT_DEGREE,
  ]
}

function originToSegmentDistanceKm(
  start: [number, number],
  end: [number, number],
): number {
  const deltaX = end[0] - start[0]
  const deltaY = end[1] - start[1]
  const denominator = deltaX * deltaX + deltaY * deltaY

  if (denominator === 0) {
    return Math.hypot(start[0], start[1])
  }

  const ratio = Math.max(
    0,
    Math.min(1, -(start[0] * deltaX + start[1] * deltaY) / denominator),
  )
  const nearestX = start[0] + ratio * deltaX
  const nearestY = start[1] + ratio * deltaY
  return Math.hypot(nearestX, nearestY)
}

function locationRouteMatch(
  coordinates: number[][],
  event: RefinedMiEvent,
) {
  const matchedCodes: string[] = []
  let minimumDistance = Number.POSITIVE_INFINITY
  let zoneRouteIndex = -1

  for (const location of event.affected_locations) {
    const centerLon = Number(location.lon)
    const centerLat = Number(location.lat)
    const radiusKm = Math.max(10, numberValue(location.radius_km, 150))

    for (let index = 0; index < coordinates.length - 1; index += 1) {
      const first = localPointKm(
        coordinates[index][0],
        coordinates[index][1],
        centerLon,
        centerLat,
      )
      const second = localPointKm(
        coordinates[index + 1][0],
        coordinates[index + 1][1],
        centerLon,
        centerLat,
      )
      const distance = originToSegmentDistanceKm(first, second)

      if (distance < minimumDistance) {
        minimumDistance = distance
        zoneRouteIndex = index
      }
      if (distance <= radiusKm) {
        matchedCodes.push(location.code)
      }
    }
  }

  return {
    matched: matchedCodes.length > 0,
    matchedCodes: [...new Set(matchedCodes)],
    minimumDistance: Number.isFinite(minimumDistance)
      ? minimumDistance
      : null,
    zoneRouteIndex,
  }
}

function laneRouteMatch(
  pol: string,
  pod: string,
  event: RefinedMiEvent,
): boolean {
  return event.affected_lanes.some((rawLane) => {
    const lane = rawLane as Record<string, unknown>
    const polCodes = Array.isArray(lane.pol_codes)
      ? lane.pol_codes.map((value) => textValue(value).toUpperCase()).filter(Boolean)
      : []
    const podCodes = Array.isArray(lane.pod_codes)
      ? lane.pod_codes.map((value) => textValue(value).toUpperCase()).filter(Boolean)
      : []

    const polMatches = polCodes.length === 0 || polCodes.includes(pol)
    const podMatches = podCodes.length === 0 || podCodes.includes(pod)
    return polMatches && podMatches
  })
}

function severityWeight(severity: RefinedMiEvent['severity']): number {
  if (severity === 'CRITICAL') return 20
  if (severity === 'HIGH') return 15
  if (severity === 'MEDIUM') return 10
  return 5
}

function nearestRouteIndex(
  coordinates: number[][],
  lon: number,
  lat: number,
) {
  let bestIndex = -1
  let bestDistance = Number.POSITIVE_INFINITY

  coordinates.forEach((coordinate, index) => {
    const distance = haversineKm(
      coordinate[0],
      coordinate[1],
      lon,
      lat,
    )
    if (distance < bestDistance) {
      bestDistance = distance
      bestIndex = index
    }
  })

  return { index: bestIndex, distance: bestDistance }
}

export function analyzeMiImpact(
  events: RefinedMiEvent[],
  routes: GeoJsonFeatureCollection,
  aisItems: AisMapItem[],
): MiImpactAnalysis {
  const impacts: MiTransportImpact[] = []
  const impactedFeatures: Array<Record<string, unknown>> = []
  const aisByTransport = new Map(
    aisItems
      .filter((item) => Boolean(item.matched_transport_key))
      .map((item) => [item.matched_transport_key as string, item]),
  )

  for (const feature of routes.features) {
    const coordinates = routeCoordinates(feature)
    const route = routeProperties(feature)
    if (!route.transportKey || coordinates.length < 2) continue

    const routeImpacts: MiTransportImpact[] = []

    for (const event of events) {
      if (event.status === 'RESOLVED') continue

      const spatial = locationRouteMatch(coordinates, event)
      const laneMatched = laneRouteMatch(route.pol, route.pod, event)
      if (!spatial.matched && !laneMatched) continue

      const matchMethods: MiTransportImpact['match_methods'] = []
      let score = severityWeight(event.severity)

      if (spatial.matched) {
        matchMethods.push('IMPACT_ZONE')
        score += 60
      }
      if (laneMatched) {
        matchMethods.push('LANE')
        score += 45
      }
      if (event.status === 'ACTIVE') score += 10
      score += Math.round(Math.max(0, Math.min(1, event.confidence)) * 10)

      let exposureStatus: MiTransportImpact['exposure_status'] = 'ROUTE_EXPOSED'
      let distanceToZone = spatial.minimumDistance
      const ais = aisByTransport.get(route.transportKey)

      if (
        ais
        && ais.current_lon !== null
        && ais.current_lat !== null
        && event.affected_locations.length > 0
      ) {
        const current = nearestRouteIndex(
          coordinates,
          ais.current_lon,
          ais.current_lat,
        )

        const insideZone = event.affected_locations.some((location) => (
          haversineKm(
            ais.current_lon as number,
            ais.current_lat as number,
            Number(location.lon),
            Number(location.lat),
          ) <= Math.max(10, numberValue(location.radius_km, 150))
        ))

        if (insideZone) {
          exposureStatus = 'IN_ZONE'
          score += 10
        } else if (
          spatial.zoneRouteIndex >= 0
          && current.index >= 0
          && current.index <= spatial.zoneRouteIndex
        ) {
          exposureStatus = 'APPROACHING'
          score += 8
        } else if (
          spatial.zoneRouteIndex >= 0
          && current.index > spatial.zoneRouteIndex
        ) {
          exposureStatus = 'PASSED'
          score -= 10
        }

        distanceToZone = Math.min(
          ...event.affected_locations.map((location) => haversineKm(
            ais.current_lon as number,
            ais.current_lat as number,
            Number(location.lon),
            Number(location.lat),
          )),
        )
      }

      routeImpacts.push({
        event_id: event.event_id,
        transport_key: route.transportKey,
        trpr_no: route.trprNo,
        severity: event.severity,
        match_score: Math.max(0, Math.min(100, score)),
        match_methods: matchMethods,
        exposure_status: exposureStatus,
        distance_to_zone_km: distanceToZone === null
          ? null
          : Math.round(distanceToZone),
        matched_location_codes: spatial.matchedCodes,
      })
    }

    impacts.push(...routeImpacts)

    if (routeImpacts.length > 0) {
      const best = [...routeImpacts].sort(
        (left, right) => right.match_score - left.match_score,
      )[0]

      impactedFeatures.push({
        ...feature,
        properties: {
          ...route.properties,
          mi_event_count: routeImpacts.length,
          mi_event_ids: routeImpacts.map((item) => item.event_id).join(','),
          mi_max_severity: best.severity,
          mi_match_score: best.match_score,
          mi_exposure_status: best.exposure_status,
        },
      })
    }
  }

  const impactedTransportKeys = new Set(
    impacts.map((impact) => impact.transport_key),
  )

  return {
    impacts,
    impactedRoutes: {
      type: 'FeatureCollection',
      features: impactedFeatures,
    },
    summary: {
      event_count: events.length,
      mappable_event_count: events.filter((event) => (
        event.affected_locations.length > 0
        || event.affected_lanes.length > 0
      )).length,
      impacted_transport_count: impactedTransportKeys.size,
      approaching_count: impacts.filter(
        (impact) => impact.exposure_status === 'APPROACHING',
      ).length,
      in_zone_count: impacts.filter(
        (impact) => impact.exposure_status === 'IN_ZONE',
      ).length,
    },
  }
}
