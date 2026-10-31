# NIRANTAR 2.0 — Neuro-Symbolic Orchestrator & Tool Usage Telemetry Report

## Aggregate Telemetry Summary
- `total_model_calls`: `10`
- `total_tool_calls`: `10`
- `total_input_tokens`: `564`
- `total_output_tokens`: `1322`
- `total_tokens`: `1886`
- `avg_latency_ms`: `130.78 ms`
- `total_cost_usd`: `$0.002478`

## Per-Turn Multi-Agent & Tool Execution Trace
| Step | Agent Role | Model Tier | Tool Invoked | In Tokens | Out Tokens | Latency | Est. Cost (USD) |
|---|---|---|---|---|---|---|---|
| 1 | `IntakeRouterAgent` | `meta/llama-3.1-8b-instruct` | `hybrid_graphrag_retrieve_tool` | 54 | 150 | 0.43 ms | $0.0000981 |
| 2 | `GraphInvestigatorAgent` | `meta/llama-3.1-70b-instruct` | `query_cascading_blast_radius_tool` | 56 | 150 | 0.14 ms | $0.0004048 |
| 3 | `GraphInvestigatorAgent` | `meta/llama-3.1-70b-instruct` | `discover_topological_chokepoints_tool` | 57 | 150 | 1.34 ms | $0.0004056 |
| 4 | `MissionPlannerAgent` | `meta/llama-3.1-8b-instruct` | `compute_risk_budgeted_route_tool` | 55 | 129 | 0.07 ms | $0.0000856 |
| 5 | `VerifierGateAgent` | `meta/llama-3.1-70b-instruct` | `verify_and_gate_copilot_output` | 60 | 82 | 189.48 ms | $0.0002448 |
| 6 | `IntakeRouterAgent` | `meta/llama-3.1-8b-instruct` | `hybrid_graphrag_retrieve_tool` | 54 | 150 | 0.89 ms | $0.0000981 |
| 7 | `GraphInvestigatorAgent` | `meta/llama-3.1-70b-instruct` | `query_cascading_blast_radius_tool` | 56 | 150 | 0.27 ms | $0.0004048 |
| 8 | `GraphInvestigatorAgent` | `meta/llama-3.1-70b-instruct` | `discover_topological_chokepoints_tool` | 57 | 150 | 2.56 ms | $0.0004056 |
| 9 | `MissionPlannerAgent` | `meta/llama-3.1-8b-instruct` | `compute_risk_budgeted_route_tool` | 55 | 129 | 0.11 ms | $0.0000856 |
| 10 | `VerifierGateAgent` | `meta/llama-3.1-70b-instruct` | `verify_and_gate_copilot_output` | 60 | 82 | 1112.56 ms | $0.0002448 |
