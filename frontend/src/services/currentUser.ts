const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export interface CurrentUser {
  username: string
  can_manage_mi: boolean
}

// 현재 사용자 정보 — 서버가 OS 로그인 사용자명을 REPORT_PUBLISH_USERS와 대조해 권한 반환
export async function getCurrentUser(): Promise<CurrentUser> {
  const response = await fetch(`${API_BASE}/api/me`)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return response.json() as Promise<CurrentUser>
}
