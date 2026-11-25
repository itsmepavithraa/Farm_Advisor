import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "tests" / "fixtures"

NOW = datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc)   # 11:30 IST, same date
TODAY = date(2026, 11, 25)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FARM_DB_PATH", str(tmp_path / "test.db"))


@pytest.fixture
def reference():
    """Simple synthetic reference: Kc 1.0, root 1 m, FC 0.30, WP 0.20 -> TAW 100 mm, RAW 50 mm."""
    return {
        "crops": [{"crop_name_en": "Testcrop", "crop_name_kn": "", "aliases": "tc;test crop",
                   "root_depth_m": "1.0"}],
        "calendar": [
            {"crop": "Testcrop", "stage": "early", "start_day": "0", "end_day": "29", "kc": "1.0"},
            {"crop": "Testcrop", "stage": "mid", "start_day": "30", "end_day": "99", "kc": "1.0"},
        ],
        "soils": [{"soil_type": "testsoil", "field_capacity": "0.30", "wilting_point": "0.20",
                   "source": "test"}],
    }


def make_weather(rain=None, et0=None, default_et0=5.0, retrieved_at=NOW, status="ok",
                 freshness="live", first=-8, last=3):
    """Daily weather from `first` to `last` days relative to TODAY. rain/et0: {offset: mm}."""
    rain, et0 = rain or {}, et0 or {}
    daily = [{"date": (TODAY + timedelta(days=o)).isoformat(),
              "rain_mm": float(rain.get(o, 0.0)), "et0_mm": float(et0.get(o, default_et0)),
              "temp_max_c": 28.0} for o in range(first, last + 1)]
    return {"status": status, "source": "Open-Meteo", "retrieved_at": retrieved_at.isoformat(),
            "freshness": freshness, "stale": False, "utc_offset_seconds": 19800, "daily": daily,
            "location": {"latitude": 12.97, "longitude": 77.59}}


@pytest.fixture
def profile():
    return {"crop": "Testcrop", "sowing_date": (TODAY - timedelta(days=40)).isoformat(),
            "soil_type": "testsoil", "water_source": "borewell"}
