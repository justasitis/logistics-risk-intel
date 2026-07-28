// 관심화물(watchlist) + 알림 feed 타입

export interface WatchlistItem {
  type: string // 'hbl' (po 등 확장 여지)
  id: string
  label: string
  added_at: string
}

export interface WatchlistResponse {
  items: WatchlistItem[]
}

export type NotificationType = 'DELIVERY_REQ_BREACH' | 'SIGNAL' | 'NOT_FOUND' | string

export interface NotificationAlert {
  type: NotificationType
  severity: string
  message: string
  value: number | null
}

export interface NotificationItem {
  hbl_no: string
  label: string
  alerts: NotificationAlert[]
}

export interface NotificationsResponse {
  computed_at: string
  cache_hit: boolean
  items: NotificationItem[]
}
