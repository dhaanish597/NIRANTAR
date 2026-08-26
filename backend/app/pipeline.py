"""The pipeline orchestrator (BUILD_PLAN.md task 0.10).

frame -> risk -> impact -> decision -> dissemination(recommendation only) -> audit. Phase 0 had
every stage past risk/ as a deterministic stub ("the pipe is real, the water is fake"). This
version wires in the real modules built across Phase 1/2/3 (tasks 1.12-1.19, 2.1-2.6, 3.1-3.3,
3.6) — the water is now real for Aizawl. This file itself must never check `if mode == REPLAY`
(CLAUDE.md §2) — `mode` and `scenario_id` are passed in only to be stamped onto the outgoing
TickResult, not branched on. Every module this file calls is itself mode-blind; wiring them
together does not change that.

===================================================================================================
RULINGS MADE WIRING THIS TOGETHER (read before changing this file)
===================================================================================================

1. **The cell-id mismatch is real and NOT fixed here.** CLAUDE.md's Current State and
   `risk/model.py`'s own docstring both flag it: LIVE's `ingest/live/stub_source.py` and every
   committed scenario JSON still use the Phase-0 stub `aizawl_{row}{col}` cell-id convention,
   while `data/static/aizawl/cells.gpkg` (the real terrain grid `risk/model.py` predicts against)
   uses a different convention. Unifying them is a separate, larger task (touching 3 committed
   scenario files + `ingest/live/stub_source.py` + `frontend/src/lib/grid.ts`) — deliberately out
   of scope for "wire the already-built real modules into the pipeline." Consequence, stated
   plainly rather than hidden: **every cell in a LIVE or REPLAY tick today reports as "unmatched"
   against the real terrain grid**, so `_compute_cell_risks()` below always falls back to the
   threshold-only path for all of them (see ruling 2). The real ML model, real SHAP attributions,
   and real terrain-driven runout envelopes are fully wired and will start actually firing the
   moment a future session lands that id migration — no further pipeline.py change needed then.

2. **Threshold-only fallback for unmatched cells, not silence.** `risk/model.py`'s
   `predict_batch()` correctly refuses to fabricate a p_fail for a cell_id it has no terrain row
   for (drops it, returns it in `unmatched_cell_ids`). Dropping those cells entirely from the tick
   would mean the map renders nothing at all — worse than degrading to the always-available,
   physically-grounded fallback BUILD_PLAN.md's own risk register names: `risk/thresholds.py`'s
   I-D/E-D exceedance engine, which needs only rainfall (no terrain), and `risk/fusion.py`'s own
   `max(ml_p_fail, exceedance)` rule degrades correctly to `exceedance` alone when `ml_p_fail=0`.
   Every such cell is returned with `model_version="threshold_only_v1"` — never silently presented
   as an ML prediction (CLAUDE.md rule 1).

3. **Escalation and action cards are tracked per VILLAGE, not per cell.** BUILD_PLAN.md task 3.2
   says "off a CellRisk/p_fail trajectory" and `decision/escalation.py` is deliberately entity-
   agnostic about what a "trajectory" belongs to. `decision/action_card.py`'s own convenience
   entry point (`build_action_card_from_escalation`) defaults `entity_id` to `village_id` — the
   module's own design already assumes a village is the natural unit for an evacuation
   recommendation (a cell is an abstract 500m terrain patch; nobody evacuates a cell). This file
   tracks one `EscalationStateMachine` keyed by `village_id`, fed by `impact/priority.py`'s
   resolved "this village's nearest cell's p_fail" — not a second, separate per-cell escalation
   ladder.

4. **`decision/window.py`'s safe-window is computed once per tick, at AOI level — not per
   village.** Building a real per-village-nearest-cell rolling trajectory (a `{cell_id: history}`
   map, kept in sync with which cell is nearest which village) is a bigger piece of new state than
   this integration pass's scope justifies. Instead: one rolling trajectory per AOI, one point per
   tick, each point being that tick's MAXIMUM `threshold_exceedance_ratio` across every observed
   cell (`config.PIPELINE_EXCEEDANCE_HISTORY_LEN`-capped) — "the AOI's worst-observed exceedance
   trend." The resulting `SafeWindowEstimate` is applied to every alert-worthy village's card this
   tick. Documented here and in `docs/BUILD_PLAN.md` as an AOI-level approximation, not a per-
   village-precise one — a natural refinement, not silently claimed as finer-grained than it is.

5. **No village-level SHAP attributions this pass.** Wiring "this village's nearest cell's
   `Attribution` list" would need a village -> nearest-cell-id lookup `impact/priority.py`'s
   `resolve_priority_inputs()` does not expose (it returns the resolved p_fail VALUE, not which
   cell it came from). `decision/action_card.py` already handles `attributions=None` gracefully
   (a still-honest, non-fabricated generic reason sentence) — used here rather than adding new
   surface area to an already-tested module for this pass. Given ruling 1, real attributions are
   moot right now anyway (every cell is threshold-only, `attributions=[]`, until the id migration
   lands).

6. **Dissemination is NOT auto-fired from this file.** `dissemination/channels.py` (task 3.5) and
   `audit/producers.record_dissemination()` (task 3.6) are real and fully wired-*able*, but calling
   them automatically here — sending every alert-worthy card out over every simulated channel the
   instant the AI flags it — would bypass CLAUDE.md's explicit human-in-the-loop rule ("The AI
   recommends, a DDMA officer approves. Human-in-the-loop always"; rule 9: "Autonomous evacuation
   orders" is something this project deliberately does NOT build). This file produces the AI
   RECOMMENDATION (`TickResult.new_action_cards`) and nothing past it. A DDMA-approval API endpoint
   that calls `audit.producers.record_ddma_decision()` and then the channels is BUILD_PLAN.md task
   3.7 (the DDMA Console) — not built this session, and intentionally not simulated here either.

7. **AOIs with no Phase-2 static data (or no `config.AOIS` entry at all — e.g. `wayanad-2024`/
   `tupul-2022`, whose scenario files use `aoi_id`s not yet registered, a gap those scenarios'
   own tasks already flagged) degrade to risk-only, not a crash.** `FileNotFoundError` (raised by
   every real loader when its AOI's static artifact is missing) and `KeyError` (raised by
   `config.get_aoi()` for an unregistered AOI) around the whole impact/decision block are both
   caught; `TickResult.road_risks`/`isolations`/`priorities`/`runouts`/`new_action_cards` are empty
   for that tick, `cell_risks` (real risk, still driven by real rainfall via the threshold engine)
   are not.

8. **Known, documented, NOT this pass's problem: per-tick GeoPandas re-reads.**
   `impact/priority.py`'s `resolve_priority_inputs()` re-reads `cells.gpkg`/`exposure.gpkg` from
   disk every call (it takes the tick's dynamic `cell_risks_by_cell_id` as an argument, so it
   cannot be cached the same way the purely-static loaders below are). Acceptable for a demo's
   tick cadence; a real perf pass would split that function into a cached static half + a cheap
   dynamic lookup half — not attempted here, to avoid restructuring an already-tested module's
   public API as a side effect of pipeline wiring.
"""
from __future__ import annotations

