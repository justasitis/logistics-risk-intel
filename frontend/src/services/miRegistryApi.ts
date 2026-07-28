import type { RegistryRebuildResponse, RegistryResponse } from '../types/miRegistry'

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

export async function getMiRegistry(status?: string): Promise<RegistryResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return parseResponse(await fetch(`${API_BASE}/api/mi/registry${query}`))
}

export async function rebuildMiRegistry(): Promise<RegistryRebuildResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/mi/registry/rebuild`, { method: 'POST' }),
  )
}
