/**
 * Reads the full scenario JSON files (BUILD_PLAN.md Appendix B) directly, at build time, via
 * Vite's `import.meta.glob`. `GET /api/scenarios` (backend/app/api/routes.py) only projects a
 * few fields onto `ScenarioSummary` (id, aoi_id, held_out_of_training, frame_count, start, end,
 * provenance) — it does not carry `name`, `event_date`, `ground_truth`, or `narration`, and this
 * frontend slice is not allowed to add a backend endpoint to fill that gap. The scenario JSON
 * files are already committed to git and validated (task 4.1), so importing them directly is
 * both simpler and strictly more offline-safe than adding a network round trip: every card field
 * this module exposes is read from the committed file, never invented here (CLAUDE.md's
 * honesty rules — most concretely, "don't hardcode death tolls in the frontend", BUILD_PLAN.md
 * task 4.8).
 *
 * Only `data/scenarios/_smoke.json` exists as of this writing; it deliberately has no `name`,
 * `event_date`, or `ground_truth` block (it isn't a real event). Every accessor below degrades
 * gracefully when a field is absent rather than assuming a real scenario's shape.
 */

export interface GroundTruthFailure {
  t: string
  lat: number
  lon: number
  note?: string
  deaths_attributed?: string
}

export interface GroundTruthRoadEvent {
  t: string
  road: string
  location?: string
  effect: string
  consequence?: string
}

export interface GroundTruthWarning {
  t: string
  issuer: string
  level: string
  spatial_scale?: string
  note?: string
}

export interface GroundTruthOutcome {
  deaths?: string
  source_note?: string
}

export interface GroundTruth {
  failures?: GroundTruthFailure[]
  road_events?: GroundTruthRoadEvent[]
  official_warnings?: GroundTruthWarning[]
  outcome?: GroundTruthOutcome
}

export interface NarrationEntry {
  t: string
  text: string
}

export interface ScenarioProvenance {
  confidence?: string
  method?: string
  sources?: string[]
  disclaimer?: string
}

/** The full scenario file shape (Appendix B), as far as this frontend reads it. Every field
 * beyond `id`/`aoi_id`/`held_out_of_training`/`provenance` is optional because `_smoke.json`
 * doesn't carry it and future real scenario files are produced by a separate task (4.2/4.3+). */
export interface ScenarioFile {
  id: string
  name?: string
  event_date?: string
  aoi_id: string
  hazard_type?: string
  trigger?: string
  held_out_of_training: boolean
  provenance: ScenarioProvenance
  ground_truth?: GroundTruth
  narration?: NarrationEntry[]
}

// Eager + typed: every data/scenarios/*.json file is bundled at build time (production build)
// or read via Vite's transform pipeline (dev/test) — never fetched over the network at runtime,
// consistent with CLAUDE.md rule 10 (the demo runs with the network cable unplugged).
const scenarioModules = import.meta.glob<ScenarioFile>('../../../data/scenarios/*.json', {
  eager: true,
  import: 'default',
})

const scenarioFilesById = new Map<string, ScenarioFile>()
for (const mod of Object.values(scenarioModules)) {
  if (mod?.id) scenarioFilesById.set(mod.id, mod)
}

/** Looks up the full scenario file for a scenario id known to `/api/scenarios`. Returns
 * `undefined` if the id isn't found (shouldn't happen for a scenario the backend also lists,
 * but callers must render gracefully regardless — see module docstring). */
export function getScenarioDetail(id: string): ScenarioFile | undefined {
  return scenarioFilesById.get(id)
}

export interface DeathTollInfo {
  deaths: string
  sourceNote: string | null
}

/** `ground_truth.outcome` per Appendix B. Returns `null` when the scenario has no ground truth
 * (e.g. `_smoke`) or no recorded death toll — callers must not fabricate a figure in that case. */
export function deathTollInfo(detail: ScenarioFile | undefined): DeathTollInfo | null {
  const outcome = detail?.ground_truth?.outcome
  if (!outcome?.deaths) return null
  return { deaths: outcome.deaths, sourceNote: outcome.source_note ?? null }
}

/**
 * A one-line "what went wrong" derived from the scenario's own ground truth — never a hardcoded
 * narrative. Preference order, all read straight off the committed JSON:
 *   1. The first official warning's `note` (e.g. "No slope-specific warning issued") — this is
 *      literally what a post-event review found wrong with the response.
 *   2. The first road event's `consequence` (e.g. "Aizawl isolated from the rest of the
 *      country") — the concrete on-the-ground effect.
 *   3. The first narration caption, if the scenario has one.
 * Returns `null` (render nothing, not a fabricated line) if none of the above exist.
 */
export function whatWentWrongLine(detail: ScenarioFile | undefined): string | null {
  if (!detail) return null
  const warningNote = detail.ground_truth?.official_warnings?.[0]?.note
  if (warningNote) return warningNote
  const consequence = detail.ground_truth?.road_events?.[0]?.consequence
  if (consequence) return consequence
  const narrationText = detail.narration?.[0]?.text
  if (narrationText) return narrationText
  return null
}

/** Formats an aoi_id ("aizawl") as a readable label ("Aizawl") when no better location string is
 * available. This is a display transform of an id already present in the data, not a new fact —
 * the authoritative location string (e.g. "Aizawl, Mizoram") comes from `GET /api/aoi/{id}`
 * (backend/app/config.py) when that AOI happens to already be loaded; callers should prefer that
 * over this fallback where they have it. */
export function formatAoiIdFallback(aoiId: string): string {
  return aoiId
    .split(/[-_]/)
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
}
