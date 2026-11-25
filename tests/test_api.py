"""API smoke tests (Ananya). Uses the temporary pipeline stub."""
from fastapi.testclient import TestClient

import api

client = TestClient(api.app)
FIELDS = {"status", "intent", "decision", "message_en", "message_local", "reasons", "source",
          "data_timestamp", "freshness", "confidence", "assumptions", "audio_url"}


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_returns_shared_fields():
    r = client.post("/ask", json={"question": "Should I water my maize?", "profile": {}})
    assert r.status_code == 200 and FIELDS <= set(r.json())


def test_ask_error_is_handled(monkeypatch):
    monkeypatch.setattr(api.pipeline, "ask", lambda req: 1 / 0)
    r = client.post("/ask", json={})
    assert r.status_code == 500 and r.json()["status"] == "error"


def test_reference_lists_dropdown_data():
    d = client.get("/reference").json()
    assert d["crops"] and d["soils"] and d["mandis"]


def test_frontend_and_samples_served():
    assert client.get("/").status_code == 200
    assert client.get("/eval/sample_price.json").status_code == 200
