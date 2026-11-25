"""Weather, mandi, cache and crop_rules tests (network calls are faked)."""
from datetime import timedelta

import pytest

from advice import crop_rules
from tools import cache, mandi, weather
from tests.conftest import FIXTURES, NOW, TODAY


# ----------------------------------------------------------------------- cache
def test_cache_roundtrip():
    cache.save("k", "src", {"a": 1}, fetched_at=NOW)
    got = cache.load("k")
    assert got["payload"] == {"a": 1} and got["source"] == "src"
    assert cache.load("missing") is None


def test_is_fresh_boundaries():
    assert cache.is_fresh(NOW - timedelta(seconds=3600), 3600, NOW)
    assert not cache.is_fresh(NOW - timedelta(seconds=3601), 3600, NOW)
    assert not cache.is_fresh("garbage", 3600, NOW)
    assert not cache.is_fresh(NOW + timedelta(hours=1), 3600, NOW)   # future timestamp


# --------------------------------------------------------------------- weather
def good_response():
    days = [(TODAY + timedelta(days=o)).isoformat() for o in range(-3, 3)]
    return {"utc_offset_seconds": 19800, "daily": {
        "time": days, "precipitation_sum": [0, 1, 0, 2.5, 0, 0],
        "et0_fao_evapotranspiration": [4, 4, 4, 4, 4, 4],
        "temperature_2m_max": [30] * 6}}


def test_weather_live_then_cached():
    calls = []

    def fake(url, params, timeout):
        calls.append(params)
        return good_response()
    first = weather.get_weather(12.9716, 77.5946, http_get=fake, now=NOW)
    assert first["freshness"] == "live" and first["retrieved_at"] == NOW.isoformat()
    assert first["location"] == {"latitude": 12.97, "longitude": 77.59}
    assert calls[0]["latitude"] == 12.97                       # rounded before sending
    second = weather.get_weather(12.9716, 77.5946, http_get=fake, now=NOW + timedelta(hours=1))
    assert second["freshness"] == "cached" and len(calls) == 1


def test_weather_refetches_after_max_age():
    n = []
    weather.get_weather(12.97, 77.59, http_get=lambda *a: n.append(1) or good_response(), now=NOW)
    weather.get_weather(12.97, 77.59, http_get=lambda *a: n.append(1) or good_response(),
                        now=NOW + timedelta(hours=7))
    assert len(n) == 2


@pytest.mark.parametrize("payload,code", [
    ({"nothing": 1}, "bad_response"),
    ({"daily": {"time": []}}, "missing_fields"),
    ({"daily": {"time": ["2026-11-25"], "precipitation_sum": [None],
                "et0_fao_evapotranspiration": [1], "temperature_2m_max": [1]}}, "missing_fields"),
    ({"daily": {"time": ["2026-11-25"], "precipitation_sum": [1]}}, "missing_fields"),
])
def test_weather_bad_payloads_return_error_not_fake_values(payload, code):
    r = weather.get_weather(12.97, 77.59, http_get=lambda *a: payload, now=NOW)
    assert r["status"] == "error" and r["error"] == code and "daily" not in r


def test_weather_timeout_error():
    def boom(*a):
        raise weather.WeatherError("timeout", "slow")
    r = weather.get_weather(12.97, 77.59, http_get=boom, now=NOW)
    assert r["status"] == "error" and r["error"] == "timeout" and r["attempted_at"] == NOW.isoformat()


def test_weather_falls_back_to_old_cache_marked_stale():
    weather.get_weather(12.97, 77.59, http_get=lambda *a: good_response(), now=NOW)

    def boom(*a):
        raise weather.WeatherError("network_error", "offline")
    r = weather.get_weather(12.97, 77.59, http_get=boom, now=NOW + timedelta(hours=9))
    assert r["status"] == "ok" and r["stale"] is True and r["freshness"] == "cached"
    assert r["retrieved_at"] == NOW.isoformat()


def test_local_today_uses_offset():
    w = {"utc_offset_seconds": 19800}
    late_utc = NOW.replace(hour=20)           # 01:30 IST next day
    assert weather.local_today(w, late_utc) == TODAY + timedelta(days=1)


