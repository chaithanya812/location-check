"""Tests for the scoring rules, including unavailable factors."""
import pytest

from app.scoring import (
    Fact, MIN_COVERAGE, TOTAL_MAX, elevation_points, score_facts,
    settlement_points, temperature_points, verdict_for, wind_points,
)


def all_good_facts():
    return {
        "elevation": Fact(value=5236.0),
        "temperature": Fact(value=65.0),
        "wind": Fact(value=5.0),
        "settlement": Fact(value="city"),
    }


def by_name(result):
    return {f["name"]: f for f in result["factors"]}


def test_max_points_add_up_to_100():
    assert TOTAL_MAX == 100


@pytest.mark.parametrize("feet, expected", [
    (-10, 0), (0, 10), (49.9, 10), (50, 25), (499, 25), (500, 40), (5236, 40),
])
def test_elevation_bands(feet, expected):
    assert elevation_points(feet) == expected


@pytest.mark.parametrize("temp, expected", [
    (10, 0), (32, 15), (49.9, 15), (50, 30), (85, 30), (85.1, 15), (100, 15), (101, 0),
])
def test_temperature_bands(temp, expected):
    assert temperature_points(temp) == expected


@pytest.mark.parametrize("mph, expected", [(0, 10), (14.9, 10), (15, 5), (29.9, 5), (30, 0)])
def test_wind_bands(mph, expected):
    assert wind_points(mph) == expected


def test_settlement_points():
    assert [settlement_points(k) for k in ("city", "town", "village", "hamlet", "rural")] == [20, 15, 10, 10, 5]


def test_everything_available_scores_full_marks():
    result = score_facts(all_good_facts())
    assert result["score"] == 100
    assert result["coverage"] == 100
    assert result["verdict"] == "Pursue"
    assert all(f["status"] == "ok" for f in result["factors"])


def test_unavailable_factor_is_not_scored_as_zero():
    facts = all_good_facts()
    facts["elevation"] = Fact(error="timed out after 8 s")
    result = score_facts(facts)

    elevation = by_name(result)["elevation"]
    assert elevation["status"] == "unavailable"
    assert elevation["points"] is None      # not 0
    assert elevation["value"] is None       # not 0
    assert elevation["error"] == "timed out after 8 s"

    # The other three earned all 60 of their 60 possible points. If the missing
    # elevation had been counted as 0 the score would be 60, not 100.
    assert result["score"] == 100
    assert result["coverage"] == 60


def test_real_zero_is_different_from_unavailable():
    facts = all_good_facts()
    facts["wind"] = Fact(value=45.0)  # a real, terrible value
    wind = by_name(score_facts(facts))["wind"]
    assert wind["status"] == "ok"
    assert wind["points"] == 0
    assert wind["value"] == 45.0


def test_missing_key_is_treated_as_unavailable():
    facts = all_good_facts()
    del facts["settlement"]
    settlement = by_name(score_facts(facts))["settlement"]
    assert settlement["status"] == "unavailable"
    assert settlement["points"] is None


def test_low_coverage_gives_no_verdict():
    # Only weather (40 of 100 points) is available: the score can be computed
    # but it is too thin to act on.
    facts = {
        "elevation": Fact(error="HTTP 503"),
        "temperature": Fact(value=65.0),
        "wind": Fact(value=5.0),
        "settlement": Fact(error="timed out after 8 s"),
    }
    result = score_facts(facts)
    assert result["coverage"] == 40 < MIN_COVERAGE
    assert result["score"] == 100
    assert result["verdict"] == "Not enough data"


def test_nothing_available_gives_no_score():
    result = score_facts({})
    assert result["score"] is None
    assert result["coverage"] == 0
    assert result["verdict"] == "Not enough data"
    assert all(f["points"] is None for f in result["factors"])


def test_partial_score_is_rescaled():
    facts = all_good_facts()
    facts["elevation"] = Fact(value=20.0)   # 10 of 40
    facts["settlement"] = Fact(error="HTTP 500")
    # available: elevation 10/40 + temperature 30/30 + wind 10/10 = 50/80 -> 62.5 -> 62
    result = score_facts(facts)
    assert result["coverage"] == 80
    assert result["score"] == round(50 / 80 * 100)
    assert result["verdict"] == "Review"


@pytest.mark.parametrize("score, coverage, expected", [
    (70, 100, "Pursue"), (69, 100, "Review"), (40, 100, "Review"),
    (39, 100, "Skip"), (0, 100, "Skip"), (100, MIN_COVERAGE - 1, "Not enough data"),
    (100, MIN_COVERAGE, "Pursue"), (None, 0, "Not enough data"),
])
def test_verdict_thresholds(score, coverage, expected):
    assert verdict_for(score, coverage) == expected
