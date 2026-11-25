"""The real data/*.csv files must load and give a stage + soil for every crop (Ananya)."""
from datetime import date, timedelta
from pathlib import Path

import pytest

from advice import crop_rules

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def ref():
    return crop_rules.load_reference(DATA)


def test_files_load_and_not_empty(ref):
    assert all(ref[k] for k in ("crops", "calendar", "soils"))


def test_every_crop_has_calendar_and_no_gaps(ref):
    for crop in ref["crops"]:
        name = crop["crop_name_en"]
        last = max(int(r["end_day"]) for r in ref["calendar"] if r["crop"] == name)
        for das in range(0, last + 1):
            res = crop_rules.get_stage(name, date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=das), ref["calendar"])
            assert res["status"] == "ok", (name, das, res)


def test_calendar_kc_matches_crops_csv(ref):
    for crop in ref["crops"]:
        rows = {r["stage"]: float(r["kc"]) for r in ref["calendar"] if r["crop"] == crop["crop_name_en"]}
        assert rows["initial"] == float(crop["kc_initial"])
        assert rows["mid"] == float(crop["kc_mid"])
        assert rows["late"] == float(crop["kc_end"])


def test_soils_valid(ref):
    for s in ref["soils"]:
        assert crop_rules.get_soil(s["soil_type"], ref["soils"]) is not None


def test_aliases_resolve_and_root_depth_present(ref):
    assert crop_rules.resolve_crop("ragi", ref["crops"]) == "Ragi"
    assert crop_rules.resolve_crop("ಮೆಕ್ಕೆಜೋಳ", ref["crops"]) == "Maize"
    for c in ref["crops"]:
        assert crop_rules.get_root_depth(c["crop_name_en"], ref["crops"])[1] is False


def test_mandi_coordinates_rounded_and_in_karnataka():
    import csv
    with open(DATA / "mandis.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            lat, lon = float(r["rounded_latitude"]), float(r["rounded_longitude"])
            assert round(lat, 2) == lat and round(lon, 2) == lon
            assert 11 < lat < 19 and 74 < lon < 79
