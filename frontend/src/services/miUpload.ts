import type {
  AisMapItem,
  GeoJsonFeatureCollection,
  MiCauseCandidate,
  MiEvent,
  MiImpactSummary,
  MiSeverity,
  MiTransportImpact,
  MiUploadResult,
  ScheduleTimelineResponse,
} from '@/types/dashboard'

const EARTH_RADIUS_KM = 6371.0088

const knownLocations: Record<
  string,
  { code: string; name: string; lat: number; lon: number; radius_km: number }
> = {
  'strait of hormuz': {
    code: 'STRAIT_OF_HORMUZ',
    name: 'Strait of Hormuz',
    lat: 26.57,
    lon: 56.25,
    radius_km: 250,
  },
  hormuz: {
    code: 'STRAIT_OF_HORMUZ',
    name: 'Strait of Hormuz',
    lat: 26.57,
    lon: 56.25,
    radius_km: 250,
  },
  'suez canal': {
    code: 'SUEZ_CANAL',
    name: 'Suez Canal',
    lat: 30.46,
    lon: 32.35,
    radius_km: 160,
  },
  suez: {
    code: 'SUEZ_CANAL',
    name: 'Suez Canal',
    lat: 30.46,
    lon: 32.35,
    radius_km: 160,
  },
  'red sea': {
    code: 'RED_SEA',
    name: 'Red Sea',
    lat: 20.0,
    lon: 38.5,
    radius_km: 420,
  },
  'bab el mandeb': {
    code: 'BAB_EL_MANDEB',
    name: 'Bab-el-Mandeb',
    lat: 12.58,
    lon: 43.33,
    radius_km: 180,
  },
  'bab-el-mandeb': {
    code: 'BAB_EL_MANDEB',
    name: 'Bab-el-Mandeb',
    lat: 12.58,
    lon: 43.33,
    radius_km: 180,
  },
  'cape of good hope': {
    code: 'CAPE_OF_GOOD_HOPE',
    name: 'Cape of Good Hope',
    lat: -34.36,
    lon: 18.47,
    radius_km: 260,
  },
  'panama canal': {
    code: 'PANAMA_CANAL',
    name: 'Panama Canal',
    lat: 9.08,
    lon: -79.68,
    radius_km: 180,
  },
  panama: {
    code: 'PANAMA_CANAL',
    name: 'Panama Canal',
    lat: 9.08,
    lon: -79.68,
    radius_km: 180,
  },
  rotterdam: {
    code: 'NLRTM',
    name: 'Rotterdam',
    lat: 51.92,
    lon: 4.48,
    radius_km: 100,
  },
  hamburg: {
    code: 'DEHAM',
    name: 'Hamburg',
    lat: 53.55,
    lon: 9.99,
    radius_km: 100,
  },
  bremerhaven: {
    code: 'DEBRV',
    name: 'Bremerhaven',
    lat: 53.54,
    lon: 8.58,
    radius_km: 100,
  },
  antwerp: {
    code: 'BEANR',
    name: 'Antwerp',
    lat: 51.26,
    lon: 4.40,
    radius_km: 100,
  },
  singapore: {
    code: 'SGSIN',
    name: 'Singapore',
    lat: 1.26,
    lon: 103.84,
    radius_km: 120,
  },
  shanghai: {
    code: 'CNSHA',
    name: 'Shanghai',
    lat: 31.23,
    lon: 121.47,
    radius_km: 100,
  },
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => asString(item))
    .filter(Boolean)
}

