#!/usr/bin/env python
"""Validate data/scenarios/*.json against the ScenarioFile contract (BUILD_PLAN.md task 4.1).

Three layers of checking, in order:

1. Pydantic schema validation (`app.schemas.scenario.ScenarioFile`) — structural correctness
   against Appendix B, including the "real events must carry full metadata" rule enforced in the
   schema itself (a `held_out_of_training: true` scenario must have `name`, `event_date`,
   `hazard_type`, `trigger`, and a `ground_truth` block, or it fails to even parse).
2. Honesty-rule checks CLAUDE.md demands that Pydantic alone can't express (see
   `_check_honesty_rules`) — e.g. a held-out scenario's `provenance.confidence` must actually say
   `"reconstructed"`, never something that would let reconstructed rainfall be mistaken for
   archived observation (CLAUDE.md rule 3).
3. A dry run of every frame through `ingest/replay/scenario_source.py`'s real per-cell merge
   function (`_merged_cell_observation`) — the exact "defaults + cell override -> CellObservation"
   path the live replay pipeline uses. This is what proves a scenario is actually *runnable*, not
   merely well-formed JSON — see this task's own instruction: "a scenario file that validates
   syntactically but was never actually run through the pipeline is not verified." (The fuller
   verification — running the whole file through Pipeline.process end to end — lives in
   backend/tests/test_scenario_replays.py; this script is the fast, CI-friendly structural check
   that make demo-check and CI run on every commit.)

Usage:
    python scripts/validate_scenario.py                  # validate every data/scenarios/*.json
    python scripts/validate_scenario.py aizawl-2024       # validate just this one (by id)
    python scripts/validate_scenario.py data/scenarios/x.json   # ...or by path

Exit code 0 if every targeted file is valid, 1 otherwise (CI-friendly, per task 4.1: "This should
be runnable in CI, a plain script/test, not interactive"). Also exercised directly, non-CLI,
from backend/tests/test_validate_scenario_script.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from pydantic import ValidationError  # noqa: E402

from app.ingest.replay.scenario_source import _merged_cell_observation  # noqa: E402
from app.schemas.scenario import ScenarioFile  # noqa: E402

SCENARIOS_DIR = REPO_ROOT / "data" / "scenarios"


class ScenarioValidationError(Exception):
    """One or more problems found in a scenario file. `.errors` holds every message found so a
    single run reports everything wrong at once, not just the first failure."""

    def __init__(self, path: Path, errors: list[str]):
        self.path = path
        self.errors = errors
        summary = f"{path}: {len(errors)} problem(s):\n" + "\n".join(f"  - {e}" for e in errors)
        super().__init__(summary)


def load_and_validate(path: Path) -> ScenarioFile:
    """Raises ScenarioValidationError (schema or honesty-rule failure), or a `json.JSONDecodeError`
    for unparseable JSON. Returns the parsed, fully-checked ScenarioFile on success."""
    data = json.loads(path.read_text(encoding="utf-8"))

    try:
        scenario = ScenarioFile.model_validate(data)
    except ValidationError as exc:
        raise ScenarioValidationError(path, [str(exc)]) from exc

    errors: list[str] = []
    errors.extend(_check_honesty_rules(scenario))
    errors.extend(_check_frame_ordering_and_bounds(scenario))
    errors.extend(_check_frames_are_runnable(scenario))

    if errors:
        raise ScenarioValidationError(path, errors)
    return scenario


def _check_honesty_rules(scenario: ScenarioFile) -> list[str]:
    """CLAUDE.md rules 2/3: reconstructed data must be labelled as reconstructed, and a scenario
    claiming the "held out of training" badge must actually be documented as a reconstruction of
    a real event, not a placeholder."""
    errors = []
    if scenario.held_out_of_training:
        if scenario.provenance.confidence != "reconstructed":
            errors.append(
                "held_out_of_training=true but provenance.confidence is "
                f"{scenario.provenance.confidence!r}, not 'reconstructed' (CLAUDE.md rule 3: "
                "reconstructed scenario data must be labelled as reconstructed, not presented as "
                "archived observation)"
            )
        if not scenario.provenance.sources:
            errors.append(
                "held_out_of_training=true but provenance.sources is empty — a real event needs "
                "at least one cited source"
            )
    elif scenario.provenance.confidence == "reconstructed":
        errors.append(
            "provenance.confidence is 'reconstructed' but held_out_of_training is false — a "
            "reconstructed real event must also carry the held-out-of-training badge"
        )
    return errors


def _check_frame_ordering_and_bounds(scenario: ScenarioFile) -> list[str]:
    """Frames must be strictly time-ordered and fall inside the scenario's own clock window —
    both are silent-corruption risks a bare schema check would miss."""
    errors = []
    prev_t = None
    for i, frame in enumerate(scenario.frames):
        if frame.t < scenario.clock.start or frame.t > scenario.clock.end:
            errors.append(
                f"frame[{i}].t={frame.t} falls outside clock range "
                f"[{scenario.clock.start}, {scenario.clock.end}]"
            )
        if prev_t is not None and frame.t <= prev_t:
            errors.append(f"frame[{i}].t={frame.t} is not strictly after frame[{i - 1}].t={prev_t}")
        prev_t = frame.t
    return errors


def _check_frames_are_runnable(scenario: ScenarioFile) -> list[str]:
    """Exercises ingest/replay/scenario_source.py's real per-cell merge for every cell in every
    frame — the same function the live replay pipeline calls — so a passing file is proven to
    produce valid CellObservations, not just valid JSON."""
    errors = []
    for i, frame in enumerate(scenario.frames):
        for cell_entry in frame.cells:
            cell_id = cell_entry.get("cell_id", "<missing>")
            try:
                _merged_cell_observation(
                    cell_entry, frame.defaults, scenario_id=scenario.id, frame_t=frame.t
                )
            except (ValueError, ValidationError) as exc:
                errors.append(f"frame[{i}] cell {cell_id!r}: {exc}")
    return errors


def _resolve_targets(args: list[str]) -> list[Path]:
    if not args:
        return sorted(SCENARIOS_DIR.glob("*.json"))
    targets = []
    for arg in args:
        path = Path(arg)
        if not path.suffix:
            path = SCENARIOS_DIR / f"{arg}.json"
        targets.append(path)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="scenario id(s) or path(s) to validate; default: every data/scenarios/*.json",
    )
    args = parser.parse_args(argv)

    targets = _resolve_targets(args.scenarios)
    if not targets:
        print(f"no scenario files found in {SCENARIOS_DIR}", file=sys.stderr)
        return 1

    ok = True
    for path in targets:
        if not path.is_file():
            print(f"FAIL {path}: file not found")
            ok = False
            continue
        try:
            scenario = load_and_validate(path)
        except ScenarioValidationError as exc:
            print(f"FAIL {exc}")
            ok = False
        except json.JSONDecodeError as exc:
            print(f"FAIL {path}: invalid JSON: {exc}")
            ok = False
        else:
            print(f"OK   {path} (id={scenario.id!r}, {len(scenario.frames)} frames)")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
