import { useEffect, useMemo, useState } from 'react'
import { queueAcknowledgement } from '../lib/ackQueue'
import { api } from '../lib/api'
import { getCitizenReports, queueCitizenReport, type CitizenReportCategory } from '../lib/citizenReports'
import {
  deriveCachedEmergencyContacts,
  deriveCachedShelters,
  getCachedActionCards,
  type CachedShelter,
} from '../lib/offlineData'
import { actionCardForVillage, villagesWithActionCards } from '../lib/villageView'
import { useTickStore } from '../store/useTickStore'
import type { AuditEvent } from '../types/schemas'
import { MapView } from './MapView'
import { NotBuilt } from './NotBuilt'

export type CitizenRoute = 'alert' | 'route' | 'announcement' | 'report'

type AckState =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'done'; event: AuditEvent }
  | { status: 'queued' }
  | { status: 'error'; error: string }

export function CitizenApp({
  route,
  onNavigate,
}: {
  route: CitizenRoute
  onNavigate: (route: CitizenRoute) => void
}) {
  const actionCards = useTickStore((s) => s.actionCards)
  const isolations = useTickStore((s) => s.isolations)
  const announcements = useTickStore((s) => s.announcements)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)
  const aoi = useTickStore((s) => s.aoi)

  // Ported from VillageView.tsx (BUILD_PLAN.md task 3.10): no village login/selection system
  // exists, so the viewer picks among whichever villages currently carry a pending action card.
  const villageIds = useMemo(() => villagesWithActionCards(actionCards), [actionCards])
  const [selectedVillageId, setSelectedVillageId] = useState<string | null>(null)
  const activeVillageId =
    selectedVillageId && villageIds.includes(selectedVillageId) ? selectedVillageId : villageIds[0] ?? null
  const card = actionCardForVillage(actionCards, activeVillageId)
  const villageName = isolations.find((v) => v.village_id === activeVillageId)?.name ?? activeVillageId

  const [ackState, setAckState] = useState<AckState>({ status: 'idle' })
  const [queued, setQueued] = useState(() => getCitizenReports().filter((r) => r.status === 'queued').length)
  const [offline, setOffline] = useState(!navigator.onLine)
  const [category, setCategory] = useState<CitizenReportCategory>('Blocked road')
  const [note, setNote] = useState('')

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine)
    addEventListener('online', update)
    addEventListener('offline', update)
    return () => {
      removeEventListener('online', update)
      removeEventListener('offline', update)
    }
  }, [])

  const handleAcknowledge = async () => {
    if (!card) return
    setAckState({ status: 'submitting' })
    const payload = { alert_id: card.alert_id, village_id: card.village_id }
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
      return
    }
    try {
      const event = await api.acknowledgeVillage(payload)
      setAckState({ status: 'done', event })
    } catch {
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
    }
  }

  const saveReport = () => {
    queueCitizenReport({ category, note: note.trim() })
    setQueued(getCitizenReports().filter((r) => r.status === 'queued').length)
    setNote('')
  }

  return (
    <main className="citizen-app">
      <header className="citizen-head">
        <a href="/console/dashboard" className="citizen-brand" aria-label="NIRANTAR citizen home">
          <span className="brand-mark">N</span>
          <span>
            NIRANTAR
            <small>CITIZEN ACCESS</small>
          </span>
        </a>
        <div className="citizen-head-meta">
          <span className="citizen-live"><i /> LIVE</span>
          <a href="/console/dashboard" className="citizen-role">Officer view ↗</a>
        </div>
      </header>

      <div className="citizen-content">
      <div className="citizen-intro">
        <div>
          <p className="eyebrow">Community safety network</p>
          <p className="citizen-feed-title">Live safety feed</p>
        </div>
        <span className="citizen-aoi">{(aoi?.name ?? 'LOCAL AREA').toUpperCase()} / LOCAL</span>
      </div>

      {route === 'alert' &&
        (card ? (
          <section className="citizen-screen citizen-alert-screen">
            {villageIds.length > 1 && (
              <label className="citizen-village-select">
                Viewing area
                <select aria-label="Select village" value={activeVillageId ?? ''} onChange={(event) => setSelectedVillageId(event.target.value)}>
                  {villageIds.map((id) => <option key={id} value={id}>{isolations.find((v) => v.village_id === id)?.name ?? id}</option>)}
                </select>
              </label>
            )}
            <div className={`citizen-alert ${card.stage.toLowerCase()}`}>
              <div className="citizen-alert-kicker"><span className="severity-dot" /> <span>{card.stage}</span> ALERT <span>· {villageName}</span></div>
              <h1>{card.headline}</h1>
              <p>{card.reason_plain}</p>
              {card.safe_window_hours && (
                <p className="citizen-window">
                  Safe evacuation window: ~{card.safe_window_hours[0].toFixed(1)}–
                  {card.safe_window_hours[1].toFixed(1)} h (estimate, not a prediction of exact timing)
                </p>
              )}
            </div>
            <div className="citizen-card citizen-action">
              <h2>Voice alert</h2>
              <p className="muted">Listen to the latest instruction in your language.</p>
              {Object.entries(card.audio_urls).length > 0 ? (
                Object.entries(card.audio_urls).map(([lang, url]) => (
                  <div key={lang} className="audio-row">
                    <span className="audio-language">{lang}</span>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio controls src={url} />
                  </div>
                ))
              ) : (
                <button className="button secondary citizen-disabled" type="button" disabled title="Pre-generated multilingual audio is not built yet.">
                  Voice alert not available yet
                </button>
              )}
            </div>
            {card.roads_to_avoid.length > 0 && (
              <div className="citizen-card citizen-action two-column-card">
                <h2>Roads to avoid</h2>
                <p className="avoid-roads">{card.roads_to_avoid.join(' · ')}</p>
              </div>
            )}
            {card.what_to_carry.length > 0 && (
              <div className="citizen-card citizen-action">
                <h2>What to carry</h2>
                <ul className="carry-list">
                  {card.what_to_carry.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="citizen-card contact-card">
              <span>Emergency contact</span><strong>{card.contact}</strong>
            </div>
            <div className="citizen-actions">
            <button className="button citizen-primary-action" onClick={() => onNavigate('route')}>View safe route <span>→</span></button>
              {ackState.status !== 'done' && ackState.status !== 'queued' && (
                <button
                  className="button secondary"
                  type="button"
                  disabled={ackState.status === 'submitting'}
                  onClick={() => void handleAcknowledge()}
                >
                  {ackState.status === 'submitting' ? 'Submitting…' : 'I have evacuated'}
                </button>
              )}
              {ackState.status === 'error' && <p className="error">Could not submit: {ackState.error}</p>}
              {ackState.status === 'queued' && (
                <p>Saved — offline. This will be sent automatically once the device is back online.</p>
              )}
              {ackState.status === 'done' && (
                <div>
                  <p>✓ Evacuation acknowledged</p>
                  <p>
                    Recorded as {ackState.event.kind} at {new Date(ackState.event.t).toLocaleString()}
                  </p>
                  <button type="button" onClick={() => openAuditTrail(card.alert_id)}>
                    View audit trail
                  </button>
                </div>
              )}
            </div>
          </section>
        ) : (
          <NoActiveAlert />
        ))}

      {route === 'route' &&
        (card ? (
          <section className="citizen-screen route-screen">
            <div className="screen-heading"><div><p className="eyebrow">Navigation</p><h1>Safe route</h1></div><span className="route-status">RECOMMENDED</span></div>
            <div className="citizen-map">
              <MapView routeGeometry={card.route?.geometry ?? null} />
            </div>
            <div className="route-summary"><div><span className="eyebrow">Destination</span><strong>{card.shelter_name}</strong></div><div><span className="eyebrow">Estimated walk</span><strong>{card.route ? `${card.route.est_walk_minutes} min` : 'Unavailable'}</strong></div></div>
            {card.route && (
              <p className="muted route-detail">
                {(card.route.distance_m / 1000).toFixed(1)} km · approximately{' '}
                {card.route.est_walk_minutes} min
              </p>
            )}
            {card.roads_to_avoid.length > 0 && <div className="route-warning"><strong>Roads to avoid</strong><span>{card.roads_to_avoid.join(' · ')}</span></div>}
          </section>
        ) : (
          <NoActiveAlert />
        ))}

      {route === 'announcement' && (
        <section className="citizen-screen">
          <div className="screen-heading"><div><p className="eyebrow">Community updates</p><h1>Announcements</h1></div><span className="screen-count">{announcements.length}</span></div>
          {announcements.length === 0 ? (
            <NotBuilt
              task="TASK-CIT-ANNOUNCEMENT-FEED"
              what="No announcement has been sent yet."
              blocks="A DDMA officer sending an announcement from the Announce workspace"
            />
          ) : (
            <ul className="announcement-list">
              {announcements.map((a) => (
                <li key={a.id} className={`citizen-alert ${a.stage.toLowerCase()}`}>
                  <span>{a.stage}</span>
                  <h2>{a.village_id}</h2>
                  <p>{a.message}</p>
                  <small>{new Date(a.issued_at).toLocaleString()}</small>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {route === 'report' && (
        <section className="citizen-screen report-screen">
          <div className="screen-heading"><div><p className="eyebrow">Help your community</p><h1>Report an incident</h1></div></div>
          <p className="muted">
            Reports are saved in this device's durable prototype queue. They are not marked sent
            until a server accepts them.
          </p>
          <label>
            Category
            <select value={category} onChange={(e) => setCategory(e.target.value as CitizenReportCategory)}>
              <option>Crack</option>
              <option>Blocked road</option>
              <option>Water seepage</option>
            </select>
          </label>
          <label>
            Optional note
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Describe what you can see" />
          </label>
          <button className="button secondary citizen-disabled" disabled>
            Add photo · camera integration pending
          </button>
          <button className="button" onClick={saveReport}>
            Save report locally
          </button>
          {queued > 0 && (
            <p className="muted">
              {queued} report{queued === 1 ? '' : 's'} safely queued on this device.
            </p>
          )}
        </section>
      )}
      </div>

      <div className="offline-status">
      {offline
          ? `○ Offline · ${queued} item${queued === 1 ? '' : 's'} queued`
          : queued
            ? `↻ Syncing boundary · ${queued} item${queued === 1 ? '' : 's'} queued`
            : '● Online & synced'}
      </div>

      <nav className="citizen-nav" aria-label="Citizen navigation">
        {(['alert', 'route', 'announcement', 'report'] as const).map((item) => (
          <button key={item} className={route === item ? 'active' : ''} onClick={() => onNavigate(item)}>
            {item === 'alert'
              ? '⚠ Alert'
              : item === 'route'
                ? '⌁ Route'
                : item === 'announcement'
                  ? '📢 Announcements'
                  : '＋ Report'}
          </button>
        ))}
      </nav>
    </main>
  )
}

/** Ported from VillageView.tsx: when there is no LIVE action card for any village (the store is
 * empty — e.g. opened with no connectivity before hydrateFromOfflineCache resolves, or genuinely
 * no alert is active), fall back to the real shelter/contact info the last known action cards
 * actually referenced, read straight from IndexedDB. */
function NoActiveAlert() {
  const [shelters, setShelters] = useState<CachedShelter[]>([])
  const [contacts, setContacts] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    void getCachedActionCards().then((cards) => {
      if (cancelled) return
      setShelters(deriveCachedShelters(cards))
      setContacts(deriveCachedEmergencyContacts(cards))
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <section className="citizen-screen">
      <p>No active alert for any village right now</p>
      <p className="muted">
        This screen shows the citizen-facing alert for a settlement that currently has an AI
        recommendation issued (ORANGE/RED). None is issued at the moment.
      </p>
      {(shelters.length > 0 || contacts.length > 0) && (
        <div>
          <p className="muted">From the last known alert (saved on this device)</p>
          {shelters.length > 0 && (
            <ul>
              {shelters.map((s) => (
                <li key={s.shelterId}>{s.shelterName}</li>
              ))}
            </ul>
          )}
          {contacts.length > 0 && (
            <ul>
              {contacts.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
