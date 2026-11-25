# Frontend, reference data and API (Ananya) – branch `feat/frontend`

Files: `frontend/index.html`, `frontend/style.css`, `frontend/app.js`, `api.py`, `data/*.csv`,
`tests/test_reference_data.py`, `tests/test_api.py`

## Run
```bash
pip install -r requirements.txt
python -m pytest -q                 # 100 tests
uvicorn api:app --reload            # open http://localhost:8000
# http://localhost:8000/?mock=1     shows buttons that load eval/sample_*.json into the result card
```

## What the page does
Profile (picture crop buttons, nearest town, sowing date, soil, water source, area, language) -> question box
+ mic (record and play back only) -> result card: coloured decision badge, Kannada + English message, reasons,
source, data time, confidence, freshness chip (live / cached / reference / recorded sample), yellow stale warning
with the date, expert-help line for UNSUPPORTED, and a Why? expander. States: loading, network error, server
error, blocked mic. No decision logic in JavaScript; the only backend call is `askBackend()` and the URLs are
constants at the top of `app.js`.

## Request sent to `POST /ask` (Leeshal: confirm or change)
```json
{"question": "...", "language": "kn",
 "profile": {"crop": "Maize", "soil_type": "sandy_loam", "sowing_date": "2026-09-20",
             "area_acres": 2, "water_source": "borewell", "mandi": "Kolar",
             "latitude": 13.14, "longitude": 78.13}}
```
Location is always a rounded mandi/town from `data/mandis.csv`; no GPS is used.

## Proposed additions to the contract (not yet agreed – tell the team)
* `status: "needs_confirmation"` from the backend makes the page show the crop picture buttons, then re-send the question.
* `intent: "UNSUPPORTED"` shows the expert-help line. The Kisan Call Centre number is a constant in `app.js` marked TODO verify.
* Prakruthi's Why? / escalation wording can replace the texts in `app.js` once confirmed.

## Not done yet
Voice upload to the backend (needs Leeshal's STT), helper mode, slides/video, consent checkbox (Leeshal/Prakruthi).
All `data/*.csv` values are APPROXIMATE FAO-56 generic values and need Pavithra's review. Mandi names need checking against Agmarknet spelling.
