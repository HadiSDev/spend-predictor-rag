"""CORS middleware is driven by WEB_API_CORS_ORIGINS and defaults closed."""
from __future__ import annotations

from fastapi.testclient import TestClient

from web_api import app as app_module
from web_api import config

_ALLOWED = "http://localhost:5173"


def _client(monkeypatch, origins):
    monkeypatch.setattr(config, "WEB_API_CORS_ORIGINS", origins)
    return TestClient(app_module.create_app())


def test_configured_origin_gets_cors_headers(monkeypatch):
    client = _client(monkeypatch, [_ALLOWED])
    r = client.get("/api/v1/health", headers={"Origin": _ALLOWED})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == _ALLOWED


def test_unconfigured_origin_gets_no_cors(monkeypatch):
    client = _client(monkeypatch, [_ALLOWED])
    r = client.get("/api/v1/health", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_default_is_closed(monkeypatch):
    client = _client(monkeypatch, [])
    r = client.get("/api/v1/health", headers={"Origin": _ALLOWED})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
