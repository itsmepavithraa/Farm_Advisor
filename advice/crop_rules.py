"""Crop stage and Kc lookup from the reference CSVs.   Owner: Pavithra

CSV columns (agreed with Ananya)
  crops.csv          crop_name_en, crop_name_kn, aliases (separated by ; or |),
                     kc_initial, kc_mid, kc_end, season
                     + OPTIONAL root_depth_m (requested from Ananya; default 0.5 m)
  crop_calendar.csv  crop, stage, start_day, end_day, kc
                     (days after sowing, both ends inclusive; sowing day = day 0)
  soil_reference.csv soil_type, field_capacity, wilting_point, source
                     (volumetric fraction 0-1; values above 1 are read as percent)

Functions
---------
load_reference(data_dir=None) -> {"crops": [...], "calendar": [...], "soils": [...]}
    data_dir: env FARM_DATA_DIR, else <repo>/data. Raises FileNotFoundError if absent.
resolve_crop(name, crops)  -> canonical English crop name or None
get_stage(crop, sowing_date, today, calendar)
    -> {"status": "ok", "crop", "stage", "kc", "days_after_sowing"}
    or {"status": "not_sown_yet" | "past_season" | "no_stage" | "unknown_crop"
        | "bad_date", "message": ...}
get_soil(soil_type, soils)  -> {"soil_type","field_capacity","wilting_point","source"} or None
get_root_depth(crop, crops) -> (metres, is_default)
"""
from __future__ import annotations

import csv
import os
import re
from datetime import date
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_ROOT_DEPTH_M = 0.5


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return [{k.strip(): (v or "").strip() for k, v in row.items() if k}
                for row in csv.DictReader(fh)]


def load_reference(data_dir=None) -> dict:
    base = Path(data_dir or os.environ.get("FARM_DATA_DIR") or DEFAULT_DATA_DIR)
    return {"crops": _read(base / "crops.csv"),
            "calendar": _read(base / "crop_calendar.csv"),
            "soils": _read(base / "soil_reference.csv")}


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-]+", " ", str(text).strip().lower())


def resolve_crop(name, crops: list[dict]) -> str | None:
    wanted = _norm(name or "")
    if not wanted:
        return None
    for row in crops:
        names = [row.get("crop_name_en", ""), row.get("crop_name_kn", "")]
        names += re.split(r"[;|]", row.get("aliases", ""))
        if wanted in {_norm(n) for n in names if n.strip()}:
            return row["crop_name_en"]
    return None


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def get_stage(crop, sowing_date, today, calendar: list[dict]) -> dict:
    sown, now = _as_date(sowing_date), _as_date(today)
    if sown is None or now is None:
        return {"status": "bad_date", "message": "Sowing date missing or not YYYY-MM-DD"}
    rows = [r for r in calendar if _norm(r.get("crop", "")) == _norm(crop or "")]
    if not rows:
        return {"status": "unknown_crop", "message": f"No crop calendar for '{crop}'"}
    das = (now - sown).days
    if das < 0:
        return {"status": "not_sown_yet", "days_after_sowing": das,
                "message": "Sowing date is in the future"}
    try:
        spans = [(int(r["start_day"]), int(r["end_day"]), r["stage"], float(r["kc"])) for r in rows]
    except (KeyError, ValueError):
        return {"status": "no_stage", "message": "crop_calendar.csv has an unreadable row"}
    if das > max(s[1] for s in spans):
        return {"status": "past_season", "days_after_sowing": das,
                "message": f"{das} days after sowing is beyond the crop calendar"}
    for start, end, stage, kc in spans:
        if start <= das <= end:
            return {"status": "ok", "crop": rows[0]["crop"], "stage": stage, "kc": kc,
                    "days_after_sowing": das}
    return {"status": "no_stage", "days_after_sowing": das,
            "message": f"Calendar has a gap at day {das}"}


def get_soil(soil_type, soils: list[dict]) -> dict | None:
    for row in soils:
        if _norm(row.get("soil_type", "")) == _norm(soil_type or ""):
            try:
                fc, wp = float(row["field_capacity"]), float(row["wilting_point"])
            except (KeyError, ValueError):
                return None
            if fc > 1 or wp > 1:
                fc, wp = fc / 100, wp / 100
            if not 0 <= wp < fc <= 1:
                return None
            return {"soil_type": row["soil_type"], "field_capacity": fc,
                    "wilting_point": wp, "source": row.get("source", "")}
    return None


def get_root_depth(crop, crops: list[dict]) -> tuple[float, bool]:
    for row in crops:
        if _norm(row.get("crop_name_en", "")) == _norm(crop or ""):
            try:
                depth = float(row.get("root_depth_m", ""))
                if depth > 0:
                    return depth, False
            except ValueError:
                pass
    return DEFAULT_ROOT_DEPTH_M, True
