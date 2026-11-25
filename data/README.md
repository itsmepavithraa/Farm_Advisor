# Reference data (owner: Ananya, reviewer: Pavithra)

| File | Columns | Notes |
|---|---|---|
| crops.csv | crop_name_en, crop_name_kn, aliases (`;` separated), kc_initial, kc_mid, kc_end, season, root_depth_m, source | root_depth_m (lower end of FAO-56 Table 22 range) and depletion_fraction (FAO-56 Table 22 p, optional, default 0.5) added after Pavithra's review |
| crop_calendar.csv | crop, stage, start_day, end_day, kc | days after sowing, both ends inclusive. Development Kc = midpoint of initial and mid; late Kc = kc_end |
| soil_reference.csv | soil_type, field_capacity, wilting_point, source | volumetric fraction. Midpoints of FAO-56 Table 19 ranges |
| mandis.csv | mandi_name, district, rounded_latitude, rounded_longitude | Coordinates rounded to 2 dp. **mandi_name must match Agmarknet spelling exactly. Verify "Bangalore" etc. against a real response.** |

Review result and open points: see `notes/DATA_REVIEW.md`.

All values are APPROXIMATE (FAO-56 generic values, not Karnataka field measurements) until reviewed.
Every file passes through `advice.crop_rules.load_reference()` and `tests/test_reference_data.py`.
