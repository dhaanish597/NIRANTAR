# Reference documents — READ-ONLY

These are the team's research documents for SIH26001. They are the **source of truth for every
domain fact** used anywhere in this codebase or in the UI: disaster details, death tolls, rainfall
thresholds, dates, what existing government systems (GSI, NESAC, IMD, NDMA/SACHET) actually do.

## Rules

1. **Do not edit these files from code or from a coding session.** They are research inputs, not
   build artifacts. If one is wrong or stale, fix it deliberately as its own edit, not as a
   side-effect of a build task.
2. **Do not invent, estimate, or embellish a domain fact that isn't in here.** If code or the UI
   needs a fact that isn't in this folder, mark it `TODO(verify)` in the code/UI and move on. Do
   not fabricate a number to fill the gap — see CLAUDE.md §3, honesty rules.
3. When a fact from here is surfaced in the UI (a death toll, a threshold formula, a date), prefer
   citing it near-verbatim over paraphrasing loosely, especially for anything a GSI/NESAC/IMD judge
   could challenge.

## Contents

| File | Covers |
|---|---|
| `AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region.md` | Core problem-statement research: the NER landslide problem, existing systems (GSI LEWS, NESAC FLEWS, Bhuvan, SACHET), gap analysis. |
| `SIH26001_Technical_Architecture_Reference.md` | Technical architecture research: data sources, thresholds, model approach, the LHASA v2 reference architecture. |
| `SIH26001_Existing_Evacuation_Solutions_India_and_Global.md` | Survey of existing evacuation/dissemination solutions in India and globally. |
| `deep-research-report.md` | Deep-research report underlying the above. |

`CLAUDE.md` §4 (domain glossary) and the reference formulae there were extracted from these
documents. If a number in `CLAUDE.md` and a number in here ever disagree, these files win — flag
the mismatch and fix `CLAUDE.md`, not the other way round.
