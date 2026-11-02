const configuredApiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
export const API_BASE_URL = configuredApiBaseUrl.replace(/\/+$/, '')

function isLocalBackend(url: string) {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(parsed.hostname)
  } catch {
    return false
  }
}

function requestUrl(path: string) {
  // Local browser requests use the Next.js same-origin rewrite so the API does
  // not require a CORS change in the existing FastAPI service.
  return typeof window !== 'undefined' && isLocalBackend(API_BASE_URL)
    ? path
    : `${API_BASE_URL}${path}`
}

export type ApiRecord = Record<string, any>

export async function apiFetch<T = ApiRecord | ApiRecord[]>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(requestUrl(path), { ...init, headers: { Accept: 'application/json', ...init?.headers } })
    if (!response.ok) throw new Error(`Backend request failed (${response.status})`)
    return response.json()
  } catch (error) {
    if (error instanceof Error && error.message.startsWith('Backend request failed')) throw error
    throw new Error(`Failed to connect to the ChargeQueue backend at ${API_BASE_URL}.`)
  }
}

export const api = {
  health: () => apiFetch<ApiRecord>('/api/health'),
  overview: () => apiFetch<ApiRecord>('/api/dataset/overview'),
  stations: () => apiFetch<ApiRecord[] | ApiRecord>('/api/stations'),
  station: (id: string) => apiFetch<ApiRecord>(`/api/stations/${encodeURIComponent(id)}`),
  history: (id: string, options: { start?: string; end?: string; limit?: number } = {}) => {
    const params = new URLSearchParams()
    if (options.start) params.set('start', options.start)
    if (options.end) params.set('end', options.end)
    if (options.limit) params.set('limit', String(options.limit))
    const query = params.toString()
    return apiFetch<ApiRecord[] | ApiRecord>(`/api/stations/${encodeURIComponent(id)}/history${query ? `?${query}` : ''}`)
  },
  forecast: (id: string, horizon = 60) => apiFetch<ApiRecord>(`/api/stations/${encodeURIComponent(id)}/forecast?horizon=${horizon}`),
  alerts: async (id: string) => {
    const response = await apiFetch<ApiRecord>(`/api/stations/${encodeURIComponent(id)}/alerts`)
    return {
      ...response,
      ports_occupied: response.current_occupancy,
      classification: response.alert_level,
      timestamp: response.evaluation_timestamp,
    }
  },
}

export function asArray(value: any): ApiRecord[] {
  if (Array.isArray(value)) return value
  for (const key of ['data', 'items', 'stations', 'history', 'records', 'forecasts', 'forecast_points', 'alerts', 'results']) if (Array.isArray(value?.[key])) return value[key]
  return []
}

export function first(record: ApiRecord | undefined, keys: string[], fallback: any = undefined) {
  for (const key of keys) if (record?.[key] !== undefined && record[key] !== null) return record[key]
  return fallback
}

export function utilization(row: ApiRecord) {
  const reported = Number(first(row, ['operational_utilization']))
  if (Number.isFinite(reported)) return reported * 100
  const occupied = Number(first(row, ['ports_occupied', 'occupied_ports', 'occupied']))
  const available = Number(first(row, ['ports_available', 'available_ports', 'available']))
  const denominator = available + occupied
  return Number.isFinite(occupied) && denominator > 0 ? (occupied / denominator) * 100 : undefined
}
