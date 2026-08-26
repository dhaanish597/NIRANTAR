import { useEffect, useMemo, useState } from 'react'
import { queueAcknowledgement } from '../lib/ackQueue'
import { api } from '../lib/api'
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

/**
 * BUILD_PLAN.md task 3.10 — the Village View: "the citizen-facing screen: big stage colour, the
 * action card, a play button for the voice alert, an offline map with the route drawn, an
 * 'I have evacuated' acknowledge button that writes back into the audit trail."
 *
 * Big stage colour: `lib/escalation.ts::STAGE_COLOR`, the SAME palette `MapView`/
 * `VillageDetailDrawer`/`RightRail` already use — no new palette invented, per this agent's brief.
 *
 * Voice alert: `ActionCard.audio_urls` (task 3.9, IndicTrans2 + Indic-Parler-TTS pre-generated
 * audio) does not exist yet anywhere in this codebase — the play button below is real (renders
 * and plays an `<audio>` element) whenever a real URL IS present for the chosen language, but is
 * honestly `disabled` with a "voice alert not yet available" label when it isn't (which is always,
 * today) — never a fake/no-op playback control, same disabled-with-reason pattern
 * `ReplayControlBar.tsx` (task 4.9) already established for pause/resume.
 *
 * Offline map with route: reuses `MapView` (CLAUDE.md rule 10 — no external tile requests, no
 * second map implementation) with its new optional `routeGeometry` prop drawing
 * `ActionCard.route.geometry` (decision/routing.py's real `EvacuationRoute`, task 3.1) when present.
 *
 * "I have evacuated": **scope ruling, choice (a)** (same as task 3.7's DDMA Console) — calls the
 * real `POST /api/village/acknowledge` (backend/app/api/routes.py, this session), which calls the
 * real, tested `audit/producers.py::record_village_acknowledged()`, appending a genuine
 * `VILLAGE_ACKNOWLEDGED` event onto the alert's real hash-chained audit trail — verifiable
 * immediately via the "View audit trail" link this screen also offers.
 *
 * No village login/selection system exists (see `lib/villageView.ts`'s own docstring) — the
 * viewer picks which village's screen to show from whichever villages currently carry a pending
 * action card, an explicit, honest choice rather than a guessed default.
 *
 * BUILD_PLAN.md task 5.3 additions (this session): `handleAcknowledge` checks `navigator.onLine`
 * and falls back to `lib/ackQueue.ts::queueAcknowledgement` (a real IndexedDB-backed queue,
 * flushed for real by `App.tsx`'s `attachAckQueueAutoSync()` the moment the browser's `online`
 * event fires) instead of just showing an error — a citizen's tap is saved, not lost, in a real
 * offline gap. The no-active-card state (`NoActiveAlert` below) additionally shows the real
 * shelter/contact info the last known action cards referenced (`lib/offlineData.ts`), read
 * straight from IndexedDB — useful when the app is opened with no connectivity at all, before any
 * live card exists in the store.
 */
