"""Check mandis.csv spellings against the names Agmarknet really uses.

Run from the repo root (needs DATA_GOV_API_KEY, a free key from data.gov.in):
    python dev_checks/check_mandi_names.py [commodity ...]      default: Tomato Maize Ragi(Finger Millet) Groundnut

For every mandi in data/mandis.csv it prints MATCH, or the closest real names to copy.
A mandi can legitimately be missing for one commodity on one day, so the script checks
several commodities and reports a mandi as MISSING only if none of them lists it.
"""
import csv
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import mandi  # noqa: E402

commodities = sys.argv[1:] or ["Tomato", "Maize", "Ragi (Finger Millet)", "Groundnut"]
seen: set[str] = set()
for c in commodities:
    res = mandi.list_markets(c)
    if res["status"] != "ok":
        print(f"{c}: {res['error']} - {res['message']}")
        if res["error"] == "no_api_key":
            sys.exit(1)
        continue
    print(f"{c}: {len(res['markets'])} Karnataka markets reported")
    seen.update(res["markets"])

if not seen:
    sys.exit("No market names could be fetched, nothing to compare.")
with open(ROOT / "data" / "mandis.csv", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        name = row["mandi_name"]
        if name in seen:
            print(f"MATCH   {name}")
        else:
            close = difflib.get_close_matches(name, sorted(seen), n=3, cutoff=0.5)
            print(f"MISSING {name}  -> closest real names: {close or 'none'}")
print("\nAll names seen:", ", ".join(sorted(seen)))
