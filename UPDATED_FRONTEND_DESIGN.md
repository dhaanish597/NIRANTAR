# NIRANTAR: Frontend Information Architecture — Updated Design

**Status:** authoritative.  
**Purpose:** Defines the frontend structure, navigation, shell layout, screen responsibilities, and interaction model for NIRANTAR.  
**Based on:** the existing NIRANTAR frontend information architecture and the updated visual direction agreed for the product.

---

## 1. Design direction

The frontend should combine two ideas:

1. **A visually strong command-centre landing page** with the map as the hero.
2. **Independent navigation items for independent features**, so the interface never becomes one giant dashboard containing every feature.

The key principle is:

> **The first screen should immediately communicate the situation. Other features should be discoverable through navigation, not permanently displayed on the first screen.**

The product should therefore feel like a professional District Disaster Management Authority control platform rather than a collection of cards.

Do not put the simulator, AI Emergency Commander, audit system, trust/evaluation tools, isolation analysis, and evacuation composer all on the Situation screen.

Each major feature gets its own workspace.

---

# 2. Two applications, one codebase

| DDMA Console | Citizen App |
|---|---|
| `/console` | `/citizen` |
| Desktop-first, 1440px+ | Mobile-first, approximately 390px |
| District Disaster Management Authority officer | Villager / field volunteer |
| Dense information and GIS analysis | Simple, action-oriented interface |
| Assumed online, graceful degradation | Offline-first, opportunistic sync |

A global role switcher is available in the demo:

**View as: DDMA Officer | Citizen**

This is a demonstration affordance, not a security model. In deployment, the two experiences would be separate builds behind appropriate authentication.

`/` redirects to `/console/situation`.

---

# 3. DDMA navigation

The console uses a persistent navigation system.

## Primary navigation

1. **Situation**
2. **Impact**
3. **Priority**
4. **Commander**
5. **Audit**
6. **Trust**

These are independent workspaces.

The map may remain persistent across the map-based workspaces, but the information displayed around it changes according to the active workspace.

---

# 4. Global shell

The shell is shared across all DDMA workspaces.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ NIRANTAR     LIVE     AOI: Sikkim     18:00 IST     Run Case Study      │
│                                                                  DDMA    │
├──────────────────────────────────────────────────────────────────────────┤
│ Situation │ Impact │ Priority │ Commander │ Audit │ Trust                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                         ACTIVE WORKSPACE                                 │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ Data provenance · model version · tick time · replay/live state          │
└──────────────────────────────────────────────────────────────────────────┘
```

The global chrome contains:

- NIRANTAR identity
- LIVE / REPLAY MODE banner
- AOI selector
- scenario/tick clock
- Run Case Study
- role switcher
- primary navigation

The shell should remain visually stable while the active workspace changes.

---

# 5. Design principle: one screen, one primary question

Every navigation item has a clear purpose.

| Workspace | Primary question |
|---|---|
| Situation | **What is happening right now?** |
| Impact | **What will break or become isolated?** |
| Priority | **Who should be evacuated first?** |
| Commander | **What happens if conditions change?** |
| Audit | **Who was warned, who acted, and when?** |
| Trust | **Why should I believe the system?** |

Do not merge these questions into a single dashboard.

---

# 6. Situation — command-centre landing page

**Route:** `/console/situation`

This is the most visually important screen and the default landing page.

It should resemble the strongest version of the proposed prototype: a dark GIS command centre with the map as the hero.

## Answers

> What is happening right now?

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ GLOBAL CHROME                                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ Situation │ Impact │ Priority │ Commander │ Audit │ Trust                │
├────────────────────────────────────────────┬─────────────────────────────┤
│                                            │ SITUATION                   │
│                                            │                             │
│                                            │ 🔴 3 Critical               │
│              GIS MAP                       │ 🟠 7 Watch                  │
│                                            │ 🟢 Normal: 42               │
│      risk cells                            │                             │
│      villages                              │ Top drivers                 │
│      rainfall                              │ Rainfall       42%          │
│      deformation                           │ Soil moisture  28%          │
│      reports                               │ Slope          17%          │
│                                            │ Deformation    13%          │
│                                            │                             │
│ [Layers]                         [Legend]  │ Last update 18:00           │
├────────────────────────────────────────────┴─────────────────────────────┤
│ PROVENANCE: IMD · Sentinel-1 · GPM/IMERG · SMAP · OSM · Model v0.8.2    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Map layers

Situation supports:

- Risk cells
- InSAR deformation
- Rainfall accumulation
- Soil moisture context
- Village markers
- Citizen reports
- Exposure

Layer controls remain floating over the map.

Group them into:

- Hazard
- Deformation
- Weather
- Exposure
- Reports

## Context rail

The rail is contextual.

When nothing is selected:

- cells above threshold
- top drivers
- last tick
- active scenario
- current alert state

When a village is selected:

```text
RAVANGLA