# ----------------------------------------------------------------------- mandi
def agmark_response(day, modal=1000, mandi_name="Kolar"):
    return {"records": [{"state": "Karnataka", "market": mandi_name, "commodity": "Tomato",
                         "variety": "Local", "arrival_date": day, "min_price": str(modal - 100),
                         "max_price": str(modal + 100), "modal_price": str(modal)}]}


def test_mandi_parses_and_stores_history():
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW,
                         http_get=lambda *a: agmark_response("25/11/2026", 1500))
    assert r["status"] == "ok" and r["freshness"] == "live"
    modal = [o for o in r["observations"] if o["price_type"] == "modal"]
    assert modal[0]["price"] == 1500.0 and modal[0]["reported_date"] == "2026-11-25"
    assert {o["price_type"] for o in r["observations"]} == {"modal", "min", "max"}


def test_mandi_history_accumulates_across_days():
    for i, day in enumerate(["22/11/2026", "23/11/2026", "24/11/2026"]):
        mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW - timedelta(days=3 - i, hours=-1 * 0),
                         http_get=lambda *a, d=day: agmark_response(d, 1000 + 10 * len(d)))
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW,
                         http_get=lambda *a: agmark_response("25/11/2026", 1300))
    dates = {o["reported_date"] for o in r["observations"] if o["price_type"] == "modal"}
    assert len(dates) == 4


def test_mandi_fresh_cache_skips_network():
    n = []
    mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW,
                     http_get=lambda *a: n.append(1) or agmark_response("25/11/2026"))
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW + timedelta(hours=1),
                         http_get=lambda *a: n.append(1) or agmark_response("25/11/2026"))
    assert len(n) == 1 and r["freshness"] == "cached"


def test_mandi_without_key_is_clear_error(monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    r = mandi.get_prices("Tomato", "Kolar", now=NOW)
    assert r["status"] == "error" and r["error"] == "no_api_key"


def test_mandi_no_records():
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW, http_get=lambda *a: {"records": []})
    assert r["status"] == "error" and r["error"] == "no_records"


def test_mandi_bad_response():
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW, http_get=lambda *a: {"error": "x"})
    assert r["status"] == "error" and r["error"] == "bad_response"


def test_mandi_failure_falls_back_to_saved_observations_flagged_stale():
    mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW - timedelta(days=1),
                     http_get=lambda *a: agmark_response("24/11/2026", 900))

    def boom(*a):
        raise mandi.MandiError("timeout", "slow")
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW + timedelta(days=1), http_get=boom)
    assert r["status"] == "ok" and r["stale"] is True and r["freshness"] == "cached"


def test_mandi_skips_bad_records():
    resp = {"records": [{"arrival_date": "25/11/2026", "modal_price": "NR", "min_price": "-",
                         "max_price": "0"}, agmark_response("25/11/2026", 1200)["records"][0]]}
    r = mandi.get_prices("Tomato", "Kolar", api_key="k", now=NOW, http_get=lambda *a: resp)
    assert all(o["price"] > 0 for o in r["observations"]) and len(r["observations"]) == 3


def test_recorded_sample_is_labelled(tmp_path, monkeypatch):
    sample = tmp_path / "s.json"
    sample.write_text('{"recorded_at": "2026-11-01", "observations": []}')
    monkeypatch.setattr(mandi, "SAMPLE_PATH", sample)
    r = mandi.get_prices("Tomato", "Kolar", now=NOW, allow_recorded_sample=True)
    assert r["freshness"] == "recorded_sample" and "RECORDED SAMPLE" in r["label"]
    assert mandi.get_prices("Tomato", "Kolar", now=NOW)["status"] == "error"   # not used by default


def test_nearest_mandis():
    out = mandi.nearest_mandis(13.1, 78.1, FIXTURES / "mandis.csv", n=2)
    assert out[0]["mandi_name"] == "Kolar" and len(out) == 2


# ------------------------------------------------------------------ crop_rules
@pytest.fixture
def ref():
    return crop_rules.load_reference(FIXTURES)


def test_reference_files_load(ref):
    assert {"Ragi", "Maize", "Tomato", "Groundnut"} <= {c["crop_name_en"] for c in ref["crops"]}


