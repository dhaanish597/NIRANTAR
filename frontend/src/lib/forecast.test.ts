import { describe, expect, it } from 'vitest'
import { buildClientFallbackForecast } from './forecast'

describe('client forecast fallback', () => {
  it('always returns five dynamically consecutive dates and FALLBACK provenance', () => {
    const result = buildClientFallbackForecast('aizawl', 'Aizawl', null)
    expect(result.source).toBe('FALLBACK')
    expect(result.forecast).toHaveLength(5)
    expect(result.forecast.map((day) => day.date)).toEqual([
      result.forecast[0].date,
      ...result.forecast.slice(1).map((day, index) => {
        const previous = new Date(result.forecast[index].date)
        previous.setDate(previous.getDate() + 1)
        return previous.toISOString().slice(0, 10) === day.date ? day.date : ''
      }),
    ])
  })
})
