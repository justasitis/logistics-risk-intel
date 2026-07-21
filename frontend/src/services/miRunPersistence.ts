import type {
  ExternalMiCandidateEnvelope,
  RefineResponse,
  RefinedMiEvent,
  ReviewResponse,
} from '../types/mi'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const STORAGE_KEY = 'logistics-risk:last-reviewed-mi-analysis-id:v1'

export interface StoredMiRunRequest {
  candidate_envelope?: ExternalMiCandidateEnvelope
  company_codes?: string[]
  supplemental_context?: string
}

export interface StoredMiRun {
  stage?: string
  conversation_id?: string
  reviewed_at?: string
  request?: StoredMiRunRequest
  response?: RefineResponse
  canonical_payload?: ReviewResponse['canonical_payload']
  review_events?: RefinedMiEvent[]
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`

    try {
      const body = await response.json() as { detail?: string }
      detail = body.detail || detail
    } catch {
      // Keep HTTP status when the response body is not JSON.
    }

    throw new Error(detail)
  }

  return response.json() as Promise<T>
}

export async function fetchMiRun(
  analysisId: string,
): Promise<StoredMiRun> {
  const normalized = analysisId.trim()

  if (!normalized) {
    throw new Error('Analysis ID가 비어 있습니다.')
  }

  return parseResponse(
    await fetch(
      `${API_BASE}/api/mi-ai/runs/${encodeURIComponent(normalized)}`,
    ),
  )
}

export function readSavedAnalysisId(): string {
  if (typeof window === 'undefined') return ''

  try {
    return window.localStorage.getItem(STORAGE_KEY)?.trim() || ''
  } catch {
    return ''
  }
}

export function saveAnalysisId(analysisId: string): boolean {
  if (typeof window === 'undefined') return false

  const normalized = analysisId.trim()
  if (!normalized) return false

  try {
    window.localStorage.setItem(STORAGE_KEY, normalized)
    return true
  } catch {
    return false
  }
}

export function removeSavedAnalysisId(): void {
  if (typeof window === 'undefined') return

  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Browser storage may be unavailable in restricted profiles.
  }
}
