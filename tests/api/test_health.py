"""Tests for the API scaffold (SCRUM-152): health check, docs, settings."""

from fastapi.testclient import TestClient

from brandlens.api.app import create_app
from brandlens.api.config import Settings


def make_client(settings: Settings | None = None) -> TestClient:
    return TestClient(create_app(settings or Settings()))


def test_health_returns_ok_and_version():
    response = make_client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


def test_api_docs_load():
    client = make_client()
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/health" in schema.json()["paths"]


def test_unknown_route_returns_404():
    assert make_client().get("/does-not-exist").status_code == 404


def test_cors_allows_configured_origin_only():
    client = make_client(Settings(cors_origins=("http://localhost:5173",)))
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/health", headers={"Origin": "http://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_settings_defaults_and_env_overrides(monkeypatch):
    for name in ("HOST", "PORT", "LOG_LEVEL", "RELOAD", "CORS_ORIGINS"):
        monkeypatch.delenv(f"BRANDLENS_{name}", raising=False)
    defaults = Settings.from_env()
    assert (defaults.host, defaults.port, defaults.reload) == ("127.0.0.1", 8000, False)

    monkeypatch.setenv("BRANDLENS_PORT", "9000")
    monkeypatch.setenv("BRANDLENS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("BRANDLENS_RELOAD", "true")
    monkeypatch.setenv("BRANDLENS_CORS_ORIGINS", "http://a.test, http://b.test")
    overridden = Settings.from_env()
    assert overridden.port == 9000
    assert overridden.log_level == "debug"
    assert overridden.reload is True
    assert overridden.cors_origins == ("http://a.test", "http://b.test")
