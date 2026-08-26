# Frontend Rebuild — Sub-project 1: Foundation (Shared State + Navigation Shell)

**Status:** approved for implementation.
**Parent initiative:** SIH26001 Master Frontend & Demo Implementation Prompt (2026-08-26), decomposed
into 9 sequential sub-projects. This spec covers sub-project 1 only. Sub-projects 2–9 (Dashboard,
Government verification, Announce UI polish, Citizen app + routing, AI Emergency Commander, What-if
overhaul, Run Case Study repair, visual pass) are each speced separately when their turn comes.

## 1. Context

Two conflicting, uncommitted pieces of prior work exist in the working tree:

1. `UPDATED_FRONTEND_DESIGN.md` (marked "authoritative," uncommitted) describes a 6-workspace DDMA
   IA (Situation/Impact/Priority/Commander/Audit/Trust) with a 3-tab Citizen app (Alert/Route/
   Report). A partial rewrite toward this IA (`ConsoleShell.tsx`, `ConsoleWorkspaces.tsx`,
   `CitizenApp.tsx`, `NotBuilt.tsx`) is in progress in `frontend/src/`.
2. That in-flight rewrite **already dropped working, tested functionality** — `App.tsx`'s diff
   shows `DdmaConsole`, `VillageView`, `VillageDetailDrawer`, `CounterfactualScorecard`,
   `AuditTrailView`, `OnboardingOverlay`, and `InstallPrompt` are no longer mounted anywhere.

The user's new master prompt (this session) supersedes `UPDATED_FRONTEND_DESIGN.md`'s IA with a
5-item flat Government nav (Dashboard / AI Emergency Commander / What-if Simulator / Audit /
Announce) and a 4-tab Citizen nav (Alert / Route / Announcement / Report). **Decision (user
confirmed): build toward the new prompt's IA, not the old one.**

This sub-project is the foundation everything else in the rebuild depends on: the shared state
architecture (CLAUDE.md §40's requirement that Government and Citizen never hold independent
hard-coded state) and the navigation shell that replaces `ConsoleShell`/`ConsoleWorkspaces`,
re-mounting the orphaned real components instead of leaving them dropped.

## 2. Non-goals (deferred to later sub-projects)

- Heatmap rendering, working layer toggles, the Risk Intelligence Panel's visual design → **sub-project 2**.
- Verify/reject buttons and the verification workflow UI → **sub-project 3** (this spec only fixes the *schema shape* the store needs).
- The polished Announce composer (village/stage/language picker, confirmation step, verified-safe-route badge) → **sub-project 4**. This spec ships a minimal functional form only, enough to prove the real backend path end-to-end.
- Citizen point-to-point hazard-aware routing → **sub-project 5**.
- The AI Emergency Commander chat itself → **sub-project 6**.
- What-if Simulator's 35+-parameter reorganization and dedicated map → **sub-project 7**.
- Run Case Study repair/staging → **sub-project 8**.
- Visual design pass → **sub-project 9**.

## 3. Shared state architecture

Extend the existing `useTickStore` (Zustand, `frontend/src/store/useTickStore.ts`) rather than
introduce a second store. Both the Government shell and `CitizenApp` import this one store — no
per-app mock or duplicated data, satisfying the master prompt's §40 requirement directly.

New slices:

```ts
// Extends TickStoreState in useTickStore.ts
announcements: Announcement[]              // newest first, capped like auditEvents
verificationByAlertId: Record<string, VerificationRecord>
citizenReports: CitizenReport[]            // migrated off localStorage-only polling

// New actions
hydrateCitizenReports: () => void          // reads localStorage once at boot
queueCitizenReport: (input: Pick<CitizenReport,'category'|'note'>) => void  // writes store + localStorage
applyAnnouncement: (a: Announcement) => void   // called from the WS handler
setVerification: (alertId: string, record: VerificationRecord) => void
```

```ts
interface VerificationRecord {
  status: 'pending' | 'verified' | 'rejected'
  verifiedBy?: string
  verifiedAt?: string  // ISO, from LiveClock().now() server-side — never client Date.now()
}

interface Announcement {
  id: string
  alert_id: string
  village_id: string
  stage: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
  message: string
  language: string
  issued_by: string
  issued_at: string
  channel_results: Array<{ channel: string; recipient_count: number; delivered_count: number; acknowledged_count: number }>
  source: 'real'   // this slice only ever holds server-confirmed announcements
}
```

