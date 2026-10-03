"""Failure handling: bad responses from sources, and a source being down end to end.

The sample responses below are the real shapes seen when probing the APIs
(scripts/probe_apis.py). No test here touches the internet.
"""
import pytest
from fastapi.testclient import TestClient

from app import config, sources
from app.scoring import Fact


# ---------- parsers: "HTTP 200" does not mean "good data" ----------

def test_census_no_match_is_an_error_not_a_point():
    found, error = sources.parse_census({"result": {"addressMatches": []}})
    assert found is None
    assert error == "address not found"


def test_census_match_reads_x_as_longitude():
    data = {"result": {"addressMatches": [{
        "coordinates": {"x": -104.99, "y": 39.74}, "matchedAddress": "1437 BANNOCK ST, DENVER, CO, 80202",
    }]}}
    found, error = sources.parse_census(data)
    assert error is None
    assert found["lat"] == 39.74 and found["lon"] == -104.99


def test_usgs_no_data_sentinel_is_unavailable():
    assert sources.parse_elevation({"value": -1000000}).value is None
    assert sources.parse_elevation({}).value is None
    assert sources.parse_elevation({"value": 5235.917}).value == 5235.9


def test_open_meteo_error_body_gives_two_unavailable_facts():
    temp, wind = sources.parse_weather({"error": True, "reason": "Latitude must be in range"})
    assert temp.value is None and wind.value is None


def test_nominatim_nothing_found_vs_rural():
    assert sources.parse_settlement({"error": "Unable to geocode"}).value is None
    assert sources.parse_settlement({"address": {"county": "Some County", "state": "Nevada"}}).value == "rural"
    assert sources.parse_settlement({"address": {"town": "Moab"}}).value == "town"


def test_get_json_never_raises_on_a_dead_server(monkeypatch):
    # Port 9 on localhost has nothing listening, so the connection is refused.
    data, error = sources.get_json("http://127.0.0.1:9/nothing", {})
    assert data is None
    assert "could not connect" in error


# ---------- end to end: a source is down, the assessment is still saved ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    from app.main import app
    with TestClient(app) as c:
        yield c


def fake_sources(monkeypatch, elevation: Fact):
    monkeypatch.setattr(sources, "fetch_elevation", lambda lat, lon: elevation)
    monkeypatch.setattr(sources, "fetch_weather", lambda lat, lon: (Fact(value=65.0), Fact(value=5.0)))
    monkeypatch.setattr(sources, "fetch_settlement", lambda lat, lon: Fact(value="city"))


def test_source_down_assessment_still_saved_and_marked(client, monkeypatch):
    fake_sources(monkeypatch, elevation=Fact(error="timed out after 8 s"))

    r = client.post("/api/assessments", json={"label": "Denver test", "lat": 39.74, "lon": -104.99})
    assert r.status_code == 201
    run = r.json()["runs"][0]
    elevation = next(f for f in run["factors"] if f["name"] == "elevation")
    assert elevation["status"] == "unavailable"
    assert elevation["points"] is None and elevation["value"] is None
    assert elevation["error"] == "timed out after 8 s"
    assert run["coverage"] == 60

    # It is in the saved list too.
    listed = client.get("/api/assessments").json()
    assert [a["label"] for a in listed] == ["Denver test"]


def test_geocoder_down_still_saves_with_reason(client, monkeypatch):
    monkeypatch.setattr(config, "CENSUS_URL", "http://127.0.0.1:9/broken")
    r = client.post("/api/assessments", json={"label": "No geocoder", "address": "1437 Bannock St, Denver, CO"})
    assert r.status_code == 201
    run = r.json()["runs"][0]
    assert run["score"] is None
    assert run["verdict"] == "Not enough data"
    assert "could not connect" in run["location_error"]
    assert all(f["status"] == "unavailable" for f in run["factors"])


def test_retry_keeps_the_earlier_run(client, monkeypatch):
    fake_sources(monkeypatch, elevation=Fact(error="HTTP 503"))
    created = client.post("/api/assessments", json={"label": "Retry me", "lat": 39.74, "lon": -104.99}).json()

    fake_sources(monkeypatch, elevation=Fact(value=5236.0))
    retried = client.post(f"/api/assessments/{created['id']}/retry").json()

    assert len(retried["runs"]) == 2
    newest, oldest = retried["runs"]
    assert newest["coverage"] == 100 and oldest["coverage"] == 60


def test_bad_input_is_rejected(client):
    assert client.post("/api/assessments", json={"label": "x"}).status_code == 422
    assert client.post("/api/assessments", json={"label": "x", "lat": 39.7}).status_code == 422
    assert client.post("/api/assessments", json={"label": "  ", "address": "Denver"}).status_code == 422
    assert client.post("/api/assessments", json={"label": "x", "lat": 200, "lon": 0}).status_code == 422