🔴 P1

P(fail)
0.81

Population
2,840

Why?
Rainfall        42%
Soil moisture   28%
Slope           17%
Deformation     13%

[ View Priority ]
```

The rail should NOT contain:

- full evacuation composer
- simulator
- AI chatbot
- audit timeline
- complete trust documentation

Those features have their own navigation destinations.

---

# 7. Impact — isolation and infrastructure workspace

**Route:** `/console/impact`

## Answers

> What breaks, and who gets cut off?

This is the dedicated Road Isolation Index workspace.

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Situation │ IMPACT │ Priority │ Commander │ Audit │ Trust               │
├────────────────────────────────────────────┬─────────────────────────────┤
│                                            │ ISOLATION SUMMARY            │
│                                            │                             │
│                 MAP                        │ 4 villages isolated now     │
│                                            │ 9 at forecast horizon       │
│       road network                         │ 3 critical edges            │
│       blocked segments                     │ 6.8h median isolation       │
│       isolation polygons                   │                             │
│       bridges                              │ Selected road               │
│                                            │ blockage probability        │
│                                            │ alternate route             │
├────────────────────────────────────────────┴─────────────────────────────┤
│ ISOLATION TABLE                                                          │
│ Village │ Population │ RII │ Isolating Segment │ Alternate │ Hours      │
└──────────────────────────────────────────────────────────────────────────┘
```

## Map layers

- Road blockage probability
- Severed edges
- Runout envelopes
- Isolation polygons
- Bridges
- Critical infrastructure

## Rail

When a road is selected:

- blockage probability
- adjacent cell P(fail)
- road class
- alternate path
- estimated reopen window

When a village is selected:

- RII
- isolating edges
- remaining paths
- estimated isolation duration

## Table

The isolation table is a major operational component.

Columns:

- Village
- Population
- RII
- Isolating segment
- Alternate route
- Estimated isolation hours

---

# 8. Priority — evacuation decision workspace

**Route:** `/console/priority`

## Answers

> Who is evacuated first, where do they go, and what message is sent?

This workspace contains the complete evacuation decision workflow.

It should NOT permanently occupy the Situation page.

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Situation │ Impact │ PRIORITY │ Commander │ Audit │ Trust               │
├────────────────────────────────────────────┬─────────────────────────────┤
│                                            │ PRIORITY QUEUE               │
│                 MAP                        │                             │
│                                            │ 🔴 P1 Ravangla               │
│ villages coloured P1/P2/P3                │ EPS 0.91                    │
│ shelters                                   │ 2,840 people                │
│ safe routes                                │                             │
│ avoid-roads                                │ 🟠 P2 Namchi                 │
│                                            │ EPS 0.67                    │
├────────────────────────────────────────────┴─────────────────────────────┤
│ Selected village details / action workflow                               │
└──────────────────────────────────────────────────────────────────────────┘
```

## Selected village panel

```text
RAVANGLA

P1 · EPS 0.91

Population
2,840