from app.audit.log import AuditLog
from app.config import PIPELINE_EXCEEDANCE_HISTORY_LEN, get_aoi
from app.decision.action_card import ALERT_WORTHY_STAGES, build_action_card
from app.decision.escalation import EscalationStateMachine
from app.decision.routing import (
    build_reference_graph,
    build_routable_graph,
    find_best_shelter_route,
    resolve_routing_inputs,
)
from app.decision.window import (
    WindowObservation,
    estimate_safe_window,
)
from app.impact.isolation import build_isolation_inputs, compute_all_village_isolations
from app.impact.priority import compute_settlement_priorities, resolve_priority_inputs
from app.impact.road_graph import compute_road_segment_risks, load_road_graph, road_edges_from_graph
from app.impact.runout import compute_runout_envelopes, load_cell_terrain, project_envelope_to_wgs84
from app.risk.fusion import fuse_p_fail
from app.risk.model import ModelNotTrainedError, _confidence_from_probability, get_model
from app.risk.thresholds import threshold_exceedance_ratio
from app.schemas.ingest import ObservationFrame
from app.schemas.mode import RunMode
from app.schemas.risk import CellRisk
from app.schemas.tick import TickResult

# =================================================================================================
# Per-AOI static caches. Every artifact below is built once, offline, by a scripts/ one-shot job
# (task 1.2/1.3/2.1) and does not change tick to tick — re-reading a multi-MB .gpkg/.pkl from disk
# on every frame would be real, measurable waste for zero benefit. Same process-wide-cache idiom
# `risk/model.py`'s own `_MODEL_CACHE`/`get_model()` already uses, kept consistent rather than
# inventing a second caching pattern in the same codebase.
# =================================================================================================
_TERRAIN_CACHE: dict[str, dict] = {}
_ROAD_GRAPH_CACHE: dict[str, object] = {}
_ROAD_EDGES_CACHE: dict[str, list] = {}
_ISOLATION_INPUTS_CACHE: dict[str, tuple] = {}
_ROUTING_INPUTS_CACHE: dict[str, tuple] = {}


