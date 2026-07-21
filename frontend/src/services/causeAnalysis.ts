import type {
  ScheduleEvent,
  TransportRecord,
} from '@/types/dashboard'
import type { RefinedMiEvent } from '@/types/mi'
import type { MiTransportImpact } from '@/types/miImpact'
import type {
  CauseAnalysisInput,
  CauseAnalysisResult,
  CauseCandidate,
  CauseConfidenceBand,
  CauseScoreBreakdown,
  CauseTimeRelation,
} from '@/types/causeAnalysis'

const DAY_MS = 24 * 60 * 60 * 1000
const MIN_CANDIDATE_SCORE = 30
const MAX_CANDIDATES_PER_SCHEDULE_EVENT = 3

const STOP_WORDS = new Set([
  'THE',
  'AND',
  'FOR',
  'WITH',
  'FROM',
  'EVENT',
  'RISK',
  'TRANSPORT',
  'LOGISTICS',
  'SCHEDULE',
  'ANOMALY',
  'CURRENT',
  'ACTIVE',
  'WATCH',
  'HIGH',
  'MEDIUM',
  'LOW',
  '지연',
  '운송',
  '일정',
  '이상',
  '발생',
  '영향',
  '가능성',
])

function finiteNumber(
  value: number | null | undefined,
  fallback = 0,
): number {
  return Number.isFinite(Number(value))
    ? Number(value)
    : fallback
}

function clamp(
  value: number,
  minimum: number,
  maximum: number,
): number {
  return Math.max(minimum, Math.min(maximum, value))
}

function parseMillis(
  value: string | null | undefined,
): number | null {
  if (!value) return null

  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : null
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return '-'

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(parsed)
}

function actualDelayDays(event: ScheduleEvent): number {
  return Math.max(
    0,
    finiteNumber(event.etd_net_delay_days),
    finiteNumber(event.eta_net_delay_days),
    finiteNumber(event.lead_time_variance_days),
  )
}

function confidenceBand(score: number): CauseConfidenceBand {
  if (score >= 75) return 'HIGH'
  if (score >= 55) return 'MEDIUM'
  return 'LOW'
}

function tokenize(values: Array<string | null | undefined>): Set<string> {
  const result = new Set<string>()

  for (const value of values) {
    const tokens = String(value || '')
      .toUpperCase()
      .match(/[A-Z0-9가-힣]+/g) || []

    for (const token of tokens) {
      if (token.length < 2 || STOP_WORDS.has(token)) continue
      result.add(token)
    }
  }

  return result
}

function intersectionCount(
  left: Set<string>,
  right: Set<string>,
): number {
  let count = 0

  for (const token of left) {
    if (right.has(token)) count += 1
  }

  return count
}

function scoreSpatial(
  impact: MiTransportImpact,
): {
  score: number
  evidence: string[]
} {
  let score = 0
  const evidence: string[] = []

  if (impact.match_methods.includes('IMPACT_ZONE')) {
    score += 22
    evidence.push('B-LAP Route가 MI 지리 영향권과 교차')
  }

  if (impact.match_methods.includes('LANE')) {
    score += 16
    evidence.push('POL·POD Lane 조건이 MI 영향 Lane과 일치')
  }

  if (
    impact.match_methods.includes('IMPACT_ZONE')
    && impact.match_methods.includes('LANE')
  ) {
    score += 5
  }

  if (
    impact.distance_to_zone_km !== null
    && impact.distance_to_zone_km <= 100
  ) {
    score += 3
    evidence.push(
      `현재 또는 Route 기준 영향권까지 약 ${impact.distance_to_zone_km}km`,
    )
  }

  return {
    score: clamp(score, 0, 30),
    evidence,
  }
}

