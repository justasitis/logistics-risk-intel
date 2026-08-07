// 기준정보 관리 API 래퍼 — GET /api/config/*
import type { ConfigCatalog, ConfigSection } from '../types/config'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

// 오류 응답 본문의 detail(한국어 검증 오류 등)을 그대로 사용자에게 보여주기 위한 추출
async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (
      body
      && typeof body === 'object'
      && 'detail' in body
      && typeof (body as { detail: unknown }).detail === 'string'
    ) {
      return (body as { detail: string }).detail
    }
  } catch {
    // 본문 파싱 실패 시 아래 기본 메시지 사용
  }

  if (response.status === 403) {
    return '기준정보를 변경할 권한이 없습니다.'
  }
  return `요청 실패 (${response.status} ${response.statusText})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response))
  }
  return response.json() as Promise<T>
}

export async function fetchConfigCatalog(): Promise<ConfigCatalog> {
  return request<ConfigCatalog>('/api/config/catalog')
}

export async function fetchConfigSection(key: string): Promise<ConfigSection> {
  return request<ConfigSection>(`/api/config/${encodeURIComponent(key)}`)
}

export async function saveConfigSection(key: string, data: unknown): Promise<void> {
  await request<{ ok: boolean }>(`/api/config/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data }),
  })
}

export async function resetConfigSection(key: string): Promise<void> {
  await request<{ ok: boolean }>(`/api/config/${encodeURIComponent(key)}/reset`, {
    method: 'POST',
  })
}
