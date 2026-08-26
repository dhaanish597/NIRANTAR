import type { ActionCard, SettlementPriority, VillageIsolation } from '../types/schemas'

/**
 * BUILD_PLAN.md task 3.7 — the DDMA Console.
 *
 * CLAUDE.md's rule on placeholders: "Never invent a real DDMA officer name/ID/phone number — use
 * a clearly-labelled placeholder pattern, same spirit as `config.ACTION_CARD_CONTACT_PLACEHOLDER`
 * already established." No real DDMA login/credential system exists anywhere in this codebase —
 * `POST /api/ddma/decide` (backend/app/api/routes.py) takes a bare `officer_id: str`, so this is
 * an honest, explicitly self-labelling placeholder value, editable in the console UI, never
 * presented as a real credential.
 */
export const DDMA_OFFICER_ID_PLACEHOLDER =
  'ddma-officer-placeholder (no real DDMA login system — type any identifier)'

export type DdmaDecisionKind = 'approved' | 'modified' | 'rejected'

export interface RecommendationContext {
  eps: number | null
  tier: SettlementPriority['tier'] | null
  components: Record<string, number>
  population: number | null
  isolatedNow: boolean | null
}

/** Joins one pending `ActionCard` (BUILD_PLAN.md task 3.3/decision/stub.py) with its
 * `SettlementPriority` (EPS breakdown, task 2.5) and `VillageIsolation` (affected population,
 * task 2.4) by `village_id` — the same real relationship `lib/priorityDetail.ts::mergeVillageDisplay`
 * already establishes, specialized to a single card for the DDMA Console's recommendation queue. */
export function recommendationContext(
  card: ActionCard,
  priorities: SettlementPriority[],
  isolations: VillageIsolation[],
): RecommendationContext {
  const priority = priorities.find((p) => p.village_id === card.village_id)
  const isolation = isolations.find((v) => v.village_id === card.village_id)
  return {
    eps: priority?.eps ?? null,
    tier: priority?.tier ?? null,
    components: priority?.components ?? {},
    population: isolation?.population ?? null,
    isolatedNow: isolation?.isolated_now ?? null,
  }
}