function scoreTemporal(
  scheduleEvent: ScheduleEvent,
  transport: TransportRecord | undefined,
  miEvent: RefinedMiEvent,
): {
  score: number
  relation: CauseTimeRelation
  evidence: string[]
} {
  const anomalyTime = (
    parseMillis(scheduleEvent.detected_at)
    ?? parseMillis(transport?.current_eta)
    ?? parseMillis(transport?.current_etd)
  )

  const startTime = (
    parseMillis(miEvent.valid_from)
    ?? parseMillis(miEvent.first_seen_at)
  )

  const explicitEnd = parseMillis(miEvent.valid_to)
  const openEnded = (
    explicitEnd === null
    && miEvent.status !== 'RESOLVED'
  )
  const endTime = openEnded
    ? Number.POSITIVE_INFINITY
    : (
      explicitEnd
      ?? parseMillis(miEvent.last_updated_at)
    )

  if (
    anomalyTime === null
    || startTime === null
    || endTime === null
  ) {
    return {
      score: 8,
      relation: 'UNKNOWN',
      evidence: ['일정 또는 MI 시점 정보 일부가 없어 시간 일치는 보수적으로 평가'],
    }
  }

  if (anomalyTime >= startTime && anomalyTime <= endTime) {
    return {
      score: 25,
      relation: 'OVERLAP',
      evidence: [
        `일정 이상 시점이 MI 유효기간(${dateLabel(miEvent.valid_from)}~${dateLabel(miEvent.valid_to)})과 중첩`,
      ],
    }
  }

  const distanceMs = anomalyTime < startTime
    ? startTime - anomalyTime
    : anomalyTime - endTime
  const distanceDays = Math.max(
    0,
    Math.round(distanceMs / DAY_MS),
  )

  if (distanceDays <= 7) {
    return {
      score: 18,
      relation: 'NEAR',
      evidence: [`일정 이상과 MI 발생 시점 차이가 ${distanceDays}일 이내`],
    }
  }

  if (distanceDays <= 30) {
    return {
      score: 8,
      relation: anomalyTime < startTime ? 'BEFORE' : 'AFTER',
      evidence: [`일정 이상과 MI 발생 시점 차이가 약 ${distanceDays}일`],
    }
  }

  return {
    score: 0,
    relation: anomalyTime < startTime ? 'BEFORE' : 'AFTER',
    evidence: [`일정 이상과 MI 유효기간 차이가 ${distanceDays}일로 큼`],
  }
}

function scoreSignal(
  scheduleEvent: ScheduleEvent,
  miEvent: RefinedMiEvent,
): {
  score: number
  evidence: string[]
} {
  let score = 0
  const evidence: string[] = []
  const delayDays = actualDelayDays(scheduleEvent)

  const anomalyTokens = tokenize([
    scheduleEvent.event_type,
    scheduleEvent.primary_signal,
    ...scheduleEvent.signals,
    scheduleEvent.headline,
  ])
  const miTokens = tokenize([
    miEvent.event_type,
    ...miEvent.impact_types,
    ...miEvent.cause_keywords,
    miEvent.headline,
    miEvent.summary,
  ])

  const anomalyText = [
    scheduleEvent.event_type,
    scheduleEvent.primary_signal,
    ...scheduleEvent.signals,
    scheduleEvent.headline,
  ].join(' ').toUpperCase()

  const hasDelaySignal = (
    delayDays > 0
    || /ETA|ETD|DELAY|LEAD.?TIME|지연/.test(anomalyText)
  )
  const miDelayImpact = miEvent.impact_types.some(
    (value) => /DELAY|LEAD_TIME|SCHEDULE/.test(value.toUpperCase()),
  )

  if (hasDelaySignal && miDelayImpact) {
    score += 8
    evidence.push('MI 영향 유형이 B-LAP 지연·Lead Time 이상 신호와 일치')
  }

  const tokenMatches = intersectionCount(
    anomalyTokens,
    miTokens,
  )
  if (tokenMatches > 0) {
    const tokenScore = Math.min(6, tokenMatches * 2)
    score += tokenScore
    evidence.push(`원인·신호 키워드 ${tokenMatches}개 일치`)
  }

  const expected = miEvent.expected_delay_days
  if (delayDays > 0 && expected) {
    if (
      delayDays >= Math.max(0, expected.min - 2)
      && delayDays <= expected.max + 2
    ) {
      score += 6
      evidence.push(
        `실제 지연 ${delayDays}일이 MI 예상 지연 ${expected.min}~${expected.max}일과 유사`,
      )
    } else if (delayDays <= Math.max(1, expected.max * 1.5)) {
      score += 3
      evidence.push(
        `실제 지연 ${delayDays}일이 MI 예상 범위와 부분적으로 근접`,
      )
    }
  }

  return {
    score: clamp(score, 0, 20),
    evidence,
  }
}

