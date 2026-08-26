import type { ActionCard } from '../types/schemas'

/**
 * BUILD_PLAN.md task 3.10 — the Village View (citizen-facing screen). There is no citizen
 * login/village-selection system anywhere in this codebase (no auth, no per-device village
 * binding) — the demo's "which village's phone screen is this" choice is made explicitly by the
 * viewer via a picker, never guessed or defaulted to a real village silently.
 *
 * Picks the single most urgent currently-pending `ActionCard` for a given `village_id` —
 * `useTickStore.actionCards` is newest-first (see useTickStore.ts's `applyTick`), so this is
 * simply the first match; documented as a named helper (rather than an inline `.find`) so the
 * "most urgent first" ordering assumption is stated once and testable on its own.
 */
export function actionCardForVillage(
  actionCards: ActionCard[],
  villageId: string | null,
): ActionCard | null {
  if (!villageId) return null
  return actionCards.find((card) => card.village_id === villageId) ?? null
}

/** Distinct village_ids currently carrying at least one action card, in the same newest-first
 * order `actionCards` already has — the picker's option list. */
export function villagesWithActionCards(actionCards: ActionCard[]): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const card of actionCards) {
    if (!seen.has(card.village_id)) {
      seen.add(card.village_id)
      ordered.push(card.village_id)
    }
  }
  return ordered
}
