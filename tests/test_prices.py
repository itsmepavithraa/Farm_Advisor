"""Price rule tests. 'Today' is 2026-11-25 (India date)."""
from datetime import timedelta

from advice.prices import compare_price
from tests.conftest import NOW, TODAY


def obs(day_offsets_prices, mandi="Kolar", ptype="modal"):
    return [{"commodity": "Tomato", "mandi": mandi, "variety": "", "price_type": ptype,
             "price": p, "reported_date": (TODAY + timedelta(days=o)).isoformat(),
             "source": "Agmarknet (data.gov.in)"} for o, p in day_offsets_prices]


def history(latest, offset=0):
    """latest price plus 4 earlier days all at 1000 (average 1000)."""
    return obs([(offset, latest)] + [(offset - i, 1000) for i in range(1, 5)])


def run(observations, **kw):
    return compare_price(observations, mandi="Kolar", now=NOW, freshness="live", **kw)


# ------------------------------------------------------------------ normal
def test_above_recent():
    r = run(history(1200))
    assert r["decision"] == "ABOVE_RECENT" and r["values"]["difference_percent"] == 20.0


def test_below_recent():
    assert run(history(800))["decision"] == "BELOW_RECENT"


def test_near_recent():
    assert run(history(1020))["decision"] == "NEAR_RECENT"


# ------------------------------------------------------------------ 5% boundary (inclusive near)
def test_exactly_plus_five_percent_is_near():
    assert run(history(1050))["decision"] == "NEAR_RECENT"


def test_just_over_plus_five_percent_is_above():
    assert run(history(1050.5))["decision"] == "ABOVE_RECENT"


def test_exactly_minus_five_percent_is_near():
    assert run(history(950))["decision"] == "NEAR_RECENT"


def test_just_under_minus_five_percent_is_below():
    assert run(history(949.5))["decision"] == "BELOW_RECENT"


def test_float_boundary_is_exact():
    # 105 / 100 - 1 is 0.05000000000000004 in floats; the rule must still say NEAR
    o = obs([(0, 105)] + [(-i, 100) for i in range(1, 5)])
    assert run(o)["decision"] == "NEAR_RECENT"


# ------------------------------------------------------------------ freshness gate
def test_price_three_days_old_is_fresh():
    assert run(history(1200, offset=-3))["decision"] == "ABOVE_RECENT"


def test_price_four_days_old_is_stale():
    r = run(history(1200, offset=-4))
    assert r["decision"] == "STALE_DATA"
    assert r["values"]["latest_date"] == (TODAY - timedelta(days=4)).isoformat()
    assert r["data_timestamp"] == (TODAY - timedelta(days=4)).isoformat()


def test_stale_result_gives_no_sell_or_wait_advice():
    r = run(history(1200, offset=-10))
    text = " ".join(r["reasons"] + r["assumptions"]).lower()
    assert "sell" not in text and "wait" not in text
    assert r["decision"] == "STALE_DATA"


def test_stale_message_shows_the_date():
    r = run(history(1200, offset=-7))
    assert (TODAY - timedelta(days=7)).isoformat() in r["reasons"][0]


def test_future_dated_price_is_not_trusted():
    assert run(history(1200, offset=2))["decision"] == "STALE_DATA"


# ------------------------------------------------------------------ missing data
def test_no_observations():
    assert run([])["decision"] == "INSUFFICIENT_DATA"
    assert run(None)["decision"] == "INSUFFICIENT_DATA"


def test_only_min_max_prices_do_not_count():
    assert run(obs([(0, 1000), (-1, 900)], ptype="max"))["decision"] == "INSUFFICIENT_DATA"


def test_too_little_history():
    assert run(obs([(0, 1200), (-1, 1000), (-2, 1000)]))["decision"] == "INSUFFICIENT_DATA"


def test_history_outside_window_ignored():
    o = obs([(0, 1200)] + [(-20 - i, 1000) for i in range(5)])
    assert run(o)["decision"] == "INSUFFICIENT_DATA"


def test_other_mandi_ignored():
    o = history(1200) + obs([(-1, 5000)], mandi="Mandya")
    assert run(o)["values"]["recent_average_rs_per_quintal"] == 1000.0


def test_malformed_rows_are_skipped():
    o = history(1200) + [{"price_type": "modal", "price": "abc", "reported_date": "2026-11-24"},
                         {"price_type": "modal", "price": 50, "reported_date": "not a date"}, None]
    assert run(o)["decision"] == "ABOVE_RECENT"


# ------------------------------------------------------------------ result content
def test_result_lists_dated_observations_and_mandi():
    r = run(history(1200))
    assert r["values"]["mandi"] == "Kolar" and len(r["values"]["observations_used"]) == 4
    assert r["data_timestamp"] == TODAY.isoformat() and r["freshness"] == "live"


def test_multiple_varieties_are_averaged_per_day():
    o = history(1200) + obs([(0, 1400)])      # two modal prices today: 1200 and 1400 -> 1300
    assert run(o)["values"]["latest_price_rs_per_quintal"] == 1300.0


def test_no_forecast_language():
    text = " ".join(run(history(1200))["assumptions"]).lower()
    assert "not a price forecast" in text