function scoreAis(
  impact: MiTransportImpact,
  aisStatus: string,
): {
  score: number
  evidence: string[]
} {
  let score = 0
  const evidence: string[] = []

  if (impact.exposure_status === 'IN_ZONE') {
    score = 15
    evidence.push('AIS 선박이 현재 MI 영향권 내부')
  } else if (impact.exposure_status === 'APPROACHING') {
    score = 12
    evidence.push('AIS 선박이 MI 영향 구간에 접근 중')
  } else if (impact.exposure_status === 'ROUTE_EXPOSED') {
    score = 7
    evidence.push('AIS 현재 위치와 무관하게 계획 Route가 MI 영향권에 노출')
  } else {
    score = 3
    evidence.push('AIS 선박은 영향 구간을 이미 통과한 것으로 추정')
  }

  if (aisStatus === 'STALE') {
    score = Math.max(0, score - 3)
    evidence.push('AIS 위치가 오래되어 노출 판단 신뢰도를 하향')
  } else if (
    aisStatus === 'NO_SIGNAL'
    || aisStatus === 'ERROR'
  ) {
    score = Math.max(0, score - 5)
    evidence.push('AIS 위치 신호가 없어 Route 기준으로만 판단')
  }

  return {
    score: clamp(score, 0, 15),
    evidence,
  }
}

function scoreEventQuality(
  miEvent: RefinedMiEvent,
): {
  score: number
  evidence: string[]
} {
  let score = 0
  const evidence: string[] = []

  if (miEvent.severity === 'CRITICAL') score += 4
  else if (miEvent.severity === 'HIGH') score += 3
  else if (miEvent.severity === 'MEDIUM') score += 2
  else score += 1

  score += Math.round(
    clamp(miEvent.confidence, 0, 1) * 4,
  )

  if (miEvent.status === 'ACTIVE') score += 2
  else if (miEvent.status === 'WATCH') score += 1
  else if (miEvent.status === 'RESOLVED') score -= 3

  evidence.push(
    `MI ${miEvent.severity} · 신뢰도 ${Math.round(clamp(miEvent.confidence, 0, 1) * 100)}% · ${miEvent.status}`,
  )

  return {
    score: clamp(score, 0, 10),
    evidence,
  }
}

function unique(values: string[]): string[] {
  return [...new Set(
    values.map((value) => value.trim()).filter(Boolean),
  )]
}

function recommendedActions(
  scheduleEvent: ScheduleEvent,
  miEvent: RefinedMiEvent,
  impact: MiTransportImpact,
): string[] {
  const actions = [...miEvent.recommended_actions]
  const delayDays = actualDelayDays(scheduleEvent)
  const expectedMaximum = miEvent.expected_delay_days?.max ?? 0

  if (impact.exposure_status === 'IN_ZONE') {
    actions.push('선사·포워더에 현재 운항 상태와 최신 ETA를 즉시 재확인')
  } else if (impact.exposure_status === 'APPROACHING') {
    actions.push('영향 구간 진입 전 우회 여부와 대체 Route를 확인')
  }

  if (
    delayDays > 0
    && expectedMaximum > 0
    && delayDays > expectedMaximum
  ) {
    actions.push('MI 예상치를 초과한 지연은 통관·선복·내부 운영 원인을 추가 확인')
  }

  actions.push('원인 확정 전 관련 운송 일정 변경이력과 증빙을 확인')

  return unique(actions).slice(0, 5)
}

