import type {
  CompanyCode,
  ExternalMiCandidateEnvelope,
  MiLocationMasterEntry,
  RefineResponse,
  RefinedMiEvent,
  ReviewResponse,
} from '../types/mi'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // Ignore JSON parsing failure and keep HTTP status.
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export interface SharePointExternalMiResponse {
  found: boolean
  source_type: 'SHAREPOINT'
  source_root: string
  source_file: string | null
  source_file_name: string | null
  source_modified_at: string | null
  source_size_bytes: number
  source_sha256: string | null
  candidate_count: number
  candidate_envelope: ExternalMiCandidateEnvelope | null
  warnings: string[]
}

export async function getMiAiHealth(): Promise<{
  configured: boolean
  model_service: string
  response_mode: string
}> {
  return parseResponse(await fetch(`${API_BASE}/api/mi-ai/health`))
}

export async function fetchSharePointExternalCandidates(
  signal?: AbortSignal,
): Promise<SharePointExternalMiResponse> {
  return parseResponse(
    await fetch(
      `${API_BASE}/api/mi-ai/external-candidates/sharepoint`,
      {
        cache: 'no-store',
        signal,
      },
    ),
  )
}

export async function refineExternalCandidates(
  candidateEnvelope: ExternalMiCandidateEnvelope,
  companyCodes: CompanyCode[],
  supplementalContext = '',
): Promise<RefineResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi-ai/refine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        candidate_envelope: candidateEnvelope,
        company_codes: companyCodes,
        supplemental_context: supplementalContext,
      }),
    }),
  )
}

export async function getMiLocationMaster(): Promise<{
  locations: MiLocationMasterEntry[]
}> {
  return parseResponse(await fetch(`${API_BASE}/api/mi/location-master`))
}

export async function submitMiReview(
  analysisId: string,
  events: RefinedMiEvent[],
): Promise<ReviewResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi-ai/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ analysis_id: analysisId, events }),
    }),
  )
}
