"""Tests for the liveness endpoint and application factory."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_health_reports_ok_and_version() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["environment"] in {"development", "test", "production"}


def test_health_reports_the_knowledge_base_version() -> None:
    """Conflict verdicts depend on the knowledge base, so its version is part
    of identifying what a running service will do."""
    from app.kb.loader import load_knowledge_base

    response = TestClient(create_app()).get("/health")

    assert response.json()["kb_version"] == load_knowledge_base().version


def test_docs_are_exposed_outside_production(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setenv("APP_ENV", "development")
    config.get_settings.cache_clear()

    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200

    config.get_settings.cache_clear()


def test_docs_are_disabled_in_production(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setenv("APP_ENV", "production")
    config.get_settings.cache_clear()

    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404

    config.get_settings.cache_clear()
