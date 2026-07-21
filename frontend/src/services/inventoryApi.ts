import type {
  InventoryItemsResponse,
  SimulateResponse,
} from '../types/inventory'

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

export async function getInventoryItems(): Promise<InventoryItemsResponse> {
  return parseResponse(await fetch(`${API_BASE}/api/inventory/items`))
}

export async function postInventorySimulate(
  itemId: string,
  extraDelayDays: number,
  horizonDays = 45,
): Promise<SimulateResponse> {
  return parseResponse(
    await fetch(`${API_BASE}/api/inventory/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: itemId,
        extra_delay_days: extraDelayDays,
        horizon_days: horizonDays,
      }),
    }),
  )
}