def _get_terrain(aoi_id: str) -> dict:
    if aoi_id not in _TERRAIN_CACHE:
        _TERRAIN_CACHE[aoi_id] = load_cell_terrain(aoi_id)
    return _TERRAIN_CACHE[aoi_id]


def _get_road_graph(aoi_id: str):
    if aoi_id not in _ROAD_GRAPH_CACHE:
        _ROAD_GRAPH_CACHE[aoi_id] = load_road_graph(aoi_id)
    return _ROAD_GRAPH_CACHE[aoi_id]


def _get_road_edges(aoi_id: str) -> list:
    if aoi_id not in _ROAD_EDGES_CACHE:
        _ROAD_EDGES_CACHE[aoi_id] = road_edges_from_graph(_get_road_graph(aoi_id))
    return _ROAD_EDGES_CACHE[aoi_id]


def _get_isolation_inputs(aoi_id: str) -> tuple:
    if aoi_id not in _ISOLATION_INPUTS_CACHE:
        _ISOLATION_INPUTS_CACHE[aoi_id] = build_isolation_inputs(aoi_id, _get_road_graph(aoi_id))
    return _ISOLATION_INPUTS_CACHE[aoi_id]


def _get_routing_inputs(aoi_id: str) -> tuple:
    if aoi_id not in _ROUTING_INPUTS_CACHE:
        _ROUTING_INPUTS_CACHE[aoi_id] = resolve_routing_inputs(aoi_id, _get_road_graph(aoi_id))
    return _ROUTING_INPUTS_CACHE[aoi_id]


def _compute_cell_risks(frame: ObservationFrame) -> tuple[list[CellRisk], list[str]]:
    """Real ML inference (task 1.17) for cells whose id matches the real terrain grid, threshold-
    engine-only fallback (see module docstring, ruling 2) for every cell that doesn't. Returns
    (all_cell_risks, unmatched_ids_that_used_the_fallback)."""
    try:
        model = get_model(frame.aoi_id)
    except FileNotFoundError:
        # ModelNotTrainedError (model artifact missing) is itself a FileNotFoundError subclass;
        # RiskModel.load() also raises a plain FileNotFoundError if this AOI has no cells.gpkg at
        # all. Both mean "no real ML signal available for this AOI right now" — degrade to the
        # threshold-only fallback for every cell, don't crash the tick.
        model = None

    if model is not None:
        matched_risks, unmatched_ids = model.predict_batch(frame.cells)
    else:
        matched_risks, unmatched_ids = [], [obs.cell_id for obs in frame.cells]

    fallback_risks: list[CellRisk] = []
    obs_by_id = {obs.cell_id: obs for obs in frame.cells}
    for cell_id in unmatched_ids:
        obs = obs_by_id[cell_id]
        exceedance = threshold_exceedance_ratio(obs)
        p_fail = fuse_p_fail(0.0, exceedance)
        fallback_risks.append(
            CellRisk(
                cell_id=cell_id,
                p_fail=p_fail,
                threshold_exceedance=exceedance,
                confidence=_confidence_from_probability(p_fail),
                attributions=[],
                model_version="threshold_only_v1",
            )
        )
    return matched_risks + fallback_risks, unmatched_ids


