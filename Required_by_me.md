# Required by me — things only you can do

Phases 0 and most of Phases 1–5's independently-buildable tasks are done and verified (see
BUILD_PLAN.md's checkboxes and CLAUDE.md §11/§12 for the full state). This file only tracks what
is genuinely stuck on YOU — an external account, a portal registration, a decision that's yours,
or a physical action. Everything else keeps moving in parallel regardless of these.

**Nothing below blocks the current work.** Check items off as you do them.

---

## Genuinely time-sensitive (start these when you have a few minutes — they have real lead time)

- [ ] **IMD public API access** (`api.imd.gov.in`) — task 1.8. `ingest/live/imd.py` is now
      written and unit-tested (34 tests, real endpoint paths confirmed against IMD's own public
      `api_reference.html`, wrapped in a circuit breaker so its absence never stalls the
      pipeline) — the only thing missing is a real key to verify the live path against. Expect
      IP-whitelisting friction (BUILD_PLAN.md already flags this). Put the key in `.env` as
      `IMD_API_KEY` once you have it, then re-run `python -m app.ingest.live.imd --aoi aizawl`
      (from `backend/`) to confirm the real auth-header assumption in `build_auth_headers()` —
      that one field name is the single genuinely-unconfirmed guess in the module. Supplementary,
      not on the critical path — nothing is waiting on this.
- [ ] **GSI Bhukosh access** for lithology/geology data (task 1.4 — deliberately scheduled last
      in Phase 1, still not urgent). Unchanged from before: `bhukosh.gsi.gov.in/Bhukosh/Public`
      refused an automated connection outright, so registration steps are unconfirmed from this
      end. Also worth checking `bhusanket.gsi.gov.in`. If a bulk export comes through, commit it
      as a small static file (same pattern as the COOLR CSV). If it doesn't come through in time,
      the documented `coarse_fallback` path is fine — this has a real fallback, so it's worth
      attempting but isn't a hard blocker. `ml/train.py`'s trained model already carries
      `lithology_class` as an explicit missing feature ready to use the moment this lands, with a
      documented retrain step — no code changes needed when it does.
- [ ] **NASA SMAP real-download verification (task 1.7) may need its own separate Earthdata
      step**, not automatically covered by task 1.6's GES DISC authorization. `ingest/live/smap.py`
      is written and unit-tested (30 tests against a real NSIDC v5 User Guide-verified product
      structure) — real verification is blocked because this session's environment couldn't open
      a TCP connection to `n5eil01u.ecs.nsidc.org` at all (stricter than task 1.6's original
      session, which at least reached GES DISC). Worth checking whether your Earthdata profile's
      Applications tab needs a separate "NSIDC DAAC" (not just "GESDISC") authorization the same
      way GES DISC did — genuinely unconfirmed, not assumed either way.

## Your call, not mine

- [ ] **Git branching strategy.** Still undecided by you, but in practice this session (and the
      large parallel-subagent session after it) has continued committing straight to `main` out
      of necessity — every worktree-isolated subagent's branch gets merged back to `main`
      directly once reviewed, since no feature-branch/PR policy was ever chosen. If you want that
      to change for what's left of the build (Phase 3's remaining UI, Phase 5 polish, Phase 6),
      say so; otherwise this is now the de facto convention, not just a default.
- [ ] **Aeroplane-mode rehearsal (task 5.4)** will need you at the actual demo laptop at some
      point before the freeze — physically disabling networking and running a full replay is not
      something I can do remotely. Not urgent yet; flagging so it's on your radar before Phase 6.
- [ ] **Phase 6 in general** (demo script content, freeze/tag timing, which judge questions get
      rehearsed, the actual submission) is yours by design — CLAUDE.md's rule against trading
      honesty for demo polish means none of those are mine to decide unilaterally.

## Resolved since the last version of this file (informational, not actionable)

- The `RunoutEnvelope`/`TickResult` schema gap this file used to flag under "known gaps" is
  fixed — `runouts` is now a real field, populated by the real impact pipeline.
- `pipeline.py` is now wired to every real risk/impact/decision module built this session (was
  100% Phase-0 stubs before). A real, non-trivial limitation surfaced while doing that and is
  now **mostly** fixed, not just flagged: LIVE mode and two of the four replay scenarios
  (`wayanad-2024`, `tupul-2022`) still use `aoi_id`s with no registered `config.AOIS` entry or
  built Phase-2 static data (a pre-existing, already-documented gap from when those scenarios
  were built) — for those, `pipeline.py` degrades gracefully to risk-only ticks rather than
  crashing, but real village-level escalation/action-cards don't fire. `_smoke.json` and
  `aizawl-2024.json` (which share the same 9-cell layout) were remapped this session onto real
  `cells.gpkg` cells matching real named villages, so the primary case-study scenario now
  produces genuine end-to-end village escalation and action cards. Standing up Wayanad/Tupul's
  own AOI static data (DEM/grid/exposure/road-graph, all public/no-auth) is real future work but
  not blocked on you — it's schedulable like any other READY task.