function asNumber(value: unknown, fallback = 0): number {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function normalizeSeverity(value: unknown): MiSeverity {
  const severity = asString(value).toUpperCase()
  if (severity === 'CRITICAL') return 'CRITICAL'
  if (severity === 'HIGH') return 'HIGH'
  if (severity === 'MEDIUM') return 'MEDIUM'
  return 'LOW'
}

function normalizeStatus(value: unknown): MiEvent['status'] {
  const status = asString(value).toUpperCase()
  if (status === 'RESOLVED') return 'RESOLVED'
  if (status === 'IMPROVING') return 'IMPROVING'
  if (status === 'WATCH') return 'WATCH'
  return 'ACTIVE'
}

function legacyRegionToLocation(region: string) {
  const normalized = region.trim().toLowerCase()
  const exact = knownLocations[normalized]
  if (exact) return exact

  for (const [key, location] of Object.entries(knownLocations)) {
    if (normalized.includes(key) || key.includes(normalized)) {
      return location
    }
  }

  return null
}

function normalizeCanonicalEvent(raw: Record<string, unknown>, index: number): MiEvent {
  const locations = Array.isArray(raw.affected_locations)
    ? raw.affected_locations
        .map((value) => {
          if (!value || typeof value !== 'object') return null
          const item = value as Record<string, unknown>
          const lat = Number(item.lat)
          const lon = Number(item.lon)
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null

          return {
            location_type: (asString(item.location_type).toUpperCase()
              || 'REGION') as MiEvent['affected_locations'][number]['location_type'],
            code: asString(item.code) || `LOC-${index + 1}`,
            name: asString(item.name) || asString(item.code) || 'Unknown location',
            lat,
            lon,
            radius_km: Math.max(10, asNumber(item.radius_km, 150)),
          }
        })
        .filter((value): value is NonNullable<typeof value> => Boolean(value))
    : []

  const lanes = Array.isArray(raw.affected_lanes)
    ? raw.affected_lanes
        .map((value) => {
          if (!value || typeof value !== 'object') return null
          const item = value as Record<string, unknown>
          return {
            pol_codes: asStringArray(item.pol_codes).map((x) => x.toUpperCase()),
            pod_codes: asStringArray(item.pod_codes).map((x) => x.toUpperCase()),
            origin_regions: asStringArray(item.origin_regions),
            destination_regions: asStringArray(item.destination_regions),
            corridor: asString(item.corridor) || null,
          }
        })
        .filter((value): value is NonNullable<typeof value> => Boolean(value))
    : []

  const evidence = Array.isArray(raw.evidence)
    ? raw.evidence
        .map((value) => {
          if (!value || typeof value !== 'object') return null
          const item = value as Record<string, unknown>
          return {
            title: asString(item.title),
            url: asString(item.url),
            source: asString(item.source),
            published_at: asString(item.published_at) || null,
          }
        })
        .filter((value): value is NonNullable<typeof value> => Boolean(value))
    : []

  const expected = raw.expected_delay_days
  let expectedDelay: { min: number; max: number } | null = null
  if (expected && typeof expected === 'object') {
    const item = expected as Record<string, unknown>
    expectedDelay = {
      min: Math.max(0, asNumber(item.min)),
      max: Math.max(0, asNumber(item.max)),
    }
  }

  const now = new Date().toISOString()

  return {
    event_id: asString(raw.event_id) || `MI-UPLOAD-${String(index + 1).padStart(3, '0')}`,
    cluster_key: asString(raw.cluster_key) || asString(raw.event_id) || `cluster-${index + 1}`,
    source_type: asString(raw.source_type).toUpperCase() === 'INTERNAL_MI'
      ? 'INTERNAL_MI'
      : 'EXTERNAL_MI',
    status: normalizeStatus(raw.status),
    event_type: asString(raw.event_type) || asString(raw.risk_category) || 'OTHER',
    severity: normalizeSeverity(raw.severity),
    confidence: Math.min(1, Math.max(0, asNumber(raw.confidence, 0.7))),
    headline: asString(raw.headline) || `MI Event ${index + 1}`,
    summary: asString(raw.summary),
    first_seen_at: asString(raw.first_seen_at) || asString(raw.event_date) || now,
    last_updated_at: asString(raw.last_updated_at) || now,
    valid_from: asString(raw.valid_from) || asString(raw.event_date) || now,
    valid_to: asString(raw.valid_to) || null,
    transport_modes: asStringArray(raw.transport_modes).map((x) => x.toUpperCase()),
    affected_corridors: asStringArray(raw.affected_corridors),
    affected_locations: locations,
    affected_lanes: lanes,
    expected_delay_days: expectedDelay,
    impact_types: asStringArray(raw.impact_types),
    cause_keywords: asStringArray(raw.cause_keywords),
    evidence,
  }
}

function convertLegacyEvent(raw: Record<string, unknown>, index: number): MiEvent {
  const regions = asStringArray(raw.affected_regions)
  const locations = regions
    .map((region) => legacyRegionToLocation(region))
    .filter((value): value is NonNullable<typeof value> => Boolean(value))
    .map((location) => ({
      location_type: 'REGION' as const,
      ...location,
    }))

  const eventDate = asString(raw.event_date) || new Date().toISOString()

  return normalizeCanonicalEvent({
    event_id: raw.event_id,
    cluster_key: raw.event_id,
    source_type: 'EXTERNAL_MI',
    status: 'ACTIVE',
    event_type: raw.risk_category,
    severity: raw.severity,
    confidence: 0.65,
    headline: raw.headline,
    summary: raw.summary,
    first_seen_at: eventDate,
    last_updated_at: eventDate,
    valid_from: eventDate,
    valid_to: null,
    transport_modes: ['SEA'],
    affected_corridors: raw.affected_corridors,
    affected_locations: locations,
    affected_lanes: [],
    expected_delay_days:
      raw.estimated_delay_days === null
        ? null
        : {
            min: asNumber(raw.estimated_delay_days),
            max: asNumber(raw.estimated_delay_days),
          },
    impact_types: ['DELAY'],
    cause_keywords: regions,
    evidence: [
      {
        title: asString(raw.source_title),
        url: asString(raw.source_url),
        source: '',
        published_at: eventDate,
      },
    ],
  }, index)
}

export async function parseMiUpload(file: File): Promise<MiUploadResult> {
  const rawText = await file.text()
  let parsed: unknown

  try {
    parsed = JSON.parse(rawText)
  } catch {
    throw new Error('MI 파일이 올바른 JSON 형식이 아닙니다.')
  }

  let rawEvents: unknown[] = []
  let schemaVersion = 'legacy'
  let generatedAt: string | null = null

  if (Array.isArray(parsed)) {
    rawEvents = parsed
  } else if (parsed && typeof parsed === 'object') {
    const root = parsed as Record<string, unknown>
    if (Array.isArray(root.events)) {
      rawEvents = root.events
      schemaVersion = asString(root.schema_version) || '1.0'
      generatedAt = asString(root.generated_at) || null
    }
  }

  if (rawEvents.length === 0) {
    throw new Error('MI 이벤트 배열을 찾지 못했습니다.')
  }

  const first = rawEvents[0]
  if (!first || typeof first !== 'object') {
    throw new Error('MI 이벤트 구조가 올바르지 않습니다.')
  }

  const firstRecord = first as Record<string, unknown>
  const isCanonical =
    'affected_locations' in firstRecord
    || 'cluster_key' in firstRecord
    || 'source_type' in firstRecord
  const isLegacy =
    'affected_regions' in firstRecord
    && 'affected_corridors' in firstRecord

  if (!isCanonical && !isLegacy) {
    if ('title' in firstRecord && 'url' in firstRecord) {
      throw new Error(
        'all_news.json은 원문 수집 파일입니다. Gemini가 생성한 mi_events.json을 업로드하세요.',
      )
    }
    throw new Error('지원하지 않는 MI JSON 구조입니다.')
  }

  const events = rawEvents
    .map((value, index) => {
      if (!value || typeof value !== 'object') return null
      return isCanonical
        ? normalizeCanonicalEvent(value as Record<string, unknown>, index)
        : convertLegacyEvent(value as Record<string, unknown>, index)
    })
    .filter((value): value is MiEvent => Boolean(value))

  const warnings: string[] = []
  const unmappable = events.filter(
    (event) =>
      event.affected_locations.length === 0
      && event.affected_lanes.length === 0,
  ).length

  if (unmappable > 0) {
    warnings.push(
      `${unmappable}개 이벤트는 위치 또는 Lane 정보가 없어 자동 영향 매핑에서 제외됩니다.`,
    )
  }

  return {
    schema_version: schemaVersion,
    generated_at: generatedAt,
    file_name: file.name,
    events,
    warnings,
  }
}

function degreesToRadians(value: number) {
  return (value * Math.PI) / 180
}

function haversineKm(
  lon1: number,
  lat1: number,
  lon2: number,
  lat2: number,
) {
  const dLat = degreesToRadians(lat2 - lat1)
  const dLon = degreesToRadians(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2
    + Math.cos(degreesToRadians(lat1))
      * Math.cos(degreesToRadians(lat2))
      * Math.sin(dLon / 2) ** 2

  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)))
}

