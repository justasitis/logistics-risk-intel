import { computed, reactive, watch } from 'vue'
import {
  fetchSharePointExternalCandidates,
  getMiAiHealth,
  refineExternalCandidates,
  submitMiReview,
  type SharePointExternalMiResponse,
} from '../services/miAiApi'
import {
  fetchMiRun,
  readSavedAnalysisId,
  removeSavedAnalysisId,
  saveAnalysisId,
  type StoredMiRun,
} from '../services/miRunPersistence'
import type {
  CompanyCode,
  ExternalMiCandidateEnvelope,
  RefinedMiEvent,
  ReviewResponse,
  ReviewStatus,
} from '../types/mi'

import { companyCodes } from './useCompanies'

// 법인 목록은 useCompanies(/api/config/companies) 공유 소스를 따른다.
// 사용자가 직접 선택을 바꾸기 전까지는 전체 법인 선택을 기본값으로 동기화한다.
let companySelectionTouched = false

export type MiWorkspaceStatus =
  | 'EMPTY'
  | 'UPLOADED'
  | 'REFINING'
  | 'REFINED'
  | 'REVIEWED'
  | 'ERROR'

export type MiRecoveryStatus =
  | 'IDLE'
  | 'EMPTY'
  | 'RESTORING'
  | 'RESTORED'
  | 'ERROR'

export type CandidateSource =
  | 'NONE'
  | 'LOCAL_FILE'
  | 'SHAREPOINT'

export type SharePointCandidateStatus =
  | 'IDLE'
  | 'LOADING'
  | 'LOADED'
  | 'NOT_FOUND'
  | 'UPDATE_AVAILABLE'
  | 'ERROR'

const state = reactive({
  status: 'EMPTY' as MiWorkspaceStatus,
  candidateEnvelope: null as ExternalMiCandidateEnvelope | null,
  candidateSource: 'NONE' as CandidateSource,
  candidateSourceSha256: '',
  analysisId: '',
  refinedEvents: [] as RefinedMiEvent[],
  reviewResult: null as ReviewResponse | null,
  selectedCompanies: [] as CompanyCode[],
  supplementalContext: '',
  apiConfigured: false,
  error: '',

  savedAnalysisId: readSavedAnalysisId(),
  recoveryStatus: 'IDLE' as MiRecoveryStatus,
  recoveryMessage: '',

  sharePointStatus: 'IDLE' as SharePointCandidateStatus,
  sharePointMessage: '',
  sharePointError: '',
  sharePointRoot: '',
  sharePointSourceFile: '',
  sharePointSourceFileName: '',
  sharePointModifiedAt: '',
  sharePointSizeBytes: 0,
  sharePointSha256: '',
  sharePointCandidateCount: 0,
  sharePointWarnings: [] as string[],
})

let initializationPromise: Promise<void> | null = null
let sharePointController: AbortController | null = null
let pendingSharePointResponse: SharePointExternalMiResponse | null = null

// 공유 법인 목록이 로드/변경되면 전체 법인 선택을 기본값으로 맞춘다
watch(
  companyCodes,
  (codes) => {
    if (!companySelectionTouched) {
      state.selectedCompanies = [...codes]
    }
  },
  { immediate: true },
)

function toggleCompanySelection(company: CompanyCode): void {
  companySelectionTouched = true
  const index = state.selectedCompanies.indexOf(company)
  if (index >= 0) state.selectedCompanies.splice(index, 1)
  else state.selectedCompanies.push(company)
}

function validateEnvelope(value: unknown): ExternalMiCandidateEnvelope {
  if (!value || typeof value !== 'object') {
    throw new Error('JSON 최상위 구조가 object가 아닙니다.')
  }

  const envelope = value as ExternalMiCandidateEnvelope

  if (envelope.source_stage !== 'EXTERNAL_GEMINI_CANDIDATES') {
    throw new Error(
      'source_stage가 EXTERNAL_GEMINI_CANDIDATES가 아닙니다.',
    )
  }

  if (!Array.isArray(envelope.candidates)) {
    throw new Error('candidates 배열이 없습니다.')
  }

  return envelope
}

function isReviewStatus(value: unknown): value is ReviewStatus {
  return [
    'PENDING',
    'APPROVED',
    'EDITED',
    'REJECTED',
  ].includes(String(value))
}

