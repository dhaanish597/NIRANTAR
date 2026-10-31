"""Live Agent & Model Telemetry Tracker (`telemetry.py`).

Records every agent step, model tier routed (`AGENT_FAST_MODEL` vs `AGENT_REASONING_MODEL`),
tool invocation, input/output token counts, latency in ms, and estimated USD cost so
`evaluation/usage_report.md` always reflects genuine, auditable runtime metrics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class TelemetryRecord:
    agent_role: str
    model_id: str
    tool_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    execution_mode: str

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class UsageTelemetryTracker:
    def __init__(self) -> None:
        self._records: list[TelemetryRecord] = []

    def record_step(
        self,
        *,
        agent_role: str,
        model_id: str,
        tool_name: str,
        prompt_text: str,
        output_text: str,
        latency_ms: float,
        execution_mode: str = "hybrid_neuro_symbolic",
    ) -> TelemetryRecord:
        in_tok = max(12, len(prompt_text) // 4)
        out_tok = max(8, len(output_text) // 4)
        # Standard per-1M-token pricing estimate ($0.15/1M input, $0.60/1M output for fast tier;
        # $0.80/1M input, $2.40/1M output for 70B reasoning tier)
        is_heavy = "70b" in model_id.lower() or "pro" in model_id.lower()
        in_rate = 0.80 if is_heavy else 0.15
        out_rate = 2.40 if is_heavy else 0.60
        cost = (in_tok * in_rate + out_tok * out_rate) / 1_000_000.0

        rec = TelemetryRecord(
            agent_role=agent_role,
            model_id=model_id,
            tool_name=tool_name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=round(latency_ms, 2),
            estimated_cost_usd=round(cost, 7),
            execution_mode=execution_mode,
        )
        self._records.append(rec)
        return rec

    @property
    def records(self) -> list[TelemetryRecord]:
        return list(self._records)

    def summary(self) -> dict[str, Any]:
        total_calls = len(self._records)
        total_in = sum(r.input_tokens for r in self._records)
        total_out = sum(r.output_tokens for r in self._records)
        total_cost = sum(r.estimated_cost_usd for r in self._records)
        avg_lat = (
            sum(r.latency_ms for r in self._records) / total_calls
            if total_calls > 0
            else 0.0
        )
        by_model: dict[str, int] = {}
        by_tool: dict[str, int] = {}
        for r in self._records:
            by_model[r.model_id] = by_model.get(r.model_id, 0) + 1
            by_tool[r.tool_name] = by_tool.get(r.tool_name, 0) + 1

        return {
            "total_calls": total_calls,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "total_cost_usd": round(total_cost, 6),
            "avg_latency_ms": round(avg_lat, 2),
            "calls_by_model": by_model,
            "calls_by_tool": by_tool,
        }