function circlePolygon(
  lon: number,
  lat: number,
  radiusKm: number,
  steps = 64,
): number[][] {
  const coordinates: number[][] = []
  const angularDistance = radiusKm / EARTH_RADIUS_KM
  const latRad = degreesToRadians(lat)
  const lonRad = degreesToRadians(lon)

  for (let index = 0; index <= steps; index += 1) {
    const bearing = (2 * Math.PI * index) / steps
    const pointLat = Math.asin(
      Math.sin(latRad) * Math.cos(angularDistance)
      + Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearing),
    )
    const pointLon =
      lonRad
      + Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latRad),
        Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(pointLat),
      )

    coordinates.push([
      (pointLon * 180) / Math.PI,
      (pointLat * 180) / Math.PI,
    ])
  }

  return coordinates
}

export function buildMiZoneGeoJson(events: MiEvent[]): GeoJsonFeatureCollection {
  return {
    type: 'FeatureCollection',
    features: events.flatMap((event) =>
      event.affected_locations.map((location) => ({
        type: 'Feature',
        id: `${event.event_id}|${location.code}`,
        properties: {
          event_id: event.event_id,
          headline: event.headline,
          severity: event.severity,
          status: event.status,
          location_code: location.code,
          location_name: location.name,
          radius_km: location.radius_km,
          expected_delay_min: event.expected_delay_days?.min ?? 0,
          expected_delay_max: event.expected_delay_days?.max ?? 0,
        },
        geometry: {
          type: 'Polygon',
          coordinates: [
            circlePolygon(
              location.lon,
              location.lat,
              location.radius_km,
            ),
          ],
        },
      })),
    ),
  }
}

