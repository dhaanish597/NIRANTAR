"""impact/demographics.py — simulated household/census-level demographics per village.

No such dataset exists for the NER pilot AOIs (CLAUDE.md's honesty rules — this is SIMULATED,
never presented as Census/ground-truth data). Derived from each village's real WorldPop-based
`population` figure (scripts/fetch_exposure.py) via a fixed ratio table, not randomness — same
population always produces the same breakdown (CLAUDE.md rule 13), so no seed is needed at all.

Ratios are an engineering judgment call (rural NER's younger-skewing population pyramid), not a
cited statistic — documented as such, same spirit as ml/negative_sampling.py's buffer distances.
"""
from __future__ import annotations

from app.schemas.impact import Demographics

CHILDREN_RATIO = 0.30
SENIOR_RATIO = 0.08
AVERAGE_HOUSEHOLD_SIZE = 4.8
HIGH_RISK_HOUSEHOLD_RATIO = 0.05  # of estimated households, not population


def simulate_demographics(population: int) -> Demographics:
    children = round(population * CHILDREN_RATIO)
    seniors = round(population * SENIOR_RATIO)
    adults = population - children - seniors
    households = population / AVERAGE_HOUSEHOLD_SIZE
    high_risk_households = round(households * HIGH_RISK_HOUSEHOLD_RATIO)
    return Demographics(
        children=children,
        seniors=seniors,
        adults=adults,
        high_risk_households=high_risk_households,
        source="simulated",
    )