def test_resolve_crop_by_alias_and_kannada(ref):
    assert crop_rules.resolve_crop("Finger Millet", ref["crops"]) == "Ragi"
    assert crop_rules.resolve_crop("ರಾಗಿ", ref["crops"]) == "Ragi"
    assert crop_rules.resolve_crop("unknown", ref["crops"]) is None
    assert crop_rules.resolve_crop("", ref["crops"]) is None


@pytest.mark.parametrize("das,stage,kc", [(0, "initial", 0.30), (29, "initial", 0.30),
                                          (30, "development", 0.75), (70, "mid", 1.20),
                                          (169, "late", 0.60)])
def test_stage_boundaries(ref, das, stage, kc):
    sown = TODAY - timedelta(days=das)
    r = crop_rules.get_stage("Maize", sown, TODAY, ref["calendar"])
    assert (r["stage"], r["kc"], r["days_after_sowing"]) == (stage, kc, das)


def test_stage_failures(ref):
    cal = ref["calendar"]
    assert crop_rules.get_stage("Maize", TODAY + timedelta(days=1), TODAY, cal)["status"] == "not_sown_yet"
    assert crop_rules.get_stage("Maize", TODAY - timedelta(days=170), TODAY, cal)["status"] == "past_season"
    assert crop_rules.get_stage("Wheat", TODAY, TODAY, cal)["status"] == "unknown_crop"
    assert crop_rules.get_stage("Maize", "oops", TODAY, cal)["status"] == "bad_date"


def test_soil_lookup_and_percent_values(ref):
    s = crop_rules.get_soil("Black Clay", ref["soils"])
    assert s["field_capacity"] == 0.36
    pct = [{"soil_type": "x", "field_capacity": "30", "wilting_point": "15", "source": ""}]
    assert crop_rules.get_soil("x", pct)["field_capacity"] == 0.30
    assert crop_rules.get_soil("nope", ref["soils"]) is None
    bad = [{"soil_type": "y", "field_capacity": "0.1", "wilting_point": "0.2"}]
    assert crop_rules.get_soil("y", bad) is None


def test_root_depth(ref):
    assert crop_rules.get_root_depth("Maize", ref["crops"]) == (0.8, False)
    assert crop_rules.get_root_depth("Unknown", ref["crops"]) == (0.5, True)


# ------------------------------------------------------------- mandi.list_markets
def test_list_markets_returns_exact_names_sorted():
    resp = {"records": [{"market": "Kolar"}, {"market": "Bangalore"}, {"market": "Kolar"}, {"market": ""}]}
    r = mandi.list_markets("Tomato", api_key="k", http_get=lambda *a: resp)
    assert r == {"status": "ok", "commodity": "Tomato", "state": "Karnataka",
                 "markets": ["Bangalore", "Kolar"]}


def test_list_markets_errors(monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    assert mandi.list_markets("Tomato")["error"] == "no_api_key"
    assert mandi.list_markets("Tomato", api_key="k", http_get=lambda *a: {"records": []})["error"] == "no_records"
    assert mandi.list_markets("Tomato", api_key="k", http_get=lambda *a: {"x": 1})["error"] == "bad_response"

    def boom(*a):
        raise mandi.MandiError("timeout", "slow")
    assert mandi.list_markets("Tomato", api_key="k", http_get=boom)["error"] == "timeout"


# ------------------------------------------------------- depletion fraction (crop_rules)
def test_depletion_fraction_from_csv_and_default():
    crops = [{"crop_name_en": "Tomato", "depletion_fraction": "0.40"},
             {"crop_name_en": "Bad", "depletion_fraction": "7"},
             {"crop_name_en": "Empty", "depletion_fraction": ""}]
    assert crop_rules.get_depletion_fraction("tomato", crops, 0.5) == (0.40, False)
    assert crop_rules.get_depletion_fraction("Bad", crops, 0.5) == (0.5, True)
    assert crop_rules.get_depletion_fraction("Empty", crops, 0.5) == (0.5, True)
    assert crop_rules.get_depletion_fraction("Nope", crops, 0.5) == (0.5, True)