function routeCoordinates(feature: Record<string, unknown>): number[][] {
  const geometry = feature.geometry
  if (!geometry || typeof geometry !== 'object') return []

  const typed = geometry as Record<string, unknown>
  if (typed.type !== 'LineString' || !Array.isArray(typed.coordinates)) {
    return []
  }

  return typed.coordinates
    .filter(
      (value) =>
        Array.isArray(value)
        && value.length >= 2
        && Number.isFinite(Number(value[0]))
        && Number.isFinite(Number(value[1])),
    )
    .map((value) => [
      Number((value as unknown[])[0]),
      Number((value as unknown[])[1]),
    ])
}

function routeProperties(feature: Record<string, unknown>) {
  const properties =
    feature.properties && typeof feature.properties === 'object'
      ? (feature.properties as Record<string, unknown>)
      : {}

  return {
    properties,
    transportKey: asString(properties.transport_key),
    trprNo: asString(properties.trpr_no),
    pol: asString(properties.pol).toUpperCase(),
    pod: asString(properties.pod).toUpperCase(),
  }
}

function locationRouteMatch(
  coordinates: number[][],
  event: MiEvent,
) {
  const matchedCodes: string[] = []
  let minDistance = Number.POSITIVE_INFINITY
  let zoneRouteIndex = -1

  for (const location of event.affected_locations) {
    coordinates.forEach((coordinate, index) => {
      const distance = haversineKm(
        coordinate[0],
        coordinate[1],
        location.lon,
        location.lat,
      )
      if (distance < minDistance) {
        minDistance = distance
        zoneRouteIndex = index
      }
      if (distance <= location.radius_km) {
        matchedCodes.push(location.code)
      }
    })
  }

  return {
    matched: matchedCodes.length > 0,
    matchedCodes: [...new Set(matchedCodes)],
    minDistance: Number.isFinite(minDistance) ? minDistance : null,
    zoneRouteIndex,
  }
}

function laneRouteMatch(
  pol: string,
  pod: string,
  event: MiEvent,
) {
  for (const lane of event.affected_lanes) {
    const polCodes = lane.pol_codes ?? []
    const podCodes = lane.pod_codes ?? []

    const polMatch = polCodes.length === 0 || polCodes.includes(pol)
    const podMatch = podCodes.length === 0 || podCodes.includes(pod)

    if (polMatch && podMatch) return true
  }

  return false
}