function buildCandidate(
  scheduleEvent: ScheduleEvent,
  transport: TransportRecord | undefined,
  miEvent: RefinedMiEvent,
  impact: MiTransportImpact,
  aisStatus: string,
): CauseCandidate {
  const spatial = scoreSpatial(impact)
  const temporal = scoreTemporal(
    scheduleEvent,
    transport,
    miEvent,
  )
  const signal = scoreSignal(scheduleEvent, miEvent)
  const ais = scoreAis(impact, aisStatus)
  const eventQuality = scoreEventQuality(miEvent)

  const breakdown: CauseScoreBreakdown = {
    spatial: spatial.score,
    temporal: temporal.score,
    signal: signal.score,
    ais: ais.score,
    event_quality: eventQuality.score,
  }

  const totalScore = clamp(
    Object.values(breakdown).reduce(
      (sum, value) => sum + value,
      0,
    ),
    0,
    100,
  )

  return {
    candidate_id: (
      `${scheduleEvent.event_id}|${miEvent.event_id}`
    ),
    schedule_event_id: scheduleEvent.event_id,
    transport_key: scheduleEvent.transport_key,
    trpr_no: scheduleEvent.trpr_no,
    schedule_headline: scheduleEvent.headline,
    schedule_severity: scheduleEvent.severity,
    schedule_detected_at: scheduleEvent.detected_at,
    actual_delay_days: actualDelayDays(scheduleEvent),

    mi_event_id: miEvent.event_id,
    mi_headline: miEvent.headline,
    mi_event_type: miEvent.event_type,
    mi_severity: miEvent.severity,
    mi_status: miEvent.status,
    mi_valid_from: miEvent.valid_from,
    mi_valid_to: miEvent.valid_to,

    total_score: totalScore,
    confidence_band: confidenceBand(totalScore),
    score_breakdown: breakdown,
    time_relation: temporal.relation,
    match_methods: [...impact.match_methods],
    exposure_status: impact.exposure_status,
    distance_to_zone_km: impact.distance_to_zone_km,

    evidence: unique([
      ...spatial.evidence,
      ...temporal.evidence,
      ...signal.evidence,
      ...ais.evidence,
      ...eventQuality.evidence,
    ]),
    recommended_actions: recommendedActions(
      scheduleEvent,
      miEvent,
      impact,
    ),
    decision: 'PENDING',
  }
}

export function analyzeCauseCandidates(
  input: CauseAnalysisInput,
): CauseAnalysisResult {
  const transportByKey = new Map(
    input.transports.map((transport) => [
      transport.transport_key,
      transport,
    ]),
  )
  const miEventById = new Map(
    input.miEvents.map((event) => [
      event.event_id,
      event,
    ]),
  )
  const impactsByTransport = new Map<
    string,
    MiTransportImpact[]
  >()

  for (const impact of input.miImpacts) {
    const values = impactsByTransport.get(
      impact.transport_key,
    ) ?? []
    values.push(impact)
    impactsByTransport.set(
      impact.transport_key,
      values,
    )
  }

  const aisStatusByTransport = new Map(
    input.aisItems
      .filter((item) => Boolean(item.matched_transport_key))
      .map((item) => [
        item.matched_transport_key as string,
        item.position_status,
      ]),
  )

  const candidates: CauseCandidate[] = []

  for (const scheduleEvent of input.scheduleEvents) {
    const impacts = impactsByTransport.get(
      scheduleEvent.transport_key,
    ) ?? []
    const transport = transportByKey.get(
      scheduleEvent.transport_key,
    )
    const eventCandidates: CauseCandidate[] = []

    for (const impact of impacts) {
      const miEvent = miEventById.get(impact.event_id)
      if (!miEvent || miEvent.status === 'RESOLVED') continue

      const candidate = buildCandidate(
        scheduleEvent,
        transport,
        miEvent,
        impact,
        aisStatusByTransport.get(
          scheduleEvent.transport_key,
        ) ?? 'UNKNOWN',
      )

      if (candidate.total_score >= MIN_CANDIDATE_SCORE) {
        eventCandidates.push(candidate)
      }
    }

    eventCandidates.sort(
      (left, right) => right.total_score - left.total_score,
    )

    candidates.push(
      ...eventCandidates.slice(
        0,
        MAX_CANDIDATES_PER_SCHEDULE_EVENT,
      ),
    )
  }

  candidates.sort((left, right) => {
    if (right.total_score !== left.total_score) {
      return right.total_score - left.total_score
    }

    return left.transport_key.localeCompare(
      right.transport_key,
    )
  })

  const anomalyTransportKeys = new Set(
    input.scheduleEvents.map(
      (event) => event.transport_key,
    ),
  )
  const candidateTransportKeys = new Set(
    candidates.map(
      (candidate) => candidate.transport_key,
    ),
  )

  return {
    candidates,
    summary: {
      anomaly_event_count: input.scheduleEvents.length,
      anomaly_transport_count: anomalyTransportKeys.size,
      candidate_count: candidates.length,
      candidate_transport_count: candidateTransportKeys.size,
      high_confidence_count: candidates.filter(
        (candidate) => (
          candidate.confidence_band === 'HIGH'
        ),
      ).length,
      medium_confidence_count: candidates.filter(
        (candidate) => (
          candidate.confidence_band === 'MEDIUM'
        ),
      ).length,
      no_candidate_transport_count: Math.max(
        0,
        anomalyTransportKeys.size - candidateTransportKeys.size,
      ),
    },
  }
}
