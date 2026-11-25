"""Irrigation decision rule (modelled soil water balance).   Owner: Pavithra

HOW IT WORKS, IN PLAIN WORDS
  1. Daily crop water use  =  reference evapotranspiration (ET0)  x  crop coefficient (Kc).
     Kc comes from the crop calendar for the crop's current growth stage.
  2. Effective rainfall = 80% of the rain that fell (some runs off or evaporates).
  3. We keep a running "bucket": depletion = how much of the soil's available water the
     crop has used up. Each day: depletion = depletion + crop water use - effective rain,
     never below 0 (full) and never above TAW (empty).
  4. TAW (total available water, mm) = (field capacity - wilting point) x root depth x 1000.
     RAW (the trigger) = p x TAW, where p is the crop's depletion fraction (crops.csv
     depletion_fraction, FAO-56 Table 22; 0.5 if the column is empty). Past it the crop
     starts to be water-stressed.
  5. Decision
       IRRIGATE_NOW        depletion today >= RAW (and no rain forecast that refills it)
       IRRIGATE_SOON       depletion is projected to reach RAW within today/tomorrow
       WAIT                plenty of water left, or enough rain is forecast
       INSUFFICIENT_DATA   any required input missing, unknown or stale
IMPORTANT: soil moisture is MODELLED from weather and crop data, NOT measured.
No pesticide, fertiliser or disease advice is given anywhere in this module.

decide_irrigation(profile, weather, reference, now=None) -> dict
  profile   : {"crop", "sowing_date" (YYYY-MM-DD), "soil_type",
               optional "water_source", "last_irrigation_date", "area_acres"}
  weather   : result of tools.weather.get_weather()
  reference : result of advice.crop_rules.load_reference()
Output (shared response fields; message_en/message_local/audio_url are filled later
by the language and voice layers): status, intent, decision, message_en, message_local,
reasons, source, data_timestamp, freshness, confidence, assumptions, audio_url,
plus `values` (every number used) and `inputs`.
Failure cases: every one returns decision INSUFFICIENT_DATA with the reason listed.
Boundaries: depletion exactly equal to RAW counts as reaching RAW.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from advice import crop_rules
from tools import cache, weather as weather_tool

RAW_FRACTION = 0.5               # default share of available water usable before stress (crops.csv can override per crop)
EFFECTIVE_RAIN = 0.8             # share of rainfall that reaches the root zone
HISTORY_DAYS = 7                 # days of past weather used to build the water balance
SOON_HORIZON_DAYS = 2            # "soon" = today or tomorrow
RAIN_WAIT_MM = 5.0               # effective rain (mm) needed to justify waiting
WEATHER_MAX_AGE_S = weather_tool.WEATHER_MAX_AGE_S
SOURCE = "Open-Meteo weather + modelled soil water balance (soil moisture is not measured)"
MODEL_NOTE = "Soil moisture is modelled from weather and crop data, not measured in your field."


def _envelope(decision, reasons, *, status="ok", source=SOURCE, timestamp=None,
              freshness=None, confidence=None, assumptions=None, values=None, inputs=None):
    return {"status": status, "intent": "IRRIGATION", "decision": decision,
            "message_en": None, "message_local": None, "reasons": reasons,
            "source": source, "data_timestamp": timestamp, "freshness": freshness,
            "confidence": confidence, "assumptions": assumptions or [MODEL_NOTE],
            "audio_url": None, "values": values or {}, "inputs": inputs or {}}


def _insufficient(reasons, weather=None, inputs=None):
    w = weather if isinstance(weather, dict) else {}
    return _envelope("INSUFFICIENT_DATA", reasons, status="insufficient_data",
                     timestamp=w.get("retrieved_at"), freshness=w.get("freshness"),
                     confidence="none", inputs=inputs)


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _r(x):
    return round(x, 1)


def decide_irrigation(profile: dict, weather: dict, reference: dict,
                      now: datetime | None = None) -> dict:
    now = now or cache.utc_now()
    profile = profile or {}
    inputs = {k: profile.get(k) for k in ("crop", "sowing_date", "soil_type", "water_source",
                                           "last_irrigation_date", "area_acres")}
    # ---- 1. weather present and fresh
    if not isinstance(weather, dict) or weather.get("status") != "ok":
        msg = (weather or {}).get("message", "no weather data") if isinstance(weather, dict) else "no weather data"
        return _insufficient([f"Weather data is unavailable ({msg})."], weather, inputs)
    age = cache.age_seconds(weather.get("retrieved_at"), now)
    if age is None or age < 0 or age > WEATHER_MAX_AGE_S:
        return _insufficient([f"Weather data is older than {WEATHER_MAX_AGE_S // 3600} hours "
                              f"(retrieved {weather.get('retrieved_at')}), so it cannot be used."],
                             weather, inputs)

    # ---- 2. profile inputs
    missing = [f for f in ("crop", "sowing_date", "soil_type") if not profile.get(f)]
    if missing:
        return _insufficient([f"Missing farm detail: {', '.join(missing)}."], weather, inputs)
    crop = crop_rules.resolve_crop(profile["crop"], reference["crops"]) or profile["crop"]
    soil = crop_rules.get_soil(profile["soil_type"], reference["soils"])
    if soil is None:
        return _insufficient([f"Soil type '{profile['soil_type']}' is not in the soil reference."],
                             weather, inputs)
    sown = _date(profile["sowing_date"])
    if sown is None:
        return _insufficient(["Sowing date is not a valid date (use YYYY-MM-DD)."], weather, inputs)
    last_irr = None
    if profile.get("last_irrigation_date"):
        last_irr = _date(profile["last_irrigation_date"])
        if last_irr is None:
            return _insufficient(["Last irrigation date is not a valid date."], weather, inputs)

    today = weather_tool.local_today(weather, now)
    stage_today = crop_rules.get_stage(crop, sown, today, reference["calendar"])
    if stage_today["status"] != "ok":
        return _insufficient([f"Crop stage unavailable: {stage_today['message']}."], weather, inputs)

    # ---- 3. weather coverage for the window we need
    by_date = {d["date"]: d for d in weather.get("daily", []) if isinstance(d, dict)}
    start = max(sown, today - timedelta(days=HISTORY_DAYS))
    if last_irr is not None and last_irr >= start:
        start = min(last_irr + timedelta(days=1), today)
    needed = [start + timedelta(days=i)
              for i in range((today - start).days + SOON_HORIZON_DAYS)]
    gaps = [d.isoformat() for d in needed if d.isoformat() not in by_date]
    if gaps:
        return _insufficient([f"Weather data is missing for {', '.join(gaps[:3])}"
                              f"{' and more' if len(gaps) > 3 else ''}."], weather, inputs)

    # ---- 4. water balance
    depth_m, depth_default = crop_rules.get_root_depth(crop, reference["crops"])
    taw = (soil["field_capacity"] - soil["wilting_point"]) * depth_m * 1000
    p, p_default = crop_rules.get_depletion_fraction(crop, reference["crops"], RAW_FRACTION)
    raw = p * taw

    def kc_on(day):
        st = crop_rules.get_stage(crop, sown, day, reference["calendar"])
        return st["kc"] if st["status"] == "ok" else None

    depletion, anchored = 0.0, last_irr is not None
    for day in needed[: (today - start).days]:            # up to and including yesterday
        kc = kc_on(day)
        if kc is None:
            return _insufficient([f"Crop calendar has no Kc for {day.isoformat()}."], weather, inputs)
        w = by_date[day.isoformat()]
        raw_change = depletion + kc * w["et0_mm"] - EFFECTIVE_RAIN * w["rain_mm"]
        if raw_change <= 0:
            anchored = True                                # soil back at field capacity
        depletion = min(max(raw_change, 0.0), taw)
    depletion_now = depletion

    projected, forecast_rain = [], 0.0
    for day in needed[(today - start).days:]:             # today, tomorrow
        kc = kc_on(day)
        if kc is None:
            return _insufficient([f"Crop calendar has no Kc for {day.isoformat()}."], weather, inputs)
        w = by_date[day.isoformat()]
        forecast_rain += w["rain_mm"]
        depletion = min(max(depletion + kc * w["et0_mm"] - EFFECTIVE_RAIN * w["rain_mm"], 0.0), taw)
        projected.append(depletion)
    recent_rain = sum(by_date[d.isoformat()]["rain_mm"] for d in needed[: (today - start).days]
                      if d >= today - timedelta(days=3))
    eff_forecast_rain = EFFECTIVE_RAIN * forecast_rain

    # ---- 5. decision
    if depletion_now >= raw:
        if eff_forecast_rain >= RAIN_WAIT_MM and projected[-1] < raw:
            decision = "WAIT"
            reasons = [f"Modelled soil water used so far ({_r(depletion_now)} mm) has reached the "
                       f"trigger ({_r(raw)} mm), but about {_r(forecast_rain)} mm of rain is forecast "
                       f"for today and tomorrow, which should bring it back below the trigger.",
                       "Check again after the rain; irrigate if it does not arrive."]
        else:
            decision = "IRRIGATE_NOW"
            reasons = [f"Modelled soil water used so far ({_r(depletion_now)} mm) has reached the "
                       f"trigger ({_r(raw)} mm) for {crop} at the {stage_today['stage']} stage.",
                       f"Little rain is forecast ({_r(forecast_rain)} mm over today and tomorrow)."]
    elif max(projected) >= raw:
        decision = "IRRIGATE_SOON"
        reasons = [f"Modelled soil water used so far is {_r(depletion_now)} mm, below the trigger "
                   f"({_r(raw)} mm), but it is projected to reach {_r(max(projected))} mm within "
                   f"two days.",
                   f"Forecast rain over today and tomorrow is {_r(forecast_rain)} mm."]
    else:
        decision = "WAIT"
        why_rain = f" Forecast rain: {_r(forecast_rain)} mm over today and tomorrow." if forecast_rain else ""
        reasons = [f"Modelled soil water used so far is {_r(depletion_now)} mm, well below the "
                   f"trigger ({_r(raw)} mm), and is projected to stay below it for two days "
                   f"({_r(max(projected))} mm).{why_rain}"]
    reasons.append(f"{crop} is {stage_today['days_after_sowing']} days after sowing, in the "
                   f"{stage_today['stage']} stage (Kc {stage_today['kc']}).")

    assumptions = [MODEL_NOTE,
                   f"Soil: {soil['soil_type']} (field capacity {soil['field_capacity']:.2f}, "
                   f"wilting point {soil['wilting_point']:.2f}); root depth {depth_m} m"
                   f"{' (default, not in crops.csv)' if depth_default else ''}.",
                   f"Irrigation is triggered when {round(p * 100)}% of the available "
                   f"soil water is used{' (default)' if p_default else ' (FAO-56 value for this crop)'}; {int(EFFECTIVE_RAIN * 100)}% of rainfall is counted as effective."]
    assumptions.append(f"Soil assumed full after your last irrigation on {last_irr}." if last_irr
                       else f"Soil assumed full at the start of the weather window ({start}) unless "
                            f"rain in the window refilled it; give the last irrigation date to improve this.")
    if profile.get("water_source"):
        assumptions.append(f"Water source: {profile['water_source']} (noted; not used in the calculation).")

    values = {"taw_mm": _r(taw), "raw_trigger_mm": _r(raw), "depletion_now_mm": _r(depletion_now),
              "projected_depletion_mm": [_r(p) for p in projected],
              "recent_rain_3d_mm": _r(recent_rain), "forecast_rain_2d_mm": _r(forecast_rain),
              "kc": stage_today["kc"], "stage": stage_today["stage"],
              "days_after_sowing": stage_today["days_after_sowing"],
              "refill_depth_mm": _r(depletion_now) if decision == "IRRIGATE_NOW" else None,
              "window_start": start.isoformat(), "state_anchored": anchored}
    inputs["crop"] = crop
    return _envelope(decision, reasons, timestamp=weather["retrieved_at"],
                     freshness=weather.get("freshness"),
                     confidence="medium" if anchored else "low",
                     assumptions=assumptions, values=values, inputs=inputs)
