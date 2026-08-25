"""CLAUDE.md rule 14: `datetime.now()` is banned outside core/clock.py. This test enforces it
with an AST walk over backend/app/. **Do not delete this test** (CLAUDE.md, this file's own
header, and BUILD_PLAN.md task 0.6 all say so — it's one of two non-negotiable Phase 0 tests).

Scope note: this is a structural check on `X.now()` / `X.utcnow()` / `X.time()` call *shapes*
(anything of the form `<name possibly dotted>.now(...)`, matched by walking down to the leftmost
identifier). It does not do full type resolution, so a determined evasion like
`from time import time as sneaky; sneaky()` (a bare-name call, not an attribute call) would slip
past it. That's an accepted limitation for a lint-style gate, not a bug to silently "fix" by
guessing at intent — if you find a real evasion, tighten this test, don't loosen it.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
ALLOWED_FILE = APP_ROOT / "core" / "clock.py"


def _leftmost_name(node: ast.expr) -> str | None:
    """Walk down a dotted attribute chain (a.b.c) and return the leftmost identifier."""
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def find_wallclock_violations(source: str, filename: str = "<string>") -> list[tuple[int, str]]:
    """Return a list of (line_number, description) for every banned call in `source`.

    Banned shapes: `datetime.now(...)`, `datetime.utcnow(...)`, `<anything>.datetime.now(...)`,
    and `time.time(...)`.
    """
    tree = ast.parse(source, filename=filename)
    violations: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue

        root = _leftmost_name(func.value)

        if func.attr in ("now", "utcnow") and root == "datetime":
            violations.append((node.lineno, f"datetime.{func.attr}()"))
        elif func.attr == "time" and root == "time":
            violations.append((node.lineno, "time.time()"))

    return violations


def test_scanner_detects_a_known_violation():
    """Guard against the scanner itself silently regressing into a no-op."""
    source = "import datetime\ndef f():\n    return datetime.datetime.now()\n"
    violations = find_wallclock_violations(source)
    assert violations == [(3, "datetime.now()")]

    source = "import time\ndef g():\n    return time.time()\n"
    violations = find_wallclock_violations(source)
    assert violations == [(3, "time.time()")]


def test_scanner_ignores_clock_dot_now():
    """`clock.now()` — calling *our* Clock protocol — must never be flagged."""
    source = "def f(clock):\n    return clock.now()\n"
    assert find_wallclock_violations(source) == []


def test_no_wallclock_calls_outside_core_clock():
    assert APP_ROOT.is_dir(), f"expected {APP_ROOT} to exist"
    assert ALLOWED_FILE.is_file(), f"expected {ALLOWED_FILE} to exist"

    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.resolve() == ALLOWED_FILE.resolve():
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, desc in find_wallclock_violations(source, filename=str(path)):
            offenders.append(f"{path.relative_to(APP_ROOT.parent)}:{lineno}: {desc}")

    assert not offenders, (
        "Wall-clock call(s) found outside core/clock.py (CLAUDE.md rule 14 — use clock.now() "
        "instead):\n" + "\n".join(offenders)
    )
