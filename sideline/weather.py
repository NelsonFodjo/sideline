"""The weather at the ground, from Open-Meteo (free, no key, CC BY 4.0).

The football feed gives no weather, so a match preview borrows it here. The rules
are the product's rules: a fact or nothing. If the city cannot be placed with
confidence (the vendor's country must match the geocoder's), if the forecast is
unavailable, or if it is switched off (SIDELINE_WEATHER=off), the preview simply
leaves the weather out. It is never guessed and a failure is never an error.

Only a city name and a country leave the machine; the listener's identity never does.
"""

import json
import logging
import os
import time
import urllib.parse
import urllib.request

from . import clock, tls

LOG = logging.getLogger("sideline.weather")
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 4
CACHE_SECONDS = 1800

GENERIC_COUNTRIES = ("world", "europe", "international")

_cache = {}

# WMO weather codes, as a listener would hear them.
SKY = {0: "clear skies", 1: "mostly clear skies", 2: "partly cloudy", 3: "overcast",
       45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
       56: "freezing drizzle", 57: "freezing drizzle", 61: "light rain", 63: "rain",
       65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow",
       73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
       81: "showers", 82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
       95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}


def enabled():
    return os.environ.get("SIDELINE_WEATHER", "on").strip().lower() not in ("off", "0", "false", "no")


def _get(url, **params):
    req = urllib.request.Request("%s?%s" % (url, urllib.parse.urlencode(params)),
                                 headers={"User-Agent": "sideline-hackathon"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=tls.context()) as r:
        return json.loads(r.read().decode("utf-8"))


def _place(city, country):
    """(latitude, longitude) for the city in that country, or None if unsure."""
    if not city:
        return None
    hits = _get(GEOCODE, name=city, count=10, language="en", format="json").get("results") or []
    want = (country or "").strip().lower()
    if want and want not in GENERIC_COUNTRIES:
        for hit in hits:
            # "England" is an admin area of the United Kingdom in the geocoder.
            if want in ((hit.get("country") or "").lower(), (hit.get("admin1") or "").lower()):
                return hit["latitude"], hit["longitude"]
        return None
    # A European or world competition names no country. Accept the city only when it is
    # unmistakable: the only place of that name, or at least ten times the size of the next
    # (London, UK, against London, Ontario). Otherwise leave the weather out.
    if len(hits) == 1:
        return hits[0]["latitude"], hits[0]["longitude"]
    if len(hits) > 1:
        top, nxt = (hits[0].get("population") or 0), (hits[1].get("population") or 0)
        if top and top >= 10 * max(nxt, 1):
            return hits[0]["latitude"], hits[0]["longitude"]
    return None


def at_ground(city, country, when):
    """{"sky", "temperature_c", "wind_kmh", "rain_chance"} around `when` (a UTC datetime), or None."""
    if not enabled() or when is None:
        return None
    hour = when.astimezone(clock.UTC).strftime("%Y-%m-%dT%H:00")
    key = (city, country, hour)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        spot = _place(city, country)
        out = None
        if spot:
            doc = _get(FORECAST, latitude=spot[0], longitude=spot[1], timezone="UTC",
                       hourly="temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
                       start_hour=hour, end_hour=hour)
            h = doc.get("hourly") or {}
            code = (h.get("weather_code") or [None])[0]
            temp = (h.get("temperature_2m") or [None])[0]
            if code in SKY and temp is not None:
                out = {"sky": SKY[code], "temperature_c": int(round(temp)),
                       "wind_kmh": int(round((h.get("wind_speed_10m") or [0])[0] or 0)),
                       "rain_chance": (h.get("precipitation_probability") or [None])[0]}
    except Exception as e:                                   # noqa: BLE001  never an error
        LOG.warning("weather unavailable: %s", e)
        return None
    _cache[key] = (time.time(), out)
    return out


def say(w):
    """"Clear skies, 12 degrees, and a fresh wind of 21 kilometres an hour." """
    if not w:
        return ""
    bits = [w["sky"], "%d degrees" % w["temperature_c"]]
    wind = w.get("wind_kmh") or 0
    if wind >= 30:
        bits.append("a strong wind of %d kilometres an hour" % wind)
    elif wind >= 15:
        bits.append("a breeze of %d kilometres an hour" % wind)
    chance = w.get("rain_chance")
    if chance is not None and chance >= 30 and "rain" not in w["sky"] and "shower" not in w["sky"]:
        bits.append("a %d percent chance of rain" % chance)
    return ", ".join(bits[:-1]) + ", and " + bits[-1] if len(bits) > 2 else " and ".join(bits)
