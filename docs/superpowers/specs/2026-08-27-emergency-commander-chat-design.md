# Emergency Commander Chat Design

## Goal

Add a backend-powered conversational assistant to the AI Emergency Commander. The assistant answers questions using the current operational state, returns up to three deterministic safety routes that exclude landslide-affected roads, and persists saved route plans.

## Architecture

FastAPI owns chat orchestration, route computation, validation, and persistence. The existing live `AppState` is the source of current priorities, isolations, action cards, and road risks. The NVIDIA chat-completions API is used only to explain verified context and produce a concise answer; route safety is computed by the existing risk-aware routing engine. SQLite stores saved plans.

The frontend renders structured assistant messages, route cards, loading/error states, and save confirmations. If NVIDIA is unavailable or returns invalid output, the backend returns a deterministic fallback answer with `source: "fallback"` and the same structured route payload.

## Contracts

`POST /api/commander/chat` accepts `{ message, history, village_id?, aoi_id? }` and returns `{ answer, source, routes, context }`. `routes` is an array of zero to three `EvacuationRoute`-compatible route alternatives with `route_rank`, `safety_reason`, and `risk_snapshot`.

`POST /api/commander/saved-routes` stores a named plan and returns it. `GET /api/commander/saved-routes` lists saved plans newest first. The saved payload includes the route alternatives and the road-risk snapshot used when they were computed.

## Safety Rules

- Severed roads are excluded from candidate paths.
- A route must be reachable in the current risk-filtered graph.
- Alternatives are distinct by path edge sequence and are ranked by risk-adjusted cost.
- If fewer than three valid alternatives exist, return fewer than three and explain why.
- The model cannot add, alter, or certify route geometry or road safety.

## Degraded Operation

NVIDIA configuration is optional at startup. Missing key, timeout, non-2xx response, malformed JSON, or invalid model output switches only the explanation layer to deterministic fallback. Route computation and saving remain available.

## Testing

Backend tests cover route exclusion/alternative ranking, NVIDIA success and fallback, chat response shape, SQLite save/list behavior, and validation. Frontend tests cover question submission, structured route rendering, saving, and fallback messaging. Vite build and the existing test suites remain required gates.
