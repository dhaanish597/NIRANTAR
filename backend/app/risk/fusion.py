"""Fusion rule between the ML model's `p_fail` and `risk/thresholds.py`'s exceedance ratio
(BUILD_PLAN.md task 1.19).

**The rule:** `p_fail = max(ml_p_fail, min(1.0, threshold_exceedance))`.

**One-sentence rationale (have this ready — a judge will ask):** for a life-safety system,
under-alerting is the costlier error than over-alerting, and `max` stays fully explainable
without needing to justify arbitrary blend weights — "whichever method is more concerned wins."

**Why not a weighted blend?** A calibrated weighted average (e.g. `0.6*ml + 0.4*threshold`)
would need a defensible way to pick 0.6/0.4, which — given `data/models/eval_report.md`'s honest
56-row training set — cannot itself be justified by measured calibration data yet. `max` needs no
such tuning and degrades gracefully: if the ML side is wrong (plausible, given how little data
trained it — see `eval_report.md` §0), the physically-grounded, published threshold engine
(`risk/thresholds.py`, task 1.11) alone is enough to drive an alert; the reverse also holds if a
cell's rainfall genuinely hasn't crossed a published threshold yet but its terrain profile
resembles known failures. BUILD_PLAN.md's risk register explicitly anticipates leaning on the
threshold engine as the credible primary — `max` is the simplest rule that guarantees the
threshold engine's signal is never suppressed by a weak ML score.

**Mapping the exceedance ratio onto a probability-like scale:** `threshold_exceedance` is
unbounded above (`observed / published_threshold`, per `risk/thresholds.py`) and is not itself a
probability. `min(1.0, exceedance)` treats "meets or exceeds the published threshold" (ratio >= 1)
as maximally concerned (1.0), and scales linearly below that — a simple, monotonic, explainable
squashing, not a calibrated transform (there is no ground-truth calibration data linking
exceedance ratio to failure probability in this project yet).
"""
from __future__ import annotations


def exceedance_as_probability_like(threshold_exceedance: float) -> float:
    """Caps the (unbounded, >= 0) exceedance ratio at 1.0 so it's comparable to a probability.
    See module docstring for why this is a simple cap, not a calibrated transform."""
    return min(1.0, max(0.0, threshold_exceedance))


def fuse_p_fail(ml_p_fail: float, threshold_exceedance: float) -> float:
    """The task 1.19 fusion rule: max(ml_p_fail, capped exceedance ratio). See module docstring
    for the one-sentence rationale."""
    return max(ml_p_fail, exceedance_as_probability_like(threshold_exceedance))