function normalizeRecoveredEvents(
  run: StoredMiRun,
): RefinedMiEvent[] {
  if (Array.isArray(run.review_events)) {
    return run.review_events.map((event) => ({
      ...event,
      review_status: isReviewStatus(event.review_status)
        ? event.review_status
        : 'PENDING',
    }))
  }

  const canonicalEvents = run.canonical_payload?.events

  if (!Array.isArray(canonicalEvents)) {
    return []
  }

  return canonicalEvents.map((event) => ({
    ...event,
    review_status: isReviewStatus(event.review_status)
      ? event.review_status
      : 'APPROVED',
  }))
}

function hydrateReviewedRun(
  requestedAnalysisId: string,
  run: StoredMiRun,
): void {
  const canonicalPayload = run.canonical_payload

  if (
    run.stage !== 'REVIEWED'
    || !canonicalPayload
    || !Array.isArray(canonicalPayload.events)
  ) {
    throw new Error(
      '해당 Run은 아직 REVIEWED 상태가 아니거나 승인 Payload가 없습니다.',
    )
  }

  const analysisId = (
    canonicalPayload.analysis_id
    || requestedAnalysisId
  ).trim()

  const recoveredEvents = normalizeRecoveredEvents(run)
  const rejectedCount = recoveredEvents.filter(
    (event) => event.review_status === 'REJECTED',
  ).length

  state.candidateEnvelope = (
    run.request?.candidate_envelope
    || state.candidateEnvelope
  )
  state.analysisId = analysisId
  state.refinedEvents = recoveredEvents
  state.reviewResult = {
    analysis_id: analysisId,
    approved_count: canonicalPayload.events.length,
    rejected_count: rejectedCount,
    canonical_payload: canonicalPayload,
  }
  state.status = 'REVIEWED'
  state.error = ''
}

function resetAnalysisForCandidate(): void {
  state.refinedEvents = []
  state.analysisId = ''
  state.reviewResult = null
  state.status = 'UPLOADED'
  state.error = ''
}

function applyCandidateEnvelope(
  envelope: ExternalMiCandidateEnvelope,
  source: CandidateSource,
  sha256 = '',
): void {
  state.candidateEnvelope = validateEnvelope(envelope)
  state.candidateSource = source
  state.candidateSourceSha256 = sha256
  resetAnalysisForCandidate()
}

async function loadCandidateFile(file: File): Promise<void> {
  state.error = ''
  const text = await file.text()
  applyCandidateEnvelope(
    validateEnvelope(JSON.parse(text)),
    'LOCAL_FILE',
  )

  if (state.sharePointStatus === 'UPDATE_AVAILABLE') {
    state.sharePointMessage = (
      '로컬 JSON을 사용 중입니다. SharePoint 파일로 바꾸려면 '
      + '“새 SharePoint 파일로 교체”를 누르세요.'
    )
  }
}

function updateSharePointMetadata(
  response: SharePointExternalMiResponse,
): void {
  state.sharePointRoot = response.source_root
  state.sharePointSourceFile = response.source_file || ''
  state.sharePointSourceFileName = response.source_file_name || ''
  state.sharePointModifiedAt = response.source_modified_at || ''
  state.sharePointSizeBytes = response.source_size_bytes
  state.sharePointSha256 = response.source_sha256 || ''
  state.sharePointCandidateCount = response.candidate_count
  state.sharePointWarnings = [...response.warnings]
}

function isSameCandidateEnvelope(
  left: ExternalMiCandidateEnvelope | null,
  right: ExternalMiCandidateEnvelope,
): boolean {
  if (!left) return false

  if (
    left.generated_at
    && right.generated_at
    && left.generated_at !== right.generated_at
  ) {
    return false
  }

  const leftIds = left.candidates.map(
    (candidate) => candidate.candidate_id,
  )
  const rightIds = right.candidates.map(
    (candidate) => candidate.candidate_id,
  )

  return (
    left.source_stage === right.source_stage
    && left.generation_status === right.generation_status
    && leftIds.length === rightIds.length
    && leftIds.every((value, index) => value === rightIds[index])
  )
}

function isWorkspaceLocked(): boolean {
  return [
    'REFINING',
    'REFINED',
    'REVIEWED',
  ].includes(state.status)
}

