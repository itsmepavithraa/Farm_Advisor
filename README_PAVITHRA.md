# Data and Decision Engine (Pavithra) – branch `feat/data-rules`

Files: `tools/weather.py`, `tools/mandi.py`, `tools/cache.py`, `advice/irrigation.py`,
`advice/prices.py`, `advice/crop_rules.py`, plus a temporary `backend/pipeline.py` stub.
Prakruthi: merge this into the main README.

## Run
```bash
pip install -r requirements.txt
python -m pytest -q                 # 89 tests, no network needed
python dev_checks/e2e_check.py      # real Open-Meteo weather -> irrigation decision
```
Env vars: `DATA_GOV_API_KEY` (free key from data.gov.in, for mandi prices), optional
`FARM_DB_PATH` (cache DB, default `farm_advisor.db`), `FARM_DATA_DIR` (reference CSVs, default `data/`).

## Function reference
| Function | Input | Output | Failure cases |
|---|---|---|---|
| `weather.get_weather(lat, lon, past_days=7, forecast_days=3)` | lat/lon (rounded to 2 dp) | `status ok` + `daily[{date, rain_mm, et0_mm, temp_max_c}]`, `source`, `location`, `retrieved_at`, `freshness` live/cached, `stale` | `status error` with `error` = timeout / network_error / bad_response / missing_fields. Never fake values. Falls back to older cache marked `stale: true` |
| `weather.local_today(weather, now)` | weather dict | local date | – |
| `mandi.get_prices(commodity, mandi, state)` | names as Agmarknet spells them | `observations[{commodity, mandi, variety, price_type, price, reported_date, source}]` (Rs/quintal), `freshness` live/cached/recorded_sample | `error` = no_api_key / timeout / network_error / bad_response / no_records; falls back to saved observations (`stale: true`) |
| `mandi.nearest_mandis(lat, lon, csv, n)` | coordinates, `mandis.csv` | mandis sorted by distance | skips rows with bad coordinates |
| `cache.save / load / is_fresh / record_observations / get_history` | see docstring | – | bad timestamp = not fresh; corrupt payload = None |
| `crop_rules.get_stage(crop, sowing_date, today, calendar)` | crop, sowing date | `stage`, `kc`, `days_after_sowing` | `unknown_crop`, `not_sown_yet`, `past_season`, `no_stage`, `bad_date` |
| `irrigation.decide_irrigation(profile, weather, reference, now)` | profile `{crop, sowing_date, soil_type, water_source?, last_irrigation_date?}` | shared response fields + `values` | any missing/unknown/stale input -> `INSUFFICIENT_DATA` with the reason |
| `prices.compare_price(observations, mandi, freshness=...)` | `mandi.get_prices()["observations"]` | `ABOVE_RECENT / NEAR_RECENT / BELOW_RECENT` + dated observations | older than 3 days -> `STALE_DATA` (no advice); < 3 earlier prices or no modal price -> `INSUFFICIENT_DATA` |

Both rules return the 12 shared fields (`status, intent, decision, message_en, message_local,
reasons, source, data_timestamp, freshness, confidence, assumptions, audio_url`) plus `values`
(every number used). `message_en`, `message_local` and `audio_url` are `null` – the language
and voice layers fill them.

## Thresholds (all constants at the top of each file)
Weather fresh 6 h · mandi price fresh 3 days · NEAR = within 5 % (boundary counts as NEAR) ·
irrigation trigger = 50 % of available soil water used (exactly at trigger = trigger reached) ·
80 % of rain counted as effective · "soon" = today or tomorrow · rain forecast must give ≥ 5 mm
effective to justify waiting.

## Honest limitations
* Soil moisture is **modelled, not measured**. Without a last-irrigation date the soil is assumed full at the
  start of a 7-day window unless rain refilled it; confidence is then `low`.
* The Agmarknet open API shows only the latest day. Price history is built from each fetch (`price_history` table),
  so run `scripts/warm_cache.py` daily (Leeshal) or the price rule says `INSUFFICIENT_DATA`.
* No forecasting of prices, no pesticide/fertiliser/disease advice.
