import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import store as auth_store
from app.main import app


def test_health_is_public_and_returns_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # main.py's lifespan hook toca auth_store.get_connection() (bootstrap admin) en cada
    # arranque -- sin esto, "with TestClient(app)" pega contra la Turso real.
    auth_db_path = tmp_path / "auth-lifespan.db"

    def _fake_auth_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(str(auth_db_path), check_same_thread=False)
        auth_store._init_schema(conn)
        return conn

    monkeypatch.setattr(auth_store, "get_connection", _fake_auth_connection)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
