# Required by me — things only you can do

Phase 0 itself is **done and verified** — nothing below blocks calling Phase 0 complete. This is
a punch-list for what to do *before/while* Phase 1 gets going, split by how urgent it actually is.
Check items off as you do them; delete the file (or the section) once it's empty.

---

## Before Phase 1 can really start (do these first — they have lead time)

- [x] **NASA Earthdata account** — done, credentials are set in `.env` as `EARTHDATA_USERNAME` /
      `EARTHDATA_PASSWORD`. **Note:** they were briefly pasted into `.env.example` (the tracked
      template) instead of `.env` — caught before it was committed, `.env.example` has been
      reverted to empty placeholders, real values moved to `.env`. No leak reached git history.
- [ ] **Authorize the "GES DISC" application on your Earthdata profile — blocks task 1.6 for
      real.** `ingest/live/imerg.py` is written and unit-tested, but every real granule-download
      attempt this session got back NASA's generic GES DISC web-app shell (HTTP 200, HTML, not
      the actual HDF5 file) instead of data — confirmed by actually downloading it and inspecting
      the bytes, not assumed. This is a well-documented NASA Earthdata gotcha (Earthdata Forum:
      *"you need to authorize the application... approve all the apps containing the word
      GESDISC"*) — logging in once does NOT automatically grant every DAAC's data archive access;
      each one needs a one-time explicit approval on your account. **Fix:** log into
      https://urs.earthdata.nasa.gov/profile/applications (or the "Applications" tab of your
      Earthdata profile) with the credentials already in `.env`, and approve/authorize anything
      with "GESDISC" or "GES DISC" in the name. Then re-run
      `python -m app.ingest.live.imerg --aoi aizawl --backfill-hours 1` (from `backend/`, venv
      active) — it should download a real granule instead of raising the "not an HDF5 file"
      error. **This will very likely also block task 1.7 (SMAP)** the same way, since SMAP is
      also GES DISC/NSIDC-hosted — worth checking the same profile page covers it, or expect to
      repeat this exact dance for task 1.7.
- [ ] **IMD public API access** (`api.imd.gov.in`) — task 1.8. BUILD_PLAN.md already flags this:
      *"Expect IP-whitelisting friction."* Start the request now, not when task 1.8 comes up —
      it's supplementary to IMERG (circuit-broken, not on the critical path) so Phase 1 isn't
      blocked waiting on it, but it'll be wasted if left until the last minute. Put the key in
      `.env` as `IMD_API_KEY` once you have it.