export function VillageView({ onBack }: { onBack: () => void }) {
  const actionCards = useTickStore((s) => s.actionCards)
  const isolations = useTickStore((s) => s.isolations)
  const openAuditTrail = useTickStore((s) => s.openAuditTrail)

  const villageIds = useMemo(() => villagesWithActionCards(actionCards), [actionCards])
  const [selectedVillageId, setSelectedVillageId] = useState<string | null>(villageIds[0] ?? null)
  const activeVillageId = selectedVillageId && villageIds.includes(selectedVillageId)
    ? selectedVillageId
    : villageIds[0] ?? null

  const card = actionCardForVillage(actionCards, activeVillageId)
  const villageName = isolations.find((v) => v.village_id === activeVillageId)?.name ?? activeVillageId

  const [ackState, setAckState] = useState<
    | { status: 'idle' }
    | { status: 'submitting' }
    | { status: 'done'; event: AuditEvent }
    | { status: 'queued' } // BUILD_PLAN.md task 5.3: saved offline, will sync on reconnect
    | { status: 'error'; error: string }
  >({ status: 'idle' })

  const handleAcknowledge = async () => {
    if (!card) return
    setAckState({ status: 'submitting' })
    const payload = { alert_id: card.alert_id, village_id: card.village_id }
    // BUILD_PLAN.md task 5.3: check connectivity BEFORE attempting the request — `navigator.
    // onLine` being false is a fast, reliable "don't even bother, queue it" signal (a real fetch
    // attempt while genuinely offline can take a while to fail on some platforms).
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
      return
    }
    try {
      const event = await api.acknowledgeVillage(payload)
      setAckState({ status: 'done', event })
    } catch (err) {
      // The request itself failed (e.g. a real network drop mid-request, not caught by the
      // navigator.onLine check above) — still queue it rather than losing the acknowledgement;
      // `attachAckQueueAutoSync()` (App.tsx) retries it for real the next time `online` fires.
      await queueAcknowledgement(payload)
      setAckState({ status: 'queued' })
      void err // the queued path doesn't surface the specific error — it will simply be retried
    }
  }

  if (!card) {
    return <NoActiveAlert onBack={onBack} />
  }

  const audioEntries = Object.entries(card.audio_urls)
  const hasAudio = audioEntries.length > 0

  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: STAGE_COLOR[card.stage] }}>
      <div className="flex items-center justify-between p-4">
        <button
          type="button"
          onClick={onBack}
          className="rounded bg-black/20 px-3 py-1.5 text-sm font-semibold text-white hover:bg-black/30"
        >
          ← Back
        </button>
        {villageIds.length > 1 && (
          <select
            aria-label="Select village"
            value={activeVillageId ?? ''}
            onChange={(event) => setSelectedVillageId(event.target.value)}
            className="rounded bg-black/20 px-2 py-1.5 text-sm text-white"
          >
            {villageIds.map((id) => (
              <option key={id} value={id} className="text-black">
                {isolations.find((v) => v.village_id === id)?.name ?? id}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="flex-1 space-y-4 px-4 pb-8">
        <div className="rounded-lg bg-black/25 p-5 text-white shadow-lg">
          <p className="text-xs font-semibold tracking-wide uppercase opacity-80">{villageName}</p>
          <h1 className="text-3xl font-black tracking-tight">{card.stage}</h1>
          <p className="mt-1 text-xl font-bold">{card.headline}</p>
          <p className="mt-3 text-sm opacity-90">{card.reason_plain}</p>
          {card.safe_window_hours && (
            <p className="mt-2 text-xs opacity-80">
              Safe evacuation window: ~{card.safe_window_hours[0].toFixed(1)}–
              {card.safe_window_hours[1].toFixed(1)} h (estimate, not a prediction of exact timing)
            </p>
          )}
        </div>

        {/* Play button for the voice alert (task 3.9's pre-generated audio doesn't exist yet). */}
        <div className="rounded-lg bg-black/20 p-4 text-white">
          <h2 className="mb-2 text-xs font-semibold tracking-wide uppercase opacity-80">Voice alert</h2>
          {hasAudio ? (
            <div className="space-y-2">
              {audioEntries.map(([lang, url]) => (
                <div key={lang} className="flex items-center gap-2">
                  <span className="w-20 text-xs uppercase opacity-80">{lang}</span>
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <audio controls src={url} className="h-8 flex-1" />
                </div>
              ))}
            </div>
          ) : (
            <button
              type="button"
              disabled
              title="Voice alert not yet available — pre-generated multilingual audio (BUILD_PLAN.md task 3.9) has not been built yet."
              className="rounded bg-white/20 px-4 py-2 text-sm font-semibold text-white/60 disabled:cursor-not-allowed"
            >
              ▶ Play voice alert — not yet available
            </button>
          )}
        </div>

        <div>
          <h2 className="mb-1 px-1 text-xs font-semibold tracking-wide text-white uppercase opacity-80">
            Route to shelter
          </h2>
          <div className="h-64 overflow-hidden rounded-lg border border-white/20">
            <MapView routeGeometry={card.route?.geometry ?? null} />
          </div>
          <p className="mt-1 px-1 text-xs text-white/80">
            Shelter: {card.shelter_name}
            {card.route && ` · ~${card.route.est_walk_minutes} min walk`}
          </p>
        </div>

        {card.roads_to_avoid.length > 0 && (
          <div className="rounded-lg bg-black/20 p-4 text-white">
            <h2 className="mb-1 text-xs font-semibold tracking-wide uppercase opacity-80">Roads to avoid</h2>
            <p className="text-sm">{card.roads_to_avoid.join(', ')}</p>
          </div>
        )}

        {card.what_to_carry.length > 0 && (
          <div className="rounded-lg bg-black/20 p-4 text-white">
            <h2 className="mb-1 text-xs font-semibold tracking-wide uppercase opacity-80">What to carry</h2>
            <ul className="list-inside list-disc text-sm">
              {card.what_to_carry.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-lg bg-black/20 p-4 text-sm text-white">
          <span className="opacity-80">Contact: </span>
          {card.contact}
        </div>

        <div className="rounded-lg bg-black/30 p-4">
          {ackState.status !== 'done' && ackState.status !== 'queued' && (
            <button
              type="button"
              disabled={ackState.status === 'submitting'}
              onClick={() => void handleAcknowledge()}
              className="w-full rounded-lg bg-white py-4 text-lg font-bold text-slate-900 shadow disabled:opacity-60"
            >
              {ackState.status === 'submitting' ? 'Submitting…' : 'I have evacuated'}
            </button>
          )}
          {ackState.status === 'error' && (
            <p className="mt-2 text-xs text-red-200">Could not submit: {ackState.error}</p>
          )}
          {ackState.status === 'queued' && (
            <div className="text-center text-white">
              <p className="text-lg font-bold">Saved — offline</p>
              <p className="mt-1 text-xs opacity-80">
                No connection right now. This will be sent automatically the moment the device is
                back online (BUILD_PLAN.md task 5.3).
              </p>
            </div>
          )}
          {ackState.status === 'done' && (
            <div className="text-center text-white">
              <p className="text-lg font-bold">✓ Evacuation acknowledged</p>
              <p className="mt-1 text-xs opacity-80">
                Recorded as {ackState.event.kind} at {new Date(ackState.event.t).toLocaleString()}
              </p>
              <button
                type="button"
                onClick={() => openAuditTrail(card.alert_id)}
                className="mt-3 rounded bg-white/20 px-3 py-1.5 text-xs font-semibold hover:bg-white/30"
              >
                View audit trail
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * BUILD_PLAN.md task 5.3's other half of "offline data": when there is no LIVE action card (the
 * store is empty — e.g. the app was opened with no connectivity at all, before `hydrateFromOfflineCache`'s
 * cache read resolves, or genuinely no alert is active), fall back to the real shelter/contact
 * info the last known action cards actually referenced (frontend/src/lib/offlineData.ts) rather
 * than showing nothing useful. Reads directly from IndexedDB (not the store) so this works even
 * in the brief window before `hydrateFromOfflineCache()` has populated the store.
 */
function NoActiveAlert({ onBack }: { onBack: () => void }) {
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
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-slate-950 p-6 text-center">
      <p className="text-lg font-semibold text-slate-200">No active alert for any village right now</p>
      <p className="max-w-md text-sm text-slate-500">
        Village View shows the citizen-facing screen for a settlement that currently has an AI
        recommendation issued (ORANGE/RED). None is issued at the moment.
      </p>
      {(shelters.length > 0 || contacts.length > 0) && (
        <div className="w-full max-w-md rounded-lg border border-white/10 bg-white/5 p-4 text-left">
          <p className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">
            From the last known alert (saved on this device)
          </p>
          {shelters.length > 0 && (
            <div className="mb-2">
              <p className="text-xs text-slate-500">Known shelters</p>
              <ul className="text-sm text-slate-300">
                {shelters.map((s) => (
                  <li key={s.shelterId}>{s.shelterName}</li>
                ))}
              </ul>
            </div>
          )}
          {contacts.length > 0 && (
            <div>
              <p className="text-xs text-slate-500">Emergency contact</p>
              <ul className="text-sm text-slate-300">
                {contacts.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={onBack}
        className="rounded bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/20"
      >
        ← Back to map
      </button>
    </div>
  )
}
