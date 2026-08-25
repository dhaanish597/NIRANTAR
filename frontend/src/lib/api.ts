import type { AoiInfo, ModeState, ScenarioSummary } from '../types/schemas'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    const body = await response.text().catch(() => '')
    throw new Error(`${init?.method ?? 'GET'} ${path} -> ${response.status}: ${body}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  getState: () => request<ModeState>('/api/state'),
  getScenarios: () => request<ScenarioSummary[]>('/api/scenarios'),
  getAoi: (aoiId: string) => request<AoiInfo>(`/api/aoi/${aoiId}`),
  startReplay: (scenarioId: string) =>
    request<ModeState>('/api/replay/start', {
      method: 'POST',
      body: JSON.stringify({ scenario_id: scenarioId }),
    }),
  stopReplay: () => request<ModeState>('/api/replay/stop', { method: 'POST' }),
}
