"""Open-Meteo weather tool.   Owner: Pavithra

get_weather(lat, lon, past_days=7, forecast_days=3, ...) -> dict

Input   : latitude/longitude (rounded to 2 decimals ~1 km before use or storage).
Output  : on success
    {"status": "ok", "source": "Open-Meteo", "location": {"latitude","longitude"},
     "retrieved_at": ISO UTC, "freshness": "live" | "cached", "stale": bool,
     "utc_offset_seconds": int,
     "daily": [{"date","rain_mm","et0_mm","temp_max_c"}, ...]   # past + today + forecast
     }
  on failure
    {"status": "error", "error": code, "message": str, "source": "Open-Meteo",
     "location": {...}, "attempted_at": ISO UTC}
Failure codes: timeout, network_error, bad_response, missing_fields.
Never returns made-up values. If the live call fails but an older cached copy
exists, that copy is returned with freshness="cached", stale=True, and its ORIGINAL
retrieved_at; the irrigation rule then decides whether it is too old to use.

Use local_today(weather, now) to find which entry of `daily` is "today".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from tools import cache

API_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "Open-Meteo"
WEATHER_MAX_AGE_S = 6 * 3600          # agreed: weather is fresh for 6 hours
DAILY_VARS = ("precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_max")


class WeatherError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _default_http_get(url, params, timeout):
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.Timeout as e:
        raise WeatherError("timeout", f"Open-Meteo did not answer within {timeout}s") from e
    except requests.RequestException as e:
        raise WeatherError("network_error", f"Could not reach Open-Meteo: {e}") from e
    if resp.status_code != 200:
        raise WeatherError("bad_response", f"Open-Meteo returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as e:
        raise WeatherError("bad_response", "Open-Meteo returned invalid JSON") from e


def _parse(raw: dict) -> dict:
    daily = raw.get("daily") if isinstance(raw, dict) else None
    if not isinstance(daily, dict):
        raise WeatherError("bad_response", "Response has no 'daily' block")
    dates = daily.get("time")
    if not isinstance(dates, list) or not dates:
        raise WeatherError("missing_fields", "No dates in response")
    series = {}
    for var in DAILY_VARS:
        vals = daily.get(var)
        if not isinstance(vals, list) or len(vals) != len(dates):
            raise WeatherError("missing_fields", f"Field '{var}' missing or wrong length")
        if any(v is None or isinstance(v, bool) or not isinstance(v, (int, float)) for v in vals):
            raise WeatherError("missing_fields", f"Field '{var}' has empty values")
        series[var] = vals
    return {
        "utc_offset_seconds": int(raw.get("utc_offset_seconds", 0) or 0),
        "daily": [
            {"date": d,
             "rain_mm": float(series["precipitation_sum"][i]),
             "et0_mm": float(series["et0_fao_evapotranspiration"][i]),
             "temp_max_c": float(series["temperature_2m_max"][i])}
            for i, d in enumerate(dates)
        ],
    }


def local_today(weather: dict, now: datetime | None = None):
    """Calendar date 'today' at the weather location."""
    offset = timedelta(seconds=weather.get("utc_offset_seconds", 0))
    return ((now or cache.utc_now()) + offset).date()


def get_weather(lat: float, lon: float, past_days: int = 7, forecast_days: int = 3, *,
                use_cache: bool = True, max_age: float = WEATHER_MAX_AGE_S,
                timeout: float = 10, http_get=None, now: datetime | None = None) -> dict:
    now = now or cache.utc_now()
    lat, lon = round(float(lat), 2), round(float(lon), 2)
    location = {"latitude": lat, "longitude": lon}
    key = f"weather:{lat:.2f}:{lon:.2f}:{past_days}:{forecast_days}"

    cached = cache.load(key) if use_cache else None
    if cached and cache.is_fresh(cached["fetched_at"], max_age, now):
        return {**cached["payload"], "status": "ok", "source": SOURCE, "location": location,
                "retrieved_at": cached["fetched_at"], "freshness": "cached", "stale": False}

    params = {"latitude": lat, "longitude": lon, "daily": ",".join(DAILY_VARS),
              "past_days": past_days, "forecast_days": forecast_days, "timezone": "auto"}
    try:
        parsed = _parse((http_get or _default_http_get)(API_URL, params, timeout))
    except WeatherError as err:
        if cached:  # older copy: usable only if the rule accepts its age
            return {**cached["payload"], "status": "ok", "source": SOURCE, "location": location,
                    "retrieved_at": cached["fetched_at"], "freshness": "cached", "stale": True,
                    "warning": f"Live call failed ({err.code}); showing older cached data"}
        return {"status": "error", "error": err.code, "message": err.message,
                "source": SOURCE, "location": location, "attempted_at": now.isoformat()}

    retrieved_at = cache.save(key, SOURCE, parsed, fetched_at=now)
    return {**parsed, "status": "ok", "source": SOURCE, "location": location,
            "retrieved_at": retrieved_at, "freshness": "live", "stale": False}