`CitizenReport` keeps its existing shape (`frontend/src/lib/citizenReports.ts`) but the
`_source: 'simulated'` tag is added explicitly, and `queueCitizenReport` writes to the Zustand
store (for reactivity) *and* `localStorage` (for offline durability across reloads) — both, not
either/or.

## 4. New backend surface — the Announce endpoint

This closes the exact gap CLAUDE.md's own "Known gaps" section names: *"`record_dissemination`
... is real and tested but not auto-fired from `pipeline.py` ... nothing yet chains an approval to
an actual channel send."*

`backend/app/schemas/announcement.py`:

```python
class ChannelResultSummary(BaseModel):
    channel: str
    recipient_count: int
    delivered_count: int
    acknowledged_count: int

class Announcement(BaseModel):
    id: str
    alert_id: str
    village_id: str
    stage: Literal["GREEN", "YELLOW", "ORANGE", "RED"]
    message: str
    language: str = "en"
    issued_by: str
    issued_at: datetime
    channel_results: list[ChannelResultSummary]
```

This is the exact shape the frontend's `Announcement.channel_results` (§3) mirrors — one schema,
serialized straight across the WS/REST boundary, no independent re-derivation on either side.

`backend/app/api/announcements.py`:

- `POST /api/announcements` — request body carries the existing `ActionCard` (the frontend already
  holds a real one from `/ws/ticks`, same pattern `ddma_decide` already uses) + `officer_id` +
  `recipient_count` (derived from the village's real population figure, resolved during
  implementation — not hardcoded). Handler:
  1. Calls `record_ddma_decision(..., decision="approved")` if this `alert_id` has no prior
     `DDMA_APPROVED`/`STOOD_DOWN` event yet (idempotent — announcing twice must not double-approve).
  2. Iterates the existing `dissemination/channels.py` channel set, calling `.send(card,
     recipient_count=...)` on each — real, already-tested, deterministic-seeded simulation, not new
     code.
  3. Calls `record_dissemination(...)` with the aggregated `ChannelSendResult`s — real audit event.
  4. Builds and returns an `Announcement`, and pushes it onto the existing `/ws/ticks` connection as
     a second discriminated message shape (`{"type": "announcement", "data": {...}}`) — reusing the
     one WS channel the stack table mandates (`Realtime: ... one channel, /ws/ticks`), not adding a
     second endpoint.
  5. Uses `LiveClock().now()` for `issued_at` — same rationale `ddma_decide` already documents: a
     real officer action happens at real wall-clock time even inside an accelerated replay.
- `GET /api/announcements` — list, newest first, so a freshly-loaded Citizen tab (or a WS
  reconnect) can backfill without having missed the push.

Frontend `lib/api.ts` gets `sendAnnouncement()` / `listAnnouncements()`; `lib/ws.ts`'s tick handler
gains a branch for the `announcement` message type that calls `applyAnnouncement`.

## 5. Census/demographics

A small deterministic function (exact backend attachment point — likely `/api/aoi/{id}` or
wherever village/exposure data is currently serialized — confirmed during planning, since the
current `get_aoi` handler returns only `{id, name, center, bbox}` and villages are not in that
payload yet) derives, per village, from its real WorldPop-based population figure:

```python
def simulate_demographics(population: int, village_id: str) -> Demographics:
    ...  # fixed ratio table, seeded by village_id so it's stable across calls — not random.random()
```

```python
class Demographics(BaseModel):
    children: int
    seniors: int
    adults: int
    high_risk_households: int
    source: Literal["simulated"] = "simulated"
```

Same village → same numbers, every call, every session. Labeled `source: "simulated"` at the
schema level so no consumer can mistake it for Census/ground-truth data (CLAUDE.md's honesty
rules).

## 6. Navigation shell

Replace `ConsoleShell.tsx` + `ConsoleWorkspaces.tsx`'s 6-workspace structure with 5 flat
Government routes and keep the existing hand-rolled `pushState` router (no router library
anywhere in this codebase; YAGNI for 9 total flat routes):

| Government | Route |
|---|---|
| Dashboard | `/console/dashboard` |
| AI Emergency Commander | `/console/commander` |
| What-if Simulator | `/console/whatif` |
| Audit | `/console/audit` |
| Announce | `/console/announce` |

| Citizen | Route |
|---|---|
| Alert | `/citizen/alert` |
| Route | `/citizen/route` |
| Announcement | `/citizen/announcement` |
| Report | `/citizen/report` |