function severityWeight(severity: MiSeverity) {
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
  events: MiEvent[],
  routes: GeoJsonFeatureCollection,
  aisItems: AisMapItem[],
): {
  impacts: MiTransportImpact[]
  impactedRoutes: GeoJsonFeatureCollection
  summary: MiImpactSummary
} {
  const impacts: MiTransportImpact[] = []
  const impactedFeatures: Record<string, unknown>[] = []
  const aisByTransport = new Map(
    aisItems
      .filter((item) => item.matched_transport_key)
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

      const methods: string[] = []
      let score = severityWeight(event.severity)

      if (spatial.matched) {
        methods.push('IMPACT_ZONE')
        score += 60
      }
      if (laneMatched) {
        methods.push('LANE')
        score += 45
      }
      if (event.status === 'ACTIVE') score += 10
      score += Math.round(event.confidence * 10)

      let exposureStatus: MiTransportImpact['exposure_status'] =
        'ROUTE_EXPOSED'
      let distanceToZone = spatial.minDistance
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

        const insideZone = event.affected_locations.some(
          (location) =>
            haversineKm(
              ais.current_lon as number,
              ais.current_lat as number,
              location.lon,
              location.lat,
            ) <= location.radius_km,
        )

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
          ...event.affected_locations.map((location) =>
            haversineKm(
              ais.current_lon as number,
              ais.current_lat as number,
              location.lon,
              location.lat,
            ),
          ),
        )
      }

      routeImpacts.push({
        event_id: event.event_id,
        transport_key: route.transportKey,
        trpr_no: route.trprNo,
        severity: event.severity,
        match_score: Math.max(0, Math.min(100, score)),
        match_methods: methods,
        exposure_status: exposureStatus,
        distance_to_zone_km:
          distanceToZone === null
            ? null
            : Math.round(distanceToZone),
        matched_location_codes: spatial.matchedCodes,
      })
    }

    impacts.push(...routeImpacts)

    if (routeImpacts.length > 0) {
      const best = [...routeImpacts].sort(
        (a, b) => b.match_score - a.match_score,
      )[0]

      impactedFeatures.push({
        ...feature,
        properties: {
          ...(feature.properties as Record<string, unknown>),
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
      mappable_event_count: events.filter(
        (event) =>
          event.affected_locations.length > 0
          || event.affected_lanes.length > 0,
      ).length,
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

function parseDate(value: string | null | undefined) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function buildMiCauseCandidates(
  transportKey: string,
  events: MiEvent[],
  impacts: MiTransportImpact[],
  timeline: ScheduleTimelineResponse | null,
): MiCauseCandidate[] {
  const eventMap = new Map(events.map((event) => [event.event_id, event]))
  const changeTimes = [
    ...(timeline?.eta.events ?? []),
    ...(timeline?.etd.events ?? []),
  ]
    .map((item) => parseDate(item.changed_at))
    .filter((item): item is Date => Boolean(item))

  return impacts
    .filter((impact) => impact.transport_key === transportKey)
    .map((impact) => {
      const event = eventMap.get(impact.event_id)
      if (!event) return null

      let causeScore = impact.match_score
      const reasons = [
        impact.match_methods.includes('IMPACT_ZONE')
          ? '운송경로가 MI 영향권과 교차'
          : 'POL/POD Lane 조건 일치',
      ]

      const validFrom = parseDate(event.valid_from)
      const validTo =
        parseDate(event.valid_to)
        ?? new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)

      const temporalOverlap = changeTimes.some((changedAt) => {
        if (!validFrom || !validTo) return false
        const marginBefore = new Date(
          validFrom.getTime() - 24 * 60 * 60 * 1000,
        )
        const marginAfter = new Date(
          validTo.getTime() + 7 * 24 * 60 * 60 * 1000,
        )
        return changedAt >= marginBefore && changedAt <= marginAfter
      })

      if (temporalOverlap) {
        causeScore += 15
        reasons.push('일정 변경시각과 MI 유효기간 중첩')
      }

      if (impact.exposure_status === 'IN_ZONE') {
        causeScore += 10
        reasons.push('AIS 현재 위치가 영향권 내부')
      } else if (impact.exposure_status === 'APPROACHING') {
        causeScore += 7
        reasons.push('AIS 기준 영향권 접근 예상')
      }

      return {
        event,
        impact,
        cause_score: Math.min(100, causeScore),
        reasons,
      }
    })
    .filter((value): value is MiCauseCandidate => Boolean(value))
    .sort((a, b) => b.cause_score - a.cause_score)
}
