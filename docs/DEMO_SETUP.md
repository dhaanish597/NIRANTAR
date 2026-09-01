# SIH Demo Setup

## Prerequisites

- Python 3.13 with `uv` available.
- Node.js/npm installed in `frontend/`.
- No cloud credentials are required for replay.

## Preflight

From the repository root:

```text
make demo-check
```

The command checks model/schema, all three scenario files, DEM/cells/exposure/road graphs, local PMTiles and hillshades, deterministic replay, no replay network URLs, backend tests, and frontend checks. It prints `RESULT: READY` only when every check passes.

## Start locally

```text
docker compose up -d postgis
make dev-backend
make dev-frontend
```

Open `http://localhost:5173`. If Docker is unavailable, the application still runs with the local replay path; database-backed optional features may be unavailable and are labelled in the UI.

## Rebuild data

```text
make data AOI=aizawl
make graph AOI=aizawl
make tiles AOI=aizawl
```

Repeat with `AOI=wayanad` and `AOI=tupul` when refreshing the historical artifacts. Public OSM/WorldCover/WorldPop downloads are build-time inputs and are cached under `data/`; replay itself does not fetch them.

## Human-only airplane-mode rehearsal

1. Start normally and confirm Aizawl replay.
2. Disable Wi-Fi/Ethernet on the actual demo machine.
3. Reload/restart as needed.
4. Run the replay, citizen alert, route, map, audit, and What-if.
5. Play voice only if a local audio asset has been added; the current build reports unavailable voice honestly.
6. Record every failure and repeat five clean runs before freezing the submission.