EPS breakdown
Rainfall              +0.31
Population            +0.22
Isolation risk        +0.19
Shelter distance      +0.11

Assigned shelter
Government HS
Capacity 3,200

Safe route
2.4 km
NH-10 avoided

[ Create Action Card ]
```

---

# 9. Action Card Composer

The composer opens from the Priority workspace.

It can be a modal, drawer, or dedicated sub-route:

`/console/priority/action/:villageId`

## Composer

```text
ACTION CARD

Escalation stage
[ Green Watch ]
[ Yellow Pre-Alert ]
[ Orange Evacuation Ready ]
[ Red Evacuate Now ]

Language
[ Mizo ▼ ]

Generated instruction

"Residents of Ravangla should move to
Government Higher Secondary School..."

[ Edit ]

🔊 Audio preview

Shelter
✓ Confirmed

Route
✓ Confirmed

Officer
R. Das

Timestamp
18:04 IST

[ Cancel ]     [ Approve & Dispatch ]
```

The final action is deliberately separated from prediction.

The officer must explicitly approve.

---

# 10. Approve & Dispatch workflow

`Approve & Dispatch` opens a confirmation step.

```text
CONFIRM EVACUATION

Village       Ravangla
Stage         RED
Population    2,840
Shelter       Confirmed
Route         Confirmed
Language      Mizo

Channels
✓ CAP 1.2
✓ SMS
✓ Cell Broadcast
✓ Voice

Approved by
Officer R. Das

[ Cancel ]

[ CONFIRM DISPATCH ]
```

After confirmation:

```text
✓ ALERT DISPATCHED

CAP 1.2 generated
SMS queued
Cell broadcast queued
Voice alert generated
Audit event recorded
```

This is the central operational moment of the product.

---

# 11. Commander — simulation workspace

**Route:** `/console/commander`

## Answers

> What if conditions change?

The What-if simulator is its own navigation item.

Do not put the simulator permanently on Situation.

## Layout

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Situation │ Impact │ Priority │ COMMANDER │ Audit │ Trust               │
├───────────────────────────────────────┬──────────────────────────────────┤
│                                       │ WHAT-IF SIMULATOR                │
│              MAP                      │                                  │
│                                       │ Rainfall intensity               │
│ scenario delta                       │ [ 70 mm/h ───────── ]             │
│                                       │                                  │
│                                       │ Duration                         │
│                                       │ [ 6 hours ▼ ]                    │
│                                       │                                  │
│                                       │ [ RUN SCENARIO ]                 │
├───────────────────────────────────────┴──────────────────────────────────┤
│ SCENARIO RESULT                                                          │
│ +6 cells · +2 P1 villages · +3 blocked roads · +1,240 potentially cut off│
└──────────────────────────────────────────────────────────────────────────┘
```

## Scenario controls

- Rainfall intensity
- Rainfall duration
- Other supported scenario inputs from `BUILD_PLAN.md`

## Result diff

Always compare against the current baseline.

Show:

- cells crossing threshold
- new village tier promotions
- newly isolated villages
- newly blocked road segments
- population affected
- evacuation-window changes

---

# 12. AI Emergency Commander

The AI Emergency Commander is a **separate feature inside Commander**, not part of the main Situation page.

Possible sub-navigation:

```text
Commander
├── What-if Simulator
└── AI Emergency Commander
```

Routes:

- `/console/commander/simulator`
- `/console/commander/ai`

## AI Emergency Commander

```text
AI EMERGENCY COMMANDER

Situation summary

3 villages are currently P1.
NH-10 has elevated blockage probability.

────────────────────────────────────

AI recommendation

"Consider preparing an evacuation
order for Ravangla because..."

────────────────────────────────────

Reasoning

• rainfall threshold exceeded
• elevated soil moisture
• road isolation risk increasing

────────────────────────────────────

⚠ HUMAN-IN-THE-LOOP

This system proposes.
An authorised officer decides.

[ Open Priority ]
[ Run What-if ]
```

The AI cannot directly dispatch an alert.

