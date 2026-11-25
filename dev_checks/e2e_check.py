"""End-to-end check: REAL Open-Meteo weather -> irrigation rule for a demo crop.

Run from the repo root:   python dev_checks/e2e_check.py [lat] [lon]
Uses data/ if it has the reference CSVs, otherwise tests/fixtures (placeholders).
Also tries one real mandi request if DATA_GOV_API_KEY is set.
"""
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from advice import crop_rules, irrigation, prices          # noqa: E402
from tools import cache, mandi, weather                    # noqa: E402

lat = float(sys.argv[1]) if len(sys.argv) > 1 else 12.97   # Bengaluru area (demo location)
lon = float(sys.argv[2]) if len(sys.argv) > 2 else 77.59

data_dir = ROOT / "data" if (ROOT / "data" / "crop_calendar.csv").exists() else ROOT / "tests" / "fixtures"
print(f"Reference data: {data_dir}")
reference = crop_rules.load_reference(data_dir)

w = weather.get_weather(lat, lon, use_cache=False)
print(f"\nWEATHER status={w['status']} freshness={w.get('freshness')} retrieved_at={w.get('retrieved_at')}")
if w["status"] != "ok":
    print(json.dumps(w, indent=2))
    sys.exit(1)
today = weather.local_today(w)
for d in w["daily"]:
    if abs((__import__("datetime").date.fromisoformat(d["date"]) - today).days) <= 3:
        print("  ", d)

profile = {"crop": "Maize", "soil_type": "sandy_loam", "water_source": "borewell",
           "sowing_date": (today - timedelta(days=65)).isoformat()}
result = irrigation.decide_irrigation(profile, w, reference)
print("\nIRRIGATION DECISION:", result["decision"], f"(confidence {result['confidence']})")
print("data_timestamp:", result["data_timestamp"], "| freshness:", result["freshness"])
for r in result["reasons"]:
    print(" -", r)
print("values:", json.dumps(result["values"]))

print("\nMANDI")
if os.environ.get("DATA_GOV_API_KEY"):
    m = mandi.get_prices("Tomato", "Kolar")
    print(json.dumps({k: v for k, v in m.items() if k != "observations"}, indent=2))
    if m["status"] == "ok":
        print(json.dumps(prices.compare_price(m["observations"], "Kolar", freshness=m["freshness"]), indent=2))
else:
    print("DATA_GOV_API_KEY not set - skipping the live mandi call (get a free key at data.gov.in).")
