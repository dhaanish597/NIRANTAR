import { beforeEach, describe, expect, it } from 'vitest'
import { getCitizenReports, queueCitizenReport } from './citizenReports'

beforeEach(() => localStorage.clear())

describe('citizenReports', () => {
  it('queues a report tagged as simulated and persists it to localStorage', () => {
    const report = queueCitizenReport({ category: 'Crack', note: 'Wall crack near the school' })
    expect(report.source).toBe('simulated')
    expect(report.status).toBe('queued')
    expect(getCitizenReports()).toHaveLength(1)
    expect(getCitizenReports()[0].id).toBe(report.id)
  })
})
