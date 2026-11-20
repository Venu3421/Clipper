"""Pytest configuration and shared fixtures for ClipStream AI tests."""
import os
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# A test token so the API-token middleware does not block the test client.
os.environ.setdefault("CLIPSTREAM_API_TOKEN", "test-token-123")

from fastapi.testclient import TestClient  # noqa: E402

from app import main as app_module  # noqa: E402
from app import config as cfg  # noqa: E402


@pytest.fixture(autouse=True)
def mock_api_keys(monkeypatch):
    """Provide deterministic, non-real API keys for every test."""
    keys = {"gemini_api_key": "mock-gemini-key-123", "groq_api_key": "mock-groq-key-456"}
    monkeypatch.setattr(cfg, "get_api_keys", lambda: keys)
    # routes.py imported get_api_keys at module load time, so patch it there too.
    monkeypatch.setattr("app.api.routes.get_api_keys", lambda: keys)
    monkeypatch.setattr("app.core.transcriber.get_api_keys", lambda: keys)
    monkeypatch.setattr("app.core.viral_scorer.get_api_keys", lambda: keys)


@pytest.fixture(scope="session")
def client():
    # raise_server_exceptions=False so HTTPExceptions are returned as responses
    # instead of being re-raised inside the test process.
    with TestClient(app_module.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def api_headers():
    return {"X-API-Key": "test-token-123"}


@pytest.fixture
def tmp_storage(tmp_path, monkeypatch):
    """Point the app's storage directories at a temp dir for isolated tests."""
    storage = tmp_path / "storage"
    for sub in ("downloads", "temp", "clips", "exports", "downloads/uploads"):
        (storage / sub).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(app_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(cfg, "STORAGE_DIR", storage)
    monkeypatch.setattr(cfg, "DOWNLOADS_DIR", storage / "downloads")
    monkeypatch.setattr(cfg, "TEMP_DIR", storage / "temp")
    monkeypatch.setattr(cfg, "CLIPS_DIR", storage / "clips")
    monkeypatch.setattr(cfg, "EXPORTS_DIR", storage / "exports")
    monkeypatch.setattr(cfg, "BIN_DIR", tmp_path / "bin")
    monkeypatch.setattr(cfg, "FONTS_DIR", tmp_path / "app" / "web" / "static" / "fonts")
    return storage