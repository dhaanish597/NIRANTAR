import type { RiskForecast, RiskForecastDay, TickResult } from '../types/schemas'

const RAINFALL_TREND = [1, 1.14, 0.96, 0.74, 0.56]

function riskLevel(probability: number): string {
  if (probability >= 0.75) return 'VERY HIGH'
  if (probability >= 0.5) return 'HIGH'
  if (probability >= 0.25) return 'MODERATE'
  return 'LOW'
}

/** Offline-safe mirror of the backend adapter. It uses the latest spatial tick when available;
 * the stable rainfall trend is only the final no-data fallback, never a random demo sequence. */
export function buildClientFallbackForecast(locationId: string, location: string, tick: TickResult | null): RiskForecast {
  const today = new Date()
  const baseRain = tick?.cell_risks.length
    ? Math.max(1, tick.cell_risks.reduce((sum, cell) => sum + Math.max(0, cell.threshold_exceedance), 0) / tick.cell_risks.length * 24)
    : 4
  const days: RiskForecastDay[] = RAINFALL_TREND.map((factor, offset) => {
    const date = new Date(today)
    date.setHours(0, 0, 0, 0)
    date.setDate(date.getDate() + offset)
    const isoDate = date.toISOString().slice(0, 10)
    const cells = (tick?.cell_risks ?? []).map((cell) => {
      const probability = Math.min(1, Math.max(0, cell.p_fail * (0.72 + 0.28 * factor)))
      return { ...cell, p_fail: probability, confidence: 1 - Math.abs(probability - 0.5) * 2 }
    })
    const probability = cells.length ? Math.max(...cells.map((cell) => cell.p_fail)) : Math.min(0.85, 0.18 + 0.12 * factor)
    const rainfall = Math.round(baseRain * factor * 10) / 10
    const label = offset === 0 ? 'TODAY' : offset === 1 ? 'TOMORROW' : date.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase()
    const driver = factor >= 1 ? 'Heavy rainfall' : factor >= 0.8 ? 'Antecedent rainfall and terrain susceptibility' : 'High terrain susceptibility'
    return {
      date: isoDate, day_label: label, risk_level: riskLevel(probability), risk_probability: probability,
      rainfall_mm: rainfall, confidence: cells.length ? Math.max(...cells.map((cell) => cell.confidence)) : 0.45,
      primary_driver: driver,
      explanation: factor >= 0.8 ? `Risk elevated primarily due to forecast rainfall (${rainfall.toFixed(1)} mm) and terrain susceptibility.` : `Risk decreasing as forecast rainfall falls to ${rainfall.toFixed(1)} mm, while terrain susceptibility persists.`,
      affected_villages: tick?.isolations.filter((item) => item.p_isolated >= 0.5).length ?? 0,
      affected_road_segments: tick?.road_risks.filter((item) => item.p_blocked >= 0.5).length ?? 0,
      cell_risks: cells, road_risks: tick?.road_risks ?? [], isolations: tick?.isolations ?? [], priorities: tick?.priorities ?? [],
      areas: cells.map((cell) => ({ id: cell.cell_id, name: cell.cell_id, risk_probability: cell.p_fail, risk_level: riskLevel(cell.p_fail) })),
    }
  })
  return { location, location_id: locationId, generated_at: new Date().toISOString(), source: 'FALLBACK', forecast: days }
}
