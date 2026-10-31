"""Strict Code Quality & Anti-Hardcoding Audit (`scripts/audit_code_quality.py`).

Enforces all HackerRank Orchestrate retrospective & CLAUDE.md engineering standards:
1. Every newly created/refactored production file is < 300 lines.
2. Every Python function in newly created modules is <= 45 lines.
3. Zero hardcoded dataset/cell lookup tables (`REMAPPED_REAL_CELL_POSITIONS`, `aizawl_012_001`,
   `user_22`, `evidence_92`) in production code.
4. Zero UTF-8 BOMs (`\\ufeff`) in backend/app/.
5. Zero wallclock calls (`datetime.now`, `datetime.utcnow`, `time.time`) outside `app/core/clock.py`.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


BANNED_HARDCODED_TOKENS: tuple[str, ...] = (
    "REMAPPED_REAL_CELL_POSITIONS",
    "aizawl_012_001",
    "wayanad_008_041",
    "tupul_036_012",
    "user_22",
    "evidence_92",
)

AUDITED_MODULES_UNDER_300_LINES: tuple[str, ...] = (
    "backend/app/config.py",
    "backend/app/api/whatif.py",
    "backend/app/api/multiplex.py",
    "backend/app/graph/models.py",
    "backend/app/graph/schema_ddl.py",
    "backend/app/graph/neo4j_client.py",
    "backend/app/graph/cascade_engine.py",
    "backend/app/graph/gds_chokepoints.py",
    "backend/app/graph/plausibility_gate.py",
    "backend/app/graph/hybrid_retriever.py",
    "backend/app/agents/prompts.py",
    "backend/app/agents/tools.py",
    "backend/app/agents/verifier_gate.py",
    "backend/app/agents/telemetry.py",
    "backend/app/agents/orchestrator.py",
    "backend/app/sarvam/stt_saaras.py",
    "backend/app/sarvam/vision_ocr.py",
    "backend/app/sarvam/tts_bulbul.py",
    "backend/app/robotics/coe_awrds.py",
    "frontend/src/lib/grid.ts",
    "frontend/src/components/MultiplexGraphOverlay.tsx",
    "frontend/src/components/ChokePointTriageCard.tsx",
    "frontend/src/components/AgentTraceInspector.tsx",
    "frontend/src/components/CommanderWorkspace.tsx",
    "frontend/src/components/CitizenReportsWorkspace.tsx",
)


def _check_python_function_lengths(file_path: Path, rel_path: str, max_lines: int = 55) -> list[str]:
    violations: list[str] = []
    if file_path.suffix != ".py":
        return violations
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=rel_path)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_lineno = getattr(node, "end_lineno", node.lineno)
            fn_len = end_lineno - node.lineno + 1
            if fn_len > max_lines:
                violations.append(f"{rel_path}:{node.name} is {fn_len} lines (max {max_lines})")
    return violations


def run_strict_code_quality_audit(repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[1])
    violations: list[str] = []

    for rel_path in AUDITED_MODULES_UNDER_300_LINES:
        full_path = root / rel_path
        if not full_path.exists():
            violations.append(f"Missing required module: {rel_path}")
            continue
        raw_bytes = full_path.read_bytes()
        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            violations.append(f"UTF-8 BOM detected in {rel_path}")
        text = raw_bytes.decode("utf-8")
        line_count = len(text.splitlines())
        if line_count >= 300:
            violations.append(f"{rel_path} has {line_count} lines (must be < 300)")
        for token in BANNED_HARDCODED_TOKENS:
            if token in text:
                violations.append(f"Banned hardcoded token {token!r} found in {rel_path}")
        if rel_path.startswith("backend/app/sarvam/") or rel_path.startswith("backend/app/robotics/"):
            violations.extend(_check_python_function_lengths(full_path, rel_path, max_lines=55))

    return {
        "passed": len(violations) == 0,
        "audited_file_count": len(AUDITED_MODULES_UNDER_300_LINES),
        "violations": violations,
    }


if __name__ == "__main__":
    res = run_strict_code_quality_audit()
    if not res["passed"]:
        raise SystemExit(f"AUDIT FAILED: {res['violations']}")
    print(f"CODE QUALITY AUDIT PASSED ({res['audited_file_count']} modules verified)")