async function loadSharePointCandidates(
  force = false,
  silent = false,
): Promise<void> {
  sharePointController?.abort()
  const controller = new AbortController()
  sharePointController = controller

  state.sharePointStatus = 'LOADING'
  state.sharePointError = ''
  if (!silent) state.sharePointMessage = 'SharePoint 파일 확인 중...'

  try {
    const response = await fetchSharePointExternalCandidates(
      controller.signal,
    )
    updateSharePointMetadata(response)

    if (!response.found || !response.candidate_envelope) {
      pendingSharePointResponse = null
      state.sharePointStatus = 'NOT_FOUND'
      state.sharePointMessage = (
        'external_mi_candidates.json을 찾지 못했습니다.'
      )
      return
    }

    const sameFile = Boolean(
      response.source_sha256
      && state.candidateSource === 'SHAREPOINT'
      && state.candidateSourceSha256 === response.source_sha256
    )
    const sameEnvelope = isSameCandidateEnvelope(
      state.candidateEnvelope,
      response.candidate_envelope,
    )

    if (sameFile || sameEnvelope) {
      if (state.candidateSource === 'NONE') {
        state.candidateSource = 'SHAREPOINT'
        state.candidateSourceSha256 = response.source_sha256 || ''
      }
      pendingSharePointResponse = null
      state.sharePointStatus = 'LOADED'
      state.sharePointMessage = (
        `SharePoint 후보 ${response.candidate_count}건 · 변경 없음`
      )
      return
    }

    const protectsCurrentCandidate = (
      isWorkspaceLocked()
      || (
        Boolean(state.candidateEnvelope)
        && state.candidateSource === 'LOCAL_FILE'
      )
    )

    if (!force && protectsCurrentCandidate) {
      pendingSharePointResponse = response
      state.sharePointStatus = 'UPDATE_AVAILABLE'
      state.sharePointMessage = (
        `새 SharePoint 후보 ${response.candidate_count}건이 있습니다. `
        + '현재 분석 결과는 자동으로 덮어쓰지 않았습니다.'
      )
      return
    }

    applyCandidateEnvelope(
      response.candidate_envelope,
      'SHAREPOINT',
      response.source_sha256 || '',
    )
    pendingSharePointResponse = null
    state.sharePointStatus = 'LOADED'
    state.sharePointMessage = (
      `SharePoint에서 외부 MI 후보 ${response.candidate_count}건 자동 반입`
    )
  } catch (error) {
    if (
      error instanceof DOMException
      && error.name === 'AbortError'
    ) {
      return
    }

    const message = error instanceof Error
      ? error.message
      : String(error)
    state.sharePointStatus = 'ERROR'
    state.sharePointError = message
    state.sharePointMessage = 'SharePoint 후보 반입 실패'

    if (!silent) state.error = message
    throw error
  } finally {
    if (sharePointController === controller) {
      sharePointController = null
    }
  }
}

function applyPendingSharePointCandidates(): void {
  const response = pendingSharePointResponse

  if (!response?.candidate_envelope) {
    throw new Error('교체할 새 SharePoint 후보 파일이 없습니다.')
  }

  applyCandidateEnvelope(
    response.candidate_envelope,
    'SHAREPOINT',
    response.source_sha256 || '',
  )
  updateSharePointMetadata(response)
  pendingSharePointResponse = null
  state.sharePointStatus = 'LOADED'
  state.sharePointMessage = (
    `새 SharePoint 후보 ${response.candidate_count}건으로 교체했습니다.`
  )
}

async function checkHealth(): Promise<void> {
  try {
    const health = await getMiAiHealth()
    state.apiConfigured = health.configured
  } catch {
    state.apiConfigured = false
  }
}

async function refine(): Promise<void> {
  if (!state.candidateEnvelope) {
    throw new Error('외부 MI 후보 JSON을 먼저 업로드하세요.')
  }

  state.status = 'REFINING'
  state.error = ''

  try {
    const response = await refineExternalCandidates(
      state.candidateEnvelope,
      state.selectedCompanies,
      state.supplementalContext,
    )

    state.analysisId = response.analysis_id
    state.refinedEvents = response.events
    state.reviewResult = null
    state.status = 'REFINED'
  } catch (error) {
    state.status = 'ERROR'
    state.error = error instanceof Error
      ? error.message
      : String(error)
    throw error
  }
}

