import type {
  NotificationsResponse,
  WatchlistItem,
  WatchlistResponse,
} from '../types/watchlist'

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

export async function getWatchlist(): Promise<WatchlistResponse> {
  return parseResponse(await fetch(`${API_BASE}/api/watchlist`))
}

export async function addWatchlist(id: string, label = ''): Promise<WatchlistItem> {
  return parseResponse(
    await fetch(`${API_BASE}/api/watchlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, label }),
    }),
  )
}

export async function removeWatchlist(id: string): Promise<void> {
  await parseResponse(
    await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  )
}

export async function getNotifications(): Promise<NotificationsResponse> {
  return parseResponse(await fetch(`${API_BASE}/api/notifications`))
}
