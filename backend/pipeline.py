# TEMPORARY STUB - Leeshal replaces this with the real pipeline.ask().
# It only loads and returns eval/sample_irrigation.json so that the web API
# (Ananya) and the Telegram bot (Prakruthi) can import the same entry point.
import json
from pathlib import Path

_SAMPLE = Path(__file__).resolve().parent.parent / "eval" / "sample_irrigation.json"


def ask(request: dict | None = None) -> dict:
    """Return the sample irrigation response, whatever the request is."""
    return json.loads(_SAMPLE.read_text(encoding="utf-8"))
