export type CitizenReportCategory = 'Crack' | 'Blocked road' | 'Water seepage'
export interface CitizenReport {
  id: string
  category: CitizenReportCategory
  note: string
  createdAt: string
  status: 'queued' | 'sent'
  source: 'simulated'
}
const STORAGE_KEY = 'nirantar-citizen-reports-v1'
export function getCitizenReports(): CitizenReport[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as CitizenReport[]
  } catch {
    return []
  }
}
export function queueCitizenReport(input: Pick<CitizenReport, 'category' | 'note'>): CitizenReport {
  const report: CitizenReport = {
    ...input,
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    status: 'queued',
    source: 'simulated',
  }
  const reports = [...getCitizenReports(), report]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(reports))
  return report
}
