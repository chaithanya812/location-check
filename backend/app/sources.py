"""Fetch facts from public data sources.

Every network call goes through get_json(), which never raises: it returns
(data, None) on success or (None, "reason") on any failure. Each source then
has a small parse_* function that checks the body actually contains what we
expect, because these services can answer HTTP 200 with an error or an empty
result inside.
"""
import time
from typing import Optional

import requests

from . import config
from .scoring import Fact


def get_json(url: str, params: dict) -> tuple[Optional[dict], Optional[str]]:
    try:
        response = requests.get(
            url, params=params, timeout=config.TIMEOUT,
            headers={"User-Agent": config.USER_AGENT},
        )
    except requests.Timeout:
        return None, f"timed out after {config.TIMEOUT[1]} s"
    except requests.RequestException as e:
        return None, f"could not connect ({type(e).__name__})"

    if response.status_code != 200:
        return None, f"HTTP {response.status_code}"
    try:
        return response.json(), None
    except ValueError:
        return None, "response was not valid JSON"


def is_number(x) -> bool:
    # bool is a subclass of int in Python, so exclude it explicitly.
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------- Geocoding: address -> coordinates (US Census) ----------

def parse_census(data: dict) -> tuple[Optional[dict], Optional[str]]:
    matches = (data.get("result") or {}).get("addressMatches")
    if matches is None:
        return None, "unexpected response from geocoder"
    if not matches:
        return None, "address not found"
    best = matches[0]
    coords = best.get("coordinates") or {}
    # Census uses x = longitude, y = latitude.
    lon, lat = coords.get("x"), coords.get("y")
    if not (is_number(lat) and is_number(lon)):
        return None, "geocoder returned no coordinates"
    return {"lat": lat, "lon": lon, "matched_address": best.get("matchedAddress")}, None


def geocode(address: str) -> tuple[Optional[dict], Optional[str]]:
    data, error = get_json(config.CENSUS_URL, {
        "address": address, "benchmark": "Public_AR_Current", "format": "json",
    })
    if error:
        return None, f"US Census geocoder: {error}"
    result, error = parse_census(data)
    if error:
        return None, f"US Census geocoder: {error}"
    return result, None


# ---------- Elevation (USGS) ----------

def parse_elevation(data: dict) -> Fact:
    value = data.get("value")
    # USGS returns a huge negative number (e.g. -1000000) when it has no data.
    if not is_number(value) or value < -1000:
        return Fact(error="no elevation data for this point")
    return Fact(value=round(value, 1))


def fetch_elevation(lat: float, lon: float) -> Fact:
    # USGS also uses x = longitude, y = latitude.
    data, error = get_json(config.USGS_URL, {"x": lon, "y": lat, "units": "Feet", "wkid": 4326})
    if error:
        return Fact(error=error)
    return parse_elevation(data)


# ---------- Weather (Open-Meteo): one request, two facts ----------

def parse_weather(data: dict) -> tuple[Fact, Fact]:
    current = data.get("current") or {}
    temp, wind = current.get("temperature_2m"), current.get("wind_speed_10m")
    temp_fact = Fact(value=temp) if is_number(temp) else Fact(error="no temperature in response")
    wind_fact = Fact(value=wind) if is_number(wind) else Fact(error="no wind speed in response")
    return temp_fact, wind_fact


def fetch_weather(lat: float, lon: float) -> tuple[Fact, Fact]:
    data, error = get_json(config.OPEN_METEO_URL, {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,wind_speed_10m",
        "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
    })
    if error:
        return Fact(error=error), Fact(error=error)
    return parse_weather(data)


# ---------- Settlement type (Nominatim reverse geocoding) ----------

def parse_settlement(data: dict) -> Fact:
    if "error" in data:
        return Fact(error=f"Nominatim: {data['error']}")
    address = data.get("address")
    if not isinstance(address, dict):
        return Fact(error="no address in response")
    for kind in ("city", "town", "village", "hamlet"):
        if kind in address:
            return Fact(value=kind)
    # Nominatim did answer, it just found no settlement: that is a real value.
    return Fact(value="rural")


_last_nominatim_call = 0.0


def fetch_settlement(lat: float, lon: float) -> Fact:
    # Nominatim's usage policy allows at most 1 request per second.
    global _last_nominatim_call
    wait = 1.0 - (time.monotonic() - _last_nominatim_call)
    if wait > 0:
        time.sleep(wait)
    _last_nominatim_call = time.monotonic()

    data, error = get_json(config.NOMINATIM_URL, {"lat": lat, "lon": lon, "format": "jsonv2"})
    if error:
        return Fact(error=error)
    return parse_settlement(data)


def fetch_all_facts(lat: float, lon: float) -> dict[str, Fact]:
    """Fetch every fact for a point. Each source fails independently."""
    temperature, wind = fetch_weather(lat, lon)
    return {
        "elevation": fetch_elevation(lat, lon),
        "temperature": temperature,
        "wind": wind,
        "settlement": fetch_settlement(lat, lon),
    }