This boundary must remain visible.

---

# 13. Audit — accountability workspace

**Route:** `/console/audit`

## Answers

> Who was warned, who approved it, who acknowledged it, and when?

Full-width workspace.

The map is hidden.

## Two views

### Alert Log

```text
ALERT LOG

ID          Village      Stage   Approved       Delivery   Ack
ALT-0812    Ravangla     RED     R. Das         94%        86%
ALT-0811    Namchi       ORANGE  P. Singh       91%        72%
```

Clicking an alert opens its event timeline.

### Timeline

```text
18:00  Risk detected
18:01  DDMA notified
18:03  Officer opened alert
18:04  Officer approved
18:05  CAP generated
18:05  SMS dispatched
18:07  Cell broadcast
18:12  86% acknowledged
```

### Scorecard

Replay-only comparison against held-out scenarios.

Include:

- system lead time
- villages flagged
- events missed
- evaluation statement

---

# 14. CAP 1.2 export

Available from Audit.

```text
Selected alert
ALT-2026-0812

[ Export CAP 1.2 XML ]
```

The export must produce the actual CAP 1.2 representation once implemented.

Do not display fabricated XML in the prototype.

---

# 15. Trust — evidence and transparency workspace

**Route:** `/console/trust`

## Answers

> Why should I believe this system?

Full-width.

Sections:

1. Model card
2. Evaluation
3. Held-out events
4. Threshold tuning
5. False-alarm cost
6. Data provenance
7. Known limitations

## Model card

Show:

- model version
- algorithm
- features
- training window
- spatial cross-validation
- evaluation results

## Threshold tuning

The threshold control may also have a compact mirrored version in Situation.

However, the complete threshold analysis belongs here.

Show:

- threshold
- confusion matrix
- false-alarm tradeoff
- labelled sample size
- explicit caveats

## Known limitations

Keep limitations visible:

- InSAR vegetation decorrelation
- satellite soil moisture is a proxy
- sparse gauge density
- sudden shallow debris flows may not have useful InSAR precursors
- data coverage gaps

Never hide these limitations behind a generic disclaimer.

---

# 16. Global provenance footer

Every DDMA workspace ends with the same compact provenance component.

```text
MODE: LIVE
TICK: 18:00 IST
MODEL: v0.8.2
RECONSTRUCTED: NO
```

This is four lines maximum.

It should not become a large panel.

---

# 17. Citizen application

The citizen app has completely different navigation.

Three bottom tabs:

1. Alert
2. Route
3. Report

No DDMA navigation is shown.

---

# 18. Citizen — Alert

**Route:** `/citizen/alert`

The screen answers:

> Am I in danger and what should I do?

```text
┌───────────────────────────────┐
│ NIRANTAR              Mizo ▼ │
├───────────────────────────────┤
│                               │
│ 🔴 RED                        │
│ EVACUATE NOW                  │
│                               │
│ RAVANGLA                      │
│                               │
│ Heavy rainfall and slope      │
│ movement have created a       │
│ landslide risk.               │
│                               │
├───────────────────────────────┤
│ WHAT TO DO                    │
│                               │
│ Go to Government Higher       │
│ Secondary School.             │
│                               │
│ Avoid NH-10.                  │
│                               │
│ [ 🔊 LISTEN ]                 │
│                               │
│ [ 🧭 SAFE ROUTE ]             │
└───────────────────────────────┘
```

No probability, SHAP, model version, or technical information.

---

# 19. Citizen — Route

**Route:** `/citizen/route`

This is the navigation-app-like experience.

```text
┌───────────────────────────────┐
│ ← Safe route                  │
├───────────────────────────────┤
│                               │
│             MAP               │
│                               │
│       ● Current location      │
│          ╲                    │
│           ╲ SAFE ROUTE        │
│            ╲                  │
│             🏫 Shelter        │
│                               │
│       ❌ NH-10               │
│          AVOID                │
│                               │
├───────────────────────────────┤
│ Government HS                 │
│ 2.4 km · approximately 18 min │
│                               │
│ [ START ROUTE ]               │
└───────────────────────────────┘
```

