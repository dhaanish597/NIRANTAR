import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { CitizenReportRecord, CitizenReportStatus } from '../types/schemas'

const STATUS_OPTIONS: CitizenReportStatus[] = ['submitted', 'acknowledged', 'in_review', 'actioned', 'dismissed']

export function CitizenReportsWorkspace() {
  const [reports, setReports] = useState<CitizenReportRecord[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(() => new URLSearchParams(location.search).get('report'))
  const [error, setError] = useState<string | null>(null)
  const refresh = () => void api.listCitizenReports().then((items) => { setReports(items); setSelectedId((current) => current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null) }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => window.clearInterval(timer)
  }, [])
  const selected = reports.find((report) => report.id === selectedId) ?? null
  const updateStatus = async (status: CitizenReportStatus) => {
    if (!selected) return
    try { const updated = await api.updateCitizenReportStatus(selected.id, { status, officer_id: 'ddma-console', notes: status === 'in_review' ? 'Assigned for field verification.' : '' }); setReports((items) => items.map((item) => item.id === updated.id ? updated : item)) } catch (err) { setError(err instanceof Error ? err.message : String(err)) }
  }
  return <section className="wide-workspace citizen-reports-workspace">
    <div className="screen-heading"><div><p className="eyebrow">Civic Pulse workflow</p><h1>Community reports</h1></div><button className="button secondary" type="button" onClick={refresh}>Refresh queue</button></div>
    <div className="reports-layout">
      <div className="reports-list">{error && <p className="error">{error}</p>}{reports.length === 0 && <p className="muted">No citizen reports have arrived for this AOI yet.</p>}{reports.map((report) => <button key={report.id} type="button" className={`report-row ${selected?.id === report.id ? 'selected' : ''}`} onClick={() => setSelectedId(report.id)}><span><strong>{report.category}</strong><small>{new Date(report.created_at).toLocaleString()} · {report.lat.toFixed(4)}, {report.lon.toFixed(4)}</small></span><span className={`report-status ${report.status}`}>{report.status.replace('_', ' ')}</span><b>{report.urgency_score}</b></button>)}</div>
      {selected && <article className="report-detail-panel"><div className="report-detail-header"><div><p className="eyebrow">{selected.id}</p><h2>{selected.category}</h2></div><span className={`report-status ${selected.status}`}>{selected.status.replace('_', ' ')}</span></div><img className="official-report-photo" src={`${import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'}${selected.image_url}`} alt={`Citizen evidence for ${selected.category}`} /><p className="report-description">{selected.description || 'No written description provided.'}</p><div className="report-metrics"><div><span>Urgency</span><strong>{selected.urgency_score}/100</strong></div><div><span>Quality</span><strong>{Math.round(selected.quality_score * 100)}%</strong></div><div><span>Relevance</span><strong>{Math.round(selected.relevance_score * 100)}%</strong></div><div><span>Severity</span><strong>{selected.severity}/5</strong></div></div><div className="report-recommendation"><span className="eyebrow">AI recommendation</span><p>{selected.recommendation}</p></div><div className="agent-trace"><span className="eyebrow">Seven-agent trace</span>{selected.agent_traces.map((trace) => <div key={trace.step_name}><b>{trace.step_order}. {trace.step_name}</b><span>{trace.detail}</span></div>)}</div><label className="report-status-control">Officer disposition<select value={selected.status} onChange={(event) => void updateStatus(event.target.value as CitizenReportStatus)}>{STATUS_OPTIONS.map((status) => <option key={status} value={status}>{status.replace('_', ' ')}</option>)}</select></label></article>}
    </div>
  </section>
}