`/` redirects to `/console/dashboard` (matching the old design's redirect convention).

### Re-mounting orphaned components (fixes the regression already in the tree)

| Component | New home |
|---|---|
| `VillageView.tsx`, `VillageDetailDrawer.tsx` | Feed Dashboard's Risk Intelligence Panel plumbing now; sub-project 2 reskins the visuals. |
| `AuditTrailView.tsx` | Becomes the base of the new Audit workspace (`/console/audit`) — reused, not rebuilt. |
| `CounterfactualScorecard.tsx` | Stays wired to replay completion (unchanged trigger) — CLAUDE.md names this explicitly as a required deliverable; it must not silently disappear. |
| `OnboardingOverlay.tsx`, `InstallPrompt.tsx` | Remounted at the app root, route-independent (unchanged behavior). |
| `DdmaConsole.tsx` (old) | Diffed for anything not already covered by `ConsoleWorkspaces`' equivalent logic, then retired. |
| "Trust" content (model version, confidence, provenance, limitations) | No dedicated nav slot in the new 5-item IA. Folds into: (a) the Risk Intelligence Panel's confidence/provenance fields (sub-project 2), (b) a compact "model & limitations" section inside Audit. CLAUDE.md's honesty rules (§3, rules 1–6) are non-negotiable regardless of IA — this content is relocated, not dropped. |

### Minimal Announce route (this sub-project's slice of it)

`/console/announce` gets a minimal functional form in this sub-project — pick an existing
`ActionCard` from `useTickStore.actionCards`, enter an officer id, hit send, see the real
per-channel delivery/ack numbers come back. This proves the new backend endpoint end-to-end
(CLAUDE.md rule 11, vertical slice first). Sub-project 4 replaces this with the full composer
(village/stage/language picker, confirmation step, verified-safe-route badge) once verification
(sub-project 3) exists to gate it against.

## 7. REAL / SIMULATED / PLACEHOLDER labeling

Every new state slice/type carries an explicit `source: 'real' | 'simulated' | 'placeholder'`
field (as shown in §3–5 above), surfaced as a small consistent visual marker — not a disclaimer
wall. A failed `/api/announcements` call surfaces the same `status: 'error'` pattern
`WhatIfSimulator`/the existing `ActionComposer` already use: a visible error message, never a
swallowed failure or a fabricated success.

## 8. Testing

**Backend** (pytest):
- `POST /api/announcements`: creates the record, calls every configured channel, writes a real
  `DISSEMINATED` audit event, is idempotent on the approval step when called twice for the same
  `alert_id`, and pushes the WS message.
- `GET /api/announcements`: returns what was created, newest first.
- `simulate_demographics()`: determinism (same village_id + population → identical output across
  repeated calls) and that outputs sum sensibly against the input population.

**Frontend** (vitest):
- New store slices: `hydrateCitizenReports` reads localStorage correctly; `queueCitizenReport`
  updates both store and localStorage; `applyAnnouncement` appends and caps; `setVerification`
  updates the record keyed by `alert_id`.
- A smoke test asserting a change to `useTickStore` (e.g. `queueCitizenReport`) is visible from
  both a Government-shell-rendered consumer and `CitizenApp` — proving one shared instance, not
  two.
- Router: each of the 9 routes resolves to the correct component; `popstate` navigation works;
  `/` redirects to `/console/dashboard`.

## 9. Acceptance criteria for this sub-project

- [ ] `App.tsx` mounts a new shell with exactly the 5 Government routes and 4 Citizen routes above.
- [ ] `DdmaConsole`, `VillageView`, `VillageDetailDrawer`, `CounterfactualScorecard`,
      `AuditTrailView`, `OnboardingOverlay`, `InstallPrompt` are all reachable again (the regression
      from the in-flight rewrite is fixed).
- [ ] `POST /api/announcements` is real: it calls `dissemination/channels.py`'s real send methods
      and produces a real `DISSEMINATED` audit event, verifiable via `GET /api/audit/{alert_id}`.
- [ ] A citizen report queued in `CitizenApp` appears in the Government-facing store within the
      same session without a manual refresh action.
- [ ] Village demographics are available from the backend, labeled `source: "simulated"`, and
      stable across repeated calls for the same village.
- [ ] `/console/announce` renders a minimal working form (pick an action card, enter officer id,
      send) that round-trips through the real endpoint and displays the real per-channel
      delivery/ack numbers returned.
- [ ] `make test` (backend) and the frontend test suite both pass.
