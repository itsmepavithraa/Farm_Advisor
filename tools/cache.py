"""SQLite cache + freshness helpers.   Owner: Pavithra

Uses plain sqlite3 (store.py belongs to Leeshal). The `cache` table has the
fields agreed in the Team Build Guide: cache_key, source, payload, fetched_at.
A second table, `price_history`, accumulates dated mandi observations, because
the live Agmarknet feed only shows the latest day and the price rule needs
"recent observations".

Database file: env FARM_DB_PATH, default <repo>/farm_advisor.db (git-ignored).

Functions
---------
utc_now()                      -> aware datetime (UTC)
parse_ts(value)                -> aware datetime from ISO string/datetime
age_seconds(fetched_at, now)   -> float seconds
is_fresh(fetched_at, max_age_seconds, now=None) -> bool
save(cache_key, source, payload, fetched_at=None)
load(cache_key)                -> {"cache_key","source","payload","fetched_at"} or None
record_observations(rows) / get_history(commodity, mandi, since_date)

Failure cases: an unparsable timestamp is treated as NOT fresh (never raises
from is_fresh); load() returns None for a missing key or a corrupt payload.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "farm_advisor.db"
IST = timezone(timedelta(hours=5, minutes=30))


def db_path() -> str:
    return os.environ.get("FARM_DB_PATH", str(DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        " cache_key TEXT PRIMARY KEY, source TEXT, payload TEXT, fetched_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS price_history ("
        " commodity TEXT, mandi TEXT, variety TEXT, price_type TEXT,"
        " price REAL, reported_date TEXT, source TEXT,"
        " PRIMARY KEY (commodity, mandi, variety, price_type, reported_date))"
    )
    return conn


# ---------------------------------------------------------------- time helpers
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_seconds(fetched_at, now: datetime | None = None) -> float | None:
    ts = parse_ts(fetched_at)
    if ts is None:
        return None
    return ((now or utc_now()) - ts).total_seconds()


def is_fresh(fetched_at, max_age_seconds: float, now: datetime | None = None) -> bool:
    """True if fetched_at is no older than max_age_seconds (boundary = fresh)."""
    age = age_seconds(fetched_at, now)
    return age is not None and 0 <= age <= max_age_seconds


def ist_date(now: datetime | None = None) -> date:
    """Today's calendar date in India (mandi dates are reported in IST)."""
    return (now or utc_now()).astimezone(IST).date()


# ----------------------------------------------------------------- cache table
def save(cache_key: str, source: str, payload, fetched_at=None) -> str:
    ts = (parse_ts(fetched_at) or utc_now()).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, source, payload, fetched_at)"
            " VALUES (?, ?, ?, ?)",
            (cache_key, source, json.dumps(payload), ts),
        )
    return ts


def load(cache_key: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT cache_key, source, payload, fetched_at FROM cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[2])
    except (TypeError, ValueError):
        return None
    return {"cache_key": row[0], "source": row[1], "payload": payload, "fetched_at": row[3]}


# --------------------------------------------------------------- price history
def record_observations(rows: list[dict]) -> int:
    """Store dated price observations (idempotent on commodity/mandi/variety/type/date)."""
    with _connect() as conn:
        for r in rows:
            conn.execute(
                "INSERT OR REPLACE INTO price_history VALUES (?,?,?,?,?,?,?)",
                (r["commodity"], r["mandi"], r.get("variety") or "", r["price_type"],
                 r["price"], r["reported_date"], r.get("source", "")),
            )
    return len(rows)


def get_history(commodity: str, mandi: str, since_date: str) -> list[dict]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT commodity, mandi, variety, price_type, price, reported_date, source"
            " FROM price_history WHERE lower(commodity)=lower(?) AND lower(mandi)=lower(?)"
            " AND reported_date >= ? ORDER BY reported_date",
            (commodity, mandi, since_date),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
