"""Agmarknet mandi-price tool (via the data.gov.in open API).   Owner: Pavithra

get_prices(commodity, mandi, state="Karnataka", ...) -> dict

Needs a free API key from data.gov.in in env DATA_GOV_API_KEY (never commit it).
Prices are Rs per quintal.

Output on success
    {"status": "ok", "source": "Agmarknet (data.gov.in)", "commodity", "mandi",
     "retrieved_at", "freshness": "live" | "cached" | "recorded_sample", "stale": bool,
     "observations": [{"commodity","mandi","variety","price_type": "modal|min|max",
                       "price": float, "reported_date": "YYYY-MM-DD", "source"}, ...]}
`observations` merges today's fetch with earlier days saved in price_history
(each successful fetch is stored), because the live feed shows only the latest day.
Failure codes: no_api_key, timeout, network_error, bad_response, no_records.
A RECORDED SAMPLE (data/recorded_mandi_sample.json) is used only when the caller
passes allow_recorded_sample=True, and is labelled freshness="recorded_sample".

nearest_mandis(lat, lon, csv_path, n=3) ranks mandis.csv rows by distance.
"""
from __future__ import annotations

import csv
import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests

from tools import cache

API_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
SOURCE = "Agmarknet (data.gov.in)"
FETCH_MAX_AGE_S = 6 * 3600            # don't re-call the API more often than this
SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "recorded_mandi_sample.json"


class MandiError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _default_http_get(url, params, timeout):
    try:
        resp = requests.get(url, params=params, timeout=timeout)
    except requests.Timeout as e:
        raise MandiError("timeout", f"Agmarknet did not answer within {timeout}s") from e
    except requests.RequestException as e:
        raise MandiError("network_error", f"Could not reach Agmarknet: {e}") from e
    if resp.status_code != 200:
        raise MandiError("bad_response", f"Agmarknet API returned HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as e:
        raise MandiError("bad_response", "Agmarknet API returned invalid JSON") from e


def _parse_date(text) -> str | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_observations(records: list, commodity: str, mandi: str) -> list[dict]:
    out = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rec = {str(k).lower(): v for k, v in rec.items()}
        day = _parse_date(rec.get("arrival_date"))
        if day is None:
            continue
        for ptype, field in (("modal", "modal_price"), ("min", "min_price"), ("max", "max_price")):
            try:
                price = float(rec.get(field))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            out.append({"commodity": commodity, "mandi": mandi,
                        "variety": str(rec.get("variety") or "").strip(),
                        "price_type": ptype, "price": price,
                        "reported_date": day, "source": SOURCE})
    return out


def _merge(history: list[dict]) -> list[dict]:
    return sorted(history, key=lambda r: (r["reported_date"], r["price_type"]))


def _result(commodity, mandi, observations, retrieved_at, freshness, stale=False, **extra):
    return {"status": "ok", "source": SOURCE, "commodity": commodity, "mandi": mandi,
            "retrieved_at": retrieved_at, "freshness": freshness, "stale": stale,
            "observations": observations, **extra}


def get_prices(commodity: str, mandi: str, state: str = "Karnataka", *,
               use_cache: bool = True, max_age: float = FETCH_MAX_AGE_S,
               history_days: int = 14, timeout: float = 15, http_get=None,
               api_key: str | None = None, allow_recorded_sample: bool = False,
               now: datetime | None = None) -> dict:
    now = now or cache.utc_now()
    since = (cache.ist_date(now) - timedelta(days=history_days)).isoformat()
    key = f"mandi:{state.lower()}:{commodity.lower()}:{mandi.lower()}"
    api_key = api_key or os.environ.get("DATA_GOV_API_KEY")

    def from_history(freshness, stale, retrieved_at, **extra):
        hist = _merge(cache.get_history(commodity, mandi, since))
        if not hist:
            return None
        return _result(commodity, mandi, hist, retrieved_at, freshness, stale, **extra)

    cached = cache.load(key) if use_cache else None
    if cached and cache.is_fresh(cached["fetched_at"], max_age, now):
        res = from_history("cached", False, cached["fetched_at"])
        if res:
            return res

    err = None
    if not api_key:
        err = MandiError("no_api_key", "Set DATA_GOV_API_KEY (free key from data.gov.in)")
    else:
        params = {"api-key": api_key, "format": "json", "limit": 100,
                  "filters[state.keyword]": state, "filters[commodity]": commodity,
                  "filters[market]": mandi}
        try:
            raw = (http_get or _default_http_get)(API_URL, params, timeout)
            records = raw.get("records") if isinstance(raw, dict) else None
            if not isinstance(records, list):
                raise MandiError("bad_response", "Response has no 'records' list")
            obs = _to_observations(records, commodity, mandi)
            if not obs:
                raise MandiError("no_records", f"No usable price records for {commodity} at {mandi}")
            cache.record_observations(obs)
            fetched = cache.save(key, SOURCE, {"records": len(records)}, fetched_at=now)
            return _result(commodity, mandi, _merge(cache.get_history(commodity, mandi, since)),
                           fetched, "live")
        except MandiError as e:
            err = e

    # live call failed: older saved observations are real, dated data -> flag as stale-cached
    older = from_history("cached", True, cached["fetched_at"] if cached else None,
                         warning=f"Live call failed ({err.code}); showing saved observations")
    if older:
        return older
    if allow_recorded_sample and SAMPLE_PATH.exists():
        try:
            sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
            return _result(commodity, mandi, sample["observations"], sample.get("recorded_at"),
                           "recorded_sample", True,
                           label="RECORDED SAMPLE - not live data")
        except (OSError, ValueError, KeyError):
            pass
    return {"status": "error", "error": err.code, "message": err.message, "source": SOURCE,
            "commodity": commodity, "mandi": mandi, "attempted_at": now.isoformat()}


def nearest_mandis(lat: float, lon: float, csv_path, n: int = 3) -> list[dict]:
    """Rank mandis.csv rows (mandi_name,district,rounded_latitude,rounded_longitude)."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rlat, rlon = float(r["rounded_latitude"]), float(r["rounded_longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            p1, p2 = math.radians(lat), math.radians(rlat)
            a = (math.sin((p2 - p1) / 2) ** 2
                 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(rlon - lon) / 2) ** 2)
            km = 6371 * 2 * math.asin(math.sqrt(a))
            rows.append({**r, "distance_km": round(km, 1)})
    return sorted(rows, key=lambda r: r["distance_km"])[:n]
