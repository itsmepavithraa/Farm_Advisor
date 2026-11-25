"""Irrigation rule tests with fixed inputs. TAW = 100 mm, RAW = 50 mm, Kc = 1.0."""
from datetime import timedelta

import pytest

from advice.irrigation import decide_irrigation
from tests.conftest import NOW, TODAY, make_weather

SCHEMA = {"status", "intent", "decision", "message_en", "message_local", "reasons", "source",
          "data_timestamp", "freshness", "confidence", "assumptions", "audio_url"}


def run(profile, reference, weather, **overrides):
    return decide_irrigation({**profile, **overrides}, weather, reference, now=NOW)


def irrigated(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


# last irrigation 6 days ago -> window = 5 days (today-5 .. yesterday)
def five_days(et_each, today_et=5.0, tomorrow_et=5.0, rain=None):
    et0 = {o: et_each for o in range(-5, 0)}
    et0.update({0: today_et, 1: tomorrow_et})
    return make_weather(rain=rain, et0=et0)


# ---------------------------------------------------------------- one case per decision
def test_irrigate_now(profile, reference):
    r = run(profile, reference, five_days(11), last_irrigation_date=irrigated(6))  # 55 mm
    assert r["decision"] == "IRRIGATE_NOW"
    assert r["values"]["depletion_now_mm"] == 55.0
    assert r["values"]["refill_depth_mm"] == 55.0


def test_irrigate_soon(profile, reference):
    r = run(profile, reference, five_days(8, today_et=12), last_irrigation_date=irrigated(6))  # 40 -> 52
    assert r["decision"] == "IRRIGATE_SOON"


def test_wait_plenty_of_water(profile, reference):
    r = run(profile, reference, five_days(4), last_irrigation_date=irrigated(6))  # 20 mm
    assert r["decision"] == "WAIT"


def test_wait_when_rain_forecast_refills(profile, reference):
    # depleted 55 mm, 30 mm rain today -> 24 mm effective -> projected below trigger
    r = run(profile, reference, five_days(11, rain={0: 30}), last_irrigation_date=irrigated(6))
    assert r["decision"] == "WAIT"
    assert any("rain" in x for x in r["reasons"])


def test_small_rain_does_not_stop_irrigation(profile, reference):
    r = run(profile, reference, five_days(11, rain={0: 2}), last_irrigation_date=irrigated(6))
    assert r["decision"] == "IRRIGATE_NOW"


def test_rain_forecast_not_enough_to_refill_still_irrigate(profile, reference):
    # depleted 90 mm; 10 mm rain (8 effective) cannot bring it below 50
    r = run(profile, reference, five_days(18, rain={0: 10}), last_irrigation_date=irrigated(6))
    assert r["decision"] == "IRRIGATE_NOW"


# ---------------------------------------------------------------- boundaries
def test_exactly_at_trigger_is_irrigate_now(profile, reference):
    r = run(profile, reference, five_days(10), last_irrigation_date=irrigated(6))  # exactly 50.0
    assert r["values"]["depletion_now_mm"] == 50.0
    assert r["decision"] == "IRRIGATE_NOW"


def test_just_below_trigger_is_not_now(profile, reference):
    w = make_weather(et0={-5: 10, -4: 10, -3: 10, -2: 10, -1: 9.9, 0: 0, 1: 0})  # 49.9
    r = run(profile, reference, w, last_irrigation_date=irrigated(6))
    assert r["decision"] == "WAIT"


def test_projection_exactly_at_trigger_is_soon(profile, reference):
    w = make_weather(et0={-5: 8, -4: 8, -3: 8, -2: 8, -1: 8, 0: 10, 1: 0})  # 40 + 10 = 50.0
    r = run(profile, reference, w, last_irrigation_date=irrigated(6))
    assert r["decision"] == "IRRIGATE_SOON"


def test_weather_exactly_six_hours_old_is_usable(profile, reference):
    w = make_weather(retrieved_at=NOW - timedelta(hours=6))
    assert run(profile, reference, w)["decision"] != "INSUFFICIENT_DATA"


def test_weather_just_over_six_hours_is_stale(profile, reference):
    w = make_weather(retrieved_at=NOW - timedelta(hours=6, seconds=1))
    assert run(profile, reference, w)["decision"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------- missing / stale data
def test_weather_error(profile, reference):
    w = {"status": "error", "error": "timeout", "message": "no answer"}
    r = run(profile, reference, w)
    assert r["decision"] == "INSUFFICIENT_DATA" and "unavailable" in r["reasons"][0]


def test_weather_none(profile, reference):
    assert run(profile, reference, None)["decision"] == "INSUFFICIENT_DATA"


def test_stale_weather(profile, reference):
    w = make_weather(retrieved_at=NOW - timedelta(hours=7), freshness="cached")
    r = run(profile, reference, w)
    assert r["decision"] == "INSUFFICIENT_DATA" and "older than 6 hours" in r["reasons"][0]


@pytest.mark.parametrize("field", ["crop", "sowing_date", "soil_type"])
def test_missing_profile_field(profile, reference, field):
    r = run(profile, reference, make_weather(), **{field: None})
    assert r["decision"] == "INSUFFICIENT_DATA" and field in r["reasons"][0]


def test_unknown_soil(profile, reference):
    assert run(profile, reference, make_weather(), soil_type="moon dust")["decision"] == "INSUFFICIENT_DATA"


def test_unknown_crop(profile, reference):
    assert run(profile, reference, make_weather(), crop="dragonfruit")["decision"] == "INSUFFICIENT_DATA"


def test_sowing_in_future(profile, reference):
    r = run(profile, reference, make_weather(), sowing_date=(TODAY + timedelta(days=2)).isoformat())
    assert r["decision"] == "INSUFFICIENT_DATA"


def test_past_season(profile, reference):
    r = run(profile, reference, make_weather(), sowing_date=(TODAY - timedelta(days=200)).isoformat())
    assert r["decision"] == "INSUFFICIENT_DATA"


def test_bad_sowing_date(profile, reference):
    assert run(profile, reference, make_weather(), sowing_date="yesterday")["decision"] == "INSUFFICIENT_DATA"


def test_weather_missing_a_day(profile, reference):
    w = make_weather()
    w["daily"] = [d for d in w["daily"] if d["date"] != (TODAY - timedelta(days=2)).isoformat()]
    r = run(profile, reference, w)
    assert r["decision"] == "INSUFFICIENT_DATA" and "missing" in r["reasons"][0]


def test_forecast_missing(profile, reference):
    assert run(profile, reference, make_weather(last=0))["decision"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------- model behaviour
def test_alias_resolves_crop(profile, reference):
    assert run(profile, reference, make_weather(), crop="test crop")["inputs"]["crop"] == "Testcrop"


def test_rain_resets_bucket_and_anchors_confidence(profile, reference):
    # 100 mm of rain 3 days ago refills the soil; only 3 dry days since -> low depletion
    w = make_weather(rain={-3: 100})
    r = run(profile, reference, w)
    assert r["values"]["state_anchored"] is True and r["confidence"] == "medium"
    assert r["values"]["depletion_now_mm"] == 10.0   # 2 dry days after the full-bucket day


def test_unanchored_state_gives_low_confidence(profile, reference):
    r = run(profile, reference, make_weather())
    assert r["confidence"] == "low"


def test_last_irrigation_today(profile, reference):
    r = run(profile, reference, make_weather(), last_irrigation_date=TODAY.isoformat())
    assert r["values"]["depletion_now_mm"] == 0.0


def test_depletion_capped_at_taw(profile, reference):
    r = run(profile, reference, make_weather(default_et0=30))
    assert r["values"]["depletion_now_mm"] == 100.0


def test_kc_scales_water_use(profile, reference):
    reference["calendar"][1]["kc"] = "0.5"
    r = run(profile, reference, five_days(10), last_irrigation_date=irrigated(6))
    assert r["values"]["depletion_now_mm"] == 25.0


def test_missing_root_depth_uses_default_and_says_so(profile, reference):
    reference["crops"][0]["root_depth_m"] = ""
    r = run(profile, reference, make_weather())
    assert r["values"]["taw_mm"] == 50.0      # (0.30-0.20) x 0.5 m x 1000
    assert any("default" in a for a in r["assumptions"])


# ---------------------------------------------------------------- response shape / safety
@pytest.mark.parametrize("weather", [make_weather(), None])
def test_response_has_shared_fields(profile, reference, weather):
    assert SCHEMA <= set(run(profile, reference, weather))


def test_states_that_moisture_is_modelled(profile, reference):
    r = run(profile, reference, make_weather())
    assert any("modelled" in a and "not measured" in a for a in r["assumptions"])


def test_no_pesticide_or_fertiliser_advice(profile, reference):
    text = str(run(profile, reference, make_weather())).lower()
    for word in ("pesticide", "fertiliser", "fertilizer", "insecticide", "fungicide"):
        assert word not in text


def test_timestamp_and_source_present(profile, reference):
    r = run(profile, reference, make_weather())
    assert r["data_timestamp"] == NOW.isoformat() and "Open-Meteo" in r["source"]