- [ ] **GSI Bhukosh access** for lithology/geology data (task 1.4 — now deliberately scheduled
      last in Phase 1, not urgent; see BUILD_PLAN.md's 2026-08-25 note on task 1.4). Still worth
      doing whenever you have a spare few minutes since it has real lead time, just no longer
      blocking anything soon. I couldn't get
      further than public search results: `bhukosh.gsi.gov.in/Bhukosh/Public` refused the
      connection outright when I tried to fetch it (not a timeout — likely rate-limited or
      network-sensitive to automated fetchers), so I can't confirm the exact registration steps
      myself. What's confirmed from search: it distinguishes "GSI Employee" vs. "External User"
      login, and GSI publishes a "Bhukosh Unified Download Reference Guide V 2.0" PDF + tutorial
      videos for the shapefile download flow. Also worth checking `bhusanket.gsi.gov.in` — a
      newer, separate GSI public portal specifically for the Landslide Forecast Bulletin /
      landslide hazard section, which may have the field-validated inventory more directly than
      Bhukosh proper. Register as an External User on one or both, in a real browser — TODO(verify)
      on exact fields / approval turnaround, that needs you, not me. If a bulk export comes
      through, same pattern as COOLR above: commit it as a small static file, don't script against
      a live endpoint. If it doesn't come through in time, the plan already has a fallback
      (`source: "coarse_fallback"`, labelled honestly rather than presented as high-resolution) —
      so this is worth attempting but isn't a hard blocker.
- [x] **NASA COOLR / Global Landslide Catalog — manual browser export (task 1.12)**. Done —
      `data/static/COOLR_Reports_Points.csv` exists (14,963 rows, 9.4 MB). **Two things to
      decide, both mine to flag not to silently choose:**
      1. It's the **global** COOLR table, not India/NER-filtered — the portal's "Location: India"
         facet only filtered which *catalog items* were listed, not the records inside the one
         you exported. Only 177 of 14,963 rows have `country_code == "IN"`; NER-specific will be
         fewer still. `ml/build_inventory.py` (still unwritten) needs to do this filtering itself
         — that's normal, not a redo, just noting the raw file is global-scope.
      2. It currently falls under `.gitignore`'s `data/static/*` rule (confirmed with
         `git check-ignore`), so it won't get committed as-is. CLAUDE.md rule 15 commits "small
         vector files" as an exception to that — 9.4 MB global is borderline, but the India/NER
         subset after task 1.12's filtering would be a genuinely small file worth committing
         (it's not re-fetchable by a script the way the DEM/WorldCover tiles are — it required
         this manual login+export dance, so losing it means repeating today's work). Recommend:
         keep the raw global CSV gitignored as a local cache, commit only the filtered India/NER
         output. Confirm you're fine with that when 1.12 gets written.
      Schema check: the CSV does carry `event_import_source` (values like `GLC`, `SMMML`, etc.) —
      confirms COOLR's "Reports" table already folds in NASA's curated Global Landslide Catalog
      entries alongside citizen reports, so nothing was missed by there being no separate
      "Events" layer in that portal group.

## Verify before Phase 1 needs it

- [x] **Start Docker Desktop.** Done — re-verified myself: `docker compose up -d postgis`
      succeeded, `nirantar_postgis` container is `Up ... (healthy)` on port 5432. Task 1.5
      (`scripts/load_db.py`) is now actually unblocked.
- [ ] *(minor, workaround already noted)* `make up` itself throws a `docker` CLI arg-parsing
      error (`unknown shorthand flag: 'd' in -d`) on this machine specifically — reproducible via
      MSYS make's recipe shell but not when running the identical command directly in Bash. Looks
      like a mismatch between this machine's separately-installed MSYS2 (`make.exe`) and
      Git-for-Windows' bundled MSYS (`sh.exe`/`bash.exe`), not a project bug. Workaround: run
      `docker compose up -d postgis` directly instead of `make up` until/unless you want to chase
      the toolchain mismatch itself — didn't seem worth the time relative to actual Phase 1 work.

## Your call, not mine

- [ ] **Git branching strategy going forward.** Phase 0 was committed straight to `main` — there
      was no history to protect yet, so that was the obvious default. BUILD_PLAN.md's
      parallelization note says once ≥3 people are working (one on `frontend/`, one on
      `backend/risk`+`ml/`, one on `backend/impact`+`backend/decision`), the schemas are what
      let that happen safely. Decide now whether Phase 1 onward moves to feature branches / PRs,
      or stays on `main` — I'll follow whatever you pick, but I won't invent a branching policy
      you didn't ask for.
- [ ] **Skim the "known gaps" list in `CLAUDE.md` §11** (`RunoutEnvelope` not on `TickResult` yet,
      `MapView`'s deliberately-no-basemap style, synthetic cell geometry, the new
      `ingest/factory.py` file). None of these need fixing right now, but Phase 2's impact work
      in particular will run into the `RunoutEnvelope` gap directly — worth having an opinion on
      it before that phase starts rather than discovering it mid-task.

## Optional convenience (skip if you don't care)

- [ ] **Put `make` on PATH.** It's installed via MSYS2 at `C:\msys64\usr\bin\make.exe` but isn't
      on PATH in this environment, so I've been invoking it by full path. Add that directory to
      PATH (or add a shim) if you want to just type `make dev` / `make test` yourself without the
      full path.