class Pipeline:
    """Holds every piece of state that must thread from one tick to the next: the audit hash
    chain, the per-village escalation ladder, and the AOI-level exceedance trajectory
    `decision/window.py` fits a trend against (see module docstring, rulings 3 and 4)."""

    def __init__(
        self,
        *,
        audit_log: AuditLog | None = None,
        escalation: EscalationStateMachine | None = None,
    ):
        self.audit_log = audit_log or AuditLog()
        self.escalation = escalation or EscalationStateMachine(audit_log=self.audit_log)
        self._exceedance_history: list[WindowObservation] = []

    def process(
        self, frame: ObservationFrame, *, mode: RunMode, scenario_id: str | None = None
    ) -> TickResult:
        aoi_id = frame.aoi_id

        # ---- risk (task 1.17/1.19, real ML + threshold-engine fallback — ruling 1/2) ----
        cell_risks, _unmatched_ids = _compute_cell_risks(frame)

        # AI_FLAGGED is appended HERE — right after risk, before impact/decision — not at the end
        # of this method, even though it was historically written last (Phase 0). Escalation
        # transitions (below) also append to this SAME audit_log, and a real village whose
        # terrain-only floor already sits above GREEN (e.g. Durtlang's ~0.70) can genuinely
        # transition on tick 1. If AI_FLAGGED were appended after that, its own `prev_hash` would
        # chain from the ESCALATED event instead of whatever came before this tick — silently
        # wrong hash-chain ordering, caught by test_api_state.py's own restart-residue test (which
        # checks the very first tick's first event chains from the genesis hash). AI_FLAGGED is
        # conceptually "the AI observed this tick's data" — it belongs first in the chain for this
        # tick, before any consequence (an escalation) that observation produces.
        ai_flagged_event = self.audit_log.append(
            event_id=f"evt-{frame.aoi_id}-{frame.t.isoformat()}",
            alert_id=f"tick-{frame.aoi_id}-{frame.t.isoformat()}",
            kind="AI_FLAGGED",
            actor="system",
            t=frame.t,
            payload={
                "aoi_id": frame.aoi_id,
                "cell_count": len(frame.cells),
                "max_p_fail": max((r.p_fail for r in cell_risks), default=0.0),
            },
        )

        # ---- decision/window.py's AOI-level trajectory (ruling 4) ----
        safe_window = None
        if frame.cells:
            tick_max_exceedance = max(threshold_exceedance_ratio(obs) for obs in frame.cells)
            self._exceedance_history.append(
                WindowObservation(t=frame.t, exceedance_ratio=tick_max_exceedance)
            )
            self._exceedance_history = self._exceedance_history[-PIPELINE_EXCEEDANCE_HISTORY_LEN:]
            safe_window = estimate_safe_window(self._exceedance_history, now=frame.t)

        # ---- impact: runout -> road risk -> isolation -> priority (tasks 2.2-2.5) ----
        runouts_wgs84: list = []
        road_risks: list = []
        isolations: list = []
        priorities: list = []
        new_action_cards: list = []
        new_escalation_events: list = []

        try:
            aoi_cfg = get_aoi(aoi_id)
            terrain = _get_terrain(aoi_id)
            envelopes_native = compute_runout_envelopes(cell_risks, terrain)
            runouts_wgs84 = [
                project_envelope_to_wgs84(e, aoi_cfg.utm_epsg) for e in envelopes_native
            ]
            edges = _get_road_edges(aoi_id)
            road_risks = compute_road_segment_risks(edges, runouts_wgs84)
            edge_risk_by_id = {r.edge_id: r for r in road_risks}

            raw_graph = _get_road_graph(aoi_id)
            villages, targets_by_village = _get_isolation_inputs(aoi_id)
            isolations = compute_all_village_isolations(
                villages, raw_graph, edge_risk_by_id, targets_by_village
            )

            cell_risks_by_cell_id = {r.cell_id: r.p_fail for r in cell_risks}
            p_fail_by_village, shelter_distance_km_by_village = resolve_priority_inputs(
                aoi_id, cell_risks_by_cell_id
            )
            priorities = compute_settlement_priorities(
                isolations, p_fail_by_village, shelter_distance_km_by_village
            )

            # ---- decision: per-village escalation -> routing -> action card (tasks 3.1-3.3) ----
            village_node_by_id, shelter_candidates = _get_routing_inputs(aoi_id)
            routable_graph = build_routable_graph(raw_graph, edge_risk_by_id)
            reference_graph = build_reference_graph(raw_graph, edge_risk_by_id)

            for village in villages:
                p_fail = p_fail_by_village.get(village.village_id, 0.0)
                transition = self.escalation.observe(village.village_id, p_fail, frame.t)
                if transition is not None:
                    new_escalation_events.append(transition.audit_event)

                stage = self.escalation.current_stage(village.village_id)
                if stage not in ALERT_WORTHY_STAGES:
                    continue

                node_id = village_node_by_id.get(village.village_id)
                route = None
                if node_id is not None:
                    route = find_best_shelter_route(
                        village.village_id,
                        node_id,
                        shelter_candidates,
                        routable_graph,
                        reference_graph,
                    )
                new_action_cards.append(
                    build_action_card(
                        village_id=village.village_id,
                        stage=stage,
                        p_fail=p_fail,
                        now=frame.t,
                        route=route,
                        safe_window=safe_window,
                    )
                )
        except (FileNotFoundError, KeyError):
            # No Phase-2 static data for this AOI (or no config.AOIS entry at all — e.g. the
            # wayanad-2024/tupul-2022 scenarios' own already-documented AOI-config gap). Degrade
            # to risk-only for this tick rather than crash the whole replay — ruling 7.
            pass

        return TickResult(
            t=frame.t,
            mode=mode,
            scenario_id=scenario_id,
            aoi_id=frame.aoi_id,
            cell_risks=cell_risks,
            runouts=runouts_wgs84,
            road_risks=road_risks,
            isolations=isolations,
            priorities=priorities,
            new_action_cards=new_action_cards,
            new_audit_events=[ai_flagged_event, *new_escalation_events],
            is_reconstructed=any(c.is_reconstructed for c in frame.cells),
        )
