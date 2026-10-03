"""Scoring rules. This is the ONLY place the rules live.

Each factor has a maximum number of points; the maximums add up to 100.
A factor whose source failed is "unavailable": it gets no points AND it is
left out of the maximum, so it can never drag the score down as if it were 0.
The score is then rescaled to 0-100 over the factors we do have, and the
"coverage" number says how much of the full 100 points that was.

The plain-English version of these rules is in README.md. If you change a
rule here, change it there too.
"""
from dataclasses import dataclass
from typing import Callable, Optional, Union

Value = Union[float, str]

# If less than this percent of the possible points could be measured,
# we refuse to give a Pursue/Review/Skip verdict.
MIN_COVERAGE = 60

PURSUE_AT = 70  # score >= 70 -> Pursue
REVIEW_AT = 40  # score >= 40 -> Review, below -> Skip


@dataclass
class Fact:
    """One raw fact fetched from a source. Exactly one of value / error is set."""
    value: Optional[Value] = None
    error: Optional[str] = None


@dataclass
class Rule:
    name: str
    label: str
    source: str
    unit: str
    max_points: int
    description: str
    points: Callable[[Value], int]


def elevation_points(feet: float) -> int:
    if feet < 0:
        return 0
    if feet < 50:
        return 10
    if feet < 500:
        return 25
    return 40


def temperature_points(fahrenheit: float) -> int:
    if 50 <= fahrenheit <= 85:
        return 30
    if 32 <= fahrenheit <= 100:
        return 15
    return 0


def wind_points(mph: float) -> int:
    if mph < 15:
        return 10
    if mph < 30:
        return 5
    return 0


SETTLEMENT_POINTS = {"city": 20, "town": 15, "village": 10, "hamlet": 10, "rural": 5}


def settlement_points(kind: str) -> int:
    return SETTLEMENT_POINTS[kind]


RULES = [
    Rule(
        name="elevation",
        label="Elevation",
        source="USGS Elevation Point Query Service",
        unit="ft",
        max_points=40,
        description="Flood-risk proxy. Below sea level: 0. Under 50 ft: 10. "
                    "50 to 499 ft: 25. 500 ft or higher: 40.",
        points=elevation_points,
    ),
    Rule(
        name="temperature",
        label="Current temperature",
        source="Open-Meteo",
        unit="°F",
        max_points=30,
        description="Comfort for site visits. 50 to 85 °F: 30. "
                    "32 to 100 °F (outside the comfort band): 15. Anything else: 0.",
        points=temperature_points,
    ),
    Rule(
        name="wind",
        label="Current wind speed",
        source="Open-Meteo",
        unit="mph",
        max_points=10,
        description="Ease of outdoor work. Under 15 mph: 10. 15 to 29 mph: 5. 30 mph or more: 0.",
        points=wind_points,
    ),
    Rule(
        name="settlement",
        label="Settlement type",
        source="OpenStreetMap Nominatim",
        unit="",
        max_points=20,
        description="Access to roads and services. City: 20. Town: 15. "
                    "Village or hamlet: 10. None of these (rural): 5.",
        points=settlement_points,
    ),
]

TOTAL_MAX = sum(rule.max_points for rule in RULES)  # 100


def verdict_for(score: Optional[int], coverage: int) -> str:
    if score is None or coverage < MIN_COVERAGE:
        return "Not enough data"
    if score >= PURSUE_AT:
        return "Pursue"
    if score >= REVIEW_AT:
        return "Review"
    return "Skip"


def score_facts(facts: dict[str, Fact]) -> dict:
    """Turn raw facts into per-factor points, a 0-100 score, coverage and a verdict.

    `facts` maps a rule name to the Fact fetched for it. A rule with no entry
    in `facts` is treated as unavailable.
    """
    factors = []
    earned = 0
    available_max = 0

    for rule in RULES:
        fact = facts.get(rule.name) or Fact(error="not fetched")
        if fact.value is None:
            # Unavailable: points stay None (not 0) and the max is not counted.
            factors.append({
                "name": rule.name, "label": rule.label, "source": rule.source,
                "unit": rule.unit, "rule": rule.description,
                "status": "unavailable", "value": None,
                "points": None, "max_points": rule.max_points,
                "error": fact.error or "no value",
            })
            continue

        points = rule.points(fact.value)
        earned += points
        available_max += rule.max_points
        factors.append({
            "name": rule.name, "label": rule.label, "source": rule.source,
            "unit": rule.unit, "rule": rule.description,
            "status": "ok", "value": fact.value,
            "points": points, "max_points": rule.max_points,
            "error": None,
        })

    coverage = round(available_max / TOTAL_MAX * 100)
    score = round(earned / available_max * 100) if available_max else None

    return {
        "score": score,
        "coverage": coverage,
        "verdict": verdict_for(score, coverage),
        "factors": factors,
    }
