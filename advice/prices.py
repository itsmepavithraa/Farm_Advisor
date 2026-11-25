"""Price comparison rule + freshness gate.   Owner: Pavithra

compare_price(observations, mandi=None, now=None, ...) -> dict

Rule (no forecasting): compare the latest modal price with the average of the earlier
modal prices in the recent window.
    latest > average x 1.05            -> ABOVE_RECENT
    latest < average x 0.95            -> BELOW_RECENT
    otherwise (within 5%, inclusive)   -> NEAR_RECENT
Freshness gate: if the latest reported date is more than 3 days before today (India date),
the result is STALE_DATA: the date is shown and NO advice is given (the words "sell" and
"wait" appear only in results built from fresh data).
If there is no modal price, or fewer than MIN_HISTORY earlier observations, the result is
INSUFFICIENT_DATA (added to the agreed decision words; tell Leeshal/Prakruthi).

observations : list from tools.mandi.get_prices()["observations"]
               (commodity, mandi, variety, price_type, price, reported_date, source)
freshness    : pass the `freshness` of the mandi result through (live/cached/recorded_sample)
If several varieties report on one date, their modal prices are averaged for that date.
Output: shared response fields + `values` (latest price/date, average, % difference,
dated observations used, reporting mandi). Prices are Rs per quintal.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from fractions import Fraction

from tools import cache

MAX_AGE_DAYS = 3          # agreed: a mandi price is fresh for 3 days
NEAR_BAND = Fraction(5, 100)   # agreed: NEAR if within 5 percent
RECENT_WINDOW_DAYS = 14
MIN_HISTORY = 3           # earlier dated observations needed for an average
SOURCE = "Agmarknet (data.gov.in)"


def _envelope(decision, reasons, *, status="ok", timestamp=None, freshness=None,
              confidence=None, assumptions=None, values=None, source=SOURCE):
    return {"status": status, "intent": "MARKET_PRICE", "decision": decision,
            "message_en": None, "message_local": None, "reasons": reasons,
            "source": source, "data_timestamp": timestamp, "freshness": freshness,
            "confidence": confidence, "assumptions": assumptions or [], "audio_url": None,
            "values": values or {}}


def _day(text):
    try:
        return date.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None


def compare_price(observations, mandi: str | None = None, now: datetime | None = None, *,
                  freshness: str | None = None, max_age_days: int = MAX_AGE_DAYS,
                  window_days: int = RECENT_WINDOW_DAYS, min_history: int = MIN_HISTORY) -> dict:
    today = cache.ist_date(now)
    per_day: dict[date, list[float]] = {}
    mandi_name = mandi
    for o in observations or []:
        d = _day(o.get("reported_date")) if isinstance(o, dict) else None
        if d is None or o.get("price_type") != "modal" or not isinstance(o.get("price"), (int, float)):
            continue
        if mandi and str(o.get("mandi", "")).lower() != mandi.lower():
            continue
        mandi_name = mandi_name or o.get("mandi")
        per_day.setdefault(d, []).append(float(o["price"]))
    if not per_day:
        return _envelope("INSUFFICIENT_DATA", ["No modal price observations are available."],
                         status="insufficient_data", freshness=freshness, confidence="none",
                         values={"mandi": mandi_name})

    series = {d: sum(v) / len(v) for d, v in per_day.items()}
    latest_day = max(series)
    latest = series[latest_day]
    age_days = (today - latest_day).days
    base_values = {"mandi": mandi_name, "latest_price_rs_per_quintal": round(latest, 2),
                   "latest_date": latest_day.isoformat(), "age_days": age_days}

    if age_days > max_age_days or age_days < 0:
        return _envelope("STALE_DATA",
                         [f"The latest price reported for {mandi_name} is dated {latest_day.isoformat()}, "
                          f"{age_days} days ago. It is too old to compare, so no price advice is given."],
                         status="stale", timestamp=latest_day.isoformat(), freshness=freshness,
                         confidence="none", values=base_values,
                         assumptions=[f"Prices older than {max_age_days} days are treated as stale."])

    cutoff = latest_day - timedelta(days=window_days)
    earlier = {d: p for d, p in series.items() if cutoff <= d < latest_day}
    if len(earlier) < min_history:
        return _envelope("INSUFFICIENT_DATA",
                         [f"Only {len(earlier)} earlier price(s) are available for {mandi_name}; "
                          f"at least {min_history} are needed to compare."],
                         status="insufficient_data", timestamp=latest_day.isoformat(),
                         freshness=freshness, confidence="none", values=base_values)

    avg = sum(earlier.values()) / len(earlier)
    # exact comparison (floats misplace the 5% boundary): latest vs avg*(1 +/- 0.05)
    fl, fa = Fraction(str(round(latest, 4))), Fraction(str(round(avg, 4)))
    if fl > fa * (1 + NEAR_BAND):
        decision = "ABOVE_RECENT"
        hint = "This may be a reasonable time to sell, but prices can change from day to day."
    elif fl < fa * (1 - NEAR_BAND):
        decision = "BELOW_RECENT"
        hint = "If you can store the crop safely, you may prefer to wait, but prices are not forecast."
    else:
        decision = "NEAR_RECENT"
        hint = "The price is close to normal; there is no strong reason to rush or delay."
    pct = float((fl - fa) / fa * 100)
    reasons = [f"On {latest_day.isoformat()} the modal price at {mandi_name} was Rs {latest:.0f} per quintal, "
               f"{abs(pct):.1f}% {'above' if pct > 0 else 'below' if pct < 0 else 'equal to'} the average "
               f"of Rs {avg:.0f} over the previous {len(earlier)} reported days.",
               hint]
    values = {**base_values, "recent_average_rs_per_quintal": round(avg, 2),
              "difference_percent": round(pct, 1),
              "observations_used": [{"date": d.isoformat(), "modal_price": round(p, 2)}
                                    for d, p in sorted(earlier.items())]}
    return _envelope(decision, reasons, timestamp=latest_day.isoformat(), freshness=freshness,
                     confidence="medium",
                     assumptions=["Comparison is with the recent average only; this is not a price forecast.",
                                  f"'Near' means within {int(NEAR_BAND * 100)}% of the average.",
                                  "Prices are modal prices in Rs per quintal as reported by the mandi."],
                     values=values)
