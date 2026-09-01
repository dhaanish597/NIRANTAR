.PHONY: up down dev dev-backend dev-frontend data graph tiles train scenario test demo-check freeze

UV ?= uv
DEMO_PY := $(UV) run --isolated --python 3.13 \
	--with-requirements backend/requirements.txt \
	--with-requirements backend/requirements-geo.txt \
	--with-requirements backend/requirements-graph.txt \
	--with-requirements backend/requirements-ml.txt \
	--with-requirements backend/requirements-dissemination.txt \
	--with-requirements backend/requirements-ingest.txt \
	--with-requirements backend/requirements-db.txt \
	--with-requirements backend/requirements-tiles.txt

# backend/.venv layout differs Windows vs. POSIX — resolve once here so every target that needs
# the venv's python (not whatever `python` happens to be first on PATH) uses the right one.
# Caught the hard way: `python -m pytest` here originally picked up an unrelated global Python
# install that happened to also have pytest/pydantic on it, silently bypassing requirements.txt.
# Detected by testing which layout actually exists, not by trusting $(OS) — that env var isn't
# reliably "Windows_NT" inside every shell make gets invoked from (e.g. MSYS make under Git Bash).
ifneq ($(wildcard backend/.venv/Scripts/python.exe),)
    VENV_PY := .venv/Scripts/python.exe
else
    VENV_PY := .venv/bin/python
endif

up:
	docker compose up -d postgis

down:
	docker compose down

# backend (:8000) + frontend (:5173) with hot reload, natively (no Docker) — see CLAUDE.md §8.
dev:
	@echo "Starting backend (:8000) and frontend (:5173). Ctrl+C stops both."
	@trap 'kill 0' EXIT; $(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend:
	cd backend && $(VENV_PY) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

data:
	backend/$(VENV_PY) scripts/fetch_dem.py --aoi $(if $(AOI),$(AOI),aizawl)
	backend/$(VENV_PY) scripts/build_grid.py --aoi $(if $(AOI),$(AOI),aizawl)
	backend/$(VENV_PY) scripts/fetch_exposure.py --aoi $(if $(AOI),$(AOI),aizawl)

graph:
	backend/$(VENV_PY) scripts/build_road_graph.py --aoi $(if $(AOI),$(AOI),aizawl)

# BUILD_PLAN.md task 5.2: real, not a stub — builds data/tiles/<AOI>.pmtiles from the AOI's
# already-built cells.gpkg (task 1.2) + road graph GeoJSON (task 2.1). Requires both to exist
# first (make data / make graph, or the real scripts directly — see task 1.2/2.1 for why those
# two Phase-1/2 targets above are still TODO stubs, unrelated to this one).
tiles:
	backend/$(VENV_PY) scripts/build_tiles.py --aoi $(if $(AOI),$(AOI),aizawl)
	backend/$(VENV_PY) scripts/build_hillshade.py --aoi $(if $(AOI),$(AOI),aizawl)

train:
	@echo "TODO(Phase 1): ml/train.py"

# BUILD_PLAN.md task 4.1: validates data/scenarios/*.json (or just ID, if given) — schema,
# CLAUDE.md honesty rules, and a real dry-run of every cell through the replay merge logic.
scenario:
	backend/$(VENV_PY) scripts/validate_scenario.py $(ID)

freeze:
	@echo "TODO(Phase 6): tag a known-good demo build"

# --- Real from Phase 0 on ---
test:
	cd backend && $(VENV_PY) -m pytest -q
	cd frontend && npm test -- --run

demo-check:
	@echo "ICONIX DEMO CHECK"
	PYTHONPATH=backend $(DEMO_PY) python scripts/demo_check.py
	PYTHONPATH=backend $(DEMO_PY) pytest backend/tests -q -p no:cacheprovider
	npm --prefix frontend test -- --run
	npm --prefix frontend run build