async function submitReview(): Promise<void> {
  if (!state.analysisId) {
    throw new Error('분석 ID가 없습니다.')
  }

  state.error = ''

  try {
    state.reviewResult = await submitMiReview(
      state.analysisId,
      state.refinedEvents,
    )
    state.status = 'REVIEWED'

    const saved = saveAnalysisId(state.analysisId)
    state.savedAnalysisId = saved
      ? state.analysisId
      : ''
    state.recoveryStatus = 'RESTORED'
    state.recoveryMessage = saved
      ? `마지막 승인 Run 저장 완료 · ${state.analysisId}`
      : '검토 결과는 저장됐지만 브라우저 localStorage를 사용할 수 없습니다.'
  } catch (error) {
    state.status = 'ERROR'
    state.error = error instanceof Error
      ? error.message
      : String(error)
    throw error
  }
}

async function restoreReviewByAnalysisId(
  analysisId: string,
  persist = true,
  silent = false,
): Promise<void> {
  const normalized = analysisId.trim()

  if (!normalized) {
    state.recoveryStatus = 'EMPTY'
    state.recoveryMessage = '복구할 Analysis ID가 없습니다.'
    return
  }

  state.recoveryStatus = 'RESTORING'
  state.recoveryMessage = `${normalized} Run 조회 중...`

  try {
    const run = await fetchMiRun(normalized)
    hydrateReviewedRun(normalized, run)

    if (persist && saveAnalysisId(state.analysisId)) {
      state.savedAnalysisId = state.analysisId
    }

    state.recoveryStatus = 'RESTORED'
    state.recoveryMessage = (
      `Run 복구 완료 · 승인 Event `
      + `${state.reviewResult?.approved_count ?? 0}건`
    )
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : String(error)

    state.recoveryStatus = 'ERROR'
    state.recoveryMessage = `Run 복구 실패 · ${message}`

    if (!silent) {
      state.error = message
    }

    throw error
  }
}

async function restoreLatestReview(
  silent = false,
): Promise<void> {
  const savedAnalysisId = readSavedAnalysisId()
  state.savedAnalysisId = savedAnalysisId

  if (!savedAnalysisId) {
    state.recoveryStatus = 'EMPTY'
    state.recoveryMessage = '브라우저에 저장된 승인 Run이 없습니다.'
    return
  }

  await restoreReviewByAnalysisId(
    savedAnalysisId,
    true,
    silent,
  )
}

async function initializeMiPersistence(): Promise<void> {
  if (!initializationPromise) {
    initializationPromise = restoreLatestReview(true)
      .catch(() => undefined)
  }

  await initializationPromise
}

function clearSavedReview(): void {
  removeSavedAnalysisId()

  state.savedAnalysisId = ''
  state.analysisId = ''
  state.refinedEvents = []
  state.reviewResult = null
  state.recoveryStatus = 'EMPTY'
  state.recoveryMessage = '저장된 승인 Run 정보를 삭제했습니다.'
  state.error = ''
  state.status = state.candidateEnvelope
    ? 'UPLOADED'
    : 'EMPTY'
}

function setAllReviewStatuses(
  status: RefinedMiEvent['review_status'],
): void {
  state.refinedEvents.forEach((event) => {
    event.review_status = status
  })
}

function downloadCanonicalPayload(): void {
  if (!state.reviewResult) {
    throw new Error('검토 결과를 먼저 저장하세요.')
  }

  const blob = new Blob(
    [JSON.stringify(
      state.reviewResult.canonical_payload,
      null,
      2,
    )],
    { type: 'application/json' },
  )
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = (
    `mi_events_approved_${state.analysisId}.json`
  )
  anchor.click()
  URL.revokeObjectURL(url)
}

export function useMiWorkspace() {
  return {
    state,
    approvedEvents: computed(() =>
      state.refinedEvents.filter((event) =>
        ['APPROVED', 'EDITED'].includes(
          event.review_status,
        ),
      ),
    ),
    loadCandidateFile,
    toggleCompanySelection,
    loadSharePointCandidates,
    applyPendingSharePointCandidates,
    checkHealth,
    refine,
    submitReview,
    restoreReviewByAnalysisId,
    restoreLatestReview,
    initializeMiPersistence,
    clearSavedReview,
    setAllReviewStatuses,
    downloadCanonicalPayload,
  }
}
