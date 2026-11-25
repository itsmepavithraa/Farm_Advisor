# Pavithra handoff note

## Done (tests: `python -m pytest -q` -> 89 passed)
- `tools/cache.py`, `tools/weather.py`, `tools/mandi.py`
- `advice/crop_rules.py`, `advice/irrigation.py`, `advice/prices.py`
- `tests/test_irrigation.py`, `tests/test_prices.py`, `tests/test_tools.py` (every rule branch: normal, boundary, missing, stale)
- Temporary `backend/pipeline.py` stub (Leeshal replaces) and placeholder `eval/sample_*.json` (Prakruthi's versions replace mine)
- Real weather call verified: see `notes/e2e_real_run_output.txt` (timestamp 2026-11-25 04:23 UTC, Open-Meteo, Bengaluru area)

## NOT done / blocked – needs the team
1. **Live mandi request NOT verified.** It needs a free data.gov.in API key (`DATA_GOV_API_KEY`). The public demo key is
   rate-limited (HTTP 429). Register once, run `python dev_checks/e2e_check.py`, confirm one dated result, and save
   it as `data/recorded_mandi_sample.json` labelled RECORDED SAMPLE if you want an offline fallback.
   The field names (`arrival_date`, `modal_price`, `market`, `commodity`) follow the data.gov.in Agmarknet dataset; check them on the first real response.
2. **Reference CSVs are placeholders.** `tests/fixtures/*.csv` hold approximate FAO-56-style values written by Pavithra's
   assistant from memory so the rules could be tested. Ananya's real `data/*.csv` must replace them (same columns) and
   Pavithra must review the Kc, stage-day and field-capacity values against FAO/ICAR sources.
3. **Ask Ananya for one extra column:** `root_depth_m` in `crops.csv` (default 0.5 m is used if missing and stated in `assumptions`).
4. Mandi names must match Agmarknet spelling exactly (e.g. check "Bangalore" vs "Bengaluru").
5. `INSUFFICIENT_DATA` is also used for prices (added to the agreed price decision words). Tell Leeshal/Prakruthi.
6. Mandi price history only builds up over days of fetching; call `mandi.get_prices()` daily (warm_cache.py).

## Plug-in for Leeshal (pipeline.ask)
```python
from tools import weather, mandi
from advice import crop_rules, irrigation, prices
reference = crop_rules.load_reference()                 # data/*.csv
w = weather.get_weather(lat, lon)                       # rounded location
result = irrigation.decide_irrigation(profile, w, reference)
m = mandi.get_prices("Tomato", "Kolar")
result = prices.compare_price(m.get("observations"), "Kolar", freshness=m.get("freshness"))
```
Both results already use the shared response field names. Do not rename them.

## Git
Suggested: `git checkout -b feat/data-rules`, copy these folders into the repo root, `git add`, commit, push.
`backend/__init__.py`, `backend/pipeline.py`, and `eval/sample_*.json` will likely conflict with teammates' files: keep theirs.
