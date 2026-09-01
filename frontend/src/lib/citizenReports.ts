export type CitizenReportCategory = 'Slope crack' | 'Blocked road' | 'Rockfall or debris' | 'Water seepage' | 'Retaining wall damage' | 'Other' | 'Crack'
export interface CitizenReport {
  id: string
  category: CitizenReportCategory
  note: string
  createdAt: string
  status: 'queued' | 'sent'
  source: 'simulated'
  aoiId?: string
  lat?: number
  lon?: number
  accuracyM?: number | null
  imageDataUrl?: string
}
const STORAGE_KEY = 'nirantar-citizen-reports-v1'
export function getCitizenReports(): CitizenReport[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]') as CitizenReport[]
  } catch {
    return []
  }
}
export function queueCitizenReport(input: Pick<CitizenReport, 'category' | 'note'> & Partial<Pick<CitizenReport, 'aoiId' | 'lat' | 'lon' | 'accuracyM' | 'imageDataUrl'>>): CitizenReport {
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

export function markCitizenReportSent(id: string): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(getCitizenReports().map((report) => report.id === id ? { ...report, status: 'sent' as const } : report)))
}

export async function syncQueuedCitizenReports(submit: (payload: { aoi_id: string; category: string; description: string; lat: number; lon: number; accuracy_m?: number | null; image_data_url: string }) => Promise<unknown>): Promise<number> {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return 0
  let synced = 0
  for (const report of getCitizenReports().filter((item) => item.status === 'queued' && item.imageDataUrl && Number.isFinite(item.lat) && Number.isFinite(item.lon))) {
    try {
      await submit({ aoi_id: report.aoiId ?? 'aizawl', category: report.category, description: report.note, lat: report.lat!, lon: report.lon!, accuracy_m: report.accuracyM, image_data_url: report.imageDataUrl! })
      markCitizenReportSent(report.id)
      synced += 1
    } catch { /* Keep queued until a later online retry. */ }
  }
  return synced
}
