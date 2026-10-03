"""Step 1 of the build: call each public API once and print what comes back.

Not part of the app. Kept so you can see what the raw responses look like.
Run: python scripts/probe_apis.py
"""
import json
import time

import requests

HEADERS = {"User-Agent": "LocationCheck-Prototype/0.1 (take-home exercise)"}


def show(name, url, params):
    start = time.time()
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        took = time.time() - start
        print(f"\n=== {name}: HTTP {r.status_code} in {took:.2f}s")
        print(json.dumps(r.json(), indent=2)[:1200])
    except Exception as e:
        print(f"\n=== {name}: FAILED -> {type(e).__name__}: {e}")


show("Census geocoder (good address)",
     "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
     {"address": "1437 Bannock St, Denver, CO", "benchmark": "Public_AR_Current", "format": "json"})

show("Census geocoder (nonsense address)",
     "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
     {"address": "asdfgh qwerty", "benchmark": "Public_AR_Current", "format": "json"})

show("USGS elevation",
     "https://epqs.nationalmap.gov/v1/json",
     {"x": -104.99, "y": 39.74, "units": "Feet", "wkid": 4326})

show("USGS elevation (point in the ocean)",
     "https://epqs.nationalmap.gov/v1/json",
     {"x": -140.0, "y": 30.0, "units": "Feet", "wkid": 4326})

show("Open-Meteo",
     "https://api.open-meteo.com/v1/forecast",
     {"latitude": 39.74, "longitude": -104.99,
      "current": "temperature_2m,wind_speed_10m", "temperature_unit": "fahrenheit", "wind_speed_unit": "mph"})

time.sleep(1)
show("Nominatim reverse",
     "https://nominatim.openstreetmap.org/reverse",
     {"lat": 39.74, "lon": -104.99, "format": "jsonv2"})