If the route engine is not implemented, show an honest placeholder rather than a fake route.

---

# 20. Citizen — Report

**Route:** `/citizen/report`

Functions:

- camera capture
- automatic geotag
- category
- optional note
- local queue
- sync status

Categories:

- Crack
- Blocked road
- Water seepage

Offline behaviour:

```text
OFFLINE

Report saved locally.

3 reports waiting to sync.

Last successful sync
17:42 IST
```

---

# 21. Persistent citizen offline status

Always visible above the bottom navigation.

States:

### Online

`● Online & synced`

### Offline

`○ Offline · 3 items queued`

### Syncing

`↻ Syncing · 2 items remaining`

This makes the offline-first architecture visible to the user.

---

# 22. Navigation hierarchy

The complete information architecture is now:

```text
NIRANTAR
│
├── DDMA CONSOLE
│   │
│   ├── Situation
│   │   ├── Risk map
│   │   ├── Cell details
│   │   ├── Village details
│   │   ├── Citizen reports
│   │   └── Drivers / provenance
│   │
│   ├── Impact
│   │   ├── Road isolation
│   │   ├── Blockage probability
│   │   ├── Bridges
│   │   ├── Isolation polygons
│   │   └── Isolation table
│   │
│   ├── Priority
│   │   ├── EPS ranking
│   │   ├── Shelter assignment
│   │   ├── Safe route
│   │   └── Action Card Composer
│   │       └── Approve & Dispatch
│   │
│   ├── Commander
│   │   ├── What-if Simulator
│   │   └── AI Emergency Commander
│   │
│   ├── Audit
│   │   ├── Alert Log
│   │   ├── Event Timeline
│   │   ├── Delivery / acknowledgement
│   │   ├── Replay Scorecard
│   │   └── CAP 1.2 Export
│   │
│   └── Trust
│       ├── Model Card
│       ├── Evaluation
│       ├── Held-out Events
│       ├── Threshold Tuning
│       ├── Data Provenance
│       └── Known Limitations
│
└── CITIZEN APP
    │
    ├── Alert
    ├── Route
    └── Report
```

---

# 23. What belongs on the Situation page

The Situation page should remain intentionally restrained.

### Always visible

- map
- active risk state
- critical/watch/normal counts
- top drivers
- selected-object information
- layer controls
- legend
- provenance

### Accessible through navigation

Do NOT permanently show:

- Road Isolation Index
- full evacuation priority list
- Action Card Composer
- What-if Simulator
- AI Emergency Commander
- Audit timeline
- CAP export
- Model card
- full threshold analysis

This is the key change from the previous prototype.

---

# 24. Interaction rule

The interface should follow:

> **Progressive disclosure.**

A user sees only the information necessary for the current decision.

Example:

```text
Situation
    ↓
Select Ravangla
    ↓
[ View Priority ]
    ↓
Priority
    ↓
[ Create Action Card ]
    ↓
Action Card
    ↓
[ Approve & Dispatch ]
    ↓
Audit
```

The user never has to look at five unrelated panels simultaneously.

---

# 25. Map singleton

The map remains a singleton for the DDMA console.

One MapLibre instance is created when the shell mounts.

Tabs/workspaces change:

- active layers
- selected object
- map bounds
- overlays

They do not create a new map.

Audit and Trust hide the map container but do not destroy the MapLibre instance.

---

# 26. Feature placement table

