# Required by me — things only you can do

Phase 0 itself is **done and verified** — nothing below blocks calling Phase 0 complete. This is
a punch-list for what to do *before/while* Phase 1 gets going, split by how urgent it actually is.
Check items off as you do them; delete the file (or the section) once it's empty.

---

## Before Phase 1 can really start (do these first — they have lead time)

- [ ] **NASA Earthdata account** — sign up at https://urs.earthdata.nasa.gov/. Needed for
      IMERG rainfall (`ingest/live/imerg.py`, task 1.6), the primary rainfall source. Put the
      credentials in `.env` as `EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD` (copy `.env.example`
      to `.env` first — `.env` is gitignored, never commit it).
- [ ] **IMD public API access** (`api.imd.gov.in`) — task 1.8. BUILD_PLAN.md already flags this:
      *"Expect IP-whitelisting friction."* Start the request now, not when task 1.8 comes up —
      it's supplementary to IMERG (circuit-broken, not on the critical path) so Phase 1 isn't
      blocked waiting on it, but it'll be wasted if left until the last minute. Put the key in
      `.env` as `IMD_API_KEY` once you have it.
- [ ] **GSI Bhukosh access** for lithology/geology data (task 1.4) — try early. If it doesn't come
      through in time, the plan already has a fallback (`source: "coarse_fallback"`, labelled
      honestly rather than presented as high-resolution) — so this is worth attempting but isn't
      a hard blocker.
- [ ] **NASA COOLR / Global Landslide Catalog access (task 1.12)** — correcting something I got
      wrong earlier: I told you this was public/no-auth. It isn't confirmed to be. Its ArcGIS
      services live under `gis.earthdata.nasa.gov` and every endpoint I tried (several layer-name
      variants) returned a 503 "couldn't access this resource" or a 499 "Token Required" — the
      same domain family as the Earthdata login already needed for IMERG/SMAP above, so this is
      likely the *same* credential, not a separate one, though I haven't confirmed that with an
      actual authenticated request. I did not write `ml/build_inventory.py` against a guessed,
      unverified endpoint — once you have Earthdata access, try an authenticated request against
      `https://gis.earthdata.nasa.gov/gis05/rest/services/Landslides/COOLR_Events_Points/FeatureServer/0/query`
      and let me know what comes back (or if there's a more direct CSV export link on
      https://landslides.nasa.gov/viewer once logged in — I couldn't reach that page's actual
      content to check).

## Verify before Phase 1 needs it

- [ ] **Start Docker Desktop.** I checked this at the start of Phase 1 (not just left untested):
      its engine isn't running — `docker compose up -d postgis` fails with
      `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.` Start
      Docker Desktop, then run `docker compose up -d postgis` (see note below) and confirm the
      `postgis/postgis:16-3.4` image pulls and the container comes up healthy. Needed before
      Phase 1 task 1.5 (`scripts/load_db.py`) can actually load anything.
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
