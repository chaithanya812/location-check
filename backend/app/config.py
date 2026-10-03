"""All external URLs and network settings live here.

Every URL can be overridden with an environment variable, which is how you
break a source on purpose to test failure handling, for example:
    USGS_URL=https://epqs.nationalmap.gov/v1/broken uvicorn app.main:app
"""
import os

USER_AGENT = "LocationCheck-Prototype/0.1 (Navatej take-home exercise)"

# (connect timeout, read timeout) in seconds, used on every request.
# USGS normally answers in 3-5 s, so 8 s of read time gives it room
# without letting one slow source hang the whole assessment.
TIMEOUT = (3, 8)

CENSUS_URL = os.environ.get(
    "CENSUS_URL",
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
)
USGS_URL = os.environ.get("USGS_URL", "https://epqs.nationalmap.gov/v1/json")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/reverse")

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "assessments.db"))
