"""Minimal web API (Ananya).  Leeshal extends this later (backend/api.py).

Run from the repo root:   uvicorn api:app --reload      then open http://localhost:8000
Routes
  GET  /health     -> {"status": "ok"}
  GET  /reference  -> crops, soils and mandis for the profile dropdowns (read from data/*.csv)
  POST /ask        -> passes the JSON request to backend.pipeline.ask() and returns its result
The page in frontend/ is served at "/" and the sample responses at /eval/ (used by ?mock=1).

/ask request shape (proposed, Leeshal to confirm):
  {"question": str, "language": "kn"|"en",
   "profile": {"crop", "soil_type", "sowing_date" (YYYY-MM-DD), "area_acres",
               "water_source", "mandi", "latitude", "longitude"}}
No business logic here: the response is returned exactly as pipeline.ask() produced it.
"""
import csv
import os
from pathlib import Path

from fastapi import Body, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend import pipeline

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("FARM_DATA_DIR") or ROOT / "data")

app = FastAPI(title="Farm Advisor API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _read_csv(name: str) -> list[dict]:
    try:
        with open(DATA_DIR / name, newline="", encoding="utf-8-sig") as fh:
            return [{k.strip(): (v or "").strip() for k, v in row.items() if k}
                    for row in csv.DictReader(fh)]
    except FileNotFoundError:
        return []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/reference")
def reference():
    crops = [{"name_en": c.get("crop_name_en"), "name_kn": c.get("crop_name_kn")}
             for c in _read_csv("crops.csv")]
    soils = [{"soil_type": s.get("soil_type")} for s in _read_csv("soil_reference.csv")]
    mandis = [{"mandi_name": m.get("mandi_name"), "district": m.get("district"),
               "latitude": m.get("rounded_latitude"), "longitude": m.get("rounded_longitude")}
              for m in _read_csv("mandis.csv")]
    return {"crops": crops, "soils": soils, "mandis": mandis}


@app.post("/ask")
def ask(request: dict = Body(...)):
    try:
        return pipeline.ask(request)
    except Exception as exc:  # never crash the page; show a clear error state instead
        return JSONResponse(status_code=500, content={"status": "error", "decision": None,
                            "reasons": [f"Server error: {type(exc).__name__}"]})


if (ROOT / "eval").is_dir():
    app.mount("/eval", StaticFiles(directory=ROOT / "eval"), name="eval")
if (ROOT / "frontend").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
