# Emergency Commander Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a NVIDIA-backed, structured Emergency Commander chatbot with deterministic safe-route alternatives and persistent saved route plans.

**Architecture:** FastAPI exposes chat and saved-route endpoints. The backend computes route facts from current risk data, then asks NVIDIA to explain those facts; deterministic fallback handles unavailable or invalid model responses. React renders chat messages and route cards.

**Tech Stack:** FastAPI, Pydantic, SQLite, httpx, NetworkX, React, TypeScript, Zustand, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-27-emergency-commander-chat-design.md`

## Global Constraints

- Never allow the model to invent or certify route safety.
- Exclude `RoadSegmentRisk.severed` edges from routes.
- Return fewer than three routes when fewer than three valid alternatives exist.
- Keep NVIDIA credentials server-side in environment variables.
- Preserve the existing human-in-the-loop disclaimer.

### Task 1: Backend contracts and route alternatives

**Files:**
- Create: `backend/app/commander/routes.py`
- Create: `backend/app/schemas/commander.py`
- Test: `backend/tests/test_commander_routes.py`

- [ ] Write failing tests for distinct alternatives, severed-road exclusion, and fewer-than-three behavior.
- [ ] Implement Pydantic request/response models and a pure k-shortest safe-route helper over the existing risk-filtered graph.
- [ ] Run `pytest backend/tests/test_commander_routes.py -q` and confirm it passes.

### Task 2: NVIDIA client and deterministic fallback

**Files:**
- Create: `backend/app/commander/llm.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_commander_llm.py`

- [ ] Add configuration for `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_BASE_URL`, and timeout.
- [ ] Implement a small async NVIDIA OpenAI-compatible client that validates returned answer text and never accepts model route facts.
- [ ] Implement deterministic fallback copy from the supplied context.
- [ ] Add success, missing-key, timeout/error, and malformed-output tests.
- [ ] Run `pytest backend/tests/test_commander_llm.py -q`.

### Task 3: Chat orchestration and SQLite persistence

**Files:**
- Create: `backend/app/commander/service.py`
- Create: `backend/app/commander/store.py`
- Create: `backend/app/api/commander.py`
- Modify: `backend/app/api/state.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_commander_api.py`

- [ ] Add AppState-owned commander service using latest pipeline tick data.
- [ ] Implement chat endpoint context assembly, route computation, NVIDIA/fallback explanation, and structured response.
- [ ] Implement SQLite schema creation, save, and list operations with parameterized SQL.
- [ ] Register the router and add endpoint tests for chat, fallback, save, and list.
- [ ] Run `pytest backend/tests/test_commander_api.py -q`.

### Task 4: Frontend API types and Commander chat UI

**Files:**
- Modify: `frontend/src/types/schemas.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/CommanderWorkspace.tsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/src/components/CommanderWorkspace.test.tsx`

- [ ] Add typed API contracts and API methods.
- [ ] Add a chat panel with prompt shortcuts, message history, structured route cards, save controls, source badge, loading state, and error fallback state.
- [ ] Keep the existing summary, recommendation, Announce, What-if, and human-in-the-loop controls.
- [ ] Add tests for submitting a question, rendering route cards, and saving a route plan.
- [ ] Run `npm.cmd run test -- --run` and `npm.cmd run build` from `frontend`.

### Task 5: Verification

**Files:**
- No committed files.

- [ ] Run all backend tests.
- [ ] Run all frontend tests and build.
- [ ] Start the Vite app and exercise `/console/commander` with a browser/Playwright fallback if Browser is unavailable.
- [ ] Verify the page is non-blank, console-clean, route cards render, and save confirmation appears.
