import { useEffect, useMemo, useState } from 'react'
import { queueAcknowledgement } from '../lib/ackQueue'
import { api } from '../lib/api'
import { getCitizenReports, queueCitizenReport, type CitizenReportCategory } from '../lib/citizenReports'
import { STAGE_COLOR } from '../lib/escalation'
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
        <a href="/console/dashboard" className="citizen-brand">
          NIRANTAR
        </a>
        <a href="/console/dashboard" className="citizen-role">
          Officer view
        </a>
        <button>English ▾</button>
      </header>

      {route === 'alert' &&
        (card ? (
          <section className="citizen-screen" style={{ backgroundColor: STAGE_COLOR[card.stage] }}>
            {villageIds.length > 1 && (
              <select
                aria-label="Select village"
                value={activeVillageId ?? ''}
                onChange={(event) => setSelectedVillageId(event.target.value)}
              >
                {villageIds.map((id) => (
                  <option key={id} value={id}>
                    {isolations.find((v) => v.village_id === id)?.name ?? id}
                  </option>
                ))}
              </select>
            )}
            <div className="citizen-alert">
              <span>{card.stage}</span>
              <h1>{card.headline}</h1>
              <h2>{villageName}</h2>
              <p>{card.reason_plain}</p>
            </div>
            <div className="citizen-action">
              <h2>Voice alert</h2>
              {Object.entries(card.audio_urls).length > 0 ? (
                Object.entries(card.audio_urls).map(([lang, url]) => (
                  <div key={lang}>
                    <span>{lang}</span>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <audio controls src={url} />
                  </div>
                ))
              ) : (
                <button type="button" disabled title="Pre-generated multilingual audio is not built yet.">
                  ▶ Play voice alert — not yet available
                </button>
              )}
            </div>
            {card.roads_to_avoid.length > 0 && (
              <div className="citizen-action">
                <h2>Roads to avoid</h2>
                <p>{card.roads_to_avoid.join(', ')}</p>
              </div>
            )}
            {card.what_to_carry.length > 0 && (
              <div className="citizen-action">
                <h2>What to carry</h2>
                <ul>
                  {card.what_to_carry.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="citizen-action">
              <span>Contact: {card.contact}</span>
            </div>
            <button className="button" onClick={() => onNavigate('route')}>
              Safe route
            </button>
            <div className="citizen-action">
              {ackState.status !== 'done' && ackState.status !== 'queued' && (
                <button
                  type="button"
                  disabled={ackState.status === 'submitting'}
                  onClick={() => void handleAcknowledge()}
                >
                  {ackState.status === 'submitting' ? 'Submitting…' : 'I have evacuated'}
                </button>
              )}
              {ackState.status === 'error' && <p>Could not submit: {ackState.error}</p>}
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
          <section className="citizen-screen">
            <h1>Safe route</h1>
            <div style={{ height: '16rem' }}>
              <MapView routeGeometry={card.route?.geometry ?? null} />
            </div>
            {card.route ? (
              <>
                <h2>{card.route.shelter_name}</h2>
                <p>
                  {(card.route.distance_m / 1000).toFixed(1)} km · approximately{' '}
                  {card.route.est_walk_minutes} min
                </p>
              </>
            ) : (
              <NotBuilt
                task="TASK-CIT-ROUTE"
                what="A verified route has not been supplied for this alert."
                blocks="Routing engine and action-card route geometry"
              />
            )}
          </section>
        ) : (
          <NoActiveAlert />
        ))}

      {route === 'announcement' && (
        <section className="citizen-screen">
          <h1>Announcements</h1>
          {announcements.length === 0 ? (
            <NotBuilt
              task="TASK-CIT-ANNOUNCEMENT-FEED"
              what="No announcement has been sent yet."
              blocks="A DDMA officer sending an announcement from the Announce workspace"
            />
          ) : (
            <ul>
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
        <section className="citizen-screen">
          <h1>Report an incident</h1>
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
          <button className="button secondary" disabled>
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

      <div className="offline-status">
        {offline
          ? `○ Offline · ${queued} item${queued === 1 ? '' : 's'} queued`
          : queued
            ? `↻ Syncing boundary · ${queued} item${queued === 1 ? '' : 's'} queued`
            : '● Online & synced'}
      </div>

      <nav className="citizen-nav">
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