| Feature | Home |
|---|---|
| Risk heatmap | Situation |
| SHAP attribution | Situation → selected object |
| Confidence heuristic | Situation → selected object |
| InSAR creep | Situation |
| Rainfall context | Situation |
| Soil moisture | Situation |
| Citizen reports | Situation |
| Road blockage probability | Impact |
| Runout envelope | Impact |
| Bridge failure risk | Impact |
| Road Isolation Index | Impact |
| Isolation duration | Impact |
| Critical infrastructure | Impact |
| EPS P1/P2/P3 | Priority |
| EPS breakdown | Priority |
| Shelter assignment | Priority |
| Safe route | Priority |
| Action Card | Priority |
| Escalation stage | Action Card |
| Multilingual text | Action Card |
| Voice synthesis | Action Card |
| Approve & Dispatch | Action Card |
| CAP 1.2 | Audit / Dispatch |
| What-if simulator | Commander |
| AI Emergency Commander | Commander |
| Audit log | Audit |
| Delivery stats | Audit |
| Replay scorecard | Audit |
| Model card | Trust |
| False-alarm threshold | Trust |
| Held-out disclosure | Trust |
| Data provenance | Trust + global footer |
| Known limitations | Trust |
| Citizen alert | Citizen / Alert |
| Citizen navigation | Citizen / Route |
| Citizen reporting | Citizen / Report |
| Offline sync | Citizen |

---

# 27. Placeholder policy

Any feature not yet implemented uses:

```tsx
<NotBuilt
  task="TASK-ID"
  what="Short description"
  blocks="What depends on this feature"
/>
```

It must never display:

- fabricated numbers
- fake charts
- fake routes
- fake model results
- indefinite loading spinners
- lorem ipsum

Honest placeholders are part of the product design.

---

# 28. Visual design language

The interface should feel like a professional emergency operations system.

## Primary visual language

- dark navy command-centre background
- restrained cyan/teal system accents
- red = immediate danger
- orange = evacuation ready
- amber = watch
- green = safe
- high information density in DDMA workspaces
- large operational values
- minimal decorative UI
- strong GIS visual hierarchy

Avoid excessive glassmorphism, gradients, glowing cards, and decorative AI effects.

The product should communicate:

**serious · operational · trustworthy · geographic · explainable**

not:

**generic AI dashboard**.

---

# 29. Demo journey

The recommended SIH demo should use the navigation intentionally.

### 1. Situation

Show the live map.

> "The system has detected elevated risk around Ravangla."

### 2. Impact

Navigate to Impact.

> "The danger is not only the slope. NH-10 may isolate the village."

### 3. Priority

Navigate to Priority.

> "Ravangla is therefore promoted to P1."

### 4. Action Card

Open the action card.

> "The system generates the village-level evacuation instruction."

### 5. Approve & Dispatch

Officer approves.

> "This is where a prediction becomes an accountable evacuation."

### 6. Audit

Navigate to Audit.

> "Now we can prove who approved it, when it was dispatched, and who acknowledged it."

### 7. Commander

Run a What-if scenario.

> "And if rainfall intensifies, we can simulate how the situation changes."

### 8. Trust

Show the model and limitations.

> "And we expose the evidence and limitations instead of hiding them."

### 9. Citizen

Switch to Citizen.

> "The villager doesn't see any of this complexity. They simply see: evacuate, where to go, and which road to avoid."

---

# 30. Acceptance criteria

The frontend is complete when:

1. The Situation page is visually strong and uncluttered.
2. Six DDMA navigation workspaces exist.
3. Each major feature has one clear home.
4. Simulator is accessible from Commander rather than permanently displayed.
5. AI Emergency Commander is accessible from Commander rather than permanently displayed.
6. Action Card Composer lives inside Priority.
7. Audit is a separate full-width workspace.
8. Trust is a separate full-width workspace.
9. Situation never becomes a cumulative panel stack.
10. MapLibre is instantiated only once.
11. Navigation changes the active workspace without recreating the map.
12. Every unbuilt feature uses `NotBuilt`.
13. No screen displays fabricated numbers.
14. Citizen navigation contains only Alert, Route, and Report.
15. A judge can reach every major feature in at most two clicks from the main console.
16. The product remains understandable even when only the Situation page is demonstrated.
17. The complete workflow from detection to acknowledgement can be demonstrated by navigating through the relevant workspaces.
