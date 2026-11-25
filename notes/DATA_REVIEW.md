# Review of data/*.csv and mandi spellings (Pavithra)

Checked against the FAO Irrigation and Drainage Paper 56 pages on fao.org
(Table 11 stage lengths, Table 12 Kc, Table 19 soil water, Table 22 root depth and depletion fraction),
read on 2026-11-25. FAO says Table 11 values are "only a general guide". Everything is still a
generic value, not a Karnataka field measurement; ask a local agriculture officer / KVK to confirm before real use.

## Result
| Item | Ananya's value | Status |
|---|---|---|
| Kc mid / end (all 4 crops) | 1.00/0.30, 1.20/0.60, 1.15/0.80, 1.15/0.60 | OK. Matches Table 12 (tomato end is within 0.70-0.90; maize end 0.60 is for harvest at high grain moisture, 0.35 if left to dry) |
| Kc initial (all 4 crops) | 0.30, 0.30, 0.60, 0.40 | NOT CHECKED. The Kc ini column is an image on the FAO page and could not be read |
| Stage lengths: Tomato, Groundnut | 30/40/45/30, 25/35/45/25 | OK. Table 11 Mediterranean and West Africa rows |
| Stage lengths: Ragi | late stage 40 days (total 145) | CHANGED to 35 days (total 140). Table 11 millet row is 20/30/55/35 |
| Stage lengths: Maize | 30/40/50/50 = 170 days (Idaho, USA row) | CHANGED to 20/35/40/30 = 125 days (Table 11 "India" row). A 170-day crop is not typical for Karnataka. **Team decision:** if farmers grow longer-duration maize, the rule says INSUFFICIENT_DATA after day 124; extend the late stage if needed |
| Root depth | Ragi 0.5, Maize 0.8, Tomato 0.6, Groundnut 0.5 | CHANGED to 1.0, 1.0, 0.7, 0.5. The old values for ragi, maize and tomato were BELOW the Table 22 ranges (1.0-2.0, 1.0-1.7, 0.7-1.5). Lower end of the range is used, as FAO suggests for scheduling |
| Depletion fraction p | (not in file; rule used 0.5 for all) | ADDED column `depletion_fraction`: 0.55, 0.55, 0.40, 0.50 (Table 22). Tomato is more sensitive, so it now triggers earlier |
| sandy_loam, loam, black_clay | midpoints of Table 19 | OK. Midpoints computed correctly (clay row used for black_clay) |
| clay_loam | cited as "FC 0.30-0.37; WP 0.17-0.24" | Numbers right but the row is "Silt clay loam". Table 19 has NO clay loam row. Source note corrected to say it is a proxy |
| Coordinates in mandis.csv | 5 mandis | Plausible city-centre values, rounded to 2 dp. Not independently verified |

Effect of the root depth / p changes on the real run (maize, 65 days after sowing, Bengaluru,
2026-11-25): available water 120 mm (was 83 mm), trigger 66 mm. Decision WAIT, unchanged that day.

## Mandi spellings (NOT fully verified)
The live Agmarknet spelling could not be confirmed: the data.gov.in API needs a personal key and the
shared demo key is rate-limited. A secondary website that republishes Agmarknet data shows
"Bangalore", "Kolar", "Ramanagara" and "Tumkur"; "Mandya" did not appear in the results. So:
- "Bangalore" (not "Bengaluru") is probably right, **but confirm it**.
- Run the new check once you have a key:
  ```bash
  set DATA_GOV_API_KEY=your_key       # PowerShell: $env:DATA_GOV_API_KEY="your_key"
  python dev_checks/check_mandi_names.py
  ```
  It prints MATCH or the closest real names for every row of `data/mandis.csv`. Copy any corrected
  spelling into the CSV. A market with no record today for a crop shows as MISSING for that crop only, which is why
  four commodities are checked.
- A wrong spelling does not give wrong prices: the API returns no records and the app says no data.
